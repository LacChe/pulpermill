"""Card renderers: one function per card or record, returning prose. Names, never ids. A fixed order (the schema's
RENDER_ORDER where it has one), a length cap per field (limits.yaml), and any clause whose value is empty is left out
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


def fill(template: str, tokens: dict[str, Any]) -> str:
    """Fills {tokens}. The template is read as clauses; a clause after the first that holds an empty token is dropped,
    so an empty box leaves no label behind."""
    kept = []
    for i, part in enumerate(_SEGMENT.split(template)):
        names = _TOKEN.findall(part)
        if i > 0 and any(not s(tokens.get(n)) for n in names):
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
    """Names of the people and groups the on-stage ties and pressures mention. A group in this set is shown in full."""
    names: set[str] = set()
    for tie in entanglements.get("ties", []):
        names.update([s(tie.get("tie_from")), s(tie.get("tie_to"))])
    for p in entanglements.get("pressures", []):
        names.add(s(p.get("source_agent")))
        names.update(s(b) for b in p.get("bears_on") or [])
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

    # rules: common, then hidden, then myth
    rank = {"common": 0, "uncommon": 1, "false_belief": 2}
    rules = []
    for r in sorted(world.get("rules") or [], key=lambda r: rank.get(r.get("status"), 0)):
        status = s(r.get("status"))
        expand = tx.option_expand("world", "rules", status, "status") if status in rank else ""
        rules.append(fill(spec["rules"]["item_template"], {
            "statement": clip(r.get("statement"), c["rule_statement"], "rule", report).rstrip("."),
            "status": fill(expand, {"truth": soften(clip(r.get("truth"), c["rule_truth"], "rule.truth", report)).rstrip(".")}),
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
    """Ties, holdings, knowledge, pressures. Writer: anyone or any group not on stage is marked offstage (a name only).
    Planner: all pressures, no marks."""
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

    status_opts = spec["knowledge"]["item_fields"]["status"]["options"]
    knowledge = []
    for k in ent.get("knowledge") or []:
        status = s(k.get("status"))
        if status not in status_opts:
            continue
        thing = clip(k.get("rule") or k.get("fact"), c["fact"], "knowledge", report)
        line = fill(fr["knowledge_item"], {"person": s(k.get("person")), "status": status_opts[status]["expand"], "thing": thing})
        if status == "misled" and s(k.get("belief")):
            line = sentence(line) + " " + fill(fr["knowledge_belief"], {"person": s(k.get("person")), "belief": sentence(clip(k.get("belief"), c["fact"], "knowledge", report))})
        knowledge.append(line)
    block = _items_block("entanglements", "knowledge", knowledge)
    if block:
        paras.append((fr["knowledge_note"] + "\n" if writer else "") + block)

    pressures = []
    for p in ent.get("pressures") or []:
        pressures.append(fill(spec["pressures"]["item_template"], {
            "what": clip(p.get("what"), c["pressure_what"], "pressure", report).rstrip("."),
            "source_agent": who(p.get("source_agent")), "source_circumstance": s(p.get("source_circumstance")),
            "bears_on": ", ".join(who(b) for b in p.get("bears_on") or []),
            "next_move": clip(p.get("next_move"), c["next_move"], "pressure.next_move", report)}))
    block = _items_block("entanglements", "pressures", pressures)
    if block:
        paras.append(block)

    if marked[0]:
        paras.insert(0, fr["offstage_note"])
    return "\n\n".join(paras)


# ---- Setup, standing, the story so far ------------------------------------------------------------------------------

def render_setup(setup: dict, goal: str | None, chapter: int, chapter_count: int | None, *, report: Report | None = None,
                 goal_state: str | None = None) -> str:
    c = tx.limits()["setup"]
    fr = tx.prompt_text("frames")
    lines = []
    if s(setup.get("protagonist")):
        lines.append(lead("setup", "protagonist", value=s(setup["protagonist"])))
    if chapter == 1:
        if s(setup.get("normal")):
            lines.append(fr["chapter_one_normal"].format(value=clip(setup["normal"], c["normal"], "setup.normal", report)))
        if s(setup.get("disruption")):
            lines.append(fr["chapter_one_break"].format(value=clip(setup["disruption"], c["disruption"], "setup.disruption", report)))
    if s(goal):
        lines.append(lead("setup", "goal", value=clip(goal, c["goal"], "goal", report)))
    else:
        lines.append(fr["goal_between"] if goal_state == "needs_goal" else fr["goal_ended"])
    if s(setup.get("stakes")):
        lines.append(lead("setup", "stakes", value=clip(setup["stakes"], c["stakes"], "setup.stakes", report)))
    total = int(chapter_count or 0)
    lines.append(fr["chapter_of"].format(n=chapter, total=total) if total else fr["chapter_of_unknown"].format(n=chapter))
    if total and chapter >= total:
        lines.append(fr["chapter_last"])
    return "\n".join(lines)


def render_standing(standing: list[dict], report: Report | None = None) -> str:
    fr = tx.prompt_text("frames")
    cap = tx.limits()["standing"]["field"]
    rows = []
    for row in standing or []:
        parts = [fill(tmpl, {"value": clip(row.get(key), cap, f"standing.{s(row.get('character'))}.{key}", report).rstrip(".")}) for key, tmpl in fr["standing_parts"].items() if s(row.get(key))]
        if parts:
            rows.append(f"{s(row.get('character'))} " + "; ".join(parts) + ".")
    return fr["standing_lead"] + "\n" + "\n".join(rows) if rows else ""


def _first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", s(text))
    return m.group(1) if m else s(text)


def render_story_so_far(events: list[dict], chapter: int, *, keep_full: int, report: Report | None = None) -> str:
    """Earlier chapters as short plain paragraphs. The latest `keep_full` are told in full; older ones shrink to their
    'changed' line (or the first sentence of what happened)."""
    c = tx.limits()["events"]
    fr = tx.prompt_text("frames")
    rows = sorted((e for e in events or [] if int(e.get("chapter") or 0) < chapter), key=lambda e: e["chapter"])
    if not rows:
        return ""
    recent = rows[-keep_full:] if keep_full else rows
    older = rows[: len(rows) - len(recent)]
    out = [fr["story_lead"]]
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


def render_earlier_beats(beats: list[dict]) -> str:
    fr = tx.prompt_text("frames")
    rows = [fr["planner_beat_item"].format(chapter=b.get("chapter"), where=s(b.get("where")), when=s(b.get("when_time")),
                                           turn=sentence(s(b.get("turn"))), shift=s(b.get("shift")))
            for b in sorted(beats or [], key=lambda b: int(b.get("chapter") or 0))]
    return fr["planner_beats_lead"] + "\n" + "\n".join(rows) if rows else ""


# ---- The scene ------------------------------------------------------------------------------------------------------

def render_scene(beat: dict, *, protagonist: str, sex: str = "other", open_plants: list[dict] | None = None,
                 available_reveals: list[dict] | None = None, report: Report | None = None) -> str:
    """The beat as one situation: where it opens, what is wanted and what blocks it, the choice, what changes, where it
    stops, then whatever the beat names (reveal, plant, payoff, offstage move, goal change, spotlight). Empty parts leave
    nothing behind. The writer's own wording is quoted, never recased, because it may begin with a name."""
    fr = tx.prompt_text("frames")
    b = tx.limits()["beat"]["field"]
    them = PRONOUNS.get(sex, PRONOUNS["other"])["them"]
    cut = lambda key: clip(beat.get(key), b, f"beat.{key}", report)
    paras = []

    where = s(beat.get("where"))
    opening = []
    if where or s(beat.get("when_time")):
        opening.append(fr["scene_open"].format(where=where or "the place the story left off",
                                               when=s(beat.get("when_time")) or "with the scene already moving"))
    if s(beat.get("when_gap")):
        opening.append(fr["scene_gap"].format(gap=sentence(s(beat["when_gap"])).rstrip(".")))
    names = [n for n in beat.get("cast") or [] if s(n)]
    if names:
        opening.append(fr["scene_present"].format(names=join_names(names), be="is" if len(names) == 1 else "are"))
    if opening:
        paras.append(" ".join(opening))

    engine = []
    if cut("collision_goal"):
        engine.append(fr["scene_goal"].format(name=protagonist, value=sentence(cut("collision_goal"))))
    if cut("collision_block"):
        engine.append(fr["scene_block"].format(value=sentence(cut("collision_block"))))
    if cut("choice_a") and cut("choice_b"):
        engine.append(fr["scene_choice"].format(name=protagonist, them=them))
        engine.append(fr["scene_choice_a"].format(value=sentence(cut("choice_a"))))
        engine.append(fr["scene_choice_b"].format(value=sentence(cut("choice_b"))))
    if engine:
        paras.append("\n".join(engine))

    change = []
    if cut("turn"):
        change.append(fr["scene_turn"].format(value=sentence(cut("turn"))))
    if s(beat.get("shift")) in fr["scene_shift"]:
        change.append(fr["scene_shift"][beat["shift"]])
    if change:
        paras.append(" ".join(change))

    if cut("ends_on"):
        paras.append(fr["scene_end"].format(value=sentence(cut("ends_on"))) + "\n" + fr["scene_end_hold"])

    if s(beat.get("reveal_rule")):
        statement = sentence(s(beat["reveal_rule"]))
        match = next((r for r in available_reveals or [] if s(r.get("statement")) == s(beat["reveal_rule"])), {})
        truth = sentence(s(match.get("truth")))
        learners = join_names(beat.get("reveal_learners") or []) or "someone on stage"
        myth = s(match.get("status")) == "false_belief" and truth
        paras.append(fr["scene_reveal_myth" if myth else "scene_reveal_hidden"].format(statement=statement, truth=truth, learners=learners))
    if cut("plant"):
        paras.append(fr["scene_plant"].format(value=sentence(cut("plant"))))
    if beat.get("payoff"):
        known = {s(p.get("text")): p.get("chapter") for p in open_plants or []}
        items = [fr["scene_payoff_item"].format(text=s(t).rstrip("."), chapter=known[s(t)]) if known.get(s(t)) else s(t).rstrip(".")
                 for t in beat["payoff"]]
        paras.append(fr["scene_payoff"].format(value=join_names(items)))
    if s(beat.get("offstage_did")) and s(beat.get("offstage_reach")):
        paras.append(fr["scene_offstage"].format(did=sentence(soften(clip(beat["offstage_did"], b, "beat.offstage_did", report))),
                                                  name=protagonist, reach=sentence(clip(beat["offstage_reach"], b, "beat.offstage_reach", report))))
    change = s(beat.get("goal_change"))
    if change in fr["scene_goal_change"]:
        if change != "redefined" or s(beat.get("goal_now")):
            paras.append(fr["scene_goal_change"][change].format(goal_now=sentence(s(beat.get("goal_now")))))
    if s(beat.get("spotlight")):
        paras.append(fr["scene_spotlight"].format(value=sentence(clip(beat["spotlight"], b, "beat.spotlight", report))))
    paras.append(fr["scene_shape"])
    return "\n\n".join(paras)


