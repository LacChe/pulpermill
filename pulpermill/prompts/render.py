"""Card renderers: one function per card or record, returning prose. Names, never ids. A fixed order (the schema's
RENDER_ORDER where it has one), a length cap per field (the schema's `cap`, plus limits.yaml), and any clause whose value is empty is left out
instead of printing an empty label. Nothing here calls a model.

Two scopes: "writer" (the chapter writer, and the extractors that read the same cast) and "planner"."""
import re
from typing import Any, Iterable

from ..schema.style import RENDER_ORDER as STYLE_ORDER
from . import textfiles as tx

PLANNER_STYLE = ["genre", "lens", "humor", "attitude", "pacing"]
PRONOUNS = {
    "female": {"they": "she", "them": "her", "their": "her", "themselves": "herself"},
    "male": {"they": "he", "them": "him", "their": "his", "themselves": "himself"},
    "other": {"they": "they", "them": "them", "their": "their", "themselves": "themselves"},
}
# Words that may safely start a sentence-case value without being a name. Used to lower the first letter where a template
# continues a sentence ("Right now, she wants ..."). A name is never in this list, so a name is never lowered.
_FUNCTION_WORDS = {"a", "an", "the", "he", "she", "they", "it", "his", "her", "their", "its", "this", "that", "there",
                   "these", "those", "we", "you", "some", "every", "each", "no", "all", "any", "when", "if", "while", "once"}


# ---- Small tools ----------------------------------------------------------------------------------------------------

class Report:
    """What the renderers cut. A clipped field is never silent: the backend logs these."""
    def __init__(self):
        self.clips: list[str] = []

    def __bool__(self):
        return bool(self.clips)


