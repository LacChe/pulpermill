"""The `plan` call: a free-text brainstorm of three ways to take the running aim its next step, then one JSON step that designs the chapter from
them. The planner collides the protagonist's aim with the spotlight tie (R4), designs the chapter in four points inside the
`plan` text (R7), and ends in a state where both have moved (R6). Minor characters appear by role only (R5). The brainstorm only helps the plan:
if it cannot be had, the plan goes ahead without it. Wording lives in text/en/plan.yaml; this module assembles it from the renderers and checks
the reply.

Helpers at the top (names, ties in words, squeeze tiers, the spotlight) are shared with generate.py."""
import copy
import math
import re
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step

from . import advance, common, decide, driver, repeat, select

VERSION = "plan-28"
IDEA = "idea"            # in choose mode: the number (1 to 3) of the idea the plan builds on, which is also the number of its combination; the reply turns it into `picked`
IDEA_USE = "idea_use"      # the plan step's own account of which brainstorm idea it built on: for the run's trace only, never in the reply
MAX_OUTPUT = 1000          # where + when + aim + about 150 words of plan, with room to spare; the context keeps this much free
POINTS = ("1", "2", "3", "4")
BRAINSTORM_OUTPUT = 1200      # three ideas of about 130 words each need roughly 600 tokens; the rest is room to spare, so a cut-off tail is the exception
BRAINSTORM_ATTEMPTS = 2       # then the plan goes ahead without a brainstorm: it is a help to the plan, never a reason to fail a call
BRAINSTORM_MIN_CHARS = 120    # three options cannot be told in less
BRAINSTORM_STAND_IN = "word " * BRAINSTORM_OUTPUT       # the longest a brainstorm can be as the plan prompt carries it (a token a word), for the worst case


# ---- Shared helpers -------------------------------------------------------------------------------------------------------

def language_name(code: str | None) -> str:
    names = common.load_text("plan")["languages"]
    code = str(code or "en")
    return names.get(code) or names.get(code.split("-")[0]) or code


def tiers(factor: float) -> tuple[float, float, float]:
    """The squeeze order, as three factors for one squeeze `factor`: oldest history is cut first (from 0.85 down), then world detail
    (below 0.85), then cast texture (below 0.7). The plan, the scene, the spotlight tie and the style rules are never cut."""
    return factor, (1.0 if factor >= 0.85 else factor), (1.0 if factor >= 0.7 else factor)


def pressure_of(request: dict, factor: float = 1.0) -> dict | None:
    """The pressure a prompt carries, in words: the request's `pressure`, unless a squeeze asks for room. The pressure sentence is the first
    thing a squeeze drops (before any history, world or cast text), and the element then stands in its world list again."""
    pressure = request.get("pressure")
    return pressure if isinstance(pressure, dict) and pressure and factor >= 1.0 else None


def names_of(request: dict) -> dict[str, str]:
    return r.names_by_id({"world": request.get("world") or {}, "characters": request.get("cast") or []})


def in_names(items: list[dict], keys: tuple[str, ...], names: dict[str, str]) -> list[dict]:
    return r.in_words(items, {k: {"ref": True} for k in keys}, names)


def protagonist_name(request: dict, names: dict[str, str]) -> str:
    return names.get(request.get("protagonist") or "", "")


def spotlight_in_words(tie: dict, names: dict[str, str]) -> dict:
    return in_names([tie], ("tie_from", "tie_to"), names)[0]


def cut_events(events: list[dict], chapter: int, ratio: float) -> list[dict]:
    """The events before `chapter`, with the oldest dropped when `ratio` is below 1 (always at least the newest one)."""
    rows = sorted((e for e in events or [] if 0 < int(e.get("chapter") or 0) < chapter), key=lambda e: int(e["chapter"]))
    if ratio >= 1.0 or not rows:
        return rows
    return rows[-max(1, math.ceil(len(rows) * ratio)):]


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(text or "").lower())).strip()


def _words(text: Any) -> set[str]:
    """The words of a text that tell it from another (over three letters). Han text has no spaces, so its pieces are character pairs."""
    out: set[str] = set()
    for w in _norm(text).split():
        if common.han_count(w):
            runs = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", w)
            out.update(run[i:i + 2] for run in runs for i in range(max(1, len(run) - 1)))
        elif len(w) > 3:
            out.add(w)
    return out


_FILLER = {"the", "and", "for"}


def _mentions_part(text: str, name: str) -> bool:
    """True when any part of `name` stands in `text` as a whole word. A name splits at every character that is not a letter or digit, so "O'Brien"
    and "Smith-Jones" give parts, and parts of under 3 characters or the filler words ("the", "and", "for") are skipped: "O" or "The Baker's Guild"
    is then not met by every plan."""
    low = str(text or "").lower()
    parts = [w for w in re.split(r"[\W_]+", name.lower()) if len(w) >= 3 and w not in _FILLER]
    return any(re.search(rf"(?<![^\W_]){re.escape(w)}(?![^\W_])", low) for w in parts)


def spotlight_of(request: dict) -> dict | None:
    """The spotlight tie of a `generate` request: the one tie whose id is `beat.spotlight`, which the page sends inside the beat. None when the
    key is missing or names a tie that is not among the request's ties (a legacy-shaped request): the caller then falls back to
    `spotlight_candidates`. The id is only used here, to pick the tie; it never reaches a prompt."""
    beat = request.get("beat")
    wanted = beat.get("spotlight") if isinstance(beat, dict) else None
    if not isinstance(wanted, str) or not wanted:
        return None
    return next((t for t in request.get("ties") or [] if t.get("id") == wanted), None)


def spotlight_candidates(request: dict, names: dict[str, str]) -> list[dict]:
    """The ties a `generate` request may mean by the spotlight when it does not say (see `spotlight_of`): the ties whose two ends are both
    named in the beat's plan or aim, which the planner is told to do. None named: no candidates, and the caller falls back to any tie."""
    beat = request.get("beat") or {}
    text = f"{beat.get('aim', '')} {beat.get('plan', '')}"
    out = []
    for tie in request.get("ties") or []:
        a, b = names.get(tie.get("tie_from"), ""), names.get(tie.get("tie_to"), "")
        if a and b and _mentions_part(text, a) and _mentions_part(text, b):
            out.append(tie)
    return out


