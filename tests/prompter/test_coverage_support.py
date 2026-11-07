"""C1 support: the pieces the coverage and rule tests share. It holds no test of its own.

* `schema_fields()` lists every field of every card from the schema's own models (so a field added later is picked up), item fields of
  list fields included.
* `placements(ref, value)` builds, for one field, the valid requests of every call that can carry it, with `value` in the field.
* `prompts(call, request)` drives the real mill flow with the module's own scripted replies and returns the prompt text of every step.
Nothing here needs a model or a network."""
import copy
import json
import re
import sys
import typing
import zlib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _sub in ("backend", "prompts", "e2e"):
    sys.path.insert(0, str(ROOT / "tests" / _sub))

import yaml  # noqa: E402

from pulpermill import contract  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter import load_prompter  # noqa: E402
from pulpermill.prompter import mill as mill_package  # noqa: E402
from pulpermill.prompts import textfiles as tx  # noqa: E402
from pulpermill.schema import CARDS  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
ALLOWLIST_PATH = Path(__file__).resolve().parent / "coverage_allowlist.yaml"
FILL_TARGETS = ("style", "characters", "world", "entanglements", "setup")


def vector(name: str) -> dict:
    return copy.deepcopy(next(v["data"] for v in VECTORS if v["valid"] and v["name"] == name))


PLAN = vector("a plan request")
GENERATE = vector("a generate request")
PID, MID = "c0000001", "c0000002"                      # Suvi (the protagonist) and Marit
TIE_A, TIE_B = "t1000001", "t1000002"                  # Marit toward Suvi (the spotlight), Suvi toward the Board


# ---- the schema's own field list ------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Ref:
    card: str
    key: str
    item: str | None          # the item field when `key` is a list; None for a card field or for the list itself
    meta: dict = field(compare=False, hash=False)
    is_list: bool = False

    @property
    def id(self) -> str:
        return f"{self.card}.{self.key}" + (f".{self.item}" if self.item else "")

    @property
    def options(self) -> dict[str, str]:
        """The option keys of a choice and the explanatory sentence the schema text gives each (empty when the field is no choice)."""
        spec = tx.schema_text(self.card)["fields"].get(self.key) or {}
        if self.item:
            spec = (spec.get("item_fields") or {}).get(self.item) or {}
        return {k: v["expand"] for k, v in (spec.get("options") or {}).items()}


def schema_fields() -> list[Ref]:
    out = []
    for card, (model, *_rest) in CARDS.items():
        for key, f in model.model_fields.items():
            if key == "id":
                continue
            meta = f.json_schema_extra or {}
            if meta.get("repeat"):
                out.append(Ref(card, key, None, meta, True))
                item_model = typing.get_args(f.annotation)[0]
                for item_key, item_field in item_model.model_fields.items():
                    if item_key != "id":
                        out.append(Ref(card, key, item_key, item_field.json_schema_extra or {}))
            else:
                out.append(Ref(card, key, None, meta))
    return out


def allowlist() -> dict[str, str]:
    return yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8")) or {}


# ---- sentinels ------------------------------------------------------------------------------------------------------------

def sentinel(ref: Ref) -> str:
    return f"zq{zlib.crc32(ref.id.encode()):08x}x"


def number_sentinel(ref: Ref) -> int:
    return 40000 + zlib.crc32(ref.id.encode()) % 50000


def is_number(ref: Ref) -> bool:
    return ref.meta.get("input") == "number"


def value_for(ref: Ref):
    return number_sentinel(ref) if is_number(ref) else sentinel(ref)


def expected_text(ref: Ref, value, option_expand: str | None = None) -> str:
    """What must show in a prompt: the sentinel itself, or for an option the longest literal stretch of its explanatory sentence."""
    if option_expand is None:
        return str(value)
    chunks = [c.strip() for c in re.split(r"\{\w+\}", option_expand)]
    return max(chunks, key=len)


# ---- driving the mill ------------------------------------------------------------------------------------------------------

PROMPTER = load_prompter("mill")


