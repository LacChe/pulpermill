"""The advancement judge: small JSON steps that ask a model whether a chapter really moved. `aim_step` reads the protagonist's aim for a
chapter against the running aim (the chain of earlier aims and endings) and answers two questions: does it continue that aim from where the
last chapter left it (continues or drifts), and is its obstacle, person or stake new (yes or no); `edge_step` sorts the change of the spotlight tie's edge into one move
(escalates, reverses, complicates, resolves) or a rewording. A step is a classification, never a comparison of wording, and the reason
comes first in the reply so that the verdict follows from it.

The flows run these steps (plan.py, generate.py). `ENFORCE` says whether the edge flow acts on a bad edge verdict: it sends the shifts back once, with
`resend_line`, and runs the judge once more. With it False the flow only records the verdict. The aim and pressure judges are observe-only:
nothing is sent back for their verdicts. The verdict helpers are neutral on anything they cannot read: a missing or odd value is never a bad verdict, so a judge that
failed can never cost a chapter.

Inputs are read from a `plan` or `generate` request: the chain from `earlier_beats` and `earlier_events`, the edge trail from `spotlight_edges`, and the
names from the cards. Names, never ids. Wording lives in text/en/advance.yaml."""
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompter.base import Step

from . import common

VERSION = "advance-4"
ENFORCE = True
MAX_OUTPUT = 160            # one short sentence and one word, with room to spare

AIM_LINKS = ("continues", "drifts")
YES_NO = ("yes", "no")
EDGE_MOVES = ("escalates", "reverses", "complicates", "resolves", "rewords")
PRESSURE_EFFECTS = ("acts", "decor", "unclear")
TEXT_LIMIT = 1500            # the most characters of a plan or of a chapter's events the pressure judge reads


# ---- The shape of a reply -----------------------------------------------------------------------------------------------------
# Plain JSON Schema (the same keywords the backend's grammar builder accepts). The prompter never imports the backend, so the two small
# shapes are written here; `reason` comes first, and its order is the order the model writes in.

def _grammar(verdict: str, words: tuple[str, ...]) -> dict:
    return {"type": "object", "properties": {"reason": {"type": "string"}, verdict: {"type": "string", "enum": list(words)}},
            "required": ["reason", verdict], "additionalProperties": False}


def aim_grammar() -> dict:
    """{reason, link, new_obstacle}: the reason first, then the two verdicts."""
    return {"type": "object", "properties": {"reason": {"type": "string"}, "link": {"type": "string", "enum": list(AIM_LINKS)},
                                             "new_obstacle": {"type": "string", "enum": list(YES_NO)}},
            "required": ["reason", "link", "new_obstacle"], "additionalProperties": False}


def edge_grammar() -> dict:
    return _grammar("move", EDGE_MOVES)


def pressure_grammar() -> dict:
    return _grammar("effect", PRESSURE_EFFECTS)


# ---- What a prompt is made from -----------------------------------------------------------------------------------------------

def names_of(request: dict) -> dict[str, str]:
    """Id to name for the cast and the world of a request. (plan.py has the same; it is not imported, because the flows will import this.)"""
    return r.names_by_id({"world": request.get("world") or {}, "characters": request.get("cast") or []})


def _tie(request: dict) -> dict | None:
    """The spotlight tie: the one a `plan` request names by id (`spotlight`), or the one a `generate` request's beat names (`beat.spotlight`)."""
    beat = request.get("beat")
    for wanted in (request.get("spotlight"), beat.get("spotlight") if isinstance(beat, dict) else None):
        if isinstance(wanted, str) and wanted:
            found = next((t for t in request.get("ties") or [] if t.get("id") == wanted), None)
            if found:
                return found
    return None


def _ends(request: dict, names: dict[str, str]) -> tuple[str, str, str]:
    """The names of the two ends of the spotlight tie and its bond, each empty when the request does not say."""
    tie = _tie(request) or {}
    return names.get(tie.get("tie_from"), ""), names.get(tie.get("tie_to"), ""), r.s(tie.get("bond"))


def _recent(items: list, factor: float) -> list:
    """The newest of `items` when a squeeze asks for less (always at least one)."""
    if factor >= 1.0 or len(items) <= 1:
        return items
    return items[-max(1, round(len(items) * factor)):]


def earlier_aims(request: dict) -> list[tuple[int, str]]:
    """The aims of the chapters before this one, oldest first, from `earlier_beats` (a chapter with no aim is left out)."""
    chapter = int(request.get("chapter") or 0)
    rows = []
    for beat in request.get("earlier_beats") or []:
        n, aim = int(beat.get("chapter") or 0), r.s(beat.get("aim"))
        if aim and (not chapter or n < chapter):
            rows.append((n, aim))
    return sorted(rows)


