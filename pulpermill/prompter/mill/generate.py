"""The `generate` call, three steps: `write` (the chapter as prose), `events` (what happened, what changed) and `shifts` (what changed on the
cards). Wording lives in text/en/generate.yaml, where the reasoning behind the writer prompt is recorded.

Rules served: R3 (an interesting story, craft guidance in prose), R5 (minor characters by role, never the plot), R6 (the spotlight tie's edge
and the protagonist's aim end in a new state; the shifts check demands the edge), R7 (the chapter follows the plan's four points unlabelled).

The generate request carries the spotlight tie's id inside the beat (`beat.spotlight`, one of the ties sent), and the tie is that one. A request
without it, or with an id that is not among its ties, falls back to the old reading: the planner is told to name both ends of the tie in the
plan, so the tie is the one whose two ends the beat's plan names, and if none or several are named, any of the named ties (or any tie)
satisfies the edge check. The id never reaches a prompt: the model sees the tie's names and its handle."""
import json
import re
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step
from pulpermill.schema.shifts import shiftable_fields

from . import common
from .plan import cut_events, in_names, names_of, protagonist_name, spotlight_candidates, spotlight_in_words, spotlight_of, tiers, _norm

VERSION = "generate-6"

# The chapter's length (decided 3 Nov): at most 1,200 words, or 2,400 Han characters for Chinese (twice the word figure, as in tools/trial_checks.mjs).
# WRITE_TOKENS is a safety net so a chapter is never cut mid-sentence, not a target. Measured with pulpermill/prompts/tokens.py on ordinary narrative
# prose with dialogue (a 254-word sample repeated to length): 1,200 English words = 1,402 tokens; 2,400 Chinese characters = 2,041 tokens.
# The larger count (Chinese) plus 25 percent is 2,551, rounded up to 2,560. English alone would need only about 1,760.
CAP_WORDS, CAP_HAN = 1200, 2400
OVERSHOOT_WORDS, OVERSHOOT_HAN = 1500, 3000      # the write check only speaks above these, so a few extra words never cost a second attempt
WRITE_TOKENS = 2560
EVENTS_TOKENS = 800
SHIFTS_TOKENS = 1600
EVENTS_ATTEMPTS, SHIFTS_ATTEMPTS = 4, 3          # after the chapter is written, each of these steps is retried on its own and then falls back
CHANGED_WORDS, HAPPENED_WORDS = 45, 60           # the most words `changed` keeps (one short sentence) and the fallback's `happened` keeps


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

    scene_beat = {**{k: v for k, v in beat.items() if k != "spotlight"}, "cast": cast_names}     # the tie's id is never shown
    if spot:
        scene_beat["spotlight"] = spot
    with tx.squeeze(cast_f):
        cast_text = r.render_cast(cast, scope="writer")
    with tx.squeeze(world_f):
        world_text = r.render_world(request.get("world") or {}, scope="writer", place=r.s(beat.get("where")) or None,
                                    in_play=r.groups_in_play({"ties": ties}))
    events = cut_events(request.get("earlier_events"), chapter, history_ratio)
    keep = max(1, round(tx.limits()["events"]["full_chapters_writer"] * min(1.0, history_ratio)))
    history = r.render_history(events, chapter, scope="writer", keep_full=keep)
    ending = r.s(request.get("previous_ending"))
    last = bool(total) and chapter >= total
    craft = [w["craft_interest"], w["craft_dialogue"], w["craft_turn"], w["craft_people"], w["craft_change_last" if last else "craft_change"]]
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
    3,000 Han characters for Chinese; under the cap, or a little over it, passes and a short chapter is never rejected). Soft, in this order:
    the opening repeats a sentence of the previous chapter's ending ("echo"); the chapter names a person who is on no card ("unknown_person";
    English only, and a plain name must come back at least twice, because a good chapter costs more than a missed name)."""
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
    strangers = common.names_found(request, [body], _card_text(request), min_count=2)
    if strangers:
        soft.append(("unknown_person", p["unknown_person"].format(names=", ".join(strangers))))
    return None, soft


def write_problem(request: dict, text: Any, tolerate_soft: bool = False) -> str | None:
    """One plain line saying what to fix, or None. A hard problem always speaks; a soft one (the echo, then the unknown person) speaks
    unless `tolerate_soft` (the last attempt), when the reply is let through."""
    hard, soft = write_findings(request, text)
    if hard:
        return hard
    return soft[0][1] if soft and not tolerate_soft else None


def _card_text(request: dict) -> list:
    """What the writer may take names from: the cards the request carries and the beat the person approved. Not the earlier chapters' records."""
    return [request.get(k) for k in ("cast", "world", "ties", "holdings", "setup", "style", "beat")]


