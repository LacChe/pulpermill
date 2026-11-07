"""The `plan` call: a free-text brainstorm of three ways to take the running aim its next step, then one JSON step that designs the chapter from
them, then the aim judge (advance.py, observe-only). The planner collides the protagonist's aim with the spotlight tie (R4), designs the chapter in four points inside the
`plan` text (R7), and ends in a state where both have moved (R6). Minor characters appear by role only (R5). The brainstorm only helps the plan:
if it cannot be had, the plan goes ahead without it. Wording lives in text/en/plan.yaml; this module assembles it from the renderers and checks
the reply.

Helpers at the top (names, ties in words, squeeze tiers, the spotlight) are shared with generate.py."""
import copy
import math
import re
from dataclasses import replace
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step

from . import advance, common, select

VERSION = "plan-15"
IDEA = "idea"            # in choose mode: the number (1 to 3) of the idea the plan builds on, which is also the number of its combination; the reply turns it into `picked`
IDEA_USE = "idea_use"      # the plan step's own account of which brainstorm idea it built on: for the run's trace only, never in the reply
MAX_OUTPUT = 1000          # where + when + aim + about 150 words of plan, with room to spare; the context keeps this much free
POINTS = ("1", "2", "3", "4")
BRAINSTORM_OUTPUT = 1200      # three ideas of about 150 words each need roughly 700 tokens; the rest is room to spare, so a cut-off tail is the exception
BRAINSTORM_ATTEMPTS = 2       # then the plan goes ahead without a brainstorm: it is a help to the plan, never a reason to fail a call
BRAINSTORM_MIN_CHARS = 120    # three options cannot be told in less
BRAINSTORM_STAND_IN = "word " * BRAINSTORM_OUTPUT       # the longest a brainstorm can be as the plan prompt carries it (a token a word), for the worst case
JUDGE_ATTEMPTS = 2        # the advancement judge (observe-only): two tries, then a neutral verdict, so a judge can never fail a call
AIM_STAND_IN = "word " * 60       # the longest an aim is shown to a model (300 characters), for the worst case
PLAN_STAND_IN = "word " * 300      # the longest a plan is shown to the pressure judge (1,200 characters), for the worst case


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
    return {w for w in _norm(text).split() if len(w) > 3}


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


def _context(request: dict, factor: float, combos: list[dict] | None = None) -> dict:
    """What the brainstorm prompt and the plan prompt share: the names, the tie, the chapter's place in the story, and every section that
    comes before the task. The running aim (`chain_text`) closes the story so far. `combos`
    (choose mode) puts the three combinations in the place of the spotlight section; `request` is then one with no spotlight and no pressure."""
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
        cast_text = r.render_cast(cast, scope="planner")
    pressure = pressure_of(request, factor)
    with tx.squeeze(world_f):
        world_text = r.render_world(request.get("world") or {}, scope="planner", without=pressure)
    spotlight_text = r.render_spotlight(tie_words, cast, scope="planner", names=names) if tie else ""
    spotlight_text = "\n".join(x for x in (spotlight_text, r.render_pressure(pressure)) if x)       # one sentence inside the spotlight section
    spotlight_head = heads["spotlight"]
    if combos is not None:
        spotlight_head, spotlight_text = heads["combinations"], select.combos_text(combos, w)

    events = cut_events(request.get("earlier_events"), chapter, history_ratio)
    keep = max(1, round(tx.limits()["events"]["full_chapters_planner"] * min(1.0, history_ratio)))
    history = r.render_history(events, chapter, scope="planner", keep_full=keep)
    beats = [{**b, "when_time": b.get("when_time") or b.get("when")} for b in request.get("earlier_beats") or []]
    timeline = r.render_earlier_beats(beats)
    chain = chain_text(request, w, history_ratio)

    origin = r.render_origin_history(request.get("setup") or {}, chapter) if request.get("origin_history") else ""      # chapters 2+ only, and only when the page asks
    setup = r.render_setup(request.get("setup") or {}, chapter, total or None, protagonist_name=protagonist_name(request, names), origin=origin)
    blocks = [
        _section(heads["tone"], r.render_style(request.get("style") or {}, scope="planner")),
        _section(heads["setup"], setup),
        _section(heads["cast"], cast_text),
        _section(heads["world"], world_text),
        _section(heads["entanglements"], r.render_entanglements({"ties": ties, "holdings": holdings}, scope="planner")),
        _section(spotlight_head, spotlight_text),
        _section(heads["history"], "\n\n".join(x for x in (history, timeline, chain) if x)),
    ]
    return {"w": w, "names": names, "chain": chain, "chapter": chapter, "total": total, "heads": heads, "tie": tie, "blocks": blocks}


