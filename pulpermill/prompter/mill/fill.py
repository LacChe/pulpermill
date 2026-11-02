"""The `fill` call: one JSON step that fills one card from a note and/or an example chapter, given the card's current values and the cards it
reads. Wording lives in text/en/fill.yaml (field meanings, scope rules, the probe-targeted guidance). Rules served: R1 (every card field has
a meaning sentence, enforced by a test) and R2 (cards reach the model as prose; the only raw tokens are the answer words of a choice, each
explained by its own sentence).

The grammar (kit.grammar.fill()) makes every field optional and limits links to the names the request sent, so this module's job is wording
and a small check for what the grammar cannot see."""
import json
import re
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step
from pulpermill.prompter.stub.stub import sample

from . import common

VERSION = "fill-1"
MAX_OUTPUT = 2000      # a long World (nine places and their detail) is the heaviest reply


def language_name(code: str | None) -> str:
    names = common.load_text("fill")["languages"]
    code = str(code or "en")
    return names.get(code) or names.get(code.split("-")[0]) or code


# ---- what the card is linked to -----------------------------------------------------------------------------------------------

def _people(related: dict) -> list[dict]:
    people = related.get("characters") or []
    return [people] if isinstance(people, dict) else [p for p in people if isinstance(p, dict)]


def link_names(request: dict) -> dict[str, list[str]]:
    """The names a fill may link to, by kind: people, groups, places, things."""
    related = request.get("related") or {}
    world = related.get("world") or {}
    pick = lambda items, key="name": [r.s(i.get(key)) for i in items or [] if isinstance(i, dict) and r.s(i.get(key))]
    return {"people": pick(_people(related)), "groups": pick(world.get("powers")), "places": pick(world.get("places")), "things": pick(world.get("objects"))}


def _names_block(request: dict) -> str:
    w = common.load_text("fill")
    names = link_names(request)
    if request["card"] not in ("entanglements", "setup"):
        return ""
    keys = ("people",) if request["card"] == "setup" else ("people", "groups", "places", "things")
    lines = [w[f"names_{k}"].format(items=", ".join(names[k])) for k in keys if names[k]]
    return w["names_lead"] + "\n" + "\n".join(lines) if lines else w["names_none"]


# ---- cards in words ------------------------------------------------------------------------------------------------------------

def _ent_words(ent: dict, names: dict[str, str]) -> dict:
    return {"ties": r.in_words(ent.get("ties") or [], {"tie_from": {"ref": True}, "tie_to": {"ref": True}}, names),
            "holdings": r.in_words(ent.get("holdings") or [], {"holdee": {"ref": True}, "held_by": {"ref": True}}, names)}


def has_content(card: str, values: dict) -> bool:
    ignore = {"id"}
    if card == "characters":
        ignore.add("name")
    return any(v not in (None, "", [], {}) for k, v in (values or {}).items() if k not in ignore)


def _current(request: dict, names: dict[str, str]) -> str:
    """What the card already holds, in prose (empty when nothing)."""
    card, values = request["card"], request.get("values") or {}
    w = common.load_text("fill")
    if card == "style":
        return r.render_style(values, scope="writer") if has_content(card, values) else ""
    if card == "characters":
        return r.render_person(values, scope="writer") if has_content(card, values) or r.s(values.get("name")) else ""
    if card == "world":
        return r.render_world(values, scope="writer") if has_content(card, values) else ""
    if card == "entanglements":
        return r.render_entanglements(_ent_words(values, names), scope="writer") if has_content(card, values) else ""
    lines = []
    if r.s(values.get("protagonist")):
        lines.append(w["setup_protagonist"].format(value=names.get(values["protagonist"], r.s(values["protagonist"]))))
    for key in ("normal", "disruption"):
        if r.s(values.get(key)):
            lines.append(w[f"setup_{key}"].format(value=r.s(values[key])))
    if values.get("chapter_count"):
        lines.append(w["setup_count"].format(value=values["chapter_count"]))
    return " ".join(lines)


def _related_text(request: dict, names: dict[str, str]) -> str:
    related = request.get("related") or {}
    parts = []
    if related.get("style"):
        parts.append(r.render_style(related["style"], scope="planner"))
    if related.get("characters"):
        parts.append("\n".join(r.render_person_brief(p) for p in _people(related)))
    if related.get("world"):
        parts.append(r.render_world(related["world"], scope="planner"))
    if related.get("entanglements"):
        parts.append(r.render_entanglements(_ent_words(related["entanglements"], names), scope="planner"))
    return "\n\n".join(p for p in parts if p)


