"""The `generate` call: `write` (the chapter as prose), `events` (what happened, what changed), `shifts` (the new edge of the spotlight tie) and, when other ties
are on stage, `ties_touched` (which of them the chapter touched; nothing is written for them yet). Wording lives in text/en/generate.yaml, where the reasoning behind the writer prompt is recorded.

Rules served: R3 (an interesting story, craft guidance in prose), R5 (minor characters by role, never the plot), R6 (the spotlight tie's edge
and the protagonist's aim end in a new state; the shifts check demands the edge), R7 (the chapter follows the plan's four points unlabelled).

The generate request carries the spotlight tie's id inside the beat (`beat.spotlight`, one of the ties sent), and the tie is that one. A request
without it, or with an id that is not among its ties, falls back to the old reading: the planner is told to name both ends of the tie in the
plan, so the tie is the one whose two ends the beat's plan names, and if none or several are named, any of the named ties (or any tie)
satisfies the edge check. The id never reaches a prompt: the model sees the tie's names and its handle."""
import copy
import json
import re
from dataclasses import replace
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step

from . import advance, common
from .plan import cut_events, in_names, names_of, pressure_of, protagonist_name, spotlight_candidates, spotlight_in_words, spotlight_of, tiers, _norm

VERSION = "generate-16"

# The chapter's length (decided 3 Nov): at most 1,200 words, or 2,400 Han characters for Chinese (twice the word figure, as in tools/trial_checks.mjs).
# WRITE_TOKENS is a safety net so a chapter is never cut mid-sentence, not a target. Measured with pulpermill/prompts/tokens.py on ordinary narrative
# prose with dialogue (a 254-word sample repeated to length): 1,200 English words = 1,402 tokens; 2,400 Chinese characters = 2,041 tokens.
# The larger count (Chinese) plus 25 percent is 2,551, rounded up to 2,560. English alone would need only about 1,760.
CAP_WORDS, CAP_HAN = 1200, 2400
OVERSHOOT_WORDS, OVERSHOOT_HAN = 1500, 3000      # the write check only speaks above these, so a few extra words never cost a second attempt
WRITE_TOKENS = 2560
EVENTS_TOKENS = 800
SHIFTS_TOKENS = 1600
JUDGE_ATTEMPTS = 2        # the advancement judge (observe-only): two tries, then a neutral verdict, so a judge can never fail a call
RESEND_STAND_IN = "word " * 90        # the longest line the judge can send the shifts back with (a 400-character reason and the advice), for the worst case
EDGE_STAND_IN = "word " * 60       # the longest an edge is shown to a model (300 characters), for the worst case
HAPPENED_STAND_IN = "word " * 100      # the longest a chapter's `happened` is shown to the pressure judge, for the worst case
EVENTS_ATTEMPTS, SHIFTS_ATTEMPTS = 4, 3          # after the chapter is written, each of these steps is retried on its own and then falls back
TOUCH_CAP = 4            # the most ties besides the spotlight tie that one chapter can touch (the first ones, in list order), to bound the cost
TIE_EDGE_TOKENS = 300      # a new edge (at most 300 characters shown) and a bond, with room to spare
TOUCHED_TOKENS = 400     # a short reason for each of at most TOUCH_CAP ties, with room to spare
CHANGED_WORDS, HAPPENED_WORDS = 100, 60         # the most words `changed` keeps (its first two sentences, which have room for the outcome, the aim and the tie) and the fallback's `happened` keeps


def _lang(request: dict) -> str:
    names = common.load_text("generate")["languages"]
    code = str(request.get("language") or "en")
    return names.get(code) or names.get(code.split("-")[0]) or code


def _spot(request: dict, names: dict[str, str]) -> tuple[list[dict], bool]:
    """(the candidate spotlight ties, whether they were identified). By id when the beat carries one that matches a tie sent; otherwise by the
    names in the plan. Not identified: every tie is a candidate."""
    tie = spotlight_of(request)
    if tie:
        return [tie], True
    found = spotlight_candidates(request, names)
    return (found, True) if found else (list(request.get("ties") or []), False)


def _section(heading: str, body: str) -> str:
    return f"## {heading}\n{body}" if body else ""


# ---- write -----------------------------------------------------------------------------------------------------------------