def s(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(s(v) for v in value if s(v))
    return str(value).strip()


def clip(text: str, limit: int | None, where: str = "", report: Report | None = None) -> str:
    text = s(text)
    if not limit or len(text) <= limit:
        return text
    cut = text[:limit]
    ends = [m.end() for m in re.finditer(r"[.!?][\"”')]?(?=\s|$)", cut)]
    out = cut[:ends[-1]].strip() if ends and ends[-1] >= limit * 0.5 else cut[:cut.rfind(" ")].strip() + "…"
    if report is not None:
        report.clips.append(f"{where}: {len(text)} -> {len(out)} characters")
    return out


def soften(text: str) -> str:
    """Lowers the first letter of a value that starts with a function word, so it can follow a comma or a lead-in. Names and
    other words keep their capital."""
    text = s(text)
    m = re.match(r"([A-Za-z]+)\b", text)
    return text[0].lower() + text[1:] if m and m.group(1).lower() in _FUNCTION_WORDS and m.group(1) != "I" else text


def join_names(names: Iterable[str]) -> str:
    names = [n for n in (s(x) for x in names) if n]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def sentence(text: str) -> str:
    text = s(text)
    return text if not text or text[-1] in ".!?:\"”')" else text + "."


def tidy(text: str) -> str:
    """A value that already ends in a full stop must not meet the template's own."""
    return re.sub(r"(?<![.\d])\.\.(?!\.)", ".", text)


_SEGMENT = re.compile(r"(?<=\})\s+(?=[A-Z])|(?<=\.)\s+(?=[A-Z{])")
_TOKEN = re.compile(r"\{(\w+)\}")


def fill(template: str, tokens: dict[str, Any], *, drop_first: bool = False) -> str:
    """Fills {tokens}. The template is read as clauses; a clause after the first that holds an empty token is dropped,
    so an empty box leaves no label behind. With `drop_first`, the first clause is dropped the same way (for a template
    whose every clause stands alone)."""
    kept = []
    for i, part in enumerate(_SEGMENT.split(template)):
        names = _TOKEN.findall(part)
        if (i > 0 or drop_first) and any(not s(tokens.get(n)) for n in names):
            continue
        kept.append(_TOKEN.sub(lambda m: s(tokens.get(m.group(1), "")), part))
    return tidy(" ".join(kept)).strip()


def lead(card: str, key: str, **tokens) -> str:
    return fill(tx.field(card, key)["lead_in"], tokens)


def _items_block(card: str, key: str, items: list[str], **tokens) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    join = tx.field(card, key).get("item_join") or "\n"
    return fill_lead(tx.field(card, key)["lead_in"], join.join(items), tokens)


def fill_lead(lead_in: str, items: str, tokens: dict[str, Any]) -> str:
    """A lead-in with {items} filled with already-rendered lines. The lines are not re-read as templates."""
    marker = "\u0000ITEMS\u0000"
    text = _TOKEN.sub(lambda m: marker if m.group(1) == "items" else s(tokens.get(m.group(1), "")), lead_in)
    return text.replace(marker, items).strip()


# ---- Style ----------------------------------------------------------------------------------------------------------

def render_style(style: dict, *, scope: str = "writer", report: Report | None = None) -> str:
    """The Style card as instructions. Writer: both paragraphs of RENDER_ORDER. Planner: tone only."""
    directives = tx.prompt_text("style_directives")
    texts = tx.schema_text("style")["fields"]
    paragraphs = []
    order = [PLANNER_STYLE] if scope == "planner" else STYLE_ORDER
    for group in order:
        pieces = []
        for key in group:
            if scope == "planner" and key not in PLANNER_STYLE:
                continue
            value = s(style.get(key))
            if not value:
                continue                                     # an empty axis means the model decides
            spec = texts[key]
            if key in directives["notes"]:
                pieces.append(fill(directives["notes"][key], {"value": value}))
            elif "options" in spec:
                if value not in spec["options"]:
                    continue
                piece = spec["options"][value]["expand"]
                extra = directives["directives"].get(key, {}).get(value)
                pieces.append(f"{piece} {extra}" if extra and scope == "writer" else piece)
            else:                                            # lens and genre: a lead-in, then one sentence of use
                extra = directives["lead_in_extra"].get(key, "")
                pieces.append(f"{fill(spec['lead_in'], {'value': value.rstrip('.')})} {extra}".strip())
        if pieces:
            paragraphs.append(" ".join(pieces))
    return "\n\n".join(paragraphs)


# ---- Characters -----------------------------------------------------------------------------------------------------

def _list_items(person: dict, key: str, text_key: str, cap: int, report) -> list[str]:
    return [clip(i.get(text_key), cap, f"{person.get('name')}.{key}", report) for i in person.get(key) or []]


def render_person(person: dict, *, scope: str = "writer", report: Report | None = None) -> str:
    c = tx.limits()["characters"]
    name = s(person.get("name"))
    writer = scope == "writer"
    speaks = scope in ("writer", "fit")                      # the style-fit check also needs how the person speaks
    frames = tx.prompt_text("frames")
    chars = tx.schema_text("characters")["fields"]
    lines: list[str] = []

    def put(para: list[str]):
        para = [p for p in para if p]
        if para:
            lines.append(" ".join(para))

    # who they are
    first = [lead("characters", "name", value=name)]
    if writer and s(person.get("age")):
        first.append(lead("characters", "age", name=name, value=s(person.get("age"))))
    sex = s(person.get("sex"))
    if sex in chars["sex"]["options"]:
        first.append(fill(chars["sex"]["options"][sex]["expand"], {"name": name}))
    if writer and s(person.get("appearance")):
        first.append(lead("characters", "appearance", name=name, value=s(person.get("appearance"))))   # fixed: sent in full
    if s(person.get("sketch")):
        first.append(fill(frames["sketch"], {"name": name, "value": clip(person["sketch"], c["sketch"], f"{name}.sketch", report)}))
    put(first)

    pro = PRONOUNS.get(sex, PRONOUNS["other"])

    # what drives them
    drive = []
    wants = _list_items(person, "wants", "text", c["want_item"], report)
    if wants:
        drive.append(fill_lead(chars["wants"]["lead_in"], "; ".join(wants), {"name": name}))
    if s(person.get("fear")):
        drive.append(fill(frames["portrait_fear"], {"name": name, "themselves": pro["themselves"], "value": clip(person["fear"], c["fear"], f"{name}.fear", report)}))
    if s(person.get("flaw")):
        drive.append(fill(frames["portrait_flaw"], {"name": name, "their": pro["their"], "value": clip(person["flaw"], c["flaw"], f"{name}.flaw", report)}))
    values = _list_items(person, "values", "text", c["value_item"], report)
    if values:
        drive.append(fill_lead(chars["values"]["lead_in"], "; ".join(values), {"name": name}))
    if writer:
        behaviors = [fill(frames["portrait_behavior"],
                          {"state": clip(b.get("state"), c["behavior_state"], f"{name}.behavior", report),
                           "tendency": clip(b.get("tendency"), c["behavior_tendency"], f"{name}.behavior", report)})
                     for b in (person.get("behaviors") or [])[: c["max_behaviors"]]]
        if behaviors:
            drive.append(fill_lead(chars["behaviors"]["lead_in"], "; ".join(behaviors), {"name": name}))
    put(drive)

    # texture and past
    texture = []
    for key in ("competence", "vulnerability") + (("speech",) if speaks else ()) + ("history",):
        if s(person.get(key)):
            texture.append(lead("characters", key, name=name, value=clip(person[key], c[key], f"{name}.{key}", report)))
    put(texture)
    return "\n".join(lines)


def render_cast(cast: list[dict], *, scope: str = "writer", report: Report | None = None) -> str:
    people = [render_person(p, scope=scope, report=report) for p in cast]
    note = tx.prompt_text("frames")["portraits_note"] if scope == "writer" else ""
    return "\n\n".join(x for x in [note, *people] if x)


# ---- World ----------------------------------------------------------------------------------------------------------

def groups_in_play(entanglements: dict) -> set[str]:
    """Names of the people and groups the on-stage ties mention. A group in this set is shown in full."""
    names: set[str] = set()
    for tie in entanglements.get("ties", []):
        names.update([s(tie.get("tie_from")), s(tie.get("tie_to"))])
    return {n for n in names if n}


def _uses(item: dict) -> str:
    if "uses" not in item:
        return ""
    n = int(item.get("uses") or 0)
    frames = tx.prompt_text("frames")
    return frames["uses_none"] if n == 0 else fill(frames["uses_some"], {"n": n, "s": "" if n == 1 else "s"})


def render_world(world: dict, *, scope: str = "writer", place: str | None = None, in_play: set[str] | None = None,
                 report: Report | None = None) -> str:
    """Writer: all of the World the page sent (hidden truths included), the beat's place in full, other places by name.
    Planner: every place and object with its use count, and no history or terms."""
    c = tx.limits()["world"]
    fr = tx.prompt_text("frames")
    spec = tx.schema_text("world")["fields"]
    name = clip(world.get("name"), c["name"], "world.name", report)
    writer = scope == "writer"
    paras: list[str] = []

    head = []
    if name:
        head.append(lead("world", "name", value=name))
    for key in ("era_and_technology", "everyday_life") + (("history",) if writer else ()):
        if s(world.get(key)):
            head.append(lead("world", key, name=name or "this world", value=clip(world[key], c[key], f"world.{key}", report)))
    if head:
        paras.append(" ".join(head))

    # places
    places = world.get("places") or []
    shown, others = [], []
    for p in places:
        full = (not writer) or (place and s(p.get("name")) == place)
        if not full:
            others.append(s(p.get("name")))
            continue
        line = fill(spec["places"]["item_template"], {
            "name": s(p.get("name")), "description": clip(p.get("description"), c["place_description"], "place", report),
            "effect": clip(p.get("effect"), c["place_effect"], "place", report)})
        shown.append(f"{line} {_uses(p)}".strip() if not writer else line)
    block = _items_block("world", "places", shown, name=name or "this world")
    if writer and others:
        block = (block + "\n" if block else "") + fill(fr["places_other"], {"name": name or "this world", "items": join_names(others)})
    if block:
        paras.append(block)

    # things
    things = []
    for o in world.get("objects") or []:
        line = fill(spec["objects"]["item_template"], {
            "name": s(o.get("name")), "description": clip(o.get("description"), c["object_description"], "object", report),
            "significance": clip(o.get("significance"), c["object_significance"], "object", report)})
        extras = [fill(fr["object_held"], {"held_by": o.get("held_by")}) if s(o.get("held_by")) else ""]
        if not writer:
            extras.append(_uses(o))
        things.append(" ".join(x for x in [line, *extras] if x))
    block = _items_block("world", "objects", things, name=name or "this world")
    if block:
        paras.append(block)

    # groups
    powers = []
    for g in world.get("powers") or []:
        gname = s(g.get("name"))
        tokens = {"name": gname, "nature": clip(g.get("nature"), c["power_nature"], "power", report),
                  "hold": soften(clip(g.get("hold"), c["power_hold"], "power", report)),
                  "felt": soften(clip(g.get("felt"), c["power_felt"], "power", report))}
        if writer and in_play is not None and gname not in in_play:
            powers.append(fill(fr["power_felt_only"], tokens))       # the felt line always; the rest only when in play
        else:
            powers.append(fill(spec["powers"]["item_template"], tokens))
    block = _items_block("world", "powers", powers, name=name or "this world")
    if block:
        paras.append(block)

    # rules
    rules = []
    for r in world.get("rules") or []:
        rules.append(fill(spec["rules"]["item_template"], {
            "statement": clip(r.get("statement"), c["rule_statement"], "rule", report).rstrip("."),
            "cost": clip(r.get("cost"), c["rule_cost"], "rule", report),
            "when_broken": clip(r.get("when_broken"), c["rule_when_broken"], "rule", report)}))
    block = _items_block("world", "rules", rules, name=name or "this world")
    if block:
        paras.append(block)

    if writer:
        terms = [fill(spec["terms"]["item_template"], {"term": s(t.get("term")), "meaning": clip(t.get("meaning"), c["term_meaning"], "term", report)})
                 for t in world.get("terms") or []]
        block = _items_block("world", "terms", ["; ".join(terms)] if terms else [], name=name or "this world")
        if block:
            paras.append(block)
    return "\n\n".join(paras)


# ---- Entanglements --------------------------------------------------------------------------------------------------

def render_entanglements(ent: dict, cast_names: Iterable[str] = (), *, scope: str = "writer",
                         report: Report | None = None) -> str:
    """Ties and holdings. Writer: anyone or any group not on stage is marked offstage (a name only). Planner: no marks."""
    c = tx.limits()["entanglements"]
    fr = tx.prompt_text("frames")
    spec = tx.schema_text("entanglements")["fields"]
    cast = {s(n) for n in cast_names}
    writer = scope == "writer"
    marked = [False]

    def who(name: str) -> str:
        name = s(name)
        if writer and name and name not in cast:
            marked[0] = True
            return f"{name} {fr['offstage_marker']}"
        return name

    paras = []
    ties = [fill(spec["ties"]["item_template"], {
        "tie_from": who(t.get("tie_from")), "tie_to": who(t.get("tie_to")),
        "bond": clip(t.get("bond"), c["bond"], "tie.bond", report), "edge": soften(clip(t.get("edge"), c["edge"], "tie.edge", report))})
        for t in ent.get("ties") or []]
    block = _items_block("entanglements", "ties", ties)
    if block:
        paras.append(block)

    holdings = [sentence(fill(spec["holdings"]["item_template"], {"held_by": who(h.get("held_by")), "holdee": s(h.get("holdee"))}))
                for h in ent.get("holdings") or []]
    block = _items_block("entanglements", "holdings", holdings)
    if block:
        paras.append(block)

    if marked[0]:
        paras.insert(0, fr["offstage_note"])
    return "\n\n".join(paras)


# ---- Setup, the story so far ------------------------------------------------------------------------------

def render_setup(setup: dict, chapter: int, chapter_count: int | None, *, protagonist_name: str | None = None,
                 report: Report | None = None) -> str:
    """Who the story follows, the opening (chapter 1 only: the normal and what broke it) and where this chapter sits in the
    story. The Setup card holds the protagonist as an id; pass `protagonist_name` so the model reads the name."""
    c = tx.limits()["setup"]
    fr = tx.prompt_text("frames")
    lines = []
    who = s(protagonist_name) or s(setup.get("protagonist"))
    if who:
        lines.append(lead("setup", "protagonist", value=who))
    if chapter == 1:
        if s(setup.get("normal")):
            lines.append(fr["chapter_one_normal"].format(value=clip(setup["normal"], c["normal"], "setup.normal", report)))
        if s(setup.get("disruption")):
            lines.append(fr["chapter_one_break"].format(value=clip(setup["disruption"], c["disruption"], "setup.disruption", report)))
    total = int(chapter_count or 0)
    lines.append(fr["chapter_of"].format(n=chapter, total=total) if total else fr["chapter_of_unknown"].format(n=chapter))
    if total and chapter >= total:
        lines.append(fr["chapter_last"])
    return "\n".join(lines)


def _first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", s(text))
    return m.group(1) if m else s(text)


def _history(events: list[dict], chapter: int, keep_full: int, lead_in: str, report: Report | None) -> str:
    c = tx.limits()["events"]
    fr = tx.prompt_text("frames")
    rows = sorted((e for e in events or [] if 0 < int(e.get("chapter") or 0) < chapter), key=lambda e: int(e["chapter"]))
    if not rows:
        return ""
    recent = rows[-keep_full:] if keep_full else rows
    older = rows[: len(rows) - len(recent)]
    out = [lead_in]
    if older:
        out.append(fr["story_older_lead"])
        for e in older:
            text = clip(e.get("changed") or _first_sentence(e.get("happened")), c["changed"], f"events.{e['chapter']}", report)
            out.append(fr["story_older"].format(chapter=e["chapter"], text=sentence(text)))
    for e in recent:
        para = fr["story_chapter"].format(chapter=e["chapter"], happened=clip(e.get("happened"), c["happened"], f"events.{e['chapter']}", report))
        if s(e.get("changed")):
            para += " " + fr["story_changed"].format(changed=sentence(clip(e["changed"], c["changed"], f"events.{e['chapter']}.changed", report)))
        out.append(para)
    return "\n".join(out)


def render_story_so_far(events: list[dict], chapter: int, *, keep_full: int, report: Report | None = None) -> str:
    """Earlier chapters as short plain paragraphs. The latest `keep_full` are told in full; older ones shrink to their
    'changed' line (or the first sentence of what happened)."""
    return _history(events, chapter, keep_full, tx.prompt_text("frames")["story_lead"], report)


def render_history(events: list[dict], chapter: int, *, scope: str, keep_full: int, report: Report | None = None) -> str:
    """What happened and what changed in the chapters before `chapter`, in prose. The requests carry no separate shift list
    (the cards the page sends already include the shifts), so this record is the whole history. The writer is told the story so far;
    the planner is told what each chapter changed, since a plan moves forward from there."""
    _check_scope(scope)
    return _history(events, chapter, keep_full, tx.prompt_text("frames")[f"history_lead_{scope}"], report)


def render_earlier_beats(beats: list[dict]) -> str:
    fr = tx.prompt_text("frames")
    rows = [fr["planner_beat_item"].format(chapter=b.get("chapter"), where=s(b.get("where")), when=s(b.get("when_time")))
            for b in sorted(beats or [], key=lambda b: int(b.get("chapter") or 0))]
    if not rows:
        return ""
    return fr["planner_beats_lead"] + "\n" + "\n".join(rows)


# ---- The spotlight tie, the scene, a recorded change ----------------------------------------------------------------

def _check_scope(scope: str) -> None:
    if scope not in ("writer", "planner"):
        raise ValueError(f"scope must be 'writer' or 'planner', not {scope!r}")


def _brief(person: dict, *, with_sketch: bool, report: Report | None) -> str:
    """Who a person is and what drives them, in a few sentences of prose."""
    c = tx.limits()["characters"]
    fr = tx.prompt_text("frames")
    chars = tx.schema_text("characters")["fields"]
    name = s(person.get("name"))
    pro = PRONOUNS.get(s(person.get("sex")), PRONOUNS["other"])
    parts = []
    if with_sketch and s(person.get("sketch")):
        parts.append(fill(fr["sketch"], {"name": name, "value": clip(person["sketch"], c["sketch"], f"{name}.sketch", report)}))
    wants = _list_items(person, "wants", "text", c["want_item"], report)
    if wants:
        parts.append(fill_lead(chars["wants"]["lead_in"], "; ".join(wants), {"name": name}))
    if s(person.get("fear")):
        parts.append(fill(fr["portrait_fear"], {"name": name, "themselves": pro["themselves"], "value": clip(person["fear"], c["fear"], f"{name}.fear", report)}))
    if s(person.get("flaw")):
        parts.append(fill(fr["portrait_flaw"], {"name": name, "their": pro["their"], "value": clip(person["flaw"], c["flaw"], f"{name}.flaw", report)}))
    return tidy(" ".join(sentence(p) for p in parts))


def render_spotlight(tie: dict, cast: list[dict], *, scope: str, report: Report | None = None,
                     names: dict[str, str] | None = None) -> str:
    """The spotlight tie in prose: who stands toward whom, the bond, and the edge as what drives the person at the `from` end,
    then a short brief of each end that is in the cast. The ends are names (a tie from the page is turned into words first; or pass
    `names`, an id-to-name map, and any end given as an id is read through it). Planner briefs add each person's sketch; the writer
    has the full portraits already."""
    _check_scope(scope)
    c = tx.limits()["entanglements"]
    fr = tx.prompt_text("frames")
    names = names or {}
    cast_by_key = {}
    for person in cast or []:
        for key in (s(person.get("name")), s(person.get("id"))):
            if key:
                cast_by_key[key] = person

    def end(value) -> tuple[str, dict | None]:
        value = s(value)
        person = cast_by_key.get(value)
        shown = names.get(value) or (s(person.get("name")) if person else "") or value
        return shown, person

    tie_from, from_person = end(tie.get("tie_from"))
    tie_to, to_person = end(tie.get("tie_to"))
    bond = sentence(clip(tie.get("bond"), c["bond"], "tie.bond", report))
    edge = sentence(clip(tie.get("edge"), c["edge"], "tie.edge", report))
    tokens = {"tie_from": tie_from, "tie_to": tie_to, "bond": bond, "edge": edge}
    lines = [fill(fr["spotlight_tie"] if bond else fr["spotlight_tie_bare"], tokens)]
    if edge:
        lines[0] += " " + fill(fr["spotlight_drive"], tokens)
    briefs = []
    for person in (from_person, to_person):
        if person is not None and person not in [b[0] for b in briefs]:
            text = _brief(person, with_sketch=scope == "planner", report=report)
            if text:
                briefs.append((person, text))
    if briefs:
        lines.append(fr["spotlight_brief_lead"])
        lines.extend(text for _, text in briefs)
    return "\n".join(lines)


def _names_of(people) -> list[str]:
    out = []
    for p in people or []:
        out.append(s(p.get("name")) if isinstance(p, dict) else s(p))
    return [n for n in out if n]


def render_scene(beat: dict, *, scope: str, report: Report | None = None) -> str:
    """A beat in prose: the place, the time, who is on stage by name, the spotlight tie, the aim and the plan. Names, never ids:
    `cast` is a list of names (or of cards with a name) and `spotlight` is a sentence or a tie whose ends are names. The cast are the
    only people on stage; anyone else is a role. Writer: also told to begin mid-scene and to tell the plan as a living scene."""
    _check_scope(scope)
    c = tx.limits()["scene"]
    e = tx.limits()["entanglements"]
    fr = tx.prompt_text("frames")
    spot = beat.get("spotlight")
    if isinstance(spot, dict):
        spot = fill(fr["scene_spotlight_line"], {"tie_from": s(spot.get("tie_from")), "tie_to": s(spot.get("tie_to")),
                                                  "bond": clip(spot.get("bond"), e["bond"], "tie.bond", report)})
    cast = _names_of(beat.get("cast"))
    tokens = {
        "where": clip(beat.get("where"), c["where"], "beat.where", report),
        "when_time": clip(beat.get("when_time"), c["when_time"], "beat.when_time", report),
        "cast": join_names(cast),
        "spotlight": sentence(s(spot)),
        "aim": sentence(clip(beat.get("aim"), c["aim"], "beat.aim", report)),
        "plan": sentence(clip(beat.get("plan"), c["plan"], "beat.plan", report)),
    }
    parts = [fill(tx.field("outline", "beats")["item_template"], tokens, drop_first=True)]
    if cast:
        parts.append(fr["scene_minor_roles"])
    if scope == "writer":
        parts.append(fr["scene_writer_note"])
    return "\n".join(p for p in parts if p)


def _humanize(key: str) -> str:
    return s(key).replace("_", " ")


def _value_words(card: str, field: str, item_key: str | None, value: Any, names: dict) -> str:
    """One value of a patch as words: a list joined, an option turned into its explanatory sentence, an id turned into a name."""
    if isinstance(value, (list, tuple)):
        return ", ".join(x for x in (_value_words(card, field, item_key, v, names) for v in value) if x)
    text = s(value)
    spec = tx.schema_text(card)["fields"].get(field, {})
    if item_key:
        spec = spec.get("item_fields", {}).get(item_key, {})
    options = spec.get("options") or {}
    if text in options:
        return s(options[text].get("expand")) or text
    return s(names.get(text, text))


def render_shift(entry: dict, handles_or_names: dict[str, str] | None = None) -> str:
    """One shift entry (chapter, card, target, patch) as a sentence or two, per the template in shifts.yaml. `handles_or_names` maps
    ids to names, for the character and for items a list operation points at. A standalone helper: nothing calls it yet, because the
    requests carry the effective cards, with the shifts already folded in."""
    names = handles_or_names or {}
    card = s(entry.get("card"))
    fields_spec = tx.field("shifts", "entries")["item_fields"]
    fr = tx.prompt_text("frames")
    pieces = []
    for key, value in (entry.get("patch") or {}).items():
        field = _humanize(key)
        if isinstance(value, list) and all(isinstance(op, dict) and "op" in op for op in value):
            for op in value:
                values = "; ".join(x for x in (_value_words(card, key, k, v, names) for k, v in (op.get("values") or {}).items()) if x)
                old = s(names.get(s(op.get("id")))) or fr["shift_unknown_item"]
                frame = {"add": "shift_add", "replace": "shift_replace", "remove": "shift_remove"}[op["op"]]
                pieces.append(sentence(fill(fr[frame], {"field": field, "values": values, "old": old}, drop_first=True) or field))
        else:
            pieces.append(sentence(fill(fr["shift_set"], {"field": field, "value": _value_words(card, key, None, value, names)}, drop_first=True)))
    target = s(entry.get("target"))
    tokens = {"beat": s(entry.get("beat", entry.get("chapter"))),
              "card": fields_spec["card"]["options"][card]["expand"] if card in fields_spec["card"]["options"] else card,
              "target": s(names.get(target, target)), "patch": " ".join(pieces)}
    return re.sub(r"\s+", " ", tidy(fill(tx.field("shifts", "entries")["item_template"], tokens))).strip()


# ---- Short forms and id-to-name helpers --------------------------------------------------------------

def render_person_brief(person: dict, *, report: Report | None = None) -> str:
    """One short paragraph: who, and what drives them."""
    c = tx.limits()["characters"]
    name = s(person.get("name"))
    she = {"female": "she/her", "male": "he/him"}.get(s(person.get("sex")), "they/them")
    wants = [clip(w.get("text"), c["want_item"], f"{name}.wants", report) for w in person.get("wants") or []]
    parts = [f"{name} ({she})."]
    if wants:
        parts.append("Wants: " + "; ".join(wants) + ".")
    for key, label in (("fear", "Fear"), ("flaw", "Flaw")):
        if s(person.get(key)):
            parts.append(f"{label}: {sentence(clip(person[key], c[key], f'{name}.{key}', report))}")
    return " ".join(parts)


def names_by_id(related: dict) -> dict[str, str]:
    """Id to name for everything a card can link to, from the cards a fill or judge request carries."""
    world = related.get("world") or {}
    characters = related.get("characters") or []
    if isinstance(characters, dict):
        characters = [characters]
    out = {c["id"]: s(c.get("name")) for c in characters if c.get("id")}
    for key, label in (("places", "name"), ("objects", "name"), ("powers", "name"), ("rules", "statement")):
        out.update({i["id"]: s(i.get(label)) for i in world.get(key) or [] if i.get("id")})
    return out


def in_words(items: list[dict], extras: dict[str, dict], names: dict[str, str]) -> list[dict]:
    """Items whose link fields hold ids, with each id turned into the name it stands for."""
    out = []
    for item in items or []:
        row = dict(item)
        for key, spec in extras.items():
            if spec.get("ref") and key in row:
                value = row[key]
                row[key] = [names.get(v, v) for v in value] if isinstance(value, list) else names.get(value, value) if value else value
        out.append(row)
    return out