def _task_block(c: dict, method: str) -> list[str]:
    """The lines of the task that both prompts open with: the collision (R4, in `method`'s wording) and what makes an aim (R4/R6)."""
    w = c["w"]
    return [w[method], w["aim_rules"]]


def build_brainstorm_prompt(request: dict, factor: float = 1.0, combos: list[dict] | None = None) -> str:
    """The brainstorm step's prompt: the same cards and history as the plan, with the earlier aims shown as the kinds already used, and a task
    that asks for three chapters of different kinds. Free text out; nothing here asks for the plan's shape. With `combos` (choose mode) the
    three chapters are one for each combination, and no single spotlight is shown."""
    if combos is not None:
        request = select.without_pair(request)
    c = _context(request, factor, combos=combos)
    w, names, chapter, total = c["w"], c["names"], c["chapter"], c["total"]
    role = w["brainstorm_role"].format(chapter=chapter, total=total) if total else w["brainstorm_role_unknown_total"].format(chapter=chapter)
    task = _task_block(c, "brainstorm_method")
    if combos is not None:
        task.append(w["brainstorm_combos"])
    task.append(w["brainstorm_task"].format(other=other_end(request, names)))
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


def build_prompt(request: dict, factor: float = 1.0, brainstorm: str = "", combos: list[dict] | None = None) -> str:
    """The plan step's prompt. `brainstorm` is the text of the brainstorm step: with it, the prompt carries it under its own heading and tells
    the planner to choose from it; without it (no brainstorm, or one that could not be had) the prompt is the plan prompt on its own. With `combos`
    (choose mode) the three combinations stand in the place of the spotlight, and the plan chooses one idea (or, with no brainstorm, one
    combination) and is built on its tie and its rule or object."""
    if combos is not None:
        request = select.without_pair(request)
    c = _context(request, factor, combos=combos)
    w, names, chapter, total, heads, tie = c["w"], c["names"], c["chapter"], c["total"], c["heads"], c["tie"]
    ends = [names.get(tie.get("tie_from"), ""), names.get(tie.get("tie_to"), "")] if tie else ["", ""]
    task = _task_block(c, "method")
    if combos is not None:
        task.append(w["choose_one"] if brainstorm else w["choose_combo"])
        if brainstorm:
            task.append(w["idea_number_chain" if c["chain"] else "idea_number"])
    elif brainstorm:
        task.append(w["choose_from"])
        task.append(w["idea_use_chain" if c["chain"] else "idea_use"])
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
    blocks = [role, *c["blocks"], _section(heads["brainstorm"], brainstorm.strip()), _section(heads["task"], "\n\n".join(x for x in task if x))]
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
    if len(_norm(aim).split()) < 3:
        return True
    first = core.split()[0] if core else ""
    return first in w["abstract_verbs"] or any(core.startswith(s) for s in w["abstract_starts"])


