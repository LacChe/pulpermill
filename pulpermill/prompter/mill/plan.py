"""The `plan` call: one JSON step that designs a chapter. The planner collides the protagonist's aim with the spotlight tie (R4), designs the
chapter in four points inside the `plan` text (R7), and ends in a state where both have moved (R6). Minor characters appear by role only (R5).
Wording lives in text/en/plan.yaml; this module assembles it from the renderers and checks the reply.

Helpers at the top (names, ties in words, squeeze tiers, the spotlight) are shared with generate.py."""
import math
import re
from dataclasses import replace
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step

from . import advance, common

VERSION = "plan-6"
MAX_OUTPUT = 1000          # where + when + aim + about 150 words of plan, with room to spare; the context keeps this much free
POINTS = ("1", "2", "3", "4")
JUDGE_ATTEMPTS = 2        # the advancement judge (observe-only): two tries, then a neutral verdict, so a judge can never fail a call
RESEND_STAND_IN = "word " * 90        # the longest line the judge can send a plan back with (a 400-character reason and the advice), for the worst case
AIM_STAND_IN = "word " * 60       # the longest an aim is shown to a model (300 characters), for the worst case


# ---- Shared helpers -------------------------------------------------------------------------------------------------------

def language_name(code: str | None) -> str:
    names = common.load_text("plan")["languages"]
    code = str(code or "en")
    return names.get(code) or names.get(code.split("-")[0]) or code


def tiers(factor: float) -> tuple[float, float, float]:
    """The squeeze order, as three factors for one squeeze `factor`: oldest history is cut first (from 0.85 down), then world detail
    (below 0.85), then cast texture (below 0.7). The plan, the scene, the spotlight tie and the style rules are never cut."""
    return factor, (1.0 if factor >= 0.85 else factor), (1.0 if factor >= 0.7 else factor)


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


def _mentions(text: str, name: str) -> bool:
    return bool(name) and name.lower() in str(text or "").lower()


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
        if a and b and _mentions(text, a) and _mentions(text, b):
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
    note = w["middle_chapter"]
    return f"{note} {w['late_chapter']}" if total and chapter >= math.ceil(total * 2 / 3) else note


def build_prompt(request: dict, factor: float = 1.0, extra: str = "") -> str:
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
    with tx.squeeze(world_f):
        world_text = r.render_world(request.get("world") or {}, scope="planner")
    spotlight_text = r.render_spotlight(tie_words, cast, scope="planner", names=names) if tie else ""

    events = cut_events(request.get("earlier_events"), chapter, history_ratio)
    keep = max(1, round(tx.limits()["events"]["full_chapters_planner"] * min(1.0, history_ratio)))
    history = r.render_history(events, chapter, scope="planner", keep_full=keep)
    beats = [{**b, "when_time": b.get("when_time") or b.get("when")} for b in request.get("earlier_beats") or []]
    timeline = r.render_earlier_beats(beats)
    aims = [w["aims_item"].format(chapter=b["chapter"], aim=r.s(b.get("aim"))) for b in sorted(beats, key=lambda b: int(b["chapter"])) if r.s(b.get("aim"))]
    aims_text = w["aims_lead"] + "\n" + "\n".join(aims) if aims else ""

    ex = tx.field("outline", "beats")["item_fields"]["aim"]["examples"]
    quote = lambda items, join="; ": join.join(f"“{i}”" for i in items)
    ends = [names.get(tie.get("tie_from"), ""), names.get(tie.get("tie_to"), "")] if tie else ["", ""]
    task = [
        w["method"],
        w["aim_rules"].format(good=quote(ex["good"]), avoid=quote(ex["avoid"], " or ")),
        w["four_points"],
        w["spotlight_names"].format(tie_from=ends[0], tie_to=ends[1]) if all(ends) else "",
        w["movement"].format(tie_from=ends[0] or "the person at the from end"),
        w["people_rule"],
        _chapter_note(w, chapter, total),
    ]
    retry = request.get("retry")
    if retry:
        beat = retry.get("beat") or {}
        problems = " ".join(r.sentence(p) for p in retry.get("problems") or [])
        task.append(w["retry_lead"].format(aim=r.sentence(r.s(beat.get("aim"))), plan=r.sentence(r.s(beat.get("plan")))) + " " + problems)
        task.append(w["retry_close"])
    if extra:                  # the advancement judge sent the plan back once: its line closes the task, ahead of the output rule
        task.append(extra)
    task.append(w["output"].format(language=language_name(request.get("language"))))

    role = w["role"].format(chapter=chapter, total=total) if total else w["role_unknown_total"].format(chapter=chapter)
    setup = r.render_setup(request.get("setup") or {}, chapter, total or None, protagonist_name=protagonist_name(request, names))
    blocks = [
        role,
        _section(heads["tone"], r.render_style(request.get("style") or {}, scope="planner")),
        _section(heads["setup"], setup),
        _section(heads["cast"], cast_text),
        _section(heads["world"], world_text),
        _section(heads["entanglements"], r.render_entanglements({"ties": ties, "holdings": holdings}, scope="planner")),
        _section(heads["spotlight"], spotlight_text),
        _section(heads["history"], "\n\n".join(x for x in (history, timeline, aims_text) if x)),
        _section(heads["task"], "\n\n".join(x for x in task if x)),
    ]
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
        absent = [e for e in ends if e and not _mentions(plan, e)]
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

