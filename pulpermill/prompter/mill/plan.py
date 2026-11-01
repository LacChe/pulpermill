"""The `plan` call: one JSON step that designs a chapter. The planner collides the protagonist's aim with the spotlight tie (R4), designs the
chapter in four points inside the `plan` text (R7), and ends in a state where both have moved (R6). Minor characters appear by role only (R5).
Wording lives in text/en/plan.yaml; this module assembles it from the renderers and checks the reply.

Helpers at the top (names, ties in words, squeeze tiers, the spotlight) are shared with generate.py."""
import math
import re
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step

from . import common

VERSION = "plan-1"
MAX_OUTPUT = 1000          # where + when + aim + about 150 words of plan, with room to spare; the context keeps this much free
POINTS = ("1", "2", "3", "4")


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


def spotlight_candidates(request: dict, names: dict[str, str]) -> list[dict]:
    """The ties a `generate` request may mean by the spotlight (the request does not carry it): the ties whose two ends are both named in the
    beat's plan or aim, which the planner is told to do. None named: no candidates, and the caller falls back to any tie."""
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


def build_prompt(request: dict, factor: float = 1.0) -> str:
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
    """None when the plan is usable, else one plain line saying what to fix."""
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


# ---- The flow -------------------------------------------------------------------------------------------------------------

class PlanFlow(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit

    def _step(self) -> Step:
        return Step("plan", lambda f: build_prompt(self.request, f), "json", MAX_OUTPUT, self.kit.grammar.plan_beat(),
                    lambda v: plan_problem(self.request, v), "thinking", True)

    def next(self, results):
        return None if results else self._step()

    def reply(self, results):
        return {"beat": results[0]}


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
    return [json.dumps({"where": place, "when_time": f"Day {n}, early morning", "aim": aim, "plan": plan})]