def chain(request: dict, factor: float = 1.0) -> list[dict]:
    """The running aim's links, oldest first: for each chapter before this one that has an aim, {chapter, aim, changed}
    (`changed` is an empty string where the chapter has no line; a chapter with a line but no aim is left out). The aim is the beat's, the `changed` line is the chapter's events entry. A squeeze drops the oldest
    links (always keeping the newest). Chapter 1 has no earlier chapter, so no chain."""
    chapter = int(request.get("chapter") or 0)
    aims = dict(earlier_aims(request))
    changed = {}
    for e in request.get("earlier_events") or []:
        n = int(e.get("chapter") or 0)
        if n > 0 and (not chapter or n < chapter) and r.s(e.get("changed")):
            changed[n] = r.s(e.get("changed"))
    links = [{"chapter": n, "aim": aims[n], "changed": changed.get(n, "")} for n in sorted(aims)]
    return _recent(links, factor)


def edge_trail(request: dict) -> list[str]:
    """The spotlight tie's edges in earlier chapters, oldest first, from `spotlight_edges` (I3); an old request without it has none."""
    return [e for e in (r.s(x) for x in request.get("spotlight_edges") or []) if e]


# ---- The aim step -----------------------------------------------------------------------------------------------------------------

def chain_lines(request: dict, w: dict, factor: float = 1.0) -> str:
    """The running aim as the judge reads it: each earlier chapter's aim and how it ended, oldest first, the latest marked, and its ending last
    as where the aim stands now. Empty when there is no earlier chapter."""
    links = chain(request, factor)
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


def aim_prompt(request: dict, aim: str, factor: float = 1.0) -> str:
    w = common.load_text("advance")
    names = names_of(request)
    protagonist = names.get(request.get("protagonist") or "", "")
    tie_from, tie_to, bond = _ends(request, names)
    tie = ""
    if tie_from and tie_to:
        tie = (w["tie_line"] if bond else w["tie_line_plain"]).format(tie_from=tie_from, tie_to=tie_to, bond=r.bare(bond))
    blocks = [
        w["aim_role"],
        w["protagonist_line"].format(protagonist=protagonist) if protagonist else "",
        tie,
        chain_lines(request, w, factor),
        w["new_aim_line"].format(chapter=int(request.get("chapter") or 0), aim=r.s(aim)),
        w["aim_questions"],
        w["aim_answer"],
    ]
    return "\n\n".join(b for b in blocks if b)


def _reason_check(value: Any) -> str | None:
    reason = r.s(value.get("reason")) if isinstance(value, dict) else ""
    if not reason:
        return "Give the reason first, as one short sentence."
    return "Keep the reason to one short sentence." if len(reason) > 400 else None


def aim_step(request: dict, aim: str) -> Step:
    """Does `aim`, the protagonist's aim for this chapter, continue the running aim from where the last chapter left it, and is its obstacle or
    stake new? Reply {reason, link, new_obstacle}. Observe-only: nothing sends anything back for it."""
    return Step("advance_aim", lambda f: aim_prompt(request, aim, f), "json", MAX_OUTPUT, aim_grammar(), _reason_check, "structured", False)


# ---- The edge step ----------------------------------------------------------------------------------------------------------------

def edge_prompt(request: dict, old_edge: str, new_edge: str, factor: float = 1.0) -> str:
    w = common.load_text("advance")
    names = names_of(request)
    protagonist = names.get(request.get("protagonist") or "", "")
    tie_from, tie_to, bond = _ends(request, names)
    who = tie_from or "the person at the from end"
    other = tie_to or "the other person"
    trail = _recent(edge_trail(request), factor)
    tie = ""
    if tie_from and tie_to:
        tie = (w["tie_line"] if bond else w["tie_line_plain"]).format(tie_from=tie_from, tie_to=tie_to, bond=r.bare(bond))
    blocks = [
        w["edge_role"],
        w["protagonist_line"].format(protagonist=protagonist) if protagonist else "",
        tie,
        w["edge_what"].format(tie_from=who, tie_to=other),
        w["edge_trail_lead"] + "\n" + "\n".join(w["edge_trail_item"].format(edge=r.s(e)) for e in trail) if trail else "",
        w["old_edge_line"].format(edge=r.s(old_edge)),
        w["new_edge_line"].format(edge=r.s(new_edge)),
        w["edge_moves"].format(tie_from=who, tie_to=other),
        w["edge_answer"].format(tie_from=who),
    ]
    return "\n\n".join(b for b in blocks if b)