def _shorten(text: str, factor: float) -> str:
    """The example chapter cut to `factor` of its length from the middle, so that its opening and its end (where late facts sit) both stay."""
    if factor >= 1.0 or len(text) <= 1200:
        return text
    keep = max(int(len(text) * factor), 1200)
    head, tail = int(keep * 0.55), int(keep * 0.45)
    cut = lambda t, n, side: (t[:n].rsplit(None, 1)[0] if side == "head" else t[-n:].split(None, 1)[-1])
    return cut(text, head, "head") + "\n" + common.load_text("fill")["chapter_gap"] + "\n" + cut(text, tail, "tail")


# ---- fields ----------------------------------------------------------------------------------------------------------------------

def field_guidance(card: str, keys: list[str]) -> str:
    """One paragraph per field the grammar offers: its meaning (our words), the answer words of a choice (with their own explanations) and one good and
    one avoid example from the schema's text. A field with no meaning sentence is a bug (a test lists the cards' fields against the wording)."""
    w = common.load_text("fill")
    spec = tx.schema_text(card)["fields"]
    out = []
    for key in keys:
        line = f"{key}: {w['fields'][card][key]}"
        field = spec.get(key) or {}
        options = field.get("options") or {}
        if options and not isinstance(next(iter(options.values())), str):
            choices = " ".join(w["choice_item"].format(key=o, expand=r.s(v.get("expand")).replace("{name}", "the person")) for o, v in options.items())
            line += f" {w['choice_lead']} {choices}"
        examples = field.get("examples") or next((i["examples"] for i in (field.get("item_fields") or {}).values() if i.get("examples")), None)
        if examples and examples.get("good") and examples.get("avoid"):
            line += " " + w["examples_good"].format(good=examples["good"][0]) + " " + w["examples_avoid"].format(avoid=examples["avoid"][0])
        out.append(line)
    return w["fields_lead"] + "\n\n" + "\n\n".join(out) + "\n\n" + w["examples_note"]


# ---- the prompt ---------------------------------------------------------------------------------------------------------------

def build_prompt(request: dict, kit: Any, factor: float = 1.0) -> str:
    w = common.load_text("fill")
    card = request["card"]
    names = r.names_by_id(request.get("related") or {})
    meta = w["cards"][card]
    note, chapter = r.s(request.get("note")), r.s(request.get("example_chapter"))
    mode = "both" if note and chapter else "note_only" if note else "chapter_only"
    label = tx.schema_text(card)["card"]["label"]

    with tx.squeeze(factor):
        related = _related_text(request, names)
    current = _current(request, names)
    keys = list(kit.grammar.fill()["properties"])

    inputs = [w[mode]]
    if note:
        inputs.append(w["note_label"] + "\n" + note)
    if chapter:
        inputs.append(w["chapter_label"] + "\n" + _shorten(chapter, factor if factor < 0.7 else 1.0))
    guidance = [meta["scope"]] + list(meta["specific"])

    blocks = [
        w["role"].format(label=label, intro=meta["intro"]),
        "\n\n".join(inputs),
        w["language_line"].format(language=language_name(request.get("language"))),
        "\n\n".join(guidance),
        field_guidance(card, keys),
        (w["related_lead"] + "\n\n" + related) if related else "",
        _names_block(request),
        (w["filled_lead"] + "\n\n" + current) if current else w["empty_card"],
        w["output"],
    ]
    return "\n\n".join(b for b in blocks if b)


# ---- the check -------------------------------------------------------------------------------------------------------------------

def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(text or "").lower())).strip()


def _strings(node: Any, path: str = ""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, path)


def stated_chapter_count(note: str) -> int | None:
    """The number of chapters a note states ("nine chapters", "6 chaps", "六章"), else None."""
    words = common.load_text("fill")["number_words"]
    text = str(note or "").lower()
    m = re.search(r"\b(\d{1,2})\s*(?:chapters?|chaps?)\b", text) or re.search(r"(\d{1,2})\s*章", text)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(" + "|".join(words) + r")\s+chapters?\b", text)
    return words[m.group(1)] if m else None