def plan_points(text: str) -> list[str]:
    """The labels Act 1 to Act 4 that start a usable point (at least three words after the label), in the order found."""
    marks = list(re.finditer(r"\bAct\s*([1-4])\b", text or ""))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        if len(re.sub(r"[^\w\s]", " ", text[m.end():end]).split()) >= 3:
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
    brainstorm, plan, aim judge (observe-only: nothing is sent back for its verdict). The brainstorm is free text that the plan prompt carries; if it cannot be had, the
    plan goes ahead without it."""

    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit
        self.notes: dict[str, Any] = {"pressure_on": bool(pressure_of(request)), "origin_history": bool(request.get("origin_history"))}      # for the run log: whether a pressure was sent, whether origin history was asked for, the judges' verdict words, whether a last resort stood in for a step, and the walk-on counts (minor_names, minor_new)
        self._pressure_at: int | None = None    # where the pressure judge's result sits among the results after the brainstorm, once that step has been asked for
        self.brainstorm = ""                    # the brainstorm's text once it has run ("" until then, and when it fell back)
        self.combos: list[dict] | None = None   # choose mode: the three combinations the select step picked (None until then, and when it fell back)
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

    @staticmethod
    def _brainstorm_check(value: Any) -> str | None:
        if len(r.s(value)) < BRAINSTORM_MIN_CHARS:
            return common.load_text("plan")["problems"]["brainstorm_short"]
        return None

    def _brainstorm_step(self, combos: list[dict] | None = None) -> Step:
        """Free text, thinking sampling, no grammar. Its last resort is no brainstorm at all (never an error). The runner does not check its
        language: it is the planner's own thinking, and the plan step that follows is the one whose language is checked."""
        def none():
            self.notes["brainstorm_fallback"] = True
            return ""
        use = combos if combos is not None else self.combos
        return Step("brainstorm", lambda f: build_brainstorm_prompt(self.request, f, use), "text", BRAINSTORM_OUTPUT, None, self._brainstorm_check,
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

    def _step(self, brainstorm: str | None = None, combos: list[dict] | None = None) -> Step:
        text = self.brainstorm if brainstorm is None else brainstorm
        use = combos if combos is not None else self.combos
        return Step("plan", lambda f: build_prompt(self.request, f, text, use), "json", MAX_OUTPUT, self._grammar(text, use), self._check(),
                    "thinking", True)

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

    def _resolved(self, beat: Any) -> dict | None:
        """The request a plan is checked and judged against. Outside choose mode (or after a select fallback) it is the request. In choose mode it
        is the request with the spotlight and the pressure of the idea the plan chose, or None when the plan names no idea from 1 to 3."""
        if self.combos is None:
            return self.request
        idea = beat.get(IDEA) if isinstance(beat, dict) else None
        if isinstance(idea, bool) or not isinstance(idea, int) or not 1 <= idea <= len(self.combos):
            return None
        combo = self.combos[idea - 1]
        request = {**{k: v for k, v in self.request.items() if k != "pressure"}, "spotlight": combo["tie_id"]}
        if combo["pressure"]:
            request["pressure"] = combo["pressure"]
        return request

    def _judges(self) -> bool:
        """The aim judge runs from the second chapter on, when there is an earlier aim to be a kind of."""
        return bool(advance.earlier_aims(self.request))

    def _aim_step(self, aim: str, beat: Any = None) -> Step:
        """The judge of the plan's aim, a step of its own after the plan. Its last resort is a neutral verdict (none), never an error."""
        def neutral():
            self.notes["aim_judge_fallback"] = True
            return {}
        request = self._resolved(beat) if beat is not None else None
        return replace(advance.aim_step(request or self.request, aim), attempts=JUDGE_ATTEMPTS, fallback=neutral)

    def _pressure_step(self, beat: Any) -> Step:
        """The judge of the chapter's pressure, a step of its own after the plan that stands. It reads the plan text. Observe-only: its last
        resort is `unclear`, and nothing is ever sent back for its verdict."""
        def unclear():
            self.notes["pressure_judge_fallback"] = True
            return {"effect": "unclear"}
        beat = beat if isinstance(beat, dict) else {}
        request = self._resolved(beat) or self.request
        return replace(advance.pressure_step(request, r.s(beat.get("plan")), "plan", r.s(beat.get("aim"))), attempts=JUDGE_ATTEMPTS, fallback=unclear)

    def _end(self, results):
        """The chain of steps is over: the pressure judge is the one step left, and only when a pressure was sent. `results` are the ones after
        the brainstorm."""
        if not self.notes["pressure_on"]:
            return None
        self._pressure_at = len(results)
        return self._pressure_step(results[0])

    @staticmethod
    def _aim_of(beat: Any) -> str:
        return r.s(beat.get("aim")) if isinstance(beat, dict) else ""

    def next(self, results):
        if self._select_on:                 # choose mode: the select result comes first; everything after it is today's flow, counted from its own start
            if not results:
                return self._select_step()
            self._take_select(results[0])
            results = results[1:]
        if not results:
            return self._brainstorm_step()
        if len(results) == 1:
            self.brainstorm = _tidy_brainstorm(results[0])
        return self._after_brainstorm(results[1:])

    def _after_brainstorm(self, results):
        """plan, the aim judge (observe-only: its verdict goes to the notes and nothing is sent back for it), then the pressure judge."""
        n = len(results)
        if self._pressure_at is not None and n == self._pressure_at + 1:      # the pressure judge has run: record its word and stop
            self.notes.update(advance.notes(pressure_value=results[self._pressure_at]))
            return None
        if n == 0:
            return self._step()
        if n == 1:
            aim = self._aim_of(results[0])
            return self._aim_step(aim, results[0]) if aim and self._judges() else self._end(results)
        self.notes.update(advance.notes(aim_value=results[1]))
        return self._end(results)

    def worst_case(self):
        """The brainstorm, then the plan carrying a brainstorm of the longest size, then the judges."""
        stand = select.stand_in(self.request) if self._select_on else None       # choose mode: the select step first, and the combinations as large as they can get
        steps = [self._select_step()] if self._select_on else []
        steps += [self._brainstorm_step(stand), self._step(brainstorm=BRAINSTORM_STAND_IN, combos=stand)]
        if self._judges():
            steps.append(self._aim_step(AIM_STAND_IN))
        if self.notes["pressure_on"]:
            steps.append(self._pressure_step({"aim": AIM_STAND_IN, "plan": PLAN_STAND_IN}))
        return steps

    def reply(self, results):
        if self._select_on:
            results = results[1:]
        beat = results[1]
        out: dict[str, Any] = {}
        if isinstance(beat, dict) and self.combos is not None and isinstance(beat.get(IDEA), int) and 1 <= beat[IDEA] <= len(self.combos):
            combo = self.combos[beat[IDEA] - 1]       # the idea the plan chose is its combination's tie and pressure: the ids come from the request, never from the model
            out["picked"] = {"spotlight": combo["tie_id"], "pressure": combo["pressure_id"]}
            self.notes["idea"] = beat[IDEA]
        if isinstance(beat, dict) and (IDEA_USE in beat or IDEA in beat):      # they stay in the trace's copy of the reply, and the page never sees them
            beat = {k: v for k, v in beat.items() if k not in (IDEA, IDEA_USE)}
        return {"beat": beat, **out}


def build_flow(request, kit) -> Flow:
    return PlanFlow(request, kit)


def script(request: dict, kit: Any) -> list[str]:
    """What a fake engine must return for a valid reply: (in choose mode, first a select reply with three different picks, and the plan then builds
    on idea 1, which is the first pick;) a brainstorm of three options, then a place, a concrete aim that differs per chapter and a plan of four points, then (from the second chapter) the aim judge's verdict (link and new_obstacle)."""
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
    chosen = {"idea": 1} if choose else {}
    texts += [brainstorm, json.dumps({**chosen, "idea_use": f"I build on option 2, the trade, and take its price quarrel.", "where": place, "when_time": f"Day {n}, early morning", "aim": aim, "plan": plan})]
    if advance.earlier_aims(request):          # the advancement judge runs from the second chapter on
        texts.append(json.dumps({"reason": "The aim takes the running aim on from where the last chapter left it, against a new obstacle.", "link": "continues", "new_obstacle": "yes"}))
    if request.get("pressure") or (choose and request.get("pressure_options")):                # the pressure judge runs last, whenever a pressure was sent
        texts.append(json.dumps({"reason": "The plan makes the element cost the protagonist something.", "effect": "acts"}))
    return texts
