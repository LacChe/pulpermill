"""The `finish` call, one step: after the last chapter, the most notable change the whole story made to each person. It reads only what the chapters'
Events records say (never a chapter's text) and the Characters cards as they were before the story began, so it knows the field names and the
current values. The reply is the contract's FinishReply: at most one patch per character, none for a character the story did not move. Wording lives in
text/en/finish.yaml.

The step has two attempts and then a last resort of no shifts: the story is never blocked by this call. Nothing is judged afterwards. Names, never ids,
reach the prompt: a person is named by label and a list item by its handle."""
import json
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step
from pulpermill.schema.shifts import shiftable_fields

from . import common

VERSION = "finish-1"
MAX_OUTPUT = 3000        # one patch of a few fields per person, for a cast of a dozen, with room to spare
ATTEMPTS = 2             # then no shifts


def _lang(request: dict) -> str:
    names = common.load_text("finish")["languages"]
    code = str(request.get("language") or "en")
    return names.get(code) or names.get(code.split("-")[0]) or code


def _item_text(item: dict, factor: float) -> str:
    parts = [r.s(v) for k, v in item.items() if k != "id" and isinstance(v, (str, int, float)) and r.s(v)]
    return common.clip(" — ".join(parts), factor)


def _people(request: dict, kit: Any, factor: float) -> str:
    """Each person: the name and sketch, then every shiftable field that holds something, a list item with its handle."""
    w = common.load_text("finish")
    people = {p.get("id"): p for p in request.get("characters") or []}
    blocks = []
    for scope in kit.handles.of_card("characters"):
        person = people.get(scope.target) or {}
        sketch = common.clip(r.s(person.get("sketch")), factor)
        lines = [w["person_head"].format(name=scope.label, sketch=sketch) if sketch else scope.label]
        for f in shiftable_fields("characters"):
            key = f["key"]
            if key == "sketch":
                continue
            if f["type"] == "scalar":
                if r.s(person.get(key)):
                    lines.append(w["field_line"].format(key=key, value=common.clip(r.s(person[key]), factor)))
            else:
                lines += [w["item_line"].format(handle=scope.of(key, i["id"]), text=_item_text(i, factor))
                          for i in person.get(key) or [] if isinstance(i, dict) and i.get("id")]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _chapters(request: dict, factor: float) -> str:
    """Every chapter's events in order, as the writer's history frames tell them. A squeeze shortens each; none is dropped."""
    c = tx.limits()["events"]
    fr = tx.prompt_text("frames")
    out = []
    for e in sorted((e for e in request.get("events") or [] if isinstance(e, dict)), key=lambda e: int(e.get("chapter") or 0)):
        happened = common.clip(r.clip(e.get("happened"), c["happened"]), factor)
        para = fr["story_chapter"].format(chapter=e.get("chapter"), happened=r.sentence(happened))
        if r.s(e.get("changed")):
            para += " " + fr["story_changed"].format(changed=r.sentence(common.clip(r.clip(e["changed"], c["changed"]), factor)))
        out.append(para)
    return "\n".join(out)


def build_prompt(request: dict, kit: Any, factor: float = 1.0) -> str:
    w = common.load_text("finish")
    setup = request.get("setup") or {}
    names = r.names_by_id({"characters": request.get("characters") or []})
    opening = [w["protagonist"].format(name=names.get(request.get("protagonist") or "", ""))]
    for key, line in (("normal", "opening_normal"), ("disruption", "opening_break")):
        if r.s(setup.get(key)):
            opening.append(r.sentence(w[line].format(value=common.clip(r.s(setup[key]), factor))))
    fields = ", ".join(f["key"] for f in shiftable_fields("characters"))
    return "\n\n".join([
        w["role"],
        "\n".join(opening),
        w["chapters_lead"] + "\n" + _chapters(request, factor),
        w["people_lead"] + "\n\n" + _people(request, kit, factor),
        w["task"],
        w["rules"].format(fields=fields),
        w["finish_example"],
        w["format"].format(language=_lang(request)),
    ])


def finish_problem(kit: Any, value: Any) -> str | None:
    """The kit's own check of the entries: only known people, one entry each, a patch that fits the card."""
    return kit.finish_problem((value or {}).get("shifts") if isinstance(value, dict) else None)


class FinishFlow(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit
        self.notes = {"finish_fallback": False}

    def _step(self) -> Step:
        g = self.kit.grammar

        def nobody():
            self.notes["finish_fallback"] = True
            return {"shifts": []}
        return Step("finish", lambda f: build_prompt(self.request, self.kit, f), "json", MAX_OUTPUT, g.obj({"shifts": g.finish()}),
                    lambda v: finish_problem(self.kit, v), "structured", True, ATTEMPTS, nobody)

    def next(self, results):
        return None if results else self._step()

    def reply(self, results):
        return {"shifts": results[0]["shifts"]}


def build_flow(request, kit) -> Flow:
    return FinishFlow(request, kit)


def script(request: dict, kit: Any) -> list[str]:
    """What a fake engine must return for a valid reply: one entry, for the first person, changing their fear."""
    entries = [{"card": "characters", "target": scope.label, "patch": {"fear": "Now afraid of being the one who stays behind."}}
               for scope in kit.handles.of_card("characters")[:1]]
    return [json.dumps({"shifts": entries})]
