"""From a flow's draft reply to the contract's reply. A draft is in the model's own references: wherever the contract carries an id, the
draft carries a handle (or, for the character a patch is about, its label). This turns them into the ids the page sent, and refuses
anything the request did not send. Shapes are in pulpermill/prompter/README.md."""
from typing import Any

from pulpermill.schema.shifts import CHAPTER_SHIFT_CARDS, MAX_SHIFTS_PER_CHAPTER, validate_patch

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


def _edges_only(patch: dict) -> None:
    """A chapter's patch holds `ties` replace operations that carry an `edge`, and a `bond` too when the chapter changed it, and nothing else; anything more raises Unresolved."""
    for key, ops in patch.items():
        if key != "ties":
            raise Unresolved(f"a chapter changes only the edge and the bond of ties, not {key}")
        for op in ops if isinstance(ops, list) else []:
            if op.get("op") != "replace" or set(op.get("values") or {}) - {"edge", "bond"}:
                raise Unresolved("a chapter changes only the edge and the bond of ties: replace those and nothing else")


def shifts(entries: Any, handles: Handles) -> list[dict]:
    """The contract's shift entries of a chapter: only the Entanglements, replacing the edge of ties. An entry whose patch holds nothing is a
    card that did not change and is left out. Anything else, or anything that points at something not sent, raises Unresolved with a line
    saying what."""
    if not isinstance(entries, list):
        raise Unresolved("shifts must be a list")
    out, seen = [], set()
    for entry in entries:
        entry = _object(entry, "a shift")
        card, label = entry.get("card"), entry.get("target")
        if card not in CHAPTER_SHIFT_CARDS:
            raise Unresolved(f"a chapter changes only the edge and the bond of ties (the entanglements card), not {card}")
        scope = handles.scope(card, label)
        if (card, scope.target) in seen:
            raise Unresolved(f"the {card} card has two entries; give each card one entry with all its changes")
        seen.add((card, scope.target))
        patch = patch_with_ids(scope, entry.get("patch") or {})
        if not patch:
            continue
        _edges_only(patch)
        problems = validate_patch(card, _stored_form(patch))
        if problems:
            raise Unresolved(problems[0].message)
        out.append({"card": card, "target": scope.target, "patch": patch})
    if len(out) > MAX_SHIFTS_PER_CHAPTER:
        raise Unresolved(f"at most {MAX_SHIFTS_PER_CHAPTER} entries are allowed")
    return out


def finish_shifts(entries: Any, handles: Handles) -> list[dict]:
    """The contract's shift entries at the end of the story: Characters only, at most one per character, each a patch of that person's own
    fields. An entry whose patch holds nothing is a person who did not change and is left out. Anything else, or anything that points at
    something not sent, raises Unresolved with a line saying what. The cap on a beat and the cast rule do not apply to these entries (they
    are the last beat's, see the rules in pulpermill/schema/shifts.py), so the one limit here is one entry per person."""
    if not isinstance(entries, list):
        raise Unresolved("shifts must be a list")
    out, seen = [], set()
    for entry in entries:
        entry = _object(entry, "a shift")
        if entry.get("card") != "characters":
            raise Unresolved(f"the end of the story changes only the characters, not {entry.get('card')}")
        scope = handles.scope("characters", entry.get("target"))
        if scope.target in seen:
            raise Unresolved(f"{scope.label} has two entries; give each person one entry with the most notable change")
        seen.add(scope.target)
        patch = patch_with_ids(scope, entry.get("patch") or {})
        if not patch:
            continue
        problems = validate_patch("characters", _stored_form(patch))
        if problems:
            raise Unresolved(problems[0].message)
        out.append({"card": "characters", "target": scope.target, "patch": patch})
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
    out = {"beat": _object(draft.get("beat"), "the beat")}
    if draft.get("picked"):        # only a flow that was asked to choose leaves one (the mill's plan flow, when the select step ran and its idea held)
        out["picked"] = draft["picked"]
    return out


def _generate(draft: dict, handles: Handles) -> dict:
    events = _object(draft.get("events"), "the events")
    return {"chapter_text": draft.get("chapter_text") or "",
            "events": {"happened": _s(events.get("happened")), "changed": _s(events.get("changed")) or None},
            "shifts": shifts(draft.get("shifts") or [], handles)}


def _finish(draft: dict, handles: Handles) -> dict:
    return {"shifts": finish_shifts(draft.get("shifts") or [], handles)}


_CALLS = {"fill": _fill, "judge": _judge, "style_fit": _style_fit, "plan": _plan, "generate": _generate, "finish": _finish}


def reply(call: str, draft: dict, handles: Handles) -> dict:
    """The contract's reply for `call`. Raises Unresolved when the draft points at something the request did not send."""
    return {"ok": True, **_CALLS[call](draft, handles)}