# ---- events ----------------------------------------------------------------------------------------------------------------

def events_prompt(request: dict, chapter_text: str, factor: float = 1.0) -> str:
    w = common.load_text("generate")
    names = names_of(request)
    beat = request.get("beat") or {}
    candidates, identified = _spot(request, names)
    tie = ""
    if identified and len(candidates) == 1:
        t = spotlight_in_words(candidates[0], names)
        tie = w["events_tie"].format(tie_from=t["tie_from"], tie_to=t["tie_to"], edge=r.s(t.get("edge")))
    parts = [w["events_task"].format(chapter=request["chapter"], language=_lang(request)),
             w["events_chapter_lead"] + "\n" + chapter_text.strip(),
             w["events_aim"].format(aim=r.sentence(r.s(beat.get("aim"))), tie=tie).strip(),
             w["events_format"]]
    return "\n\n".join(parts)


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
    """`changed` as one short sentence: its first sentence, cut to CHANGED_WORDS words. Everything else is left as it came."""
    out = dict(value or {})
    first = sentences(out.get("changed"))
    out["changed"] = _words(first[0], CHANGED_WORDS) if first else r.s(out.get("changed"))
    return out


def events_fallback(chapter_text: str) -> dict:
    """What `events` says when no model reply could be used: plain code over the chapter (no model call). `happened` is the chapter's opening
    sentences, `changed` its last sentence, both in the chapter's own language."""
    found = sentences(chapter_text)
    if not found:
        return {"happened": r.s(chapter_text)[:400], "changed": ""}
    return {"happened": _words(" ".join(found[:2]), HAPPENED_WORDS), "changed": _words(found[-1], CHANGED_WORDS)}


# ---- shifts ----------------------------------------------------------------------------------------------------------------

def _item_line(item: dict, factor: float) -> str:
    parts = [r.s(v) for k, v in item.items() if k != "id" and isinstance(v, (str, int, float)) and r.s(v)]
    return common.clip(" — ".join(parts), factor)


def _reference(request: dict, kit: Any, names: dict[str, str], factor: float) -> str:
    """Every card the model may change, with the handle of each list item, so that it points at items without seeing an id."""
    out = []
    people = {p.get("id"): p for p in request.get("cast") or []}
    for scope in kit.handles.of_card("characters"):
        person = people.get(scope.target) or {}
        lines = [f"{scope.label}: " + common.clip(r.s(person.get("sketch")), factor)]
        for key in scope.lists:
            for item in person.get(key) or []:
                if item.get("id"):
                    lines.append(common.labelled(scope, key, item["id"], _item_line(item, factor)))
        out.append("\n".join(lines))
    for scope in kit.handles.of_card("world"):
        world = request.get("world") or {}
        lines = [f"The world, {r.s(world.get('name'))}:"]
        for key in scope.lists:
            for item in world.get(key) or []:
                if item.get("id"):
                    lines.append(common.labelled(scope, key, item["id"], _item_line(item, factor)))
        out.append("\n".join(lines))
    for scope in kit.handles.of_card("entanglements"):
        lines = ["The ties and holdings:"]
        for item in in_names(request.get("ties") or [], ("tie_from", "tie_to"), names):
            if item.get("id"):
                text = f"{item['tie_from']} toward {item['tie_to']}: {r.bare(item.get('bond'))}. Edge: {r.s(item.get('edge'))}"
                lines.append(common.labelled(scope, "ties", item["id"], common.clip(text, factor)))
        for item in in_names(request.get("holdings") or [], ("holdee", "held_by"), names):
            if item.get("id"):
                lines.append(common.labelled(scope, "holdings", item["id"], f"{item['held_by']} holds {item['holdee']}"))
        out.append("\n".join(lines))
    return "\n\n".join(out)