# ---- Earlier chapters, labelled (repeat.py) ---------------------------------------------------------------------------------------

NAME_MAX = 100       # the longest a rule is written in the labeler's list of names: the labeler copies it back, so it is short


def label_items(request: dict) -> list[tuple[int, str]]:
    """The earlier chapters the labeler describes: the last K chapters before this one that have events, each as (chapter, what happened and what
    changed, then one more line with the chapter's planned aim when `earlier_beats` has it). Empty in chapter 1 and for a request with no earlier events: the flow then has no label step."""
    chapter = int(request.get("chapter") or 0)
    aims = {int(b["chapter"]): r.s(b.get("aim")) for b in request.get("earlier_beats") or [] if isinstance(b, dict) and isinstance(b.get("chapter"), int) and r.s(b.get("aim"))}
    rows = []
    for e in cut_events(request.get("earlier_events"), chapter, 1.0):
        text = " ".join(r.sentence(x) for x in (r.s(e.get("happened")), r.s(e.get("changed"))) if x)
        aim = aims.get(int(e["chapter"]))
        if text and aim:                                       # the chapter's planned aim: it is where the reason for the pursuit is stated
            text += "\n" + common.load_text("plan")["label_item_aim"].format(aim=r.sentence(aim))
        if text:
            rows.append((int(e["chapter"]), text))
    return rows[-repeat.K:]


def label_names(request: dict) -> list[str]:
    """The names the labeler may give as an obstacle's party: the cast, the groups, the rules and the objects, in words (a rule is its statement, cut
    short, as the planner sees it), without repeats."""
    world = request.get("world") or {}
    rows = [r.s(c.get("name")) for c in request.get("cast") or []] + [r.s(g.get("name")) for g in world.get("powers") or []]
    rows += [r.s(x.get("statement"))[:NAME_MAX] for x in world.get("rules") or []] + [r.s(o.get("name")) for o in world.get("objects") or []]
    return list(dict.fromkeys(n for n in (row.strip().rstrip(".!?…。！？").strip() for row in rows) if n))


def used_text(used: list[dict] | None, w: dict) -> str:
    """The "already used" table: one line for each labelled earlier chapter (its number, the seven labels, the note), oldest first, under a lead. Empty
    when no chapter was labelled."""
    if not used:
        return ""
    def words(value: str) -> str:
        return value.replace("_", " ")
    lines = []
    for row in used:
        party = w["used_party"].format(party=row["obstacle_party"]) if row["obstacle_party"] != repeat.NO_PARTY else ""
        motive = row.get("motive_kind", "other")
        driven = w["used_driven"].format(motive_kind=words(motive)) if motive != "other" else ""        # a motive that says nothing is left out
        lines.append(w["used_item"].format(chapter=row["chapter"], aim_kind=words(row["aim_kind"]), obstacle_source=words(row["obstacle_source"]), party=party,
                                           turning_kind=words(row["turning_kind"]), outcome=words(row["outcome"]), closing_hook=words(row["closing_hook"]),
                                           driven=driven, note=row["turning_note"]).strip())
    return w["used_lead"] + "\n" + "\n".join(lines)


def _used_stand_in() -> list[dict]:
    """The longest "already used" table, for the worst case."""
    longest = {k: max(v, key=len) for k, v in repeat.VALUES.items()}
    return [{"chapter": 100 + i, **longest, "obstacle_party": "word " * 20, repeat.NOTE: "w" * repeat.NOTE_MAX} for i in range(repeat.K)]


# ---- The prompt -----------------------------------------------------------------------------------------------------------

def _section(heading: str, body: str) -> str:
    return f"## {heading}\n{body}" if body else ""


def _chapter_note(w: dict, chapter: int, total: int) -> str:
    if chapter == 1:
        return w["first_chapter"]
    if total and chapter >= total:
        return w["last_chapter"]
    return w["middle_chapter"]


def other_end(request: dict, names: dict[str, str]) -> str:
    """The person at the other end of the spotlight tie from the protagonist (the to end when the protagonist is on neither end)."""
    tie = next((t for t in request.get("ties") or [] if t.get("id") == request.get("spotlight")), None) or {}
    a, b = names.get(tie.get("tie_from"), ""), names.get(tie.get("tie_to"), "")
    me = protagonist_name(request, names)
    return (a if me and me == b else b) or a or "the other person in the tie"


def chain_text(request: dict, w: dict, factor: float = 1.0) -> str:
    """The running aim as the planner prompts carry it: each earlier chapter's aim and how that chapter ended (its `changed` line), oldest
    first, with the latest chapter marked and its ending given last as where the aim stands now. Empty in chapter 1, which has no chain."""
    links = advance.chain(request, factor)
    if not links:
        return ""
    lines = []
    for i, link in enumerate(links):
        latest = i == len(links) - 1
        line = w["chain_latest" if latest else "chain_item"].format(chapter=link["chapter"], aim=r.s(link["aim"]))
        if link["changed"] and not latest:
            line += w["chain_ended"].format(changed=link["changed"])
        lines.append(line)
    if links[-1]["changed"]:
        lines.append(w["chain_now"].format(chapter=links[-1]["chapter"], changed=links[-1]["changed"]))
    return w["chain_lead"] + "\n" + "\n".join(lines)


