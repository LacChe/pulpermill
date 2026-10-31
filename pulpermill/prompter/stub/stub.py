"""The stub prompter: trivial prompts and the correct grammar for every step of every call, so the backend can be run end to end with no
model. `script(call, request, kit)` gives the texts a fake engine must return, one per step, for a valid reply to that request."""
import json
from typing import Any

from ..base import CALLS, Flow, Prompter, Step

VERSION = "stub-0.1"
CHAPTER_WORDS = 3200          # the writer step's output limit, in tokens; the stub's worst-case chapter is this many words


def _clip(text: str, factor: float) -> str:
    return text if factor >= 1.0 else text[: max(int(len(text) * factor), 40)]


def _prompt(label: str, request: dict, factor: float, extra: str = "") -> str:
    """A prompt that is the request itself, clipped to the squeeze: it grows and shrinks with the request, which is all a stub must do."""
    body = _clip(json.dumps(request, ensure_ascii=False, separators=(",", ":")), factor)
    return f"Stub prompt for {label}.\n{body}" + (f"\n\n{extra}" if extra else "")


def _is_object(value: Any) -> str | None:
    return None if isinstance(value, dict) else "the reply must be an object"


class StubPrompter(Prompter):
    name = "stub"
    version = VERSION

    def flow(self, call: str, request: dict, kit: Any) -> Flow:
        if call not in CALLS:
            raise ValueError(f"the stub prompter has no flow for {call!r}")
        return {"fill": _Fill, "judge": _Judge, "style_fit": _StyleFit, "plan": _Plan, "generate": _Generate}[call](request, kit)


