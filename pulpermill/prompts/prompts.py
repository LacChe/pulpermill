"""The prompts: one builder per call. Each returns a Prompt (the text for one user turn, the version tag of the template it came
from, and the JSON shape of the reply when the reply is structured). The material is rendered by blocks.py and render.py;
the craft text, the task and the reminder come from templates/en/*.yaml.

Gemma has no system role, so everything is one user turn: rules and material first, the task for this call last, a short
reminder at the very end of the writer's prompt."""
import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..schema import CARDS
from . import schemas, textfiles as tx
from .blocks import assemble, planner_blocks, writer_blocks
from .render import (Report, in_words, join_names, names_by_id, render_cast, render_entanglements, render_handles,
                     render_person, render_person_brief, render_setup, render_shifts_history, render_standing, render_story_so_far,
                     render_style, render_world, s, sentence)


@dataclass(frozen=True)
class Prompt:
    name: str                                   # which call: writer, planner_think, events, ...
    version: str                                # the template's version tag, recorded with every result
    text: str                                   # the one user turn
    schema: dict | None = None                  # the reply's JSON shape; None means free text
    stage: str | None = None                    # what `status` says while it runs
    meta: dict = field(default_factory=dict)    # handles, section numbers: what the caller needs to read the reply

    def messages(self) -> list[dict]:
        return [{"role": "user", "content": self.text}]


def _t(name: str) -> dict:
    return tx.template(name)


def _join(*parts: str) -> str:
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def language_name(code: str) -> str:
    return _t("writer")["languages"].get(code, code)


def _bullets(items: list[str], none: str) -> str:
    return "\n".join(f"- {i}" for i in items) if items else none


# ---- The chapter writer ---------------------------------------------------------------------------------------------

def writer_plan(sections: int | None = None, extra: bool = False) -> list[str]:
    """The roles of the sections, in order. Four sections of about 750 words by default, or three of about 1,000. An extra
    section goes before the last one."""
    n = sections or tx.limits()["chapter"]["sections"]
    roles = {4: ["open", "press", "choice", "close"], 3: ["open_press", "choice", "close"]}.get(n)
    if roles is None:
        raise ValueError("a chapter is written in 3 or 4 sections")
    return roles[:-1] + ["extra"] + roles[-1:] if extra else roles