def _context(request: dict, factor: float, combos: list[dict] | None = None, used: list[dict] | None = None) -> dict:
    """What the brainstorm prompt and the plan prompt share: the names, the tie, the chapter's place in the story, and every section that
    comes before the task. The running aim (`chain_text`) closes the story so far. `combos`
    (choose mode) puts the three combinations in the place of the spotlight section; `request` is then one with no spotlight and no pressure.
    `used` (the labelled earlier chapters, from repeat.py) adds the "already used" table after the running aim; a squeeze drops it first of all,
    as it does the pressure sentence."""
    w = common.load_text("plan")
    names = names_of(request)
    chapter, total = int(request["chapter"]), int(request.get("chapter_count") or 0)
    history_ratio, world_f, cast_f = tiers(factor)
    heads = w["headings"]
    cast = request.get("cast") or []
    tie = next((t for t in request["ties"] if t["id"] == request["spotlight"]), None) or {}
    tie_words = spotlight_in_words(tie, names) if tie else {}
    ties = in_names(request.get("ties") or [], ("tie_from", "tie_to"), names)
    holdings = in_names(request.get("holdings") or [], ("holdee", "held_by"), names)

    with tx.squeeze(cast_f):
        cast_text = r.render_cast(cast, scope="planner", pick=str(request.get("chapter")))      # one want and one value a person, the same for every planning step of this chapter
    pressure = pressure_of(request, factor)
    with tx.squeeze(world_f):
        world_text = r.render_world(request.get("world") or {}, scope="planner", without=pressure)
    spotlight_text = r.render_spotlight(tie_words, cast, scope="planner", names=names, pick=str(request.get("chapter"))) if tie else ""
    spotlight_text = "\n".join(x for x in (spotlight_text, r.render_pressure(pressure)) if x)       # one sentence inside the spotlight section
    spotlight_head = heads["spotlight"]
    if combos is not None:
        spotlight_head, spotlight_text = heads["combination" if len(combos) == 1 else "combinations"], select.combos_text(combos, w)

    events = cut_events(request.get("earlier_events"), chapter, history_ratio)
    keep = max(1, round(tx.limits()["events"]["full_chapters_planner"] * min(1.0, history_ratio)))
    history = r.render_history(events, chapter, scope="planner", keep_full=keep)
    beats = [{**b, "when_time": b.get("when_time") or b.get("when")} for b in request.get("earlier_beats") or []]
    timeline = r.render_earlier_beats(beats)
    chain = chain_text(request, w, history_ratio)
    table = used_text(used, w) if factor >= 1.0 else ""

    origin = r.render_origin_history(request.get("setup") or {}, chapter) if request.get("origin_history", True) else ""      # chapters 2+ only, and only when the page asks
    setup = r.render_setup(request.get("setup") or {}, chapter, total or None, protagonist_name=protagonist_name(request, names), origin=origin)
    setup_block = _section(heads["setup"], setup)
    history_block = _section(heads["history"], "\n\n".join(x for x in (history, timeline, chain, table) if x))
    blocks = [
        _section(heads["tone"], r.render_style(request.get("style") or {}, scope="planner")),
        setup_block,
        _section(heads["cast"], cast_text),
        _section(heads["world"], world_text),
        _section(heads["entanglements"], r.render_entanglements({"ties": ties, "holdings": holdings}, scope="planner")),
        _section(spotlight_head, spotlight_text),
        history_block,
    ]
    return {"w": w, "names": names, "chain": chain, "table": table, "chapter": chapter, "total": total, "heads": heads, "tie": tie, "blocks": blocks,
            "setup_block": setup_block, "history_block": history_block}       # the decider reads only these two, not the cards


def _task_block(c: dict, method: str) -> list[str]:
    """The lines of the task that both prompts open with: the collision (R4, in `method`'s wording) and what makes an aim (R4/R6)."""
    w = c["w"]
    return [w[method], w["aim_rules"]]


def build_brainstorm_prompt(request: dict, factor: float = 1.0, combos: list[dict] | None = None, used: list[dict] | None = None) -> str:
    """The brainstorm step's prompt: the same cards and history as the plan, with the earlier aims shown as the kinds already used, and a task
    that asks for three chapters of different kinds. Free text out; nothing here asks for the plan's shape. With `combos` (choose mode) the
    three chapters are one for each combination, and no single spotlight is shown. With `used` (and no squeeze) the history carries the "already
    used" table and the task asks each idea to differ from every line of it."""
    if combos is not None:
        request = select.without_pair(request)
    c = _context(request, factor, combos=combos, used=used)
    w, names, chapter, total = c["w"], c["names"], c["chapter"], c["total"]
    role = w["brainstorm_role"].format(chapter=chapter, total=total) if total else w["brainstorm_role_unknown_total"].format(chapter=chapter)
    task = _task_block(c, "brainstorm_method")
    task.append(w["brainstorm_task"])
    task.append(w["brainstorm_outcomes"])
    if combos is not None:
        task.append(w["brainstorm_combos"])
    if factor >= 1.0:                                          # a squeeze drops the driver lines with the "already used" table; with fewer than two kinds there are none
        task.append(driver.text(request, w))
    task.append(w["brainstorm_parts"].format(other=other_end(request, names)))
    task.append(w["brainstorm_risk"])
    if chapter > 1:
        task.append(w["brainstorm_variety"])
        if c["table"]:
            task.append(w["brainstorm_used"])
        task.append(w["brainstorm_continue"])
        if request.get("origin_history", True) and r.s((request.get("setup") or {}).get("disruption")):       # only when the prompt carries the disruption
            task.append(w["brainstorm_disruption"])
    task.append(w["brainstorm_people"])
    if chapter == 1:
        task.append(w["brainstorm_first"])
    elif total and chapter >= total:
        task.append(w["brainstorm_last"])
    else:
        task.append(w["middle_chapter"])
    retry = request.get("retry")
    if retry:
        beat = retry.get("beat") or {}
        problems = " ".join(r.sentence(p) for p in retry.get("problems") or [])
        task.append(w["brainstorm_retry"].format(aim=r.sentence(r.s(beat.get("aim"))), problems=problems))
    task.append(w["brainstorm_output"].format(language=language_name(request.get("language"))))
    blocks = [role, *c["blocks"], _section(c["heads"]["task"], "\n\n".join(x for x in task if x))]
    return "\n\n".join(b for b in blocks if b)


OUTCOMES = {n: "outcome_" + e for n, e in common.ENDINGS.items()}     # the number of an idea fixes how it ends (the brainstorm contract)