# ---- What the planner is told the code has set ----------------------------------------------------------------------

def _goal_lines(req: dict, fr: dict, lim: dict, report: Report | None) -> list[str]:
    """What the goal arc says about this chapter: the story's goal, how long the goal has stood, why a new goal is needed or
    advised, the goals so far, and the directions a new goal could take. All of it comes from the page."""
    plan = req.get("goal_plan") or {}
    cap = lim["setup"]["goal"]
    lines = []
    if s(req.get("story_goal")):
        lines.append(fr["code_story_goal"].format(value=sentence(clip(req["story_goal"], cap, "story_goal", report))))
    end = plan.get("last_end") or {}
    if s(plan.get("state")) == "needs_goal" and s(end.get("kind")) in fr["code_goal_set"]:
        lines.append(fr["code_goal_set"][s(end["kind"])].format(goal=sentence(clip(end.get("goal"), cap, "last_goal", report))))
    elif s(req.get("goal")) and int(plan.get("age") or 0) >= 1:
        lines.append(fr["code_goal_age"].format(age=int(plan["age"]), since=int(plan.get("since") or 1)))
    due = s(plan.get("due"))
    if due in fr["code_goal_due"]:
        lines.append(fr["code_goal_due"][due])
    earlier = [clip(g, cap, "earlier_goal", report).rstrip(".") for g in plan.get("earlier_goals") or [] if s(g)]
    if earlier and (due or s(plan.get("state")) == "needs_goal"):
        lines.append(fr["code_goals_so_far"].format(items="; ".join(earlier)))
    directions = [s(d.get("text")) for d in plan.get("directions") or [] if s(d.get("text"))]
    if directions:
        lines.append(fr["code_directions"] + "\n" + "\n".join(fr["code_direction_item"].format(text=sentence(clip(d, cap * 2, "direction", report))) for d in directions))
    return lines


