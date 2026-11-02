"""The `judge` call: one JSON step for each model-judged rule that has something to look at. Each rule's own question (the schema's
`judge_prompt`) is wrapped with the card's relevant items, shown as prose with their handles, and a short instruction to answer for each
item exactly once. Rule polarity (whether "yes" is the good answer) and whole-list rules are data in text/en/judge.yaml."""
import json
import re
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step

from . import common

VERSION = "judge-1"


def _question(text: str) -> str:
    """The schema's judge_prompt without its rewrite instructions (this call only answers)."""
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return " ".join(p for p in parts if not re.search(r"\b(rewrite|suggest|propose)\b", p, re.I))


def _ties_words(request: dict) -> dict[str, list[dict]]:
    names = r.names_by_id(request.get("related") or {})
    values = request.get("values") or {}
    return {"ties": r.in_words(values.get("ties") or [], {"tie_from": {"ref": True}, "tie_to": {"ref": True}}, names),
            "holdings": r.in_words(values.get("holdings") or [], {"holdee": {"ref": True}, "held_by": {"ref": True}}, names)}


def _item_text(template: str, item: dict, factor: float) -> str:
    tokens = {k: common.clip(r.s(v), factor) for k, v in item.items() if k != "id"}
    return r.fill(template, {m: tokens.get(m, "") for m in re.findall(r"\{(\w+)\}", template)})


def item_lines(request: dict, scope: Any, handles: list[str], factor: float) -> list[str]:
    """Each handle with its item in words, in the order of `handles`."""
    w = common.load_text("judge")["items"]
    card, values = request["card"], request.get("values") or {}
    words = _ties_words(request) if card == "entanglements" else {}
    lines = []
    for handle in handles:
        key, _, number = handle.partition(".")
        if number:
            source = words.get(key) or values.get(key) or []
            wanted = scope.item(handle, key)
            item = next((i for i in source if isinstance(i, dict) and i.get("id") == wanted), None) or {}
            text = _item_text(w.get(f"{card}.{key}", "{text}"), item, factor)
        else:
            text = common.clip(r.s(values.get(key)), factor)
        lines.append(f"{handle}: {text}")
    return lines


class JudgeFlow(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit
        self.scope = kit.handles.only()
        self.asked: list[tuple[dict, list[str]]] = []
        for rule in request["rules"]:
            handles: list[str] = []
            for key in rule["fields"]:
                handles += self.scope.handles(key) if key in self.scope.lists else ([key] if key in self.scope.scalars else [])
            self.asked.append((rule, handles))
        self.steps = [(rule, handles) for rule, handles in self.asked if handles]

    def prompt(self, rule: dict, handles: list[str], factor: float = 1.0) -> str:
        w = common.load_text("judge")
        card = self.request["card"]
        label = tx.schema_text(card)["card"]["label"]
        values = self.request.get("values") or {}
        name = r.s(values.get("name")) if card == "characters" else ""
        question = _question(tx.schema_text(card)["rules"][rule["id"]]["judge_prompt"])
        ok = w["ok_no"] if rule["id"] in w["ok_when_no"] else w["ok_yes"]
        return "\n\n".join([
            w["role"],
            w["card_line_for"].format(label=label, name=name) if name else w["card_line"].format(label=label),
            w["question_lead"] + " " + question,
            w["items_lead"] + "\n" + "\n".join(item_lines(self.request, self.scope, handles, factor)),
            w["answer"] + " " + ok + " " + w["language_note"],
        ])

    def _step(self, n: int) -> Step:
        rule, handles = self.steps[n]
        g = self.kit.grammar
        check = {"type": "array", "items": g.obj({"item": g.one_of(handles), "ok": {"type": "boolean"}}), "minItems": len(handles), "maxItems": len(handles)}
        pr = common.load_text("judge")["problems"]

        def once(value):
            seen = [c["item"] for c in value["checks"]]
            missing = [h for h in handles if h not in seen]
            repeated = sorted({h for h in seen if seen.count(h) > 1})
            if missing:
                return pr["missing"].format(items=", ".join(missing))
            return pr["repeated"].format(items=", ".join(repeated)) if repeated else None
        return Step("judge", lambda f: self.prompt(rule, handles, f), "json", min(900, 120 + 40 * len(handles)), g.obj({"checks": check}), once, "structured", False)

    def next(self, results):
        return self._step(len(results)) if len(results) < len(self.steps) else None

    def worst_case(self):
        return [self._step(n) for n in range(len(self.steps))]

    def reply(self, results):
        w = common.load_text("judge")
        answers = iter(results)
        out = []
        for rule, handles in self.asked:
            hits = []
            if handles:
                failed = [c["item"] for c in next(answers)["checks"] if c["ok"] is False]
                if rule["id"] in w["fires_when_none_ok"]:
                    if len(failed) == len(handles):
                        hits.append({"field": handles[0].split(".")[0], "item": None, "key": None})
                else:
                    hits += [{"field": h.split(".")[0], "item": h if "." in h else None, "key": None} for h in failed]
            out.append({"rule": rule["id"], "hits": hits})
        return {"results": out}


def build_flow(request, kit) -> Flow:
    return JudgeFlow(request, kit)


def script(request: dict, kit: Any) -> list[str]:
    """One reply per step: every item passes except the first, so a valid reply exercises a hit."""
    flow = JudgeFlow(request, kit)
    return [json.dumps({"checks": [{"item": h, "ok": i != 0} for i, h in enumerate(handles)]}) for _, handles in flow.steps]