def edge_step(request: dict, old_edge: str, new_edge: str) -> Step:
    """Did the spotlight tie's edge move from `old_edge` to `new_edge`, and how? Reply {reason, move}."""
    return Step("advance_edge", lambda f: edge_prompt(request, old_edge, new_edge, f), "json", MAX_OUTPUT, edge_grammar(), _reason_check,
                "structured", False)


# ---- The pressure step ------------------------------------------------------------------------------------------------------------

def pressure_prompt(request: dict, text: str, source: str, aim: str = "", factor: float = 1.0) -> str:
    """`source` is \"plan\" (the text is the plan of the chapter) or \"happened\" (the text is what the chapter's events say happened)."""
    w = common.load_text("advance")
    names = names_of(request)
    protagonist = names.get(request.get("protagonist") or "", "")
    tie_from, tie_to, bond = _ends(request, names)
    pressure = request.get("pressure")
    kind = r.pressure_kind(pressure)
    tie = ""
    if tie_from and tie_to:
        tie = (w["tie_line"] if bond else w["tie_line_plain"]).format(tie_from=tie_from, tie_to=tie_to, bond=r.bare(bond))
    lead = w["pressure_happened_lead" if source == "happened" else "pressure_plan_lead"]
    blocks = [
        w["pressure_role"].format(kind=kind),
        w["protagonist_line"].format(protagonist=protagonist) if protagonist else "",
        tie,
        w["pressure_element_line"].format(kind=kind, element=r.pressure_element(pressure)),
        w["pressure_aim_line"].format(aim=r.s(aim)) if r.s(aim) else "",
        lead + "\n" + r.clip(text, TEXT_LIMIT),
        w["pressure_effects"].format(kind=kind),
        w["pressure_answer"].format(kind=kind),
    ]
    return "\n\n".join(b for b in blocks if b)


def pressure_step(request: dict, text: str, source: str, aim: str = "") -> Step:
    """Did the chapter's pressure act on it, or was it only there? Reply {reason, effect}. Observe-only: nothing sends anything back for it."""
    return Step("advance_pressure", lambda f: pressure_prompt(request, text, source, aim, f), "json", MAX_OUTPUT, pressure_grammar(), _reason_check,
                "structured", False)


# ---- Reading a verdict ------------------------------------------------------------------------------------------------------------

def _word(value: Any, key: str, words: tuple[str, ...]) -> str:
    word = value.get(key) if isinstance(value, dict) else None
    return word if word in words else ""


def edge_ok(value: Any) -> bool:
    """False only when the judge said the edge only rewords. Anything else, a missing verdict included, is fine."""
    return _word(value, "move", EDGE_MOVES) != "rewords"


def pressure_effect(value: Any) -> str:
    """The pressure verdict word. Anything that cannot be read is `unclear`, the judge's neutral last resort."""
    return _word(value, "effect", PRESSURE_EFFECTS) or "unclear"


def problem_line(kind: str, value: Any) -> str:
    """One line a model can act on, built from the judge's reason: `kind` is "edge" (only the edge is sent back)."""
    if kind != "edge":
        raise ValueError(f"problem_line is for an edge, not {kind!r}")
    w = common.load_text("advance")["problems"]
    reason = r.sentence(r.s(value.get("reason"))) if isinstance(value, dict) else ""
    return w[kind].format(reason=reason) if reason else w[f"{kind}_bare"]


def resend_line(kind: str, value: Any) -> str:
    """The line a flow adds to the prompt of the judged step when it sends that step back once: it says the first reply was set aside, then
    `problem_line`. `kind` is \"edge\"."""
    return f"{common.load_text('advance')['resend'][kind]} {problem_line(kind, value)}"


def notes(aim_value: Any = None, edge_value: Any = None, pressure_value: Any = None) -> dict:
    """Short words for `Flow.notes` (the run log): {"aim_link": ..., "aim_new": ..., "edge_move": ..., "pressure_effect": ...}, each only when its verdict was read
    (the pressure verdict is always a word: `unclear` when it could not be read, as long as the judge ran)."""
    out = {}
    if _word(aim_value, "link", AIM_LINKS):
        out["aim_link"] = aim_value["link"]
    if _word(aim_value, "new_obstacle", YES_NO):
        out["aim_new"] = aim_value["new_obstacle"]
    if _word(edge_value, "move", EDGE_MOVES):
        out["edge_move"] = edge_value["move"]
    if pressure_value is not None:
        out["pressure_effect"] = pressure_effect(pressure_value)
    return out