def _shift_fields(card: str) -> str:
    return ", ".join(f["key"] for f in shiftable_fields(card))


def edge_targets(request: dict, kit: Any) -> list[tuple[str, dict]]:
    """[(handle, tie)] for the ties whose edge must move: the identified spotlight tie, else any tie."""
    names = names_of(request)
    candidates, _ = _spot(request, names)
    scopes = kit.handles.of_card("entanglements")
    if not scopes:
        return []
    return [(scopes[0].of("ties", t["id"]), t) for t in candidates if t.get("id")]


def shifts_prompt(request: dict, kit: Any, chapter_text: str, factor: float = 1.0) -> str:
    w = common.load_text("generate")
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
             w["shifts_chapter_lead"] + "\n" + chapter_text.strip(),
             w["shifts_cards_lead"] + "\n" + _reference(request, kit, names, factor),
             w["shifts_rules"],
             w["shifts_fields"].format(character=_shift_fields("characters"), world=_shift_fields("world"), entanglements=_shift_fields("entanglements")),
             w["shifts_example"], edge, w["shifts_format"]]
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


# ---- the flow --------------------------------------------------------------------------------------------------------------

class GenerateFlow(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit
        self.echo_accepted = False          # the write reply that was used carried an echo that the last attempt let through
        self.notes = {"events_fallback": False, "shifts_fallback": False}      # for the run log: did a step's last resort stand in for it?

    def _write_check(self):
        """A check for one write step instance: strict on its first call, soft-tolerant on its second (the runner's last attempt)."""
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
            return None
        return check

    def _step(self, n: int, results: list) -> Step:
        g = self.kit.grammar
        if n == 0:
            return Step("write", lambda f: write_prompt(self.request, f), "text", WRITE_TOKENS, None, self._write_check(), "prose", True)
        chapter = results[0]

        def noted(key: str, value: Any):
            def fallback():
                self.notes[key] = True
                return value() if callable(value) else value
            return fallback
        if n == 1:
            return Step("events", lambda f: events_prompt(self.request, chapter, f), "json", EVENTS_TOKENS,
                        g.obj({"happened": g.text(), "changed": g.text()}), events_problem, "structured", True,
                        EVENTS_ATTEMPTS, noted("events_fallback", lambda: events_fallback(chapter)))
        return Step("shifts", lambda f: shifts_prompt(self.request, self.kit, chapter, f), "json", SHIFTS_TOKENS,
                    g.obj({"shifts": g.shifts()}), lambda v: shifts_problem(self.request, self.kit, v), "structured", False,
                    SHIFTS_ATTEMPTS, noted("shifts_fallback", {"shifts": []}))

    def next(self, results):
        return self._step(len(results), results) if len(results) < 3 else None

    def worst_case(self):
        chapter = "word " * WRITE_TOKENS
        return [self._step(n, [chapter, {}]) for n in range(3)]

    def reply(self, results):
        text = results[0].strip()
        if self.echo_accepted:
            text, dropped = common.trim_echo(text, r.s(self.request.get("previous_ending")))
            if dropped:
                common.note_soft("generate", "write", f"{dropped} repeated opening sentence(s) dropped", what="trimmed")
        return {"chapter_text": text, "events": repair_events(results[1]), "shifts": results[2]["shifts"]}


def build_flow(request, kit) -> Flow:
    return GenerateFlow(request, kit)


def script(request: dict, kit: Any) -> list[str]:
    """What a fake engine must return for a valid reply: a chapter, events, and shifts that replace the spotlight tie's edge."""
    shifts = []
    for scope in kit.handles.of_card("characters")[:1]:
        shifts.append({"card": "characters", "target": scope.label, "patch": {"sketch": "Changed by what happened in this chapter."}})
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
    return [chapter, json.dumps({"happened": "The people met and quarrelled, and one of them gave something up.", "changed": "The tie and the aim now stand somewhere new."}),
            json.dumps({"shifts": shifts})]