class PlanFlow(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit
        self.notes: dict[str, Any] = {}         # for the run log: the aim judge's verdict word, whether its last resort stood in for it, and the walk-on counts (minor_names, minor_new)

    def _count_names(self, value: Any) -> list[str]:
        """Records the walk-on counts of the plan that stands (interface M1) in the notes, and returns the new names."""
        total, new = plan_names(self.request, value)
        self.notes["minor_names"], self.notes["minor_new"] = total, len(new)
        return new

    def _check(self):
        """A check for one plan step instance. Every problem it returns is hard and refuses the attempt. A person on no card never does: the
        plan is used, its new names go to the trace as a soft note, and the counts go to the run record. The last reply to pass is the one used,
        so its counts are the ones that stay."""
        def check(value):
            hard = plan_problem(self.request, value)
            if hard:
                return hard
            new = self._count_names(value)
            if new:
                common.note_soft("plan", "plan", common.load_text("plan")["problems"]["unknown_person"].format(names=", ".join(new)))
            return None
        return check

    def _step(self, extra: str = "", fallback=None) -> Step:
        return Step("plan", lambda f: build_prompt(self.request, f, extra), "json", MAX_OUTPUT, self.kit.grammar.plan_beat(), self._check(), "thinking", True,
                    fallback=fallback)

    def _judges(self) -> bool:
        """The aim judge runs from the second chapter on, when there is an earlier aim to be a kind of."""
        return bool(advance.earlier_aims(self.request))

    def _aim_step(self, aim: str) -> Step:
        """The judge of the plan's aim, a step of its own after the plan. Its last resort is a neutral verdict (none), never an error."""
        def neutral():
            self.notes["aim_judge_fallback"] = True
            return {}
        return replace(advance.aim_step(self.request, aim), attempts=JUDGE_ATTEMPTS, fallback=neutral)

    def _resend_step(self, first: Any, line: str) -> Step:
        """The plan step once more, with the judge's line. If this pass cannot be used either, the first plan stands (it was usable)."""
        def keep_first():
            self.notes["aim_resend_fallback"] = True
            self._count_names(first)          # the plan that stands is the first one, so its counts are the ones to record
            return first
        return self._step(line, keep_first)

    @staticmethod
    def _aim_of(beat: Any) -> str:
        return r.s(beat.get("aim")) if isinstance(beat, dict) else ""

    def _final(self, results: list) -> Any:
        """The plan the reply carries: the second pass when the plan was sent back, else the first."""
        return results[2] if len(results) >= 3 else results[0]

    def next(self, results):
        """plan, judge; and when `advance.ENFORCE` and the judge says the aim is the same kind as an earlier one: the plan once more with the
        judge's line, then the judge once more. A second bad verdict is accepted (noted). Never more than that one extra pass."""
        n = len(results)
        if n == 0:
            return self._step()
        if n == 1:
            aim = self._aim_of(results[0])
            return self._aim_step(aim) if aim and self._judges() else None
        if n == 2:
            self.notes.update(advance.notes(aim_value=results[1]))
            if advance.ENFORCE and not advance.aim_ok(results[1]):
                self.notes["aim_resent"] = True
                return self._resend_step(results[0], advance.resend_line("aim", results[1]))
            return None
        if n == 3:
            if self.notes.get("aim_resend_fallback"):       # the first plan stands, and it was judged already
                self.notes["aim_accepted"] = True
                return None
            aim = self._aim_of(results[2])
            return self._aim_step(aim) if aim else None
        again = advance.notes(aim_value=results[3]).get("aim_kind")
        if again:
            self.notes["aim_kind_after"] = again
        if not advance.aim_ok(results[3]):
            self.notes["aim_accepted"] = True
        return None

    def worst_case(self):
        steps = [self._step()]
        if self._judges():
            steps.append(self._aim_step(AIM_STAND_IN))
            if advance.ENFORCE:
                steps += [self._step(RESEND_STAND_IN), self._aim_step(AIM_STAND_IN)]
        return steps

    def reply(self, results):
        return {"beat": self._final(results)}


def build_flow(request, kit) -> Flow:
    return PlanFlow(request, kit)


def script(request: dict, kit: Any) -> list[str]:
    """What a fake engine must return for a valid reply: a place, a concrete aim that differs per chapter, and a plan of four points."""
    import json
    names = names_of(request)
    tie = next(t for t in request["ties"] if t["id"] == request["spotlight"])
    a, b = names.get(tie["tie_from"], "someone"), names.get(tie["tie_to"], "someone")
    place = ((request.get("world") or {}).get("places") or [{}])[0].get("name") or "the square"
    n = int(request["chapter"])
    words = ["lantern", "harbour", "ledger", "orchard", "bridge", "cellar", "furnace", "meadow", "tavern", "quarry", "signal", "market"]
    aim = f"Get the {words[n % len(words)]} key from {b} before the {words[(n * 5) % len(words)]} bell rings in round {n}."
    plan = (f"Act 1: {a} and {b} meet at {place} at first light. Act 2: the aim runs into the tie between {a} and {b}, and a quarrel breaks out. "
            f"Act 3: a costly choice turns the scene when {a} gives something up. Act 4: the chapter ends with the tie and the aim in a new state.")
    texts = [json.dumps({"where": place, "when_time": f"Day {n}, early morning", "aim": aim, "plan": plan})]
    if advance.earlier_aims(request):          # the advancement judge runs from the second chapter on
        texts.append(json.dumps({"reason": "The aim is a different kind of errand from the earlier ones.", "kind": "new_kind"}))
    return texts