def write_prompt(request: dict, factor: float = 1.0) -> str:
    w = common.load_text("generate")
    heads = w["headings"]
    names = names_of(request)
    chapter, total = int(request["chapter"]), int(request.get("chapter_count") or 0)
    history_ratio, world_f, cast_f = tiers(factor)
    lang = _lang(request)
    cast = request.get("cast") or []
    cast_names = [r.s(p.get("name")) for p in cast]
    beat = request.get("beat") or {}
    ties = in_names(request.get("ties") or [], ("tie_from", "tie_to"), names)
    holdings = in_names(request.get("holdings") or [], ("holdee", "held_by"), names)
    candidates, identified = _spot(request, names)
    spot = spotlight_in_words(candidates[0], names) if identified and len(candidates) == 1 else None

    pressure = pressure_of(request, factor)
    scene_beat = {**{k: v for k, v in beat.items() if k not in ("spotlight", "pressure")}, "cast": cast_names}     # the tie's and the pressure's ids are never shown
    if pressure:
        scene_beat["pressure"] = pressure          # in words, from the request; the pressure sentence is the first thing a squeeze drops
    if spot:
        scene_beat["spotlight"] = spot
    with tx.squeeze(cast_f):
        cast_text = r.render_cast(cast, scope="writer")
    with tx.squeeze(world_f):
        world_text = r.render_world(request.get("world") or {}, scope="writer", place=r.s(beat.get("where")) or None,
                                    in_play=r.groups_in_play({"ties": ties}), without=pressure)
    events = cut_events(request.get("earlier_events"), chapter, history_ratio)
    keep = max(1, round(tx.limits()["events"]["full_chapters_writer"] * min(1.0, history_ratio)))
    history = r.render_history(events, chapter, scope="writer", keep_full=keep)
    ending = r.s(request.get("previous_ending"))
    last = bool(total) and chapter >= total
    craft = [w["craft_interest"], w["craft_dialogue"], w["craft_turn"], w["craft_change_last" if last else "craft_change"]]
    style = r.render_style(request.get("style") or {}, scope="writer")

    role = w["role"].format(chapter=chapter, total=total, language=lang) if total else w["role_unknown_total"].format(chapter=chapter, language=lang)
    blocks = [
        role,
        _section(heads["plan"], w["plan_note"] + "\n" + r.render_scene(scene_beat, scope="writer")),
        _section(heads["voice"], (style + "\n" + w["voice_rule"]) if style else w["voice_rule"]),
        _section(heads["setup"], r.render_setup(request.get("setup") or {}, chapter, total or None, protagonist_name=protagonist_name(request, names))),
        _section(heads["cast"], cast_text),
        _section(heads["spotlight"], r.render_spotlight(spot, cast, scope="writer", names=names) if spot else ""),
        _section(heads["world"], world_text),
        _section(heads["entanglements"], r.render_entanglements({"ties": ties, "holdings": holdings}, cast_names, scope="writer")),
        _section(heads["history"], history),
        _section(heads["ending"], w["ending_lead"].format(previous=chapter - 1, chapter=chapter) + "\n\n" + ending if ending else ""),
        _section(heads["craft"], "\n\n".join(craft)),
        w["closing"].format(language=lang, **w["length"]["zh" if is_zh(request) else "en"]),
    ]
    return "\n\n".join(b for b in blocks if b)


def is_zh(request: dict) -> bool:
    return str(request.get("language") or "en").lower().startswith("zh")


def write_findings(request: dict, text: Any) -> tuple[str | None, list[tuple[str, str]]]:
    """(the hard problem line or None, the soft problems as [(kind, line)]). Hard: the chapter is far over the cap (more than 1,500 words, or
    3,000 Han characters for Chinese; under the cap, or a little over it, passes and a short chapter is never rejected). Soft: the opening
    repeats a sentence of the previous chapter's ending ("echo"). A person on no card is never a problem here (see `write_names`)."""
    body = r.s(text)
    p = common.load_text("generate")["write_problems"]
    if is_zh(request):
        over, cap = len(re.findall(r"[\u4e00-\u9fff]", body)) > OVERSHOOT_HAN, "zh"
    else:
        over, cap = len(re.findall(r"[\w'’-]+", body)) > OVERSHOOT_WORDS, "en"
    if over:
        return p["too_long"].format(cap=common.load_text("generate")["length"][cap]["cap"]), []
    soft: list[tuple[str, str]] = []
    ending = r.s(request.get("previous_ending"))
    if ending and not is_zh(request) and common.echoes_ending(body, ending):
        soft.append(("echo", p["echo"]))
    return None, soft


def write_problem(request: dict, text: Any, tolerate_soft: bool = False) -> str | None:
    """One plain line saying what to fix, or None. A hard problem always speaks; a soft one (the echo) speaks unless `tolerate_soft` (the
    last attempt), when the reply is let through."""
    hard, soft = write_findings(request, text)
    if hard:
        return hard
    return soft[0][1] if soft and not tolerate_soft else None


def write_names(request: dict, text: Any) -> tuple[int, list[str]]:
    """(how many people on no card the chapter names, and which of them are new). English only, and a plain name must come back at least
    twice, because a good chapter costs more than a missed name. The count includes names the earlier chapters used; the new ones are in no
    earlier chapter's events either."""
    return common.minor_people(request, [r.s(text)], _card_text(request), common.earlier_records(request), min_count=2)


def _card_text(request: dict) -> list:
    """What the writer may take names from: the cards the request carries and the beat the person approved. The earlier chapters' records are
    not in this list: they are a separate allowance (`common.earlier_records`), because `write_names` counts with and without them. They once
    were excluded on purpose, so that a name could not be passed along from chapter to chapter. That changed: the history shown to the model
    carries those names, so refusing a name the prompt itself shows contradicts the prompt."""
    return [request.get(k) for k in ("cast", "world", "ties", "holdings", "setup", "style", "beat")]


# ---- events ----------------------------------------------------------------------------------------------------------------

EVENTS_NEXT = {"reached": "new", "lost": "forced", "gave_up": "forced"}     # the planned outcomes, and which wording tells what the next aim is after each


def planned_outcome(beat: dict) -> str | None:
    """The beat's planned outcome (reached, lost or gave_up) when it has one the schema knows, else None."""
    planned = beat.get("outcome")
    return planned if isinstance(planned, str) and planned in EVENTS_NEXT else None


def planned_outcome_line(beat: dict) -> str:
    """The planned outcome as the sentence the schema gives the model, or an empty string."""
    outcome = planned_outcome(beat)
    return tx.field("outline", "beats")["item_fields"]["outcome"]["options"][outcome]["expand"] if outcome else ""


def events_prompt(request: dict, chapter_text: str, factor: float = 1.0) -> str:
    w = common.load_text("generate")
    names = names_of(request)
    beat = request.get("beat") or {}
    candidates, identified = _spot(request, names)
    tie = ""
    if identified and len(candidates) == 1:
        t = spotlight_in_words(candidates[0], names)
        tie = w["events_tie"].format(tie_from=t["tie_from"], tie_to=t["tie_to"], edge=r.s(t.get("edge")))
    outcome = planned_outcome(beat)      # how the plan ended the chapter: given to the model as a fact
    parts = [w["events_task"].format(chapter=request["chapter"], language=_lang(request)),
             w["events_chapter_lead"] + "\n" + chapter_text.strip(),
             w["events_aim"].format(aim=r.sentence(r.s(beat.get("aim"))), tie=tie).strip(),
             planned_outcome_line(beat),
             w["events_format"].format(ended=w["events_ended_" + ("given" if outcome else "any")], next=w["events_next_" + EVENTS_NEXT.get(outcome, "any")])]
    return "\n\n".join(p for p in parts if p)


