"""The advancement judge: two small JSON steps that ask a model whether a chapter really moved. `aim_step` sorts the protagonist's aim for a
chapter into a new kind or the same kind as an earlier one; `edge_step` sorts the change of the spotlight tie's edge into one move
(escalates, reverses, complicates, resolves) or a rewording. A step is a classification, never a comparison of wording, and the reason
comes first in the reply so that the verdict follows from it.

Nothing here is wired into a flow (phase 3 does that). `ENFORCE` says whether a flow should act on a bad verdict; it stays False until
phase 4. The verdict helpers are neutral on anything they cannot read: a missing or odd value is never a bad verdict, so a judge that
failed can never cost a chapter.

Inputs are read from a `plan` or `generate` request: earlier aims from `earlier_beats`, the edge trail from `spotlight_edges`, and the
names from the cards. Names, never ids. Wording lives in text/en/advance.yaml."""
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompter.base import Step

from . import common

VERSION = "advance-1"
ENFORCE = False
MAX_OUTPUT = 160            # one short sentence and one word, with room to spare

AIM_KINDS = ("new_kind", "same_kind")
EDGE_MOVES = ("escalates", "reverses", "complicates", "resolves", "rewords")


# ---- The shape of a reply -----------------------------------------------------------------------------------------------------
# Plain JSON Schema (the same keywords the backend's grammar builder accepts). The prompter never imports the backend, so the two small
# shapes are written here; `reason` comes first, and its order is the order the model writes in.

def _grammar(verdict: str, words: tuple[str, ...]) -> dict:
    return {"type": "object", "properties": {"reason": {"type": "string"}, verdict: {"type": "string", "enum": list(words)}},
            "required": ["reason", verdict], "additionalProperties": False}


def aim_grammar() -> dict:
    return _grammar("kind", AIM_KINDS)


def edge_grammar() -> dict:
    return _grammar("move", EDGE_MOVES)


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


def edge_trail(request: dict) -> list[str]:
    """The spotlight tie's edges in earlier chapters, oldest first, from `spotlight_edges` (I3); an old request without it has none."""
    return [e for e in (r.s(x) for x in request.get("spotlight_edges") or []) if e]


# ---- The aim step -----------------------------------------------------------------------------------------------------------------

def aim_prompt(request: dict, aim: str, factor: float = 1.0) -> str:
    w = common.load_text("advance")
    names = names_of(request)
    protagonist = names.get(request.get("protagonist") or "", "")
    tie_from, tie_to, bond = _ends(request, names)
    aims = _recent(earlier_aims(request), factor)
    lines = [w["aims_item"].format(chapter=n, aim=r.s(text)) for n, text in aims]
    tie = ""
    if tie_from and tie_to:
        tie = (w["tie_line"] if bond else w["tie_line_plain"]).format(tie_from=tie_from, tie_to=tie_to, bond=r.bare(bond))
    blocks = [
        w["aim_role"],
        w["protagonist_line"].format(protagonist=protagonist) if protagonist else "",
        tie,
        w["aims_lead"] + "\n" + "\n".join(lines) if lines else "",
        w["new_aim_line"].format(chapter=int(request.get("chapter") or 0), aim=r.s(aim)),
        w["aim_kinds"],
        w["aim_answer"],
    ]
    return "\n\n".join(b for b in blocks if b)


def _reason_check(value: Any) -> str | None:
    reason = r.s(value.get("reason")) if isinstance(value, dict) else ""
    if not reason:
        return "Give the reason first, as one short sentence."
    return "Keep the reason to one short sentence." if len(reason) > 400 else None


def aim_step(request: dict, aim: str) -> Step:
    """Is `aim`, the protagonist's aim for this chapter, a new kind of aim or the same kind as an earlier one? Reply {reason, kind}."""
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


# ---- Reading a verdict ------------------------------------------------------------------------------------------------------------

def _word(value: Any, key: str, words: tuple[str, ...]) -> str:
    word = value.get(key) if isinstance(value, dict) else None
    return word if word in words else ""


def aim_ok(value: Any) -> bool:
    """False only when the judge said the aim is the same kind as an earlier one. Anything else, a missing verdict included, is fine."""
    return _word(value, "kind", AIM_KINDS) != "same_kind"


def edge_ok(value: Any) -> bool:
    """False only when the judge said the edge only rewords. Anything else, a missing verdict included, is fine."""
    return _word(value, "move", EDGE_MOVES) != "rewords"


def problem_line(kind: str, value: Any) -> str:
    """One line a model can act on, built from the judge's reason: `kind` is "aim" or "edge"."""
    if kind not in ("aim", "edge"):
        raise ValueError(f"problem_line is for an aim or an edge, not {kind!r}")
    w = common.load_text("advance")["problems"]
    reason = r.sentence(r.s(value.get("reason"))) if isinstance(value, dict) else ""
    return w[kind].format(reason=reason) if reason else w[f"{kind}_bare"]


def notes(aim_value: Any = None, edge_value: Any = None) -> dict:
    """Short words for `Flow.notes` (the run log): {"aim_kind": ..., "edge_move": ...}, each only when its verdict was read."""
    out = {}
    if _word(aim_value, "kind", AIM_KINDS):
        out["aim_kind"] = aim_value["kind"]
    if _word(edge_value, "move", EDGE_MOVES):
        out["edge_move"] = edge_value["move"]
    return out