class _Base(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit

    def script(self) -> list[str]:
        raise NotImplementedError


class _Fill(_Base):
    def _step(self) -> Step:
        return Step("fill", lambda f: _prompt("fill", self.request, f), "json", 1000, self.kit.grammar.fill(), _is_object, "structured", False)

    def next(self, results):
        return None if results else self._step()

    def reply(self, results):
        return {"values": results[0]}

    def script(self):
        return [json.dumps(sample(self.kit.grammar.fill()))]


class _StyleFit(_Base):
    GRAMMAR = None

    def _step(self) -> Step:
        g = self.kit.grammar
        return Step("style_fit", lambda f: _prompt("style_fit", self.request, f), "json", 400,
                    g.obj({"fits": {"type": "boolean"}, "message": g.text()}), None, "structured", False)

    def next(self, results):
        return None if results else self._step()

    def reply(self, results):
        return results[0]

    def script(self):
        return [json.dumps({"fits": True, "message": ""})]


class _Plan(_Base):
    def _step(self) -> Step:
        return Step("plan", lambda f: _prompt("plan", self.request, f), "json", 900, self.kit.grammar.plan_beat(), _is_object, "structured", False)

    def next(self, results):
        return None if results else self._step()

    def reply(self, results):
        return {"beat": results[0]}

    def script(self):
        return [json.dumps(sample(self.kit.grammar.plan_beat()))]


class _Judge(_Base):
    """One step per rule that has something to ask about; a rule with nothing to look at has no step and no hits."""

    def __init__(self, request, kit):
        super().__init__(request, kit)
        scope = kit.handles.only()
        self.asked: list[tuple[dict, list[str]]] = []
        for rule in request["rules"]:
            handles: list[str] = []
            for key in rule["fields"]:
                handles += scope.handles(key) if key in scope.lists else ([key] if key in scope.scalars else [])
            self.asked.append((rule, handles))
        self.steps = [(rule, handles) for rule, handles in self.asked if handles]

    def _step(self, n: int) -> Step:
        rule, handles = self.steps[n]
        g = self.kit.grammar
        check = {"type": "array", "items": g.obj({"item": g.one_of(handles), "ok": {"type": "boolean"}}), "minItems": len(handles), "maxItems": len(handles)}

        def once(value):
            seen = [c["item"] for c in value["checks"]]
            return None if sorted(seen) == sorted(handles) else "ask about each item exactly once"
        return Step("judge", lambda f: _prompt(f"judge {rule['id']}", self.request, f), "json", 500, g.obj({"checks": check}), once, "structured", False)

    def next(self, results):
        return self._step(len(results)) if len(results) < len(self.steps) else None

    def worst_case(self):
        return [self._step(n) for n in range(len(self.steps))]

    def reply(self, results):
        answers = iter(results)
        out = []
        for rule, handles in self.asked:
            hits = []
            if handles:
                for c in next(answers)["checks"]:
                    if c["ok"] is False:
                        hits.append({"field": c["item"].split(".")[0], "item": c["item"] if "." in c["item"] else None, "key": None})
            out.append({"rule": rule["id"], "hits": hits})
        return {"results": out}

    def script(self):
        return [json.dumps({"checks": [{"item": h, "ok": i != 0} for i, h in enumerate(handles)]}) for _, handles in self.steps]


class _Generate(_Base):
    """The chapter as free text, then what happened, then what changed."""

    def _step(self, n: int, results: list) -> Step:
        g = self.kit.grammar
        if n == 0:
            return Step("write", lambda f: _prompt("write", self.request, f), "text", CHAPTER_WORDS, None, None, "prose", False)
        chapter = results[0]
        if n == 1:
            return Step("events", lambda f: _prompt("events", self.request, f, chapter), "json", 900,
                        g.obj({"happened": g.text(), "changed": g.text()}), _is_object, "structured", False)
        return Step("shifts", lambda f: _prompt("shifts", self.request, f, chapter), "json", 1000, g.obj({"shifts": g.shifts()}),
                    lambda v: self.kit.shifts_problem(v["shifts"]), "structured", False)

    def next(self, results):
        return self._step(len(results), results) if len(results) < 3 else None

    def worst_case(self):
        chapter = "word " * CHAPTER_WORDS
        return [self._step(n, [chapter, {}]) for n in range(3)]

    def reply(self, results):
        return {"chapter_text": results[0], "events": results[1], "shifts": results[2]["shifts"]}

    def script(self):
        return ["The stub chapter opens on a quiet morning and ends on a closed door.",
                json.dumps({"happened": "Something happened in the stub chapter.", "changed": "A thing changed."}),
                json.dumps({"shifts": stub_shifts(self.kit)})]


# ---- The script ---------------------------------------------------------------------------------------------------------

def script(call: str, request: dict, kit: Any) -> list[str]:
    """What a fake engine must return, in order, one text per step, for a valid reply to `request`: `engine.script(*script(...))`."""
    return StubPrompter().flow(call, request, kit).script()


def stub_shifts(kit: Any) -> list[dict]:
    """Shifts of every kind the request allows: a scalar, and a list `add`, `replace` and `remove` for a character and the world, and a
    tie `replace`, `remove` and `add`. A kind that needs an item the request did not send is left out."""
    out = []
    people = [s.label for s in kit.handles.of_card("characters")]
    for scope in kit.handles.of_card("characters")[:1]:
        patch: dict = {"sketch": "Changed in the stub chapter.", "wants": [{"op": "add", "values": {"text": "A new want."}}]}
        wants = scope.handles("wants")
        if wants:
            patch["wants"].append({"op": "replace", "id": wants[0], "values": {"text": "A changed want."}})
        behaviors = scope.handles("behaviors")
        if behaviors:
            patch["behaviors"] = [{"op": "remove", "id": behaviors[0]}]
        out.append({"card": "characters", "target": scope.label, "patch": patch})
    for scope in kit.handles.of_card("world"):
        patch = {"history": "The stub world remembers.", "places": [{"op": "add", "values": {"name": "A New Place", "description": "Stone.", "effect": "Quiet."}}]}
        places = scope.handles("places")
        if places:
            patch["places"].append({"op": "replace", "id": places[0], "values": {"effect": "Loud now."}})
        out.append({"card": "world", "patch": patch})
    for scope in kit.handles.of_card("entanglements"):
        ties = scope.handles("ties")
        ops: list[dict] = []
        if ties:
            ops.append({"op": "replace", "id": ties[0], "values": {"edge": "to do something new"}})
        if len(ties) > 1:
            ops.append({"op": "remove", "id": ties[1]})
        if len(people) > 1:
            ops.append({"op": "add", "values": {"tie_from": people[0], "tie_to": people[1], "bond": "allies", "edge": "to stand together"}})
        if ops:
            out.append({"card": "entanglements", "patch": {"ties": ops}})
    return out


def sample(schema: dict) -> Any:
    """A small valid value for a JSON Schema of the kind grammar.py makes: every property, one item per list, the first choice."""
    if "anyOf" in schema:
        return sample(next((b for b in schema["anyOf"] if b.get("type") != "null"), schema["anyOf"][0]))
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        return {k: sample(v) for k, v in schema.get("properties", {}).items()}
    if kind == "array":
        return [] if schema.get("maxItems") == 0 else [sample(schema.get("items", {}))]
    return {"string": "Stub text.", "integer": 1, "number": 1, "boolean": True, "null": None}.get(kind, "Stub text.")