def render_code_numbers(req: dict, *, report: Report | None = None) -> str:
    fr = tx.prompt_text("frames")
    lim = tx.limits()
    lines = _goal_lines(req, fr, lim, report)
    spot = req.get("spotlight") or {}
    if s(spot.get("what")):
        lines.append(fr["code_spotlight"].format(value=sentence(clip(spot["what"], lim["entanglements"]["pressure_what"], "spotlight", report))))
    shifts = req.get("legal_shifts") or []
    lines.append(fr["code_shifts"].format(value=" or ".join(shifts)) if shifts and len(shifts) < 2 else fr["code_no_shifts"])
    plants = req.get("open_plants") or []
    if plants:
        lines.append(fr["code_plants"] + "\n" + "\n".join(fr["code_plant_item"].format(text=clip(p.get("text"), lim["code"]["plant"], "plant", report).rstrip("."), chapter=p.get("chapter")) for p in plants))
    else:
        lines.append(fr["code_no_plants"])
    reveals = req.get("available_reveals") or []
    if reveals:
        w = lim["world"]
        rows = [fr["code_reveal_item_myth"].format(statement=sentence(clip(r.get("statement"), w["rule_statement"], "reveal", report)),
                                                   truth=sentence(clip(r.get("truth"), w["rule_truth"], "reveal", report)))
                if s(r.get("status")) == "false_belief" and s(r.get("truth")) else
                fr["code_reveal_item"].format(statement=sentence(clip(r.get("statement"), w["rule_statement"], "reveal", report)))
                for r in reveals]
        lines.append(fr["code_reveals"] + "\n" + "\n".join(rows))
    else:
        lines.append(fr["code_no_reveals"])
    seen = (req.get("use_counts") or {}).get("characters") or []
    if seen:
        items = [fr["code_cast_item_last"].format(name=c["name"], last=c["last"]) if c.get("last") else fr["code_cast_item_never"].format(name=c["name"])
                 for c in seen]
        lines.append(fr["code_cast_seen"].format(items="; ".join(items)))
    return "\n".join(lines)


