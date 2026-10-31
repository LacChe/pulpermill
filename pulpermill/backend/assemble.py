"""From a flow's draft reply to the contract's reply. A draft is in the model's own references: wherever the contract carries an id, the
draft carries a handle (or, for the character a patch is about, its label). This turns them into the ids the page sent, and refuses
anything the request did not send. Shapes are in pulpermill/prompter/README.md."""
from typing import Any

from pulpermill.schema.shifts import MAX_SHIFTS_PER_CHAPTER, validate_patch

from .handles import Handles, Scope, Unresolved


def _s(value: Any) -> str:
    return str(value or "").strip()


def _object(value: Any, what: str) -> dict:
    if not isinstance(value, dict):
        raise Unresolved(f"{what} must be an object")
    return value


def patch_with_ids(scope: Scope, patch: Any) -> dict:
    """The patch with each `replace` and `remove` pointing at the id its handle stands for. A list operation is checked here only as far
    as handles go; validate_patch checks the rest."""
    out: dict[str, Any] = {}
    for key, value in _object(patch, "a patch").items():
        if not isinstance(value, list):
            out[key] = value
            continue
        ops = []
        for op in value:
            op = dict(_object(op, f"an operation on {key}"))
            if op.get("op") in ("replace", "remove"):
                op["id"] = scope.item(op.get("id"), key)
            elif "id" in op:
                raise Unresolved(f"an add on {key} names no id")
            ops.append(op)
        out[key] = ops
    return out


def _stored_form(patch: dict) -> dict:
    """The patch as validate_patch reads it: an `add` there carries the id of the new item, which in the contract the page gives it."""
    return {k: [{**op, "id": "new-item"} if op.get("op") == "add" else op for op in v] if isinstance(v, list) else v for k, v in patch.items()}


def shifts(entries: Any, handles: Handles) -> list[dict]:
    """The contract's shift entries. An entry whose patch holds nothing is a card that did not change and is left out. Anything that is
    not a valid patch for its card, or that points at something not sent, raises Unresolved with a line saying what."""
    if not isinstance(entries, list):
        raise Unresolved("shifts must be a list")
    out, seen = [], set()
    for entry in entries:
        entry = _object(entry, "a shift")
        card, label = entry.get("card"), entry.get("target")
        scope = handles.scope(card, label)
        if (card, scope.target) in seen:
            raise Unresolved(f"the {card} card has two entries; give each card one entry with all its changes")
        seen.add((card, scope.target))
        patch = patch_with_ids(scope, entry.get("patch") or {})
        if not patch:
            continue
        problems = validate_patch(card, _stored_form(patch))
        if problems:
            raise Unresolved(problems[0].message)
        out.append({"card": card, "target": scope.target, "patch": patch})
    if len(out) > MAX_SHIFTS_PER_CHAPTER:
        raise Unresolved(f"at most {MAX_SHIFTS_PER_CHAPTER} entries are allowed")
    return out


def _fill(draft: dict, handles: Handles) -> dict:
    return {"values": _object(draft.get("values"), "the values")}


def _judge(draft: dict, handles: Handles) -> dict:
    scope = handles.only()
    results = []
    for result in draft.get("results") or []:
        hits = []
        for hit in result.get("hits") or []:
            key = hit.get("field")
            item = scope.item(hit["item"], key) if hit.get("item") else None
            hits.append({"field": key, "item": item, "key": hit.get("key")})
        results.append({"rule": result["rule"], "hits": hits})
    return {"results": results}


def _style_fit(draft: dict, handles: Handles) -> dict:
    fits = bool(draft.get("fits"))
    return {"fits": fits, "message": "" if fits else _s(draft.get("message"))}


def _plan(draft: dict, handles: Handles) -> dict:
    return {"beat": _object(draft.get("beat"), "the beat")}


def _generate(draft: dict, handles: Handles) -> dict:
    events = _object(draft.get("events"), "the events")
    return {"chapter_text": draft.get("chapter_text") or "",
            "events": {"happened": _s(events.get("happened")), "changed": _s(events.get("changed")) or None},
            "shifts": shifts(draft.get("shifts") or [], handles)}


_CALLS = {"fill": _fill, "judge": _judge, "style_fit": _style_fit, "plan": _plan, "generate": _generate}


def reply(call: str, draft: dict, handles: Handles) -> dict:
    """The contract's reply for `call`. Raises Unresolved when the draft points at something the request did not send."""
    return {"ok": True, **_CALLS[call](draft, handles)}