def build_prompt(request: dict, factor: float = 1.0, brainstorm: str = "", combos: list[dict] | None = None, decided: bool = False,
                 outcome: int = 0, used: list[dict] | None = None, avoid: list[str] | None = None) -> str:
    """The plan step's prompt. `brainstorm` is the text of the brainstorm step: with it, the prompt carries it under its own heading and tells
    the planner to choose from it; without it (no brainstorm, or one that could not be had) the prompt is the plan prompt on its own. With `combos`
    (choose mode) the three combinations stand in the place of the spotlight, and the plan chooses one idea (or, with no brainstorm, one
    combination) and is built on its tie and its rule or object. With `decided` the brainstorm is the one idea the decider chose, shown as idea 1
    (and `combos` is its combination alone): the plan is told to build on it, not to choose among ideas. With `decided` and an `outcome` of 1, 2 or 3 (the
    picked idea's place in the brainstorm, which fixes how it ends: reached at a price, lost, given up) the prompt also says that ending stands.
    Without a decision, or with outcome 0, no outcome line is added. With `used` the history carries the "already used" table (dropped under a squeeze).
    With `avoid` (the names of the fingerprint fields the only idea left still shares with an earlier chapter) the task says the chapter must change
    those aspects."""
    if combos is not None:
        request = select.without_pair(request)
    c = _context(request, factor, combos=combos, used=used)
    w, names, chapter, total, heads, tie = c["w"], c["names"], c["chapter"], c["total"], c["heads"], c["tie"]
    kind = "decided" if decided else None
    tail = "_chain" if c["chain"] else ""
    ends = [names.get(tie.get("tie_from"), ""), names.get(tie.get("tie_to"), "")] if tie else ["", ""]
    task = _task_block(c, "method")
    if combos is not None:
        task.append(w["decided_one" if kind else "choose_one"] if brainstorm else w["choose_combo"])
        if brainstorm:
            task.append(w[("decided_number" if kind else "idea_number") + tail])
    elif brainstorm:
        task.append(w["decided_from" if kind else "choose_from"])
        task.append(w[("decided_use" if kind else "idea_use") + tail])
    if kind and brainstorm and outcome in OUTCOMES:
        task.append(w[OUTCOMES[outcome]])
    if avoid:
        task.append(w["avoid_line"].format(aspects=", ".join(w["avoid_fields"][f] for f in avoid if f in w["avoid_fields"])))
    task += [
        w["four_points"],
        w["other_person"].format(other=other_end(request, names)),
        w["spotlight_names"].format(tie_from=ends[0], tie_to=ends[1]) if all(ends) else "",
        w["movement_last" if total and chapter >= total else "movement"].format(tie_from=ends[0] or "the person at the from end"),
        w["people_rule"],
        _chapter_note(w, chapter, total),
    ]
    retry = request.get("retry")
    if retry:
        beat = retry.get("beat") or {}
        problems = " ".join(r.sentence(p) for p in retry.get("problems") or [])
        task.append(w["retry_lead"].format(aim=r.sentence(r.s(beat.get("aim"))), plan=r.sentence(r.s(beat.get("plan")))) + " " + problems)
        task.append(w["retry_close"])
    task.append(w["output"].format(language=language_name(request.get("language"))))

    role = w["role"].format(chapter=chapter, total=total) if total else w["role_unknown_total"].format(chapter=chapter)
    blocks = [role, *c["blocks"], _section(heads["decided" if decided else "brainstorm"], brainstorm.strip()), _section(heads["task"], "\n\n".join(x for x in task if x))]
    return "\n\n".join(b for b in blocks if b)


# ---- The check ------------------------------------------------------------------------------------------------------------

def _first_verb_text(aim: str, phrases: list[str]) -> str:
    text = _norm(aim)
    best = None
    for p in phrases:
        m = re.search(rf"\b{re.escape(p)}\b", text)
        if m and m.start() <= 40 and (best is None or m.end() > best):
            best = m.end()
    return text[best:].strip() if best else text


def aim_is_abstract(aim: str) -> bool:
    w = common.load_text("plan")
    core = _first_verb_text(aim, w["aim_lead_phrases"])
    if common.size(_norm(aim)) < 3:
        return True
    first = core.split()[0] if core else ""
    return first in w["abstract_verbs"] or any(core.startswith(s) for s in w["abstract_starts"])


def plan_points(text: str) -> list[str]:
    """The labels Act 1 to Act 4 that start a usable point (at least three words after the label), in the order found."""
    marks = list(re.finditer(r"\bAct\s*([1-4])\b", text or ""))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        if common.size(re.sub(r"[^\w\s]", " ", text[m.end():end])) >= 3:
            out.append(m.group(1))
    return out


def plan_problem(request: dict, value: Any) -> str | None:
    """None when the plan is usable, else one plain line saying what to fix: no place, no aim, an abstract or repeated aim, the plan not in
    the four points in order, a spotlight end the plan does not name. A person on no card is never a problem here (see `plan_names`)."""
    p = common.load_text("plan")["problems"]
    names = names_of(request)
    beat = value if isinstance(value, dict) else {}
    where, aim, plan = r.s(beat.get("where")), r.s(beat.get("aim")), r.s(beat.get("plan"))
    if not where:
        return p["missing_where"]
    if not aim:
        return p["missing_aim"]
    if aim_is_abstract(aim):
        return p["abstract_aim"]
    retry = (request.get("retry") or {}).get("beat") or {}
    if retry and _norm(retry.get("aim")) == _norm(aim):
        return p["same_as_retry"].format(aim=r.s(retry.get("aim")))
    for b in sorted(request.get("earlier_beats") or [], key=lambda b: int(b.get("chapter") or 0)):
        old = _words(b.get("aim"))
        if old and len(old & _words(aim)) / len(old | _words(aim)) >= 0.8:
            return p["repeated_aim"].format(chapter=b.get("chapter"), aim=r.s(b.get("aim")))
    found = plan_points(plan)
    missing = [f"Act {n}" for n in POINTS if n not in found]
    if missing or found != sorted(found):
        return p["missing_points"].format(missing=", ".join(missing) or "the right order")
    tie = next((t for t in request.get("ties") or [] if t.get("id") == request.get("spotlight")), None)
    if tie:
        ends = [names.get(tie.get("tie_from"), ""), names.get(tie.get("tie_to"), "")]
        absent = [e for e in ends if e and not _mentions_part(plan, e)]
        if absent:
            return p["missing_names"].format(names=" and ".join(absent))
    return None