def events_problem(value: Any) -> str | None:
    p = common.load_text("generate")["events_problems"]
    happened, changed = r.s((value or {}).get("happened")), r.s((value or {}).get("changed"))
    if len(happened.split()) < 4:
        return p["empty_happened"]
    if not changed:
        return p["empty_changed"]
    return None          # a `changed` that runs on is repaired in code (repair_events), not refused


_SENTENCE_END = re.compile(r"[.!?…]+[\"”’')\]]*(?=\s|$)|[。！？]+[”’」』）]*")


def sentences(text: str) -> list[str]:
    """The sentences of a text, in order, each with its closing punctuation; a text without any stop is one sentence."""
    text, out, start = r.s(text), [], 0
    for m in _SENTENCE_END.finditer(text):
        piece = text[start:m.end()].strip()
        if piece:
            out.append(piece)
        start = m.end()
    tail = text[start:].strip()
    return out + [tail] if tail else out


def _words(text: str, limit: int) -> str:
    """At most `limit` words of the text, ended with a full stop when it was cut."""
    words = r.s(text).split()
    return " ".join(words) if len(words) <= limit else " ".join(words[:limit]).rstrip(",;:—–- ") + "."


def repair_events(value: Any) -> dict:
    """`changed` as its first two sentences (the outcome and the aim, then what drives the tie), cut to CHANGED_WORDS words. Everything else is left as it came."""
    out = dict(value or {})
    kept = sentences(out.get("changed"))[:2]
    out["changed"] = _words(" ".join(kept), CHANGED_WORDS) if kept else r.s(out.get("changed"))
    return out


def events_fallback(chapter_text: str) -> dict:
    """What `events` says when no model reply could be used: plain code over the chapter (no model call). `happened` is the chapter's opening
    sentences, `changed` its last sentence, both in the chapter's own language."""
    found = sentences(chapter_text)
    if not found:
        return {"happened": r.s(chapter_text)[:400], "changed": ""}
    return {"happened": _words(" ".join(found[:2]), HAPPENED_WORDS), "changed": _words(found[-1], CHANGED_WORDS)}


# ---- shifts ----------------------------------------------------------------------------------------------------------------

def _reference(request: dict, kit: Any, names: dict[str, str], factor: float) -> str:
    """The ties the model may change, with the handle of each, so that it points at them without seeing an id."""
    lines = []
    for scope in kit.handles.of_card("entanglements"):
        for item in in_names(request.get("ties") or [], ("tie_from", "tie_to"), names):
            if item.get("id"):
                text = f"{item['tie_from']} toward {item['tie_to']}: {r.bare(item.get('bond'))}. Edge: {r.s(item.get('edge'))}"
                lines.append(common.labelled(scope, "ties", item["id"], common.clip(text, factor)))
    return "\n".join(lines)


def edge_targets(request: dict, kit: Any) -> list[tuple[str, dict]]:
    """[(handle, tie)] for the ties whose edge must move: the identified spotlight tie, else any tie."""
    names = names_of(request)
    candidates, _ = _spot(request, names)
    scopes = kit.handles.of_card("entanglements")
    if not scopes:
        return []
    return [(scopes[0].of("ties", t["id"]), t) for t in candidates if t.get("id")]


def shifts_prompt(request: dict, kit: Any, events: Any, factor: float = 1.0, extra: str = "") -> str:
    """The ties and the facts of the chapter as its summary records them (`events`: happened, changed). The chapter's prose is never shown here."""
    w = common.load_text("generate")
    facts = repair_events(events)
    names = names_of(request)
    targets = edge_targets(request, kit)
    _, identified = _spot(request, names)
    edge = ""
    if targets and identified and len(targets) == 1:
        handle, tie = targets[0]
        edge = w["shifts_edge"].format(tie_from=names.get(tie["tie_from"], ""), tie_to=names.get(tie["tie_to"], ""), handle=handle, edge=r.bare(tie.get("edge")))
    elif targets:
        listed = "; ".join(w["shifts_edge_item"].format(handle=h, tie_from=names.get(t["tie_from"], ""), tie_to=names.get(t["tie_to"], ""), edge=r.bare(t.get("edge")))
                           for h, t in targets)
        edge = w["shifts_edge_any"].format(ties=listed)
    parts = [w["shifts_task"].format(chapter=request["chapter"]),
             w["shifts_happened_lead"] + "\n" + r.s(facts.get("happened")),
             w["shifts_changed_lead"] + "\n" + r.s(facts.get("changed")) if r.s(facts.get("changed")) else "",
             w["shifts_cards_lead"] + "\n" + _reference(request, kit, names, factor),
             w["shifts_rules"],
             w["shifts_example"], edge, w["shifts_edge_move"] if edge else "", w["shifts_bond"] if edge else "", w["shifts_form"] if edge else "", extra, w["shifts_format"]]        # `extra`: the advancement judge sent the shifts back once, and this is its line
    return "\n\n".join(p for p in parts if p)


def shifts_problem(request: dict, kit: Any, value: Any) -> str | None:
    """The kit's own check of the entries, then R6: the spotlight tie's edge is replaced by something different."""
    entries = (value or {}).get("shifts") if isinstance(value, dict) else None
    line = kit.shifts_problem(entries)
    if line:
        return line
    targets = edge_targets(request, kit)
    if not targets:
        return None
    p = common.load_text("generate")["shifts_problems"]
    names = names_of(request)
    for entry in entries:
        if entry.get("card") != "entanglements":
            continue
        for op in (entry.get("patch") or {}).get("ties") or []:
            for handle, tie in targets:
                new = (op.get("values") or {}).get("edge")
                if op.get("op") == "replace" and op.get("id") == handle and r.s(new) and _norm(new) != _norm(tie.get("edge")):
                    return None
    if len(targets) == 1:
        handle, tie = targets[0]
        return p["edge_not_moved"].format(handle=handle, tie_from=names.get(tie["tie_from"], ""), tie_to=names.get(tie["tie_to"], ""), edge=r.s(tie.get("edge")))
    return p["edge_not_moved_any"]