def flow_for(call: str, request: dict):
    contract.parse_request(request)                         # every request built here is one the page could send
    kit = Kit(request)
    return PROMPTER.flow(call, request, kit), kit


def prompts(call: str, request: dict, factor: float = 1.0) -> dict[str, str]:
    """The prompt of every step the mill runs for `request`, keyed by step name (a second step of the same name gets #2, #3...).
    The steps are driven with the module's own scripted replies, so a call with several steps is read to the end."""
    flow, kit = flow_for(call, request)
    replies = mill_package.script(call, request, kit)
    results, out = [], {}
    while (step := flow.next(results)) is not None:
        name, n = step.name, 1
        while name in out:
            n += 1
            name = f"{step.name}#{n}"
        out[name] = step.text(factor)
        raw = replies[len(results)]
        results.append(json.loads(raw) if step.kind == "json" else raw)
    return out


def sections(prompt: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", prompt, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def ids_in(node, out=None) -> set[str]:
    out = set() if out is None else out
    if isinstance(node, dict):
        if isinstance(node.get("id"), str):
            out.add(node["id"])
        for key in ("protagonist", "spotlight", "instance"):
            if isinstance(node.get(key), str) and re.fullmatch(r"[a-z]\d{7}", node[key]):
                out.add(node[key])
        for v in node.values():
            ids_in(v, out)
    elif isinstance(node, list):
        for v in node:
            ids_in(v, out)
    return out


# ---- request builders ------------------------------------------------------------------------------------------------------

def plan_request(mutate=None, chapter_one: bool = False) -> dict:
    request = copy.deepcopy(PLAN)
    request["style"] = {}
    if chapter_one:
        request.update(chapter=1, earlier_beats=[], earlier_events=[])
    if mutate:
        mutate(request)
    return request


def generate_request(mutate=None, chapter_one: bool = False) -> dict:
    request = copy.deepcopy(GENERATE)
    request["style"] = {}
    if chapter_one:
        request.update(chapter=1, earlier_events=[], previous_ending=None)
    if mutate:
        mutate(request)
    return request


def fill_request(card: str, values: dict, related: dict | None = None, instance: str | None = None) -> dict:
    return {"call": "fill", "schema_version": 4, "language": "en", "card": card, "instance": instance, "note": "A short note.",
            "example_chapter": None, "values": values, "related": related or {}}


def fit_request(style: dict, protagonist: dict) -> dict:
    return {"call": "style_fit", "schema_version": 4, "language": "en", "style": style, "protagonist": protagonist}


def judge_requests(card: str, values: dict, related: dict, key: str, instance: str | None = None) -> list[dict]:
    """One judge request carrying every model-judged rule that looks at `key`; none when no such rule exists."""
    rules = []
    texts = tx.schema_text(card).get("rules") or {}
    for rule in CARDS[card][3]:
        if rule.needs_model and key in rule.fields and (texts.get(rule.id) or {}).get("judge_prompt"):
            rules.append({"id": rule.id, "fields": [key]})
    if not rules:
        return []
    return [{"call": "judge", "schema_version": 4, "language": "en", "card": card, "instance": instance, "rules": rules, "values": values,
             "related": related}]


SUVI = copy.deepcopy(PLAN["cast"][0])
MARIT = copy.deepcopy(PLAN["cast"][1])
WORLD = copy.deepcopy(PLAN["world"])
TIES = copy.deepcopy(PLAN["ties"])
HOLDINGS = copy.deepcopy(PLAN["holdings"])


def _filler_item(ref: Ref) -> dict:
    """A new list item with every item field filled with plain text."""
    model = typing.get_args(CARDS[ref.card][0].model_fields[ref.key].annotation)[0]
    return {"id": "z0000001", **{key: "plain filler text" for key in model.model_fields if key != "id"}}


def _set(card: dict, ref: Ref, value) -> dict:
    """The card with `value` in the field `ref` (the first item of a list, made if there is none, for an item field)."""
    card = copy.deepcopy(card)
    if ref.item:
        items = card.get(ref.key) or []
        first = {**_filler_item(ref), **(items[0] if items else {}), ref.item: value}
        card[ref.key] = [first, *items[1:]]
    else:
        card[ref.key] = value
    return card


# ---- placements: the requests that can carry one field --------------------------------------------------------------------

@dataclass
class Placement:
    call: str
    request: dict
    section: str | None = None          # a heading the sentinel must sit under (the spotlight), when the field says where it shows
    control: dict | None = None         # the same request with the field left ordinary: the sentinel must not sit under `section` there


def placements(ref: Ref, value) -> list[Placement]:
    """Every valid request of every call that can carry the field, with `value` in it. `value` is a sentinel, or an option key."""
    k, i = ref.key, ref.item
    out: list[Placement] = []
    if ref.is_list:                                                          # a list is covered through its item fields
        return out
    add = lambda call, request, section=None, control=None: out.append(Placement(call, request, section, control))
    named = lambda who: (lambda q: q["cast"][who].update(name=value))        # a name is how a link field reaches the model

    if ref.card == "style":
        add("fill", fill_request("style", {k: value}))
        add("fill", fill_request("setup", {"protagonist": PID}, {"style": {k: value}, "characters": [{"id": PID, "name": "Suvi"}]}))
        add("style_fit", fit_request({k: value}, {"id": PID, "name": "Suvi"}))
        add("plan", plan_request(lambda q: q.update(style={k: value})))
        add("generate", generate_request(lambda q: q.update(style={k: value})))

    elif ref.card == "characters":
        person = _set(SUVI, ref, value)
        add("fill", fill_request("characters", person, instance=PID))
        for target in ("setup", "entanglements"):
            add("fill", fill_request(target, {"protagonist": PID} if target == "setup" else {"ties": [], "holdings": []}, {"characters": [person, MARIT]}))
        add("style_fit", fit_request({"person": "first", "tense": "past"}, person))
        add("plan", plan_request(lambda q: q["cast"].__setitem__(0, person)))
        add("generate", generate_request(lambda q: q["cast"].__setitem__(0, person)))
        for req in judge_requests("characters", person, {}, k, instance=PID):
            add("judge", req)

    elif ref.card == "world":
        world = _set(WORLD, ref, value)
        names_place = (k == "places" and i == "name")
        add("fill", fill_request("world", world))
        for target, values in (("entanglements", {"ties": [], "holdings": []}), ("setup", {"protagonist": PID})):
            add("fill", fill_request(target, values, {"world": world, "characters": [SUVI, MARIT]}))
        add("plan", plan_request(lambda q: q.update(world=world)))
        add("generate", generate_request(lambda q: (q.update(world=world), q["beat"].update(where=value) if names_place else None)))
        for req in judge_requests("world", world, {}, k):
            add("judge", req)

    elif ref.card == "entanglements":
        people = [copy.deepcopy(SUVI), copy.deepcopy(MARIT)]
        world = copy.deepcopy(WORLD)
        ties, holdings = copy.deepcopy(TIES), copy.deepcopy(HOLDINGS)
        if i in ("tie_from", "tie_to", "holdee", "held_by"):               # a link: the model reads the name of what it points at
            target = {"tie_from": (people[1], "name"), "tie_to": (people[0], "name"), "holdee": (world["objects"][0], "name"),
                      "held_by": (world["powers"][0], "name")}[i]
            target[0][target[1]] = value
        elif k == "ties":
            ties[0][i] = value
        else:
            holdings[0][i] = value
        related = {"characters": people, "world": world}
        add("fill", fill_request("entanglements", {"ties": ties, "holdings": holdings}, related))
        add("plan", plan_request(lambda q: q.update(cast=people, world=world, ties=ties, holdings=holdings)))
        add("generate", generate_request(lambda q: q.update(cast=people, world=world, ties=ties, holdings=holdings)))
        for req in judge_requests("entanglements", {"ties": ties, "holdings": holdings}, related, k):
            add("judge", req)

    elif ref.card == "setup":
        if k == "protagonist":                                              # a link: the model reads the protagonist's name
            people = [{**SUVI, "name": value}, MARIT]
            add("fill", fill_request("setup", {"protagonist": PID}, {"characters": people}))
            add("plan", plan_request(lambda q: q.update(cast=people)))
            add("generate", generate_request(lambda q: q.update(cast=people)))
        else:
            setup = {"protagonist": PID, k: value}
            add("fill", fill_request("setup", setup, {"characters": [SUVI, MARIT]}))
            if k == "chapter_count":
                add("plan", plan_request(lambda q: q.update(setup={**q["setup"], k: value}, chapter_count=value)))
                add("generate", generate_request(lambda q: q.update(setup={**q["setup"], k: value}, chapter_count=value)))
            else:
                add("plan", plan_request(lambda q: q.update(setup={**q["setup"], k: value}), chapter_one=True))
                add("generate", generate_request(lambda q: q.update(setup={**q["setup"], k: value}), chapter_one=True))
            for req in judge_requests("setup", setup, {"characters": [SUVI, MARIT]}, k):
                add("judge", req)

    elif ref.card == "outline" and i:
        if i == "where":
            add("plan", plan_request(lambda q: q["earlier_beats"][0].update(where=value)))
            add("generate", generate_request(lambda q: (q["world"]["places"][0].update(name=value), q["beat"].update(where=value))))
        elif i == "when_time":
            add("plan", plan_request(lambda q: q["earlier_beats"][0].update(when=value)))
            add("generate", generate_request(lambda q: q["beat"].update(when_time=value)))
        elif i == "aim":
            add("plan", plan_request(lambda q: q["earlier_beats"][0].update(aim=value)))
            add("plan", plan_request(lambda q: q.update(retry={"beat": {"aim": value, "plan": "A plan."}, "problems": ["Nothing changes."]})))
            add("generate", generate_request(lambda q: q["beat"].update(aim=value)))
        elif i == "plan":
            add("plan", plan_request(lambda q: q.update(retry={"beat": {"aim": "Get the ledger.", "plan": value}, "problems": ["Nothing changes."]})))
            add("generate", generate_request(lambda q: q["beat"].update(plan=value)))
        elif i == "cast":                                                   # the cast is sent as the people themselves: their names
            add("plan", plan_request(named(1)))
            add("generate", generate_request(named(1)))
        elif i == "spotlight":                                              # the tie in the spotlight is told apart from the other ties
            marked = lambda q: q["ties"][1].update(bond=value)
            add("plan", plan_request(lambda q: (marked(q), q.update(spotlight=TIE_B))), "The tie in the spotlight",
                plan_request(lambda q: (marked(q), q.update(spotlight=TIE_A))))
            add("generate", generate_request(lambda q: (marked(q), q["beat"].update(spotlight=TIE_B))), "The tie in the spotlight",
                generate_request(lambda q: (marked(q), q["beat"].update(spotlight=TIE_A))))

    elif ref.card == "summary_events" and i in ("happened", "changed"):
        add("plan", plan_request(lambda q: q["earlier_events"][0].update(**{i: value})))
        add("generate", generate_request(lambda q: q["earlier_events"][0].update(**{i: value})))
    return out


def shown_in(ref: Ref, value, expect: str) -> dict[str, list[str]]:
    """The prompts that show `expect`, as {call: [step names]}. A placement that names a heading counts only when the text sits under that
    heading, and not when the control request (the field left ordinary) shows it there too."""
    found: dict[str, list[str]] = {}
    for p in placements(ref, value):
        for step, text in prompts(p.call, p.request).items():
            haystack = sections(text).get(p.section, "") if p.section else text
            if expect.lower() not in haystack.lower():
                continue
            if p.control is not None:
                control = prompts(p.call, p.control).get(step, "")
                if expect.lower() in sections(control).get(p.section, "").lower():
                    continue
            found.setdefault(p.call, []).append(step)
    return found