def plan_names(request: dict, value: Any) -> tuple[int, list[str]]:
    """(how many people on no card the plan names, and which of them are new). Rule 5 asks for role only, but a name is no reason to throw a
    plan away, so this only counts. The count includes names the earlier chapters used (the history shown to the model carries them); the
    new ones are in no earlier chapter's events or plan either. The cards and the writer's own setup text are the names that may be used."""
    beat = value if isinstance(value, dict) else {}
    return common.minor_people(request, [r.s(beat.get("where")), r.s(beat.get("when_time")), r.s(beat.get("aim")), r.s(beat.get("plan"))],
                               [request.get(k) for k in ("cast", "world", "ties", "holdings", "setup", "style")],
                               common.earlier_records(request, beats=True))


# ---- The flow -------------------------------------------------------------------------------------------------------------

def _tidy_brainstorm(text: Any) -> str:
    """The brainstorm as the plan prompt carries it: trimmed, and when the reply was cut off mid-sentence, cut back to the last full sentence
    (when that keeps at least half of it)."""
    text = r.s(text).strip()
    if not text or text[-1] in ".!?…。！？\"”)」』":
        return text
    cut = max(text.rfind(m) for m in (".", "!", "?", "。", "！", "？"))
    return text[:cut + 1] if cut >= len(text) // 2 else text