def _replaced(request: dict, kit: Any, shifts: Any) -> tuple[dict, dict] | None:
    """(the tie, the values of the operation that replaces its edge) when the shifts replace the edge of a tie that must move, else None."""
    entries = shifts.get("shifts") if isinstance(shifts, dict) else None
    targets = edge_targets(request, kit)
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("card") != "entanglements":
            continue
        for op in (entry.get("patch") or {}).get("ties") or []:
            for handle, tie in targets:
                new = r.s((op.get("values") or {}).get("edge")) if isinstance(op, dict) else ""
                if isinstance(op, dict) and op.get("op") == "replace" and op.get("id") == handle and new and _norm(new) != _norm(tie.get("edge")):
                    return tie, op["values"]
    return None


def replaced_edge(request: dict, kit: Any, shifts: Any) -> tuple[str, str] | None:
    """(the edge the spotlight tie had, the edge the shifts replaced it with) when the shifts replace the edge of a tie that must move, else
    None. The same reading as the edge check's, so a reply that passed it has one."""
    found = _replaced(request, kit, shifts)
    return (r.s(found[0].get("edge")), r.s(found[1].get("edge"))) if found else None


def replaced_bond(request: dict, kit: Any, shifts: Any) -> str:
    """The bond the shifts wrote with the new edge, or an empty string when they left the bond alone."""
    found = _replaced(request, kit, shifts)
    return r.s(found[1].get("bond")) if found else ""


# ---- ties touched ----------------------------------------------------------------------------------------------------------

def touch_candidates(request: dict) -> list[dict]:
    """The ties besides the spotlight tie that a chapter may have touched, at most TOUCH_CAP, in list order: the tie's from end is a person on
    stage and its to end is a person on stage or a group of the world. A tie that starts at a group is skipped (an edge is what a person wants).
    The people on stage are the request's `cast` (and the beat's `cast` ids when the beat carries them); the groups are the world's `powers`."""
    beat = request.get("beat") or {}
    people = {c.get("id") for c in request.get("cast") or [] if isinstance(c, dict)} | {i for i in beat.get("cast") or [] if isinstance(i, str)}
    groups = {g.get("id") for g in (request.get("world") or {}).get("powers") or [] if isinstance(g, dict)}
    spotlight, identified = _spot(request, names_of(request))
    skip = {t.get("id") for t in spotlight} if identified else set()
    found = [t for t in request.get("ties") or []
             if t.get("id") and t["id"] not in skip and t.get("tie_from") in people and (t.get("tie_to") in people or t.get("tie_to") in groups)]
    return found[:TOUCH_CAP]


def _candidate_handles(request: dict, kit: Any) -> list[tuple[str, dict]]:
    """[(handle, tie)] for the touch candidates; none when the kit has no entanglements card."""
    scopes = kit.handles.of_card("entanglements")
    return [(scopes[0].of("ties", t["id"]), t) for t in touch_candidates(request)] if scopes else []


def touched_prompt(request: dict, kit: Any, events: Any) -> str:
    """The chapter's facts (`happened`, `changed`) and the candidate ties with their handles; the chapter's prose is never shown."""
    w = common.load_text("generate")
    facts = repair_events(events)
    names = names_of(request)
    items = []
    for handle, tie in _candidate_handles(request, kit):
        bond = r.bare(tie.get("bond"))
        items.append(w["touched_item" if bond else "touched_item_plain"].format(handle=handle, tie_from=names.get(tie["tie_from"], ""), tie_to=names.get(tie["tie_to"], ""),
                                                                                bond=bond, edge=r.bare(tie.get("edge"))))
    parts = [w["touched_task"].format(chapter=request["chapter"]),
             w["shifts_happened_lead"] + "\n" + r.s(facts.get("happened")),
             w["shifts_changed_lead"] + "\n" + r.s(facts.get("changed")) if r.s(facts.get("changed")) else "",
             w["touched_ties_lead"] + "\n" + "\n".join(items),
             w["touched_rules"], w["touched_format"]]
    return "\n\n".join(p for p in parts if p)


def touched_grammar() -> dict:
    """{touched: [{tie, reason}]}: the handle of each tie the chapter touched and one sentence why; the list may be empty."""
    text = {"type": "string"}
    item = {"type": "object", "properties": {"tie": text, "reason": text}, "required": ["tie", "reason"], "additionalProperties": False}
    return {"type": "object", "properties": {"touched": {"type": "array", "items": item}}, "required": ["touched"], "additionalProperties": False}


def touched_found(request: dict, kit: Any, value: Any) -> list[tuple[str, str]]:
    """[(handle, reason)] for the handles the reply names that are among the candidates, each once, in the reply's order; any other handle is dropped."""
    wanted = {h for h, _ in _candidate_handles(request, kit)}
    found: list[tuple[str, str]] = []
    for item in (value or {}).get("touched") or [] if isinstance(value, dict) else []:
        handle = item.get("tie") if isinstance(item, dict) else None
        if isinstance(handle, str) and handle in wanted and handle not in [h for h, _ in found]:
            found.append((handle, r.s(item.get("reason"))))
    return found


def touched_handles(request: dict, kit: Any, value: Any) -> list[str]:
    """The handles the reply names that are among the candidates (see `touched_found`)."""
    return [h for h, _ in touched_found(request, kit, value)]


