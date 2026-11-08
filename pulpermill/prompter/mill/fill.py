"""The `fill` call: one JSON step that fills one card from a note and/or an example chapter, given the cards it reads. The card's own
current values are never shown: a card that already holds values is asked for exactly as a blank one is. Wording lives in text/en/fill.yaml (field meanings, scope rules, the probe-targeted guidance). Rules served: R1 (every card field has
a meaning sentence, enforced by a test) and R2 (cards reach the model as prose; the only raw tokens are the answer words of a choice, each
explained by its own sentence).

The grammar (kit.grammar.fill()) requires every field and limits links to the names the request sent, so this module's job is wording
and a small check for what the grammar cannot see."""
import json
import re
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step
from pulpermill.prompter.stub.stub import sample

from . import common

VERSION = "fill-3"
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
        items = (w.get("item_fields") or {}).get(card, {}).get(key)
        if items:
            line += "\n" + w["item_lead"] + "\n" + "\n".join(f"  {k}: {v}" for k, v in items.items())
        out.append(line)
    return w["fields_lead"] + "\n\n" + "\n\n".join(out)


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
    keys = list(kit.grammar.fill()["properties"])

    inputs = [w[mode]]
    if note:
        inputs.append(w["note_label"] + "\n" + note)
    if chapter:
        inputs.append(w["chapter_label"] + "\n" + _shorten(chapter, factor if factor < 0.7 else 1.0))
    guidance = [meta["scope"]] + list(meta["specific"])
    person = r.s((request.get("values") or {}).get("name")) if card == "characters" else ""      # the one current value a prompt shows: who the card is for

    blocks = [
        w["role"].format(label=label, intro=meta["intro"]),
        "\n\n".join(inputs),
        w["person_line"].format(name=person) if person else "",
        w["language_line"].format(language=language_name(request.get("language"))),
        "\n\n".join(guidance),
        field_guidance(card, keys),
        (w["related_lead"] + "\n\n" + related) if related else "",
        _names_block(request),
        w["empty_card"],            # a re-fill is asked exactly as a blank card is: the card's current values are never shown
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


def item_required(card: str, key: str) -> list[str]:
    """The fields every item of the list `key` of `card` must carry, as the card's schema marks them (ids are made by the page)."""
    from typing import get_args
    from pulpermill.schema import CARDS
    item = get_args(CARDS[card][0].model_fields[key].annotation)[0]
    return [k for k, f in item.model_fields.items() if k != "id" and f.is_required()]


def empty_item_field(card: str, value: dict) -> str | None:
    """One plain line naming the list and the field when an item the fill wrote lacks a required field or holds it empty; else None.
    The grammar already requires the fields, but it still allows an empty string."""
    from pulpermill.schema import CARDS
    pr = common.load_text("fill")["problems"]
    for key, items in value.items():
        if not isinstance(items, list) or key not in CARDS[card][0].model_fields:
            continue
        try:
            needed = item_required(card, key)
        except (IndexError, AttributeError, TypeError):
            continue
        for item in items:
            if isinstance(item, dict):
                for field in needed:
                    if not r.s(item.get(field)):
                        return pr["empty_item_field"].format(list=key, field=field)
    return None


def setup_strangers(request: dict, value: Any) -> list[str]:
    """The people on no card that the setup fill's normal and disruption name (Rule 5 asks for role only). This only lists them, as the plan
    and the chapter do (`plan_names`, `write_names`): a name is no reason to refuse a reply, so the fill is used and the names go to the
    console as a soft note. The cards and the writer's own text (note, example chapter, values) are the names that may be used. Empty for
    any other card, and for a story in a language the detector does not read."""
    if request.get("card") != "setup" or not isinstance(value, dict):
        return []
    return common.names_found(request, [r.s(value.get("normal")), r.s(value.get("disruption"))],
                              [request.get(k) for k in ("note", "example_chapter", "values", "related")])


def fill_problem(request: dict, value: Any) -> str | None:
    """None when the reply is usable, else one plain line saying what to fix. Every problem it returns is hard and refuses the attempt. A
    person on no card never does (see `setup_strangers`)."""
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

    empty = empty_item_field(card, value)
    if empty:
        return empty
    # Every field is asked for, as on a blank card, so a field the reply holds empty is a miss. (A protagonist has no name to take
    # while the Characters card names nobody.)
    for key, given in value.items():
        if (given is None or (isinstance(given, str) and not given.strip())) and not (card == "setup" and key == "protagonist" and not people):
            return pr["empty_field"].format(field=key)

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
        typed = r.s((request.get("values") or {}).get("name"))
        if typed and _norm(value.get("name")) != _norm(typed):      # a blank typed name skips the check
            return pr["name_mismatch"].format(name=typed)
        wants = value.get("wants")
        if wants is not None and len(wants) < 2:
            return pr["one_want"]
    if card == "setup":
        # (A person on no card is not a problem here: see `setup_strangers`.)
        count = stated_chapter_count(r.s(request.get("note")))
        if count and "chapter_count" in value and int(value["chapter_count"]) != count:
            return pr["chapter_count"].format(count=count)
        if count and "chapter_count" not in value:
            return pr["chapter_count_missing"].format(count=count)
    if not value and card != "entanglements":
        return pr["nothing"]
    return None


# ---- the flow ---------------------------------------------------------------------------------------------------------------------

class FillFlow(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit
        self.notes: dict[str, Any] = {}     # for the run log: on a setup fill, how many people on no card the reply names (minor_names)

    def _check(self, value: Any) -> str | None:
        """The step's check: the hard problems refuse the attempt. A person on no card does not: the reply is used, the names go to the
        trace as a soft note, and the count goes to the run record. The last reply to pass is the one used, so its count is the one that stays."""
        problem = fill_problem(self.request, value)
        if problem:
            return problem
        if self.request.get("card") == "setup":
            strangers = setup_strangers(self.request, value)
            self.notes["minor_names"] = len(strangers)
            if strangers:
                common.note_soft("fill", "fill", common.load_text("fill")["problems"]["unknown_person"].format(names=", ".join(strangers)))
        return None

    def _step(self) -> Step:
        return Step("fill", lambda f: build_prompt(self.request, self.kit, f), "json", MAX_OUTPUT, self.kit.grammar.fill(),
                    self._check, "structured", True)

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
        value["chapter_count"] = stated_chapter_count(r.s(request.get("note"))) or 12
    return [json.dumps(value, ensure_ascii=False)]