class PlanFlow(Flow):
    """(In choose mode, `select` first: three combinations of a tie and a rule or object, and the brainstorm then writes one idea for each.)
    label steps (from the second chapter), brainstorm, (decide), plan; nothing runs after the plan. The brainstorm is free text that the plan prompt carries; if it cannot be had, the
    plan goes ahead without it. The decider (decide.py) reads the brainstorm's options and picks one, and the plan is then built on that one option
    alone, as idea 1 with its own combination; with any other number of options than three, or with `decide.ON` False, the plan carries the whole brainstorm as before."""

    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit
        self.notes: dict[str, Any] = {"pressure_on": bool(pressure_of(request)), "origin_history": bool(request.get("origin_history", True))}      # for the run log: whether a pressure was sent, whether origin history was asked for, the judges' verdict words, whether a last resort stood in for a step, and the walk-on counts (minor_names, minor_new)
        if driver.active(request):
            self.notes["driver_kinds"] = driver.label(request)      # the kind each of the three ideas is driven by, in order (Plan 9)
        self.brainstorm = ""                    # the brainstorm's text once it has run ("" until then, and when it fell back)
        self.combos: list[dict] | None = None   # choose mode: the three combinations the select step picked (None until then, and when it fell back)
        self._options: list[tuple[int, str]] | None = None    # the brainstorm's options when the decider is to run (at least two), else None
        self._order: list[int] = []             # the order the decider was shown them in
        self.decision: decide.Decision | None = None          # the decider's pick, once it has run
        self._shown: list[dict] | None = None   # once decided in choose mode: the one combination the plan carries (the picked option's), else None
        self._label_items = label_items(request)    # the earlier chapters the label step describes (empty: no label step)
        self.used: list[dict] = []              # the labelled earlier chapters, oldest first: {chapter, the eight keys of a fingerprint}; empty after a fallback or with no label step
        self.earlier_prints: list[repeat.Fingerprint | None] = []       # the same, one for each of the label step's chapters (None where it gave none)
        self._labelled = False                  # the label step's result has been read
        self._gated = False                     # a label step over the brainstorm's ideas is part of the chain (earlier chapters were labelled and the brainstorm gave its options)
        self._gate_done = False                 # that step's result has been read
        self._alive: list[int] = []             # the places (from 0) of the brainstorm's options the decider is to judge: all of them, or the ones the gate left
        self.avoid_fields: list[str] = []       # when every idea repeated: the fields the one kept still shares with an earlier chapter
        self._select_on = select.is_on(request)   # the request asks to choose and has at least one tie to choose from
        if self._select_on:
            self.notes["pressure_on"] = bool(pressure_of(request) or request.get("pressure_options"))
        elif request.get("choose"):
            self.notes["select"] = "few"        # choose was asked but there is no tie between two people of the cast: the flow is the single-pair one on the page's own pair

    def _count_names(self, value: Any) -> list[str]:
        """Records the walk-on counts of the plan that stands (interface M1) in the notes, and returns the new names."""
        total, new = plan_names(self.request, value)
        self.notes["minor_names"], self.notes["minor_new"] = total, len(new)
        return new

    # -- the brainstorm

    def _brainstorm_check(self, value: Any) -> str | None:
        """Refuses a reply that is too short, and one that has options but not exactly three (in choose mode, numbered 1, 2, 3 for the three
        combinations). A reply the parser cannot split (0 or 1 options) passes: the decider then notes `none` and the plan carries the whole text.
        A cut-off last option is dropped by `parse_options`, so a truncated reply parses short and is refused too."""
        text = r.s(value)
        p = common.load_text("plan")["problems"]
        if len(text) < BRAINSTORM_MIN_CHARS:
            return p["brainstorm_short"]
        if decide.ON:
            options = decide.parse_options(text)
            if options and (len(options) != 3 or (self.combos is not None and [n for n, _ in options] != [1, 2, 3])):
                return p["brainstorm_count"]
        return None

    def _brainstorm_step(self, combos: list[dict] | None = None, used: list[dict] | None = None) -> Step:
        """Free text, thinking sampling, no grammar. Its last resort is no brainstorm at all (never an error). The runner does not check its
        language: it is the planner's own thinking, and the plan step that follows is the one whose language is checked."""
        def none():
            self.notes["brainstorm_fallback"] = True
            return ""
        use = combos if combos is not None else self.combos
        table = self.used if used is None else used
        return Step("brainstorm", lambda f: build_brainstorm_prompt(self.request, f, use, table), "text", BRAINSTORM_OUTPUT, None, self._brainstorm_check,
                    "thinking", False, attempts=BRAINSTORM_ATTEMPTS, fallback=none)

    # -- the plan

    def _check(self):
        """A check for one plan step instance. Every problem it returns is hard and refuses the attempt. A person on no card never does: the
        plan is used, its new names go to the trace as a soft note, and the counts go to the run record. The last reply to pass is the one used,
        so its counts are the ones that stay."""
        def check(value):
            resolved = self._resolved(value)
            if resolved is None:
                return common.load_text("plan")["problems"]["idea_missing"]
            hard = plan_problem(resolved, value)
            if hard:
                return hard
            if self.combos is not None:
                self.notes["idea"] = value[IDEA]
            new = self._count_names(value)
            if new:
                common.note_soft("plan", "plan", common.load_text("plan")["problems"]["unknown_person"].format(names=", ".join(new)))
            return None
        return check

    def _grammar(self, brainstorm: str, combos: list[dict] | None = None) -> Any:
        """The planner grammar. When the plan carries a brainstorm it also asks for `idea_use`, first, so the choice is made before the plan is.
        In choose mode it asks for `idea` before that: 1 to 3, the idea (or combination) the plan is built on. Both keys are only for the trace
        and for `picked`; `reply` takes them out of the beat again."""
        grammar = self.kit.grammar.plan_beat()
        if not (brainstorm or combos is not None) or not isinstance(grammar, dict) or not isinstance(grammar.get("properties"), dict):
            return grammar
        grammar = copy.deepcopy(grammar)
        extra = {IDEA: {"type": "integer", "enum": [1, 2, 3]}} if combos is not None else {}
        if brainstorm:
            extra[IDEA_USE] = {"type": "string"}
        grammar["properties"] = {**extra, **grammar["properties"]}
        grammar["required"] = [*extra, *grammar.get("required", [])]
        return grammar

    def _step(self, brainstorm: str | None = None, combos: list[dict] | None = None, request: dict | None = None, used: list[dict] | None = None,
              avoid: list[str] | None = None) -> Step:
        text = self.brainstorm if brainstorm is None else brainstorm
        use = combos if combos is not None else self._shown if self._shown is not None else self.combos
        decided = brainstorm is None and self.decision is not None       # the worst case (a brainstorm given) is the longest wording, the undecided one
        table = self.used if used is None else used
        avoiding = self.avoid_fields if avoid is None else avoid
        return Step("plan", lambda f: build_prompt(request or self.request, f, text, use, decided, self.decision.position if decided else 0, table, avoiding), "json", MAX_OUTPUT, self._grammar(text, use), self._check(),
                    "thinking", True)

    # -- the label step

    def _label_step(self) -> Step:
        return repeat.label_step(self.request, self._label_items, label_names(self.request))

    def _take_label(self, value: Any) -> None:
        """Reads the label step's result: the earlier chapters with their fingerprints, in `used` (the table) and `earlier_prints` (the later
        comparison). A result with no labels (the fallback) leaves both empty: no table and no gate, never an error."""
        if self._labelled:
            return
        self._labelled = True
        prints = repeat.read(value, self._label_items, label_names(self.request))
        self.earlier_prints = prints
        self.used = [{"chapter": n, **p} for (n, _), p in zip(self._label_items, prints) if p]
        self.notes["label"] = "on" if self.used else "fallback"
        self.notes["label_chapters"] = len(self.used)

    # -- choose mode

    def _select_step(self) -> Step:
        def fallback():
            self.notes["select"] = "fallback"
        return select.step(self.request, fallback)

    def _take_select(self, value: Any) -> None:
        """Reads the select step's result (the first result in choose mode): the three combinations, or none after a fallback, which leaves the
        flow on the page's own pair."""
        self.combos = select.combos(self.request, value)
        if self.combos is None:
            self.notes["select"] = "fallback"
            self.notes["pressure_on"] = bool(pressure_of(self.request))
            return
        self.notes["select"] = "on"
        self.notes["select_ties"], self.notes["select_pressures"] = select.counts(self.combos)
        self.notes["pressure_on"] = bool(self.request.get("pressure_options"))

    def _combo_of(self, beat: Any) -> dict | None:
        """The combination the plan's `idea` stands for, or None when it names none. The plan shows three ideas, so the number is the combination's
        place among the three. After the decider it shows one, idea 1: the schema still lets 1 to 3 through, and any of them is that one idea."""
        idea = beat.get(IDEA) if isinstance(beat, dict) else None
        if isinstance(idea, bool) or not isinstance(idea, int) or self.combos is None:
            return None
        if self._shown is not None:
            return self._shown[0] if 1 <= idea <= 3 else None
        return self.combos[idea - 1] if 1 <= idea <= len(self.combos) else None

    def _resolved(self, beat: Any) -> dict | None:
        """The request a plan is checked and judged against. Outside choose mode (or after a select fallback) it is the request. In choose mode it
        is the request with the spotlight and the pressure of the idea the plan chose, or None when the plan names no idea from 1 to 3."""
        if self.combos is None:
            return self.request
        combo = self._combo_of(beat)
        if combo is None:
            return None
        request = {**{k: v for k, v in self.request.items() if k != "pressure"}, "spotlight": combo["tie_id"]}
        if combo["pressure"]:
            request["pressure"] = combo["pressure"]
        return request

    # -- the decider

    def _decide_request(self) -> dict:
        """The request the decider reads: with combinations chosen, no single pair, as in the brainstorm."""
        return select.without_pair(self.request) if self.combos is not None else self.request

    def _survivors(self) -> list[tuple[int, str]]:
        """The options the decider judges, in the brainstorm's order: all of them, or the ones the gate left."""
        return [self._options[i] for i in self._alive]

    def _places(self) -> list[int] | None:
        """The brainstorm's place (from 1) of each survivor, or None when all of the options stand (the decider then works as it always did)."""
        return [i + 1 for i in self._alive] if len(self._alive) < len(self._options) else None

    def _flags(self) -> list[bool]:
        flags = decide.invented(self.request, self._options)
        return [flags[i] for i in self._alive]

    def _decide_step(self) -> Step:
        return decide.step(self._decide_request(), self._survivors(), self._order, lambda: None, decide.criteria_for(self.request), self.combos)

    def _take_decide(self, value: Any) -> None:
        """Reads the decider's result: the plan then carries the picked option alone, as idea 1, with its own combination (in choose mode).
        An unusable result picks a random option and the notes say it fell back."""
        if self.decision is not None:
            return
        self._adopt(decide.decide(self._survivors(), self._order, value, decide.criteria_for(self.request), self._flags(), self._places()))

    def _take_single(self) -> None:
        """One option is left (the gate dropped the others): it is chosen directly and no decider call is made."""
        if self.decision is None:
            self._adopt(decide.only(self._survivors(), 0, self._places(), self._flags()))

    def _adopt(self, decision: decide.Decision) -> None:
        """The decision stands: its notes, the plan's idea (the picked option alone) and, in choose mode, its own combination. The decision's
        position is the option's place in the whole brainstorm, so the ending and the combination follow the option's own number."""
        self.decision = decision
        self.notes.update(decision.notes())
        picked = self._options[decision.position - 1][1]
        self.brainstorm = common.load_text("plan")["decided_item"].format(text=decide.unnumbered(picked))
        if self.combos is not None:
            self._shown = [self.combos[decision.combo - 1]]

    # -- the gate on the brainstorm's ideas

    def _gate_items(self) -> list[tuple[int, str]]:
        """The ideas the gate labels, each under its place in the brainstorm (from 1), without the numbers in its header."""
        return [(i, decide.unnumbered(text)) for i, (_, text) in enumerate(self._options, 1)]

    def _gate_step(self) -> Step:
        return repeat.label_step(self.request, self._gate_items(), label_names(self.request))

    def _take_gate(self, value: Any) -> None:
        """Reads the gate's labels: each idea's outcome is set from its place (the brainstorm's contract), each is screened against the labelled
        earlier chapters, and an idea that matches one of them on `repeat.T` labels or more is dropped. When every idea is dropped, the one with the
        fewest matches stays (the lowest place on a tie) and the fields it still shares are kept in `avoid_fields`. A result with no labels (the
        fallback) drops nothing."""
        if self._gate_done:
            return
        self._gate_done = True
        count = len(self._options)
        prints = repeat.read(value, self._gate_items(), label_names(self.request))
        self._alive = list(range(count))
        if not any(prints):
            self.notes["repeat"] = "fallback"
            return
        for place, found in enumerate(prints, 1):
            if found:
                found["outcome"] = common.ENDINGS.get(place, "other")
        found = repeat.screen(prints, self.earlier_prints)
        dropped = [i for i, one in enumerate(found) if repeat.too_similar(one)]
        self.notes["repeat"] = "on"
        self.notes.update({f"repeat_m{place}": one.matches for place, one in enumerate(found, 1)})
        self.notes["repeat_dropped"] = len(dropped)
        self.notes["repeat_threshold"] = f"{repeat.T} of {len(repeat.FIELDS)}"      # T is 5 of seven (raised from 4 after test 18): to be tuned on a real run
        self.notes["repeat_avoid"] = False
        if len(dropped) == count:
            best = min(range(count), key=lambda i: (found[i].matches, i))
            self._alive = [best]
            self.avoid_fields = list(found[best].fields)
            self.notes["repeat_avoid"] = True
        else:
            self._alive = [i for i in range(count) if i not in dropped]

    def next(self, results):
        if self._select_on:                 # choose mode: the select result comes first; everything after it is today's flow, counted from its own start
            if not results:
                return self._select_step()
            self._take_select(results[0])
            results = results[1:]
        if self._label_items:               # the label step comes after select and before the brainstorm: its result is taken out here too
            if not results:
                return self._label_step()
            self._take_label(results[0])
            results = results[1:]
        if not results:
            return self._brainstorm_step()
        if len(results) == 1:
            self.brainstorm = _tidy_brainstorm(results[0])
            self._options = self._options_of(r.s(results[0]).strip())     # the reply as written: the tidy cut-back would make a cut-off option look whole
        at = 1                                                              # where the results after the brainstorm's own begin
        if self._options is not None:
            self._gated = any(self.earlier_prints)                          # earlier chapters were labelled: the ideas are labelled and screened next
            if self._gated:
                if len(results) == at:
                    return self._gate_step()
                self._take_gate(results[at])
                at += 1
            else:
                self._alive = list(range(len(self._options)))
            if len(self._alive) >= 2:                                       # two or three ideas stand: the decider judges them
                self._order = decide.order_of(self._survivors(), self.request)
                if len(results) == at:
                    return self._decide_step()
                self._take_decide(results[at])
                at += 1
            else:                                                           # one idea stands: no call is made
                self._take_single()
        return self._after_brainstorm(results[at:])

    def _options_of(self, brainstorm: str) -> list[tuple[int, str]] | None:
        """The brainstorm's options, when there are exactly three and (in choose mode) each belongs to one of the combinations. Else None, and the
        plan carries the whole brainstorm as it did before the decider (the notes say `none`). Which of them the decider judges is the gate's call
        (`_take_gate`): all three, two, or one that is chosen without a call."""
        if not decide.ON:
            return None
        options = decide.parse_options(brainstorm)
        if len(options) != decide.OPTIONS_MAX or (self.combos is not None and not all(1 <= n <= len(self.combos) for n, _ in options)):
            self.notes["decide"] = "none"
            return None
        return options

    def _after_brainstorm(self, results):
        """The plan, and nothing after it: no results yet means the plan is the next step, and once it is in the chain is over."""
        return self._step() if not results else None

    def worst_case(self):
        """The brainstorm, then the plan carrying a brainstorm of the longest size."""
        stand = select.stand_in(self.request) if self._select_on else None       # choose mode: the select step first, and the combinations as large as they can get
        steps = [self._select_step()] if self._select_on else []
        table = _used_stand_in() if self._label_items else None       # the label step, and the "already used" table as long as it can get
        if self._label_items:
            steps.append(repeat.label_step(self.request, [(n, repeat.LABEL_STAND_IN) for n, _ in self._label_items], label_names(self.request)))
        steps.append(self._brainstorm_step(stand, table))
        if decide.ON and self._label_items:        # the gate labels the three ideas, each as long as the brainstorm allows
            steps.append(repeat.label_step(self.request, [(n, "word " * (BRAINSTORM_OUTPUT // decide.OPTIONS_MAX)) for n in range(1, decide.OPTIONS_MAX + 1)],
                                           label_names(self.request)))
        if decide.ON:        # whether the brainstorm gives options is not known until it is written: the call is fitted as if it did
            options = decide.stand_in(BRAINSTORM_OUTPUT)
            steps.append(decide.step(select.without_pair(self.request) if self._select_on else self.request, options, list(range(len(options))), lambda: None,
                                     decide.criteria_for(self.request), stand))
        steps.append(self._step(brainstorm=BRAINSTORM_STAND_IN, combos=stand, used=table, avoid=list(repeat.FIELDS) if table else None))
        return steps

    def _ending(self, beat: Any) -> str | None:
        """How the chapter is planned to end: reached, lost or gave_up, from the number of the idea it was built on. After the decider that is the
        picked option's place in the brainstorm; else, in choose mode with a brainstorm, the idea the plan named. None when no idea fixes it."""
        if self.decision is not None:
            return common.ENDINGS.get(self.decision.position)
        idea = beat.get(IDEA) if isinstance(beat, dict) else None
        if self.brainstorm and self.combos is not None and isinstance(idea, int) and not isinstance(idea, bool):
            return common.ENDINGS.get(idea)
        return None

    def reply(self, results):
        if self._select_on:
            results = results[1:]
        if self._label_items:
            results = results[1:]
        at = 1 + (self._options is not None and self._gated) + (self._options is not None and len(self._alive) >= 2)       # the gate's and the decider's results (each when it ran) sit between the brainstorm and the plan
        beat = results[at]
        out: dict[str, Any] = {}
        combo = self._combo_of(beat)
        if combo is not None:
            idea = beat[IDEA]                         # the idea the plan chose is its combination's tie and pressure: the ids come from the request, never from the model
            out["picked"] = {"spotlight": combo["tie_id"], "pressure": combo["pressure_id"]}
            self.notes["idea"] = idea
        ending = self._ending(beat)
        if ending:
            out["outcome"] = ending                   # kept on the beat by the page: the events step is told how the chapter was meant to end
        if isinstance(beat, dict) and (IDEA_USE in beat or IDEA in beat):      # they stay in the trace's copy of the reply, and the page never sees them
            beat = {k: v for k, v in beat.items() if k not in (IDEA, IDEA_USE)}
        return {"beat": beat, **out}


def build_flow(request, kit) -> Flow:
    return PlanFlow(request, kit)


def script(request: dict, kit: Any) -> list[str]:
    """What a fake engine must return for a valid reply: (in choose mode, first a select reply with three different picks, and the plan then builds
    on idea 1, which is the first pick;) (from the second chapter, when earlier events exist, a label reply with one fingerprint for each of the last K of them;) a brainstorm of three options, then a place, a concrete aim that differs per chapter and a plan of four points, then (from the second chapter) the aim judge's verdict (link and new_obstacle)."""
    import json
    names = names_of(request)
    choose = select.is_on(request)
    if choose:
        ties, options = select.candidates(request)
        pairs = sorted(((i, j) for i in range(len(ties)) for j in range(max(1, len(options)))), key=lambda p: (p[0] + p[1], p[0]))[:select.PICKS]
        picks = [{"reason": f"The tie and the rule or object of combination {n} pull against what the protagonist wants.", "tie": i + 1, **({"pressure": j + 1} if options else {})}
                 for n, (i, j) in enumerate((pairs * select.PICKS)[:select.PICKS], 1)]
        tie = ties[pairs[0][0]]
    else:
        tie = next(t for t in request["ties"] if t["id"] == request["spotlight"])
    a, b = names.get(tie["tie_from"], "someone"), names.get(tie["tie_to"], "someone")
    place = ((request.get("world") or {}).get("places") or [{}])[0].get("name") or "the square"
    n = int(request["chapter"])
    words = ["lantern", "harbour", "ledger", "orchard", "bridge", "cellar", "furnace", "meadow", "tavern", "quarry", "signal", "market"]
    aim = f"Get the {words[n % len(words)]} key from {b} before the {words[(n * 5) % len(words)]} bell rings in round {n}."
    plan = (f"Act 1: {a} and {b} meet at {place} at first light. Act 2: the aim runs into the tie between {a} and {b}, and a quarrel breaks out. "
            f"Act 3: a costly choice turns the scene when {a} gives something up. Act 4: the chapter ends with the tie and the aim in a new state.")
    brainstorm = (f"Option 1: a refusal. {a} asks {b} for the {words[n % len(words)]} key and is turned down; {b} wants to be asked properly, and the two clash at the door. "
                  f"It costs {a} a favour. Option 2: a trade. {a} offers {b} something in return, {b} wants more than was offered, and they clash over the price. "
                  f"It costs {a} a secret. Option 3: a misunderstanding. {a} and {b} each think the other holds the key; they clash over who lied. It costs both their trust.")
    texts = [json.dumps({"picks": picks})] if choose else []
    items = label_items(request)
    if items:                                  # the label step: one valid fingerprint for each earlier chapter it describes
        party = (label_names(request) or ["none"])[0]
        texts.append(json.dumps({"prints": [{"n": c, "turning_note": f"Chapter {c} turns on a refusal at the door.", "aim_kind": "obtain", "obstacle_source": "person",
                                             "obstacle_party": party, "turning_kind": "refusal", "outcome": "lost", "closing_hook": "new_task", "motive_kind": "recognition"} for c, _ in items]}))
    chosen = {"idea": 1} if choose else {}
    texts += [brainstorm, json.dumps({**chosen, "idea_use": f"I build on option 2, the trade, and take its price quarrel.", "where": place, "when_time": f"Day {n}, early morning", "aim": aim, "plan": plan})]
    return texts