def tail_words(text: str, words: int | None = None) -> str:
    """The last ~300 words of the chapter so far, starting at a paragraph or sentence so it does not open mid-clause."""
    limit = words or tx.limits()["chapter"]["tail_words"]
    tokens = re.findall(r"\S+\s*", text or "")
    if len(tokens) <= limit:
        return (text or "").strip()
    tail = "".join(tokens[-limit:])
    cut = re.search(r"\n\s*\n|(?<=[.!?])[\"”']?\s+", tail[: len(tail) // 3])
    return (tail[cut.end():] if cut else tail).strip()


def needs_extra(words_so_far: int, done: int, sections: int | None = None, target: int | None = None) -> bool:
    """True when the section about to be written is the last one and the chapter is running short of its pace."""
    lim = tx.limits()["chapter"]
    n = sections or lim["sections"]
    goal = target or lim["target_words"]
    return done == n - 1 and words_so_far < lim["short_ratio"] * goal * done / n


def _voice(style: dict, language: str) -> str:
    bits = [language_name(language)]
    for key, word in (("person", "{} person"), ("tense", "{} tense"), ("distance", "{} distance")):
        if s(style.get(key)):
            bits.append(word.format(style[key]))
    return ", ".join(bits)


def _voice_rules(style: dict) -> str:
    texts = tx.schema_text("style")["fields"]
    lines = []
    for key in ("person", "tense", "distance"):
        value = s(style.get(key))
        if value in texts[key]["options"]:
            lines.append(texts[key]["options"][value]["expand"])
    return "\n".join(lines)


def writer_prompt(req: dict, plan: list[str], index: int, written: str = "", target_words: int | None = None) -> Prompt:
    """One section of the chapter. `plan` is writer_plan(); `index` counts from 0; `written` is the chapter so far."""
    w = _t("writer")
    lim = tx.limits()["chapter"]
    role = plan[index]
    body = [r for r in plan if r != "extra"]
    words = round((target_words or lim["target_words"]) / len(body))
    beat = req.get("beat") or {}
    protagonist = s((req.get("setup") or {}).get("protagonist"))
    last = index == len(plan) - 1
    style = req.get("style") or {}
    language = req.get("language") or "en"

    plant, reveal = s(beat.get("plant")).rstrip("."), s(beat.get("reveal_rule"))
    payoff = join_names([s(p).rstrip(".") for p in beat.get("payoff") or []])
    tokens = {
        "where": s(beat.get("where")) or "the place the last chapter left off", "protagonist": protagonist, "words": words,
        "plant_hint": w["hints"]["plant"].format(plant=plant) if plant else "",
        "reveal_hint": w["hints"]["reveal"] if reveal else "",
        "payoff_hint": w["hints"]["payoff"].format(payoff=payoff) if payoff else "",
        "late_hint": w["hints"]["late"] if (plant or reveal or payoff) else "",
    }
    if role == "extra":
        job = w["extra"].format(**tokens)
    else:
        job = w["job"].format(k=index + 1, n=len(plan), words=words, job=w["jobs"][role].format(**tokens),
                              tail=w["tail_last"] if last else w["tail_middle"])
    so_far = _join(w["so_far_lead"] + "\n" + tail_words(written), w["so_far_tail"]) if written.strip() else ""
    reminder = w["reminder"].format(
        voice=_voice(style, language), fresh=w["fresh"] if written.strip() else "",
        ending_line=w["ending_last"] if last else w["ending_middle"])
    top = _join(w["rules"].format(language_line=f"Write in {language_name(language)}.", voice_rules=_voice_rules(style)), w["craft"])
    text = _join(top, assemble(writer_blocks(req)), so_far, job, reminder)
    return Prompt("writer", w["version"], text, None, "write", {"section": index + 1, "of": len(plan), "role": role, "words": words})


# ---- The planner ----------------------------------------------------------------------------------------------------

def _arc(chapter: int, total: int) -> str:
    arcs = _t("planner")["arc"]
    if not total:
        return ""
    if chapter >= total:
        return arcs["last"]
    return arcs["early"] if chapter <= total / 3 else arcs["late"] if chapter > 2 * total / 3 else arcs["middle"]


def _retry_block(req: dict) -> str:
    retry = req.get("retry")
    if not retry:
        return ""
    beat = "\n".join(f"{k}: {s(v)}" for k, v in (retry.get("beat") or {}).items() if s(v))
    return _t("planner")["retry"].format(problems="\n".join(f"- {p}" for p in retry.get("problems") or []),
                                         thinking=s(retry.get("thinking")), beat=beat)


def _planner_material(req: dict) -> str:
    p = _t("planner")
    extras = [p["use_of_numbers"], _arc(int(req.get("chapter") or 1), int(req.get("chapter_count") or 0))]
    if not s(req.get("goal")):
        extras.append(p["goal_ended"])
    return _join(p["job"], assemble(planner_blocks(req)), _retry_block(req), *extras)


def planner_think_prompt(req: dict) -> Prompt:
    p = _t("planner")
    return Prompt("planner_think", p["version"], _join(_planner_material(req), p["think_steps"]), None,
                  "retry" if req.get("retry") else "think")


def planner_beat_prompt(req: dict, thinking: str) -> Prompt:
    p = _t("planner")
    text = _join(_planner_material(req), p["your_plan_lead"] + "\n" + s(thinking), p["beat_guide"])
    return Prompt("planner_beat", p["version"], text, schemas.beat_schema(req), "beat")


# ---- The extractors -------------------------------------------------------------------------------------------------

def _planned(beat: dict, ev: dict) -> str:
    lines = []
    if s(beat.get("reveal_rule")):
        lines.append(ev["planned_reveal"].format(statement=sentence(s(beat["reveal_rule"]))))
    if s(beat.get("plant")):
        lines.append(ev["planned_plant"].format(plant=sentence(s(beat["plant"]))))
    if beat.get("payoff"):
        lines.append(ev["planned_payoff"].format(payoff=join_names([s(p).rstrip(".") for p in beat["payoff"]]) + "."))
    change = s(beat.get("goal_change"))
    if change:
        lines.append(ev["planned_goal"].format(change=change + (": " + s(beat.get("goal_now")) if s(beat.get("goal_now")) else "")))
    return ev["planned_lead"] + "\n" + ("\n".join(lines) if lines else ev["planned_none"])


def events_prompt(req: dict, chapter_text: str) -> Prompt:
    ev = _t("events")
    none = ev["list_none"]
    lists = _join(
        ev["lists_lead"],
        ev["list_plants"] + "\n" + _bullets(schemas.names_of(req.get("open_plants"), "text"), none),
        ev["list_reveals"] + "\n" + _bullets(schemas.names_of(req.get("available_reveals"), "statement"), none),
        ev["list_behaviors"] + "\n" + _bullets(schemas.behavior_states(req.get("cast")), none),
        ev["list_things"] + "\n" + _bullets(schemas.names_of((req.get("world") or {}).get("objects")), none))
    text = _join(ev["job"], _planned(req.get("beat") or {}, ev), lists, ev["chapter_lead"] + "\n" + chapter_text.strip(), ev["task"])
    return Prompt("events", ev["version"], text, schemas.events_schema(req), "events")


def shifts_prompt(req: dict, chapter_text: str, events: dict | None = None) -> Prompt:
    sh = _t("shifts")
    cast = req.get("cast") or []
    names = [s(p.get("name")) for p in cast]
    beat = req.get("beat") or {}
    protagonist = s((req.get("setup") or {}).get("protagonist"))
    handles = schemas.entanglement_handles(req.get("entanglements") or {})
    parts = [sh["job"], sh["people_lead"] + "\n" + "\n".join(render_person_brief(p) for p in cast)]
    if s(beat.get("choice_a")) and s(beat.get("choice_b")):
        parts.append(sh["choice_lead"].format(name=protagonist) + "\n" + sh["choice_line"].format(label="One", value=sentence(s(beat["choice_a"])))
                     + "\n" + sh["choice_line"].format(label="The other", value=sentence(s(beat["choice_b"]))))
    if s(beat.get("reveal_rule")):
        parts.append(sh["reveal_lead"].format(statement=sentence(s(beat["reveal_rule"])), learners=join_names(beat.get("reveal_learners") or []) or "someone on stage"))
    parts.append(render_standing(req.get("standing") or []))
    if events:
        found = [sh["found_happened"].format(value=s(events.get("happened")))]
        if events.get("reveals_landed"):
            found.append(sh["found_reveals"].format(value="; ".join(s(r) for r in events["reveals_landed"])))
        parts.append(sh["found_lead"] + "\n" + "\n".join(found))
    parts.append(sh["handles_lead"] + "\n" + render_handles(req.get("entanglements") or {}, handles, names))
    parts += [sh["chapter_lead"] + "\n" + chapter_text.strip(), sh["task"]]
    return Prompt("shifts", sh["version"], _join(*parts), schemas.shifts_schema(req, handles), "shifts", {"handles": handles})


def resolve_changes(changes: list[dict], handles: dict[str, dict]) -> list[dict]:
    """The model's changes with each handle turned back into the id the page sent. A handle that matches nothing is dropped."""
    out = []
    for change in changes or []:
        info = handles.get(change.get("item"))
        if info and info["section"] == change.get("section") and info.get("id"):
            out.append({"section": change["section"], "item": info["id"], "field": change["field"], "value": change["value"]})
    return out


def assemble_generate_reply(chapter_text: str, events: dict, shifts_out: dict, handles: dict[str, dict]) -> dict:
    """The contract's reply for `generate`, from the three passes. The page checks every name and link."""
    shifts = []
    for row in shifts_out.get("shifts") or []:
        kept = {k: s(row.get(k)) for k in schemas.SHIFT_FIELDS if s(row.get(k))}
        if kept:
            shifts.append({"character": s(row.get("character")), **kept})
    return {
        "ok": True, "chapter_text": chapter_text,
        "events": {"happened": s(events.get("happened")), "changed": s(events.get("changed")) or None, "planted": s(events.get("planted")) or None,
                   "paid_off": list(events.get("paid_off") or []), "reveals_landed": list(events.get("reveals_landed") or []),
                   "behaviors_seen": list(events.get("behaviors_seen") or []), "things_seen": list(events.get("things_seen") or []),
                   "goal_landed": bool(events.get("goal_landed"))},
        "shifts": shifts,
        "changes": resolve_changes(shifts_out.get("changes") or [], handles),
        "new_knowledge": [{"person": s(k.get("person")), "status": k["status"], "rule": s(k.get("rule")) or None, "fact": s(k.get("fact")) or None}
                          for k in shifts_out.get("new_knowledge") or []],
    }


# ---- Card fill ------------------------------------------------------------------------------------------------------

def describe_fields(card_id: str) -> str:
    """The card's fields as a guide for the model: what each is for, its choices, a good example."""
    spec = tx.schema_text(card_id)["fields"]
    lines = []

    def one(key: str, d: dict, indent: str = "") -> str:
        line = f"{indent}- {key}: {s(d.get('help'))}"
        options = d.get("options")
        if options:
            line += " One of: " + "; ".join(f"{v} ({o.get('description') or o.get('label', v)})" for v, o in options.items()) + "."
        good = (d.get("examples") or {}).get("good")
        if good:
            line += " For example: " + "; ".join(good[:2]) + "."
        return line

    for key in CARDS[card_id][0].model_fields:
        d = spec.get(key)
        if not d:
            continue
        lines.append(one(key, d))
        for sub, sd in (d.get("item_fields") or {}).items():
            lines.append(one(sub, sd, "    "))
    return "\n".join(lines)


def _values_lines(values: dict, names: dict[str, str]) -> str:
    rows = []
    for key, value in values.items():
        if key == "id" or value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            shown = []
            for v in value:
                if isinstance(v, dict):
                    shown.append(", ".join(f"{k}: {names.get(x, x)}" if isinstance(x, str) else f"{k}: {x}" for k, x in v.items() if k != "id" and x not in (None, "", [])))
                else:
                    shown.append(names.get(v, str(v)))
            rows.append(f"{key}: " + "; ".join(shown))
        else:
            rows.append(f"{key}: {names.get(value, value) if isinstance(value, str) else value}")
    return "\n".join(rows)


def fill_prompt(req: dict) -> Prompt:
    f = _t("fill")
    card = req["card"]
    related = req.get("related") or {}
    names = names_by_id(related)
    language = language_name(req.get("language") or "en")
    scope = f["scope"][card]
    label = tx.schema_text(card)["card"]["label"]

    shown = []
    if related.get("style"):
        shown.append(render_style(related["style"], scope="planner"))
    chars = related.get("characters") or []
    if chars:
        shown.append(render_cast(chars if isinstance(chars, list) else [chars], scope="planner"))
    if related.get("world"):
        shown.append(render_world(related["world"], scope="planner"))
    ent = related.get("entanglements")
    if ent:
        words = {k: in_words(ent.get(k), schemas.field_extras("entanglements", k), names) for k in ("ties", "holdings", "knowledge", "pressures")}
        shown.append(render_entanglements(words, (), scope="planner"))
    link = schemas.link_names(related)
    link_lines = [f"{label_}: {', '.join(found)}" for label_, key in (("People", "characters"), ("Places", "world.places"), ("Things", "world.objects"),
                                                                       ("Groups", "world.powers"), ("Rules", "world.rules")) if (found := link[key])]
    current = _values_lines(req.get("values") or {}, names)
    guidance = f.get("card_guidance", {}).get(card)
    parts = [f["job"].format(language_name=language), f["scope_line"].format(**scope)] + ([guidance.strip()] if guidance else []) + [
             f["card_lead"].format(label=label) + "\n" + describe_fields(card)]
    if shown:
        parts.append(f["other_cards_lead"] + "\n\n" + "\n\n".join(shown))
    if link_lines:
        parts.append(f["names_lead"] + "\n" + "\n".join(link_lines))
    parts.append(f["current_lead"] + "\n" + current if current else f["current_none"])
    if s(req.get("note")):
        parts.append(f["note_lead"] + "\n" + req["note"].strip())
    if s(req.get("example_chapter")):
        parts.append(f["chapter_lead"] + "\n" + req["example_chapter"].strip())
    parts.append(f["task"])
    return Prompt("fill", f["version"], _join(*parts), schemas.fill_schema(req), None, {"card": card})


# ---- Model-judged rules ---------------------------------------------------------------------------------------------

def rule_def(card_id: str, rule_id: str):
    for rule in CARDS[card_id][3]:
        if rule.id == rule_id:
            return rule
    raise KeyError(f"the {card_id} card has no rule {rule_id}")


def _judge_context(rule, related: dict, names: dict[str, str]) -> list[str]:
    chars = related.get("characters") or []
    chars = chars if isinstance(chars, list) else [chars]
    lead = next((c for c in chars if c.get("id") == (related.get("setup") or {}).get("protagonist")), None)
    ent = related.get("entanglements") or {}
    out = []
    if "protagonist_wants" in rule.context and lead:
        out.append("The protagonist's wants: " + "; ".join(w["text"] for w in lead.get("wants") or []))
    if "protagonist_values" in rule.context and lead:
        out.append("The protagonist's values: " + "; ".join(v["text"] for v in lead.get("values") or []))
    if "pressures" in rule.context and ent.get("pressures"):
        out.append("The pressures: " + "; ".join(s(p.get("what")) for p in ent["pressures"]))
    if "ties" in rule.context and ent.get("ties"):
        ties = in_words(ent["ties"], schemas.field_extras("entanglements", "ties"), names)
        out.append("The ties: " + "; ".join(f"{t['tie_from']} toward {t['tie_to']}: {s(t.get('edge'))}" for t in ties))
    return out


def _item_text(card_id: str, field_name: str, item: dict) -> str:
    extras = schemas.field_extras(card_id, field_name)
    rows = [(k, s(v)) for k, v in item.items()
            if k != "id" and isinstance(v, str) and s(v) and not extras.get(k, {}).get("ref") and extras.get(k, {}).get("filled_by") != "code"]
    return rows[0][1] if len(rows) == 1 else "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in rows)


def judge_question(text: str) -> tuple[str, str]:
    """Split a rule's judge text into the question and the answer that means the item BREAKS the rule.
    The texts end with what to do for a failing item ("If no, suggest...", "If yes, rewrite...", "Rewrite any that fail",
    "any that do so"). That tail also tells which answer fails. The answer instruction and the rewrite request are
    dropped: the reply holds only the items that break the rule (F5)."""
    head, _, tail = text.partition("Answer yes or no")
    breaks = "yes" if re.search(r"\bIf yes\b|any that do so", tail) else "no"
    return head.strip(), breaks


# Rules about the field as a whole ("at least one", "some pair"): each item is asked its own question, and the rule is broken
# only when no item keeps it. The number is how many items the field needs before the rule is worth asking.
SET_RULES = {"wants_conflict": 2, "behaviors_include_calm": 1}


def judge_prompts(req: dict) -> list[Prompt]:
    """One prompt per rule asked about. The rule's own question comes from the schema's text file."""
    j = _t("judge")
    card = req["card"]
    related = req.get("related") or {}
    names = names_by_id(related)
    values = req.get("values") or {}
    labels = tx.schema_text(card)["fields"]
    prompts = []
    for asked in req["rules"]:
        rule = rule_def(card, asked["id"])
        question, breaks = judge_question(tx.schema_text(card)["rules"][rule.id]["judge_prompt"])
        handles: dict[str, str | None] = {}
        blocks = []
        for key in asked["fields"]:
            value = values.get(key)
            head = j["field_lead"].format(label=labels.get(key, {}).get("label", key))
            if isinstance(value, list) and value and isinstance(value[0], dict):
                rows = []
                for n, item in enumerate(value, 1):
                    handle = f"{key}.{n}"
                    handles[handle] = item.get("id")
                    rows.append(f"{handle}: {_item_text(card, key, item)}")
                blocks.append(head + "\n" + "\n".join(rows))
            elif value not in (None, "", []):
                handles[key] = None
                blocks.append(f"{head} {s(value)}")
        context = _judge_context(rule, related, names)
        parts = [j["job"], j["rule_lead"].format(when=rule.when), j["question_lead"].format(question=question), j["keeps_lead"].format(answer="yes" if breaks == "no" else "no")]
        if context:
            parts.append(j["context_lead"] + "\n" + "\n".join(context))
        parts += [j["items_lead"] + "\n" + "\n\n".join(blocks), j["task"]]
        prompts.append(Prompt("judge", j["version"], _join(*parts), schemas.judge_schema(list(handles)), None,
                              {"rule": rule.id, "handles": handles}))
    return prompts


def assemble_judge_reply(prompts: list[Prompt], answers: list[dict]) -> dict:
    """The contract's reply for `judge`: one result per rule asked, each hit pointing at the item id the page sent."""
    results = []
    for prompt, answer in zip(prompts, answers):
        rule, handles = prompt.meta["rule"], prompt.meta["handles"]
        checks = [c for c in answer.get("checks") or [] if c.get("item") in handles]
        broken = [c for c in checks if c.get("keeps_the_rule") is False]
        if rule in SET_RULES:                                      # one hit on the field, only when no item keeps the rule
            enough = len(handles) >= SET_RULES[rule]
            hits = [{"field": broken[0]["item"].split(".")[0], "item": None, "key": None}] if enough and checks and len(broken) == len(checks) else []
        else:
            hits = [{"field": c["item"].split(".")[0], "item": handles[c["item"]], "key": None} for c in broken]
        results.append({"rule": rule, "hits": hits})
    return {"ok": True, "results": results}


# ---- Style fit ------------------------------------------------------------------------------------------------------

def style_fit_prompt(req: dict) -> Prompt:
    sf = _t("style_fit")
    style = req.get("style") or {}
    voice = [_voice_rules(style)]
    if s(style.get("narrator_note")):
        voice.append(s(style["narrator_note"]))
    text = _join(sf["job"].format(language_name=language_name(req.get("language") or "en")),
                 sf["voice_lead"] + "\n" + "\n".join(v for v in voice if v),
                 sf["protagonist_lead"] + "\n" + render_person(req.get("protagonist") or {}, scope="fit"), sf["task"])
    return Prompt("style_fit", sf["version"], text, schemas.style_fit_schema())


# ---- Offstage -------------------------------------------------------------------------------------------------------

def offstage_prompt(req: dict) -> Prompt:
    o = _t("offstage")
    cast = req.get("cast") or []
    total = int(req.get("chapter_count") or 0)
    parts = [o["job"].format(language_name=language_name(req.get("language") or "en"), chapter=req.get("chapter"), of_total=f" of {total}" if total else "")]
    spotlight = req.get("spotlight")
    spotlight = s(spotlight.get("what")) if isinstance(spotlight, dict) else s(spotlight)
    if spotlight:
        parts.append(o["spotlight_line"].format(value=sentence(spotlight)))
    parts.append(o["cast_lead"].format(names=join_names([s(p.get("name")) for p in cast])))
    parts.append(o["groups_lead"] + "\n" + _join(render_world(req.get("world") or {}, scope="planner"),
                                                    render_entanglements(req.get("entanglements") or {}, (), scope="planner")))
    last = req.get("latest_events")
    if last:
        last = {**last, "chapter": last.get("chapter") or max(int(req.get("chapter") or 1) - 1, 1)}
        parts.append(o["last_lead"] + "\n" + render_story_so_far([last], 10 ** 6, keep_full=1))
    parts.append(o["task"])
    return Prompt("offstage", o["version"], _join(*parts), schemas.offstage_schema(), "offstage")


# ---- End of story ---------------------------------------------------------------------------------------------------

def _numbered(events: list[dict]) -> list[dict]:
    """Events entries with a chapter number; one without a number takes its place in the list."""
    return [{**e, "chapter": e.get("chapter") or n} for n, e in enumerate(events or [], 1)]


def _end_material(req: dict) -> str:
    e = _t("end_story")
    story = render_story_so_far(_numbered(req.get("events")), 10 ** 6, keep_full=10 ** 6)
    changes = render_shifts_history(req.get("shifts") or [])
    return _join(e["story_lead"] + "\n" + story, e["shifts_lead"] + "\n" + changes if changes else "")


def end_story_prompts(req: dict) -> list[Prompt]:
    """One prompt per character, then one for the world. The cards are shown as data with their ids, because the reply must
    carry each existing item's id back (the contract's own design)."""
    e = _t("end_story")
    language = language_name(req.get("language") or "en")
    material = _end_material(req)
    people = join_names([s(c.get("name")) for c in req.get("characters") or []])
    prompts = []
    for character in req.get("characters") or []:
        name = s(character.get("name"))
        text = _join(e["job_character"].format(name=name, language_name=language), material, e["cast_lead"].format(names=people),
                     e["card_lead"] + "\n" + json.dumps(character, ensure_ascii=False, indent=1), e["task"])
        prompts.append(Prompt("end_story_character", e["version"], text, schemas.card_schema("characters", drop_fixed=True, item_ids=True),
                              "update", {"kind": "character", "id": character["id"]}))
    text = _join(e["job_world"].format(language_name=language), material, e["card_lead"] + "\n" + json.dumps(req.get("world") or {}, ensure_ascii=False, indent=1), e["task"])
    prompts.append(Prompt("end_story_world", e["version"], text, schemas.card_schema("world", item_ids=True), "update", {"kind": "world"}))
    return prompts


def assemble_end_story_reply(prompts: list[Prompt], outputs: list[dict], original: dict) -> dict:
    """The contract's reply for `end_story`: every character with the id it was sent, then the world. A field the model left
    out is left out here, and the page keeps the old value."""
    characters, world = [], {}
    for prompt, out in zip(prompts, outputs):
        if prompt.meta["kind"] == "character":
            characters.append({**out, "id": prompt.meta["id"]})
        else:
            world = out
    return {"ok": True, "characters": characters, "world": world}