# ---- rewriting a touched tie -----------------------------------------------------------------------------------------------

def tie_edge_prompt(request: dict, tie: dict, reason: str, events: Any, extra: str = "") -> str:
    """One touched tie: the tie, its old edge and bond, the chapter's facts and why the tie was touched. Asks for the edge and bond as the chapter leaves them.
    The model never sees or writes a handle: code builds the operation."""
    w = common.load_text("generate")
    facts = repair_events(events)
    names = names_of(request)
    bond = r.bare(tie.get("bond"))
    ends = dict(tie_from=names.get(tie.get("tie_from"), ""), tie_to=names.get(tie.get("tie_to"), ""), edge=r.bare(tie.get("edge")), bond=bond)
    parts = [w["tie_edge_task"].format(chapter=request["chapter"]),
             w["tie_edge_tie" if bond else "tie_edge_tie_plain"].format(**ends),
             w["shifts_happened_lead"] + "\n" + r.s(facts.get("happened")),
             w["shifts_changed_lead"] + "\n" + r.s(facts.get("changed")) if r.s(facts.get("changed")) else "",
             w["tie_edge_reason"].format(reason=r.sentence(reason)) if r.s(reason) else "",
             w["tie_edge_rules"].format(tie_from=ends["tie_from"], tie_to=ends["tie_to"]), w["shifts_form"], w["tie_edge_bond"], extra, w["tie_edge_format"]]
    return "\n\n".join(p for p in parts if p)


def tie_edge_grammar() -> dict:
    """{edge, bond}: the edge as the chapter leaves it, and the bond (empty when it did not change)."""
    text = {"type": "string"}
    return {"type": "object", "properties": {"edge": text, "bond": text}, "required": ["edge", "bond"], "additionalProperties": False}


def tie_edge_problem(value: Any) -> str | None:
    return None if isinstance(value, dict) and r.s(value.get("edge")) else common.load_text("generate")["tie_edge_problems"]["empty_edge"]


def tie_operation(handle: str, tie: dict, edge: str, bond: str) -> dict:
    """The replace operation for a touched tie. The bond rides along only when it is there and differs from the old one."""
    values = {"edge": r.s(edge)}
    if r.s(bond) and _norm(bond) != _norm(tie.get("bond")):
        values["bond"] = r.s(bond)
    return {"op": "replace", "id": handle, "values": values}


def merge_ties(entries: Any, operations: list[dict]) -> list[dict]:
    """The shifts' entries with `operations` added to the one entanglements entry (a new entry when there is none). An operation for a handle the entries
    already replace is left out. The entries are copied, never changed."""
    merged = copy.deepcopy([e for e in entries if isinstance(e, dict)]) if isinstance(entries, list) else []
    ties_of = lambda e: e["patch"].get("ties") if isinstance(e.get("patch"), dict) else None
    present = {op.get("id") for e in merged if e.get("card") == "entanglements" for op in ties_of(e) or [] if isinstance(op, dict)}
    fresh = [op for op in operations if op["id"] not in present]
    if not fresh:
        return merged
    target = next((e for e in merged if e.get("card") == "entanglements" and isinstance(e.get("patch"), dict) and isinstance(e["patch"].setdefault("ties", []), list)), None)
    if target:
        target["patch"]["ties"].extend(fresh)
    else:
        merged.append({"card": "entanglements", "patch": {"ties": fresh}})
    return merged


# ---- the flow --------------------------------------------------------------------------------------------------------------