# ---- Short forms for the extractors and the card calls --------------------------------------------------------------

def render_person_brief(person: dict, *, report: Report | None = None) -> str:
    """One short paragraph: who, and what drives them. For the Shifts extractor, which compares the chapter with where a
    person started."""
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


def render_handles(entanglements: dict, handles: dict[str, dict], cast_names: Iterable[str], *,
                   report: Report | None = None) -> str:
    """The live entanglements, each item behind its handle (T1, H1, K1, P1), grouped by what may change."""
    c = tx.limits()["entanglements"]
    fr = tx.prompt_text("frames")
    heads = tx.template("shifts")["may_change"]
    cast = {s(n) for n in cast_names}

    def who(name: str) -> str:
        name = s(name)
        return f"{name} {fr['offstage_marker']}" if name and name not in cast else name

    by_section: dict[str, list[str]] = {}
    index = {(i["section"], i["id"]): h for h, i in handles.items()}
    for section in ("ties", "holdings", "knowledge", "pressures"):
        for item in entanglements.get(section) or []:
            handle = index.get((section, item.get("id")))
            if not handle:
                continue
            if section == "ties":
                line = (f"{handle}. {who(item.get('tie_from'))} toward {who(item.get('tie_to'))}. Bond: {sentence(clip(item.get('bond'), c['bond'], 'tie', report))} "
                        f"Edge: {sentence(clip(item.get('edge'), c['edge'], 'tie', report))}")
            elif section == "holdings":
                line = f"{handle}. {s(item.get('holdee'))} is held by {who(item.get('held_by'))}."
            elif section == "knowledge":
                status = tx.schema_text("entanglements")["fields"]["knowledge"]["item_fields"]["status"]["options"].get(s(item.get("status")), {}).get("expand", s(item.get("status")))
                line = f"{handle}. {s(item.get('person'))} {status}: {sentence(clip(item.get('rule') or item.get('fact'), c['fact'], 'knowledge', report))}"
                if s(item.get("status")) == "misled" and s(item.get("belief")):
                    line += f" They believe instead: {sentence(clip(item.get('belief'), c['fact'], 'knowledge', report))}"
            else:
                bears = ", ".join(who(b) for b in item.get("bears_on") or [])
                source = who(item.get("source_agent")) or s(item.get("source_circumstance"))
                line = f"{handle}. {clip(item.get('what'), c['pressure_what'], 'pressure', report).rstrip('.')} (from {source}; bears on {bears})."
                if s(item.get("next_move")):
                    line += f" Next move: {sentence(clip(item['next_move'], c['next_move'], 'pressure', report))}"
            by_section.setdefault(section, []).append(line)
    return "\n\n".join(heads[sec] + ":\n" + "\n".join(lines) for sec, lines in by_section.items())


def render_shifts_history(shifts: list[dict], *, report: Report | None = None) -> str:
    """How people changed, chapter by chapter, for the end-of-story update."""
    fr = tx.prompt_text("frames")
    rows = []
    for row in sorted(shifts or [], key=lambda r: int(r.get("chapter") or 0)):
        parts = [fill(tmpl, {"value": s(row.get(key)).rstrip(".")}) for key, tmpl in fr["standing_parts"].items() if s(row.get(key))]
        if parts:
            rows.append(tx.template("end_story")["shift_line"].format(chapter=row.get("chapter"), character=s(row.get("character")), parts="; ".join(parts)) + ".")
    return "\n".join(rows)


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