def fill_problem(request: dict, value: Any) -> str | None:
    """None when the reply is usable, else one plain line saying what to fix."""
    p = common.load_text("fill")
    pr = p["problems"]
    if not isinstance(value, dict):
        return pr["not_object"]
    card = request["card"]
    names = link_names(request)
    people, groups, places, things = (set(names[k]) for k in ("people", "groups", "places", "things"))

    choices = {k for k, f in tx.schema_text(card)["fields"].items() if f.get("options")}      # an answer word such as "none" is a choice, not a stand-in
    for path, text in _strings(value):
        if path.split(".")[-1] not in choices and (_norm(text) in p["stand_ins"] or text.strip().lower() in p["stand_ins"]):
            return pr["stand_in"].format(field=path.split(".")[-1], value=text.strip())

    def linked(name, allowed, shown):
        return pr["bad_link"].format(name=name, names=", ".join(sorted(shown))) if name and name not in allowed else None

    if card == "setup" and r.s(value.get("protagonist")):
        bad = linked(value["protagonist"], people, people)
        if bad:
            return bad
    if card == "entanglements":
        ends = people | groups
        for tie in value.get("ties") or []:
            a, b = r.s(tie.get("tie_from")), r.s(tie.get("tie_to"))
            bad = linked(a, ends, ends) or linked(b, ends, ends)
            if bad:
                return bad
            if a and a == b:
                return pr["self_tie"].format(name=a)
            if r.s(tie.get("bond")) and _norm(tie.get("bond")) == _norm(tie.get("edge")):
                return pr["bond_is_edge"].format(tie_from=a, tie_to=b)
            if any(re.search(rf"\b{re.escape(word)}\b", _norm(tie.get("bond"))) for word in p["ownership_words"]):
                return pr["ownership_tie"].format(bond=r.s(tie.get("bond")), tie_from=a, tie_to=b)
        for h in value.get("holdings") or []:
            holdee, held_by = r.s(h.get("holdee")), r.s(h.get("held_by"))
            bad = linked(holdee, things | places, things | places) or linked(held_by, people | groups | places, people | groups | places)
            if bad:
                return bad
            if holdee in places and held_by in places:
                return pr["holding_pair"].format(holdee=holdee, held_by=held_by)
    if card == "world":
        for path, text in _strings(value):
            for name in names["people"]:
                if name and name in text:
                    return pr["name_leak"].format(name=name, where=path.split(".")[0])
    if card == "characters":
        wants = value.get("wants")
        if wants is not None and len(wants) < 2 and not (request.get("values") or {}).get("wants"):
            return pr["one_want"]
    if card == "setup":
        count = stated_chapter_count(r.s(request.get("note")))
        if count and "chapter_count" in value and int(value["chapter_count"]) != count:
            return pr["chapter_count"].format(count=count)
        if count and "chapter_count" not in value and not (request.get("values") or {}).get("chapter_count"):
            return pr["chapter_count_missing"].format(count=count)
    if not value and card != "entanglements" and not has_content(card, request.get("values") or {}):
        return pr["nothing"]
    return None


# ---- the flow ---------------------------------------------------------------------------------------------------------------------

class FillFlow(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit

    def _step(self) -> Step:
        return Step("fill", lambda f: build_prompt(self.request, self.kit, f), "json", MAX_OUTPUT, self.kit.grammar.fill(),
                    lambda v: fill_problem(self.request, v), "structured", True)

    def next(self, results):
        return None if results else self._step()

    def reply(self, results):
        return {"values": results[0]}


def build_flow(request, kit) -> Flow:
    return FillFlow(request, kit)


def script(request: dict, kit: Any) -> list[str]:
    """What a fake engine must return for a valid reply: the grammar's sample, made to pass the check."""
    grammar = kit.grammar.fill()
    value = sample(grammar)
    card = request["card"]
    names = link_names(request)

    zh = str(request.get("language") or "").lower().startswith("zh")      # the runner checks that long texts are in the story's language
    filler = "这是一个具体而独特的细节，适合这个故事。" if zh else "A specific detail for this card."

    def tidy(node):
        if isinstance(node, str):
            return filler if node.strip().lower() == "stub text." else node
        if isinstance(node, list):
            return [tidy(x) for x in node]
        return {k: tidy(v) for k, v in node.items()} if isinstance(node, dict) else node
    value = tidy(value)
    if card == "characters":
        value["name"] = r.s((request.get("values") or {}).get("name")) or f"Suvi {str(request.get('instance') or '')[-4:]}".strip()
        value["wants"] = [{"text": "渴望被放过，也渴望被需要。" if zh else "to be left alone"}, {"text": "想要被看见，同时又害怕被看见。" if zh else "to be needed"}]
    if card == "entanglements":
        ends = names["people"] + names["groups"]
        value["ties"] = [{"tie_from": ends[0], "tie_to": ends[1], "bond": "自学生时代起的老朋友，彼此知根知底。" if zh else "old friends since school", "edge": "想要得到对方的原谅，好让自己能继续往前走。" if zh else "to be forgiven"}] if len(ends) > 1 else []
        holders, held = ends, names["things"] + names["places"]
        value["holdings"] = [{"holdee": held[0], "held_by": holders[0]}] if holders and held else []   # an empty list when nothing can be linked
    if card == "setup":
        value["protagonist"] = (names["people"] or [""])[0]
        value["chapter_count"] = stated_chapter_count(r.s(request.get("note"))) or 6
    return [json.dumps(value, ensure_ascii=False)]