class GenerateFlow(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit
        self.echo_accepted = False          # the write reply that was used carried an echo that the last attempt let through
        self.notes = {"events_fallback": False, "shifts_fallback": False, "pressure_on": bool(pressure_of(request))}      # for the run log: did a step's last resort stand in for it, and was a pressure sent?
        self._last = "write"                    # the kind of step whose result comes next: write, events, shifts, check, edge or pressure
        self._shifts_at = 2                     # where the shifts that stand sit in the results
        self._check_runs = self._judge_runs = 0
        self._check_resent = self._edge_resent = False      # each of the two sends the shifts back at most once
        self._resend_failed = False             # the last pass the shifts were sent back for could not be used: the first shifts stand
        self._touched_done = False              # the step that finds the other ties the chapter touched has run (or was not needed)
        self.touched: list[str] = []            # the handles of those ties, in the reply's order
        self._reasons: dict[str, str] = {}      # why each of them was touched
        self._ti = 0                            # which touched tie is being rewritten
        self._tie_new: tuple[str, str] = ("", "")       # that tie's new (edge, bond) so far
        self._tie_retried = False               # its edge was sent back once for the check's line
        self._events: Any = {}                  # the chapter's events, once the touched step has them
        self.tie_ops: list[dict] = []           # the replace operations kept for touched ties
        self.merged: list[dict] | None = None   # the reply's shifts with those operations merged in, when there are any

    def _write_check(self):
        """A check for one write step instance: strict on its first call, soft-tolerant on its second (the runner's last attempt). Only the
        echo is soft. A person on no card never refuses a reply: the chapter that is used has its counts recorded in the notes (interface
        M1) and its new names put to the trace as a soft note."""
        attempts = common.Attempts()

        def check(value):
            last = attempts.tick()
            hard, soft = write_findings(self.request, value)
            self.echo_accepted = False
            if hard:
                return hard
            if soft and not last:
                return soft[0][1]
            for kind, line in soft:
                common.note_soft("generate", "write", line)
            self.echo_accepted = any(kind == "echo" for kind, _ in soft)
            total, new = write_names(self.request, value)
            self.notes["minor_names"], self.notes["minor_new"] = total, len(new)
            if new:
                common.note_soft("generate", "write", common.load_text("generate")["write_problems"]["unknown_person"].format(names=", ".join(new)))
            return None
        return check

    def _step(self, n: int, results: list) -> Step:
        g = self.kit.grammar
        self._last = ("write", "events", "shifts")[n]
        if n == 0:
            return Step("write", lambda f: write_prompt(self.request, f), "text", WRITE_TOKENS, None, self._write_check(), "prose", True)
        chapter, events = results[0], results[1] if n > 1 else None

        def noted(key: str, value: Any):
            def fallback():
                self.notes[key] = True
                return value() if callable(value) else value
            return fallback
        if n == 1:
            return Step("events", lambda f: events_prompt(self.request, chapter, f), "json", EVENTS_TOKENS,
                        g.obj({"happened": g.text(), "changed": g.text()}), events_problem, "structured", True,
                        EVENTS_ATTEMPTS, noted("events_fallback", lambda: events_fallback(chapter)))
        return self._shifts_step(events, "", noted("shifts_fallback", {"shifts": []}))

    def _shifts_step(self, events: Any, extra: str, fallback) -> Step:
        g = self.kit.grammar
        return Step("shifts", lambda f: shifts_prompt(self.request, self.kit, events, f, extra), "json", SHIFTS_TOKENS,
                    g.obj({"shifts": g.shifts()}), lambda v: shifts_problem(self.request, self.kit, v), "structured", False,
                    SHIFTS_ATTEMPTS, fallback)

    def _resend_step(self, events: Any, first: Any, line: str) -> Step:
        """The shifts step once more, with a check's or the judge's line (the chapter is never written again). If this pass cannot be used either,
        the first shifts stand (they were usable)."""
        def keep_first():
            self.notes["edge_resend_fallback"] = True
            self._resend_failed = True
            return first
        return self._shifts_step(events, line, keep_first)

    def _edge_facts(self, events: Any) -> dict:
        """What the edge judge reads of the chapter: the events' `happened` and `changed`, and the planned outcome."""
        events = repair_events(events)
        return {"happened": r.s(events.get("happened")), "changed": r.s(events.get("changed")), "outcome": planned_outcome_line(self.request.get("beat") or {})}

    def _go(self, kind: str, step: Step) -> Step:
        self._last = kind
        return step

    def _check_step(self, edge: str, bond: str) -> Step:
        """The check of a new edge and bond, a step of its own after the shifts. Its last resort is a neutral verdict (ok)."""
        def neutral():
            self.notes["edge_check_fallback"] = True
            return {}
        return replace(advance.edge_check_step(self.request, edge, bond), attempts=JUDGE_ATTEMPTS, fallback=neutral)

    def _edge_step(self, old: str, new: str, facts: dict | None = None) -> Step:
        """The judge of the spotlight tie's new edge, a step of its own after the shifts. Its last resort is a neutral verdict (none)."""
        def neutral():
            self.notes["edge_judge_fallback"] = True
            return {}
        return replace(advance.edge_step(self.request, old, new, facts), attempts=JUDGE_ATTEMPTS, fallback=neutral)

    def _pressure_step(self, events: Any) -> Step:
        """The judge of the chapter's pressure, a step of its own after the shifts. It reads what the chapter's events say happened, not the
        chapter's text. Observe-only: its last resort is `unclear`, and nothing is ever sent back for its verdict."""
        def unclear():
            self.notes["pressure_judge_fallback"] = True
            return {"effect": "unclear"}
        happened = r.s(repair_events(events).get("happened"))
        aim = r.s((self.request.get("beat") or {}).get("aim"))
        return replace(advance.pressure_step(self.request, happened, "happened", aim), attempts=JUDGE_ATTEMPTS, fallback=unclear)

    def _touched_step(self, events: Any) -> Step:
        """Which of the other ties on stage did the chapter touch? A step of its own after the spotlight tie's check and judge. Its last resort is an empty list."""
        def none():
            self.notes["ties_touched_fallback"] = True
            return {"touched": []}
        return Step("ties_touched", lambda f: touched_prompt(self.request, self.kit, events), "json", TOUCHED_TOKENS, touched_grammar(), None, "structured", False,
                    JUDGE_ATTEMPTS, none)

    def _touched_tie(self) -> dict:
        return dict(_candidate_handles(self.request, self.kit))[self.touched[self._ti]]

    def _tie_edge_step(self, tie: dict, reason: str, events: Any, extra: str = "", first: tuple[str, str] | None = None) -> Step:
        """The new edge and bond of one touched tie. Its last resort is no edge (the tie stays as it is), or, for the pass sent back, the first reply."""
        def none():
            self.notes["tie_edge_fallback"] = True
            return {"edge": first[0], "bond": first[1]} if first else {"edge": "", "bond": ""}
        return Step("tie_edge", lambda f: tie_edge_prompt(self.request, tie, reason, events, extra), "json", TIE_EDGE_TOKENS, tie_edge_grammar(), tie_edge_problem,
                    "structured", False, SHIFTS_ATTEMPTS, none)

    def _tie_check_step(self, tie: dict, edge: str, bond: str) -> Step:
        """The check of the touched tie's new edge and bond: the spotlight tie's check, on this tie. Its last resort is a neutral verdict (ok)."""
        def neutral():
            self.notes["tie_check_fallback"] = True
            return {}
        return replace(advance.edge_check_step(self.request, edge, bond, tie=tie), attempts=JUDGE_ATTEMPTS, fallback=neutral)

    def _tie_judge_step(self, tie: dict, edge: str, events: Any) -> Step:
        """The judge of the touched tie's new edge: the spotlight tie's judge, on this tie, reading the chapter's facts without the planned outcome (that is the
        spotlight tie's). Its last resort is a neutral verdict (none)."""
        def neutral():
            self.notes["tie_judge_fallback"] = True
            return {}
        facts = {k: v for k, v in self._edge_facts(events).items() if k != "outcome"}
        return replace(advance.edge_step(self.request, r.s(tie.get("edge")), edge, facts, tie=tie), attempts=JUDGE_ATTEMPTS, fallback=neutral)

    def _next_tie(self, results: list):
        """The next touched tie is rewritten, or, when they are all done, the chain ends."""
        self._tie_new, self._tie_retried = ("", ""), False
        if self._ti >= len(self.touched):
            self._merge(results)
            return self._pressure(results)
        return self._go("tie_edge", self._tie_edge_step(self._touched_tie(), self._reasons.get(self.touched[self._ti], ""), self._events))

    def _merge(self, results: list) -> None:
        """The kept operations go into the entanglements entry of the shifts that stand. If the kit finds a problem in the merged entries, only the operations for
        touched ties are dropped."""
        if not self.tie_ops:
            return
        merged = merge_ties(self._shifts_of(results).get("shifts"), self.tie_ops)
        if self.kit.shifts_problem(merged):
            self.notes["ties_dropped"], self.notes["ties_rewritten"] = True, 0
            return
        self.merged = merged

    def _pressure(self, results: list):
        if not self.notes["pressure_on"]:
            return None
        return self._go("pressure", self._pressure_step(results[1]))

    def _end(self, results: list):
        """The spotlight tie is done: the step that finds the other touched ties runs once when there are candidates; each tie it names is rewritten; then the
        pressure judge when a pressure was sent."""
        if not self._touched_done:
            self._touched_done = True
            if _candidate_handles(self.request, self.kit):
                self._events = results[1]
                return self._go("touched", self._touched_step(results[1]))
        return self._pressure(results)

    def _shifts_of(self, results: list) -> Any:
        """The shifts the reply carries: the ones that stand after any pass the check or the judge asked for."""
        return results[self._shifts_at]

    def _resend(self, results: list, line: str) -> Step:
        """The shifts once more with `line`; the ones that stand now are the result of that pass (or the first ones, if it cannot be used)."""
        self._resend_failed = False
        return self._go("shifts", self._resend_step(results[1], results[self._shifts_at], line))

    def _check_or_end(self, results: list):
        """The check of the new edge and bond of the shifts that stand, when they replace the edge of a tie that must move; else the judge's turn."""
        shifts = results[self._shifts_at]
        edge = replaced_edge(self.request, self.kit, shifts)             # no edge replaced (the shifts fell back, say): nothing to check or judge
        if not edge:
            return self._end(results)
        return self._go("check", self._check_step(edge[1], replaced_bond(self.request, self.kit, shifts)))

    def _judge_or_end(self, results: list):
        """The edge judge: once for the shifts first made, and once more, for the record, for the shifts it sent back."""
        if self._judge_runs > (1 if self._edge_resent else 0):
            return self._end(results)
        edge = replaced_edge(self.request, self.kit, results[self._shifts_at])
        if not edge:
            return self._end(results)
        return self._go("edge", self._edge_step(*edge, self._edge_facts(results[1])))

    def next(self, results):
        """write, events, shifts, then for the spotlight tie's new edge and bond: a check (a model: is it a want with a concrete target, and a plain
        bond) and the edge judge. A check that says no sends the shifts back once with its reason; so does a judge that says `same` (when
        `advance.ENFORCE`); each of the two at most once. What a pass sent back for is then checked again for the record and accepted, whatever the
        verdicts say. The judge runs on the shifts that stand after the check, and once more after its own pass. Then, when other ties on stage are candidates, one step names
        the ones the chapter touched (`ties_touched`), and the pressure judge runs last."""
        n = len(results)
        if n < 3:
            return self._step(n, results)
        kind, value = "shifts" if n == 3 else self._last, results[-1]
        if kind == "touched":                                               # the touched ties are found: each is rewritten in turn, then the pressure judge
            found = touched_found(self.request, self.kit, value)
            self.touched, self._reasons = [h for h, _ in found], dict(found)
            self.notes["ties_touched"] = len(self.touched)
            self.notes["ties_rewritten"] = self.notes["ties_same"] = 0
            return self._next_tie(results)
        if kind == "tie_edge":                                              # a touched tie's new edge and bond
            edge, bond = r.s((value or {}).get("edge")), r.s((value or {}).get("bond"))
            self._tie_new = (edge, bond)
            if not edge:                                                    # none could be made: the tie stays as it is
                self._ti += 1
                return self._next_tie(results)
            if self._tie_retried:
                return self._go("tie_judge", self._tie_judge_step(self._touched_tie(), edge, self._events))
            return self._go("tie_check", self._tie_check_step(self._touched_tie(), edge, bond))
        if kind == "tie_check":                                             # a no sends the edge back once, and what comes back is accepted whatever the check says
            if not advance.check_ok(value):
                self._tie_retried = True
                self.notes["tie_check_resent"] = self.notes.get("tie_check_resent", 0) + 1
                return self._go("tie_edge", self._tie_edge_step(self._touched_tie(), self._reasons.get(self.touched[self._ti], ""), self._events,
                                                                advance.resend_line("edge_check", value), self._tie_new))
            return self._go("tie_judge", self._tie_judge_step(self._touched_tie(), self._tie_new[0], self._events))
        if kind == "tie_judge":                                             # `same` keeps the old edge and bond: no operation
            if advance.edge_ok(value):
                self.tie_ops.append(tie_operation(self.touched[self._ti], self._touched_tie(), *self._tie_new))
                self.notes["ties_rewritten"] += 1
            else:
                self.notes["ties_same"] += 1
            self._ti += 1
            return self._next_tie(results)
        if kind == "pressure":                                              # the pressure judge has run: record its word and stop
            self.notes.update(advance.notes(pressure_value=value))
            return None
        if kind == "shifts":
            if self._resend_failed:                                         # a pass that could not be used: the first shifts stand, and were checked already
                if self._edge_resent:
                    self.notes["edge_accepted"] = True
                    return self._end(results)
                return self._judge_or_end(results)
            self._shifts_at = n - 1
            return self._check_or_end(results)
        if kind == "check":
            word = advance.notes(check_value=value).get("edge_check")
            if word:
                self.notes["edge_check_after" if self._check_runs else "edge_check"] = word
            self._check_runs += 1
            if not advance.check_ok(value):
                if not self._check_resent and self._judge_runs == 0:
                    self._check_resent = True
                    self.notes["edge_check_resent"] = True
                    return self._resend(results, advance.resend_line("edge_check", value))
                self.notes["edge_check_accepted"] = True
            return self._judge_or_end(results)
        self._judge_runs += 1                                                 # the edge judge
        if self._judge_runs == 1:
            self.notes.update(advance.notes(edge_value=value))
            if advance.ENFORCE and not advance.edge_ok(value) and not self._edge_resent:
                self._edge_resent = True
                self.notes["edge_resent"] = True
                return self._resend(results, advance.resend_line("edge", value))
            return self._end(results)
        again = advance.notes(edge_value=value).get("edge_move")
        if again:
            self.notes["edge_move_after"] = again
        if not advance.edge_ok(value):
            self.notes["edge_accepted"] = True
        return self._end(results)

    def worst_case(self):
        events = {"happened": HAPPENED_STAND_IN, "changed": "word " * CHANGED_WORDS}
        steps = [self._step(0, []), self._step(1, ["word " * WRITE_TOKENS]), self._step(2, ["word " * WRITE_TOKENS, events])]
        targets = edge_targets(self.request, self.kit)
        if targets:
            old = max((r.s(t.get("edge")) for _, t in targets), key=len)
            facts = self._edge_facts(events)
            once = [self._check_step(EDGE_STAND_IN, EDGE_STAND_IN), self._edge_step(old, EDGE_STAND_IN, facts)]
            steps += once
            if advance.ENFORCE:
                steps += [self._shifts_step(events, RESEND_STAND_IN, None)] + once
        candidates = _candidate_handles(self.request, self.kit)
        if candidates:
            steps.append(self._touched_step(events))
            for _, tie in candidates:                  # each candidate could be touched: its edge, the check, the edge sent back once, and the judge
                steps += [self._tie_edge_step(tie, "word " * 40, events), self._tie_check_step(tie, EDGE_STAND_IN, EDGE_STAND_IN),
                          self._tie_edge_step(tie, "word " * 40, events, RESEND_STAND_IN, (EDGE_STAND_IN, EDGE_STAND_IN)), self._tie_judge_step(tie, EDGE_STAND_IN, events)]
        if self.notes["pressure_on"]:
            steps.append(self._pressure_step({"happened": HAPPENED_STAND_IN}))
        return steps

    def reply(self, results):
        text = results[0].strip()
        if self.echo_accepted:
            text, dropped = common.trim_echo(text, r.s(self.request.get("previous_ending")))
            if dropped:
                common.note_soft("generate", "write", f"{dropped} repeated opening sentence(s) dropped", what="trimmed")
        return {"chapter_text": text, "events": repair_events(results[1]), "shifts": self.merged if self.merged is not None else self._shifts_of(results)["shifts"]}


def build_flow(request, kit) -> Flow:
    return GenerateFlow(request, kit)


def script(request: dict, kit: Any) -> list[str]:
    """What a fake engine must return for a valid reply: a chapter, events, and shifts that replace the spotlight tie's edge; then, when other ties are on stage, the touched step (naming the first) and that tie's edge, check and judge."""
    shifts = []
    targets = edge_targets(request, kit)
    if targets:
        handle, tie = targets[0]
        shifts.append({"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": handle, "values": {"edge": f"to settle what this chapter opened ({tie.get('edge')})"}}]}})
    n = int(request["chapter"])
    pick = lambda words, k: words[(n * k) % len(words)]
    chapter = (f"By the time the {pick(['lantern', 'harbour', 'orchard', 'bridge', 'cellar'], 3)} bell stopped ringing, a {pick(['quarrel', 'bargain', 'rumour', 'wager', 'debt'], 7)} "
               f"over {pick(['bread', 'timber', 'cloth', 'rope', 'candles'], 2)} had spread through the {pick(['market', 'quarry', 'meadow', 'tavern', 'furnace'], 5)} on round {n}. "
               f"A clerk waited by the {pick(['gate', 'stairs', 'counter', 'window', 'stove'], 4)}, saying nothing. Round {n} cost {pick(['coins', 'keys', 'sacks', 'letters', 'barrels'], 6)} to somebody. "
               f"What was said at the table cost something, and what was left unsaid cost more, until the last choice of the night changed the room.")
    texts = [chapter, json.dumps({"happened": "The people met and quarrelled, and one of them gave something up.", "changed": "The tie and the aim now stand somewhere new."}),
             json.dumps({"shifts": shifts})] + ([json.dumps({"reason": "The edge names a target and the bond is a noun phrase.", "ok": "yes"}), json.dumps({"old_object": "object_a", "new_object": "object_b", "reason": "The want is now a different kind of want.", "move": "complicates"})] if targets else [])
    candidates = _candidate_handles(request, kit)
    if candidates:        # the touched-ties step runs after the edge judge: the fake engine names the first candidate, whose edge is then rewritten, checked and judged
        handle, tie = candidates[0]
        texts += [json.dumps({"touched": [{"tie": handle, "reason": "The two ends dealt with each other in this chapter."}]}),
                  json.dumps({"edge": f"to hold on to what this chapter changed ({tie.get('edge')})", "bond": ""}),
                  json.dumps({"reason": "The edge names a target.", "ok": "yes"}),
                  json.dumps({"old_object": "object_a", "new_object": "object_c", "reason": "The want now points at something else.", "move": "redirects"})]
    if request.get("pressure"):                # the pressure judge runs last, whenever a pressure was sent
        texts.append(json.dumps({"reason": "The element cost one of them something.", "effect": "acts"}))
    return texts
