"""Driver kinds for the brainstorm's ideas (Plan 9): where each idea's aim is drawn from. Structural, never story content: the kind of a
driver is one of a fixed few, code gives each of the three ideas one by the chapter's number, and the model is never asked to pick or name it.

`edge` is the tie's edge (always available); `want`, `fear`, `flaw` and `value` are available when the protagonist's card has them. Pure and
deterministic: no model, no randomness."""
from typing import Any

from pulpermill.prompts import render as r

VERSION = "driver-1"
KINDS = ("edge", "want", "fear", "flaw", "value")      # the fixed order the rotation walks
IDEAS = 3                                              # one kind for each brainstorm idea


def _protagonist(request: dict) -> dict:
    """The protagonist's card from the cast, or an empty one when the request names none that is in the cast."""
    wanted = request.get("protagonist")
    return next((p for p in request.get("cast") or [] if isinstance(p, dict) and wanted and p.get("id") == wanted), {})


def _listed(person: dict, key: str) -> bool:
    """Whether a list field (`wants`, `values`) has at least one item with text."""
    return any(isinstance(item, dict) and r.s(item.get("text")) for item in person.get(key) or [])


def available(request: dict) -> list[str]:
    """The kinds the protagonist's card has, in the fixed order; `edge` always."""
    person = _protagonist(request)
    has = {"edge": True, "want": _listed(person, "wants"), "fear": bool(r.s(person.get("fear"))), "flaw": bool(r.s(person.get("flaw"))),
           "value": _listed(person, "values")}
    return [kind for kind in KINDS if has[kind]]


def assign(request: dict) -> list[str]:
    """One kind for each of the three ideas: the available kinds in the fixed order, starting at `(chapter - 1) % m` and taking three in a row,
    wrapping. With fewer than three kinds they repeat in order; with one kind every idea gets it."""
    kinds = available(request)
    m = len(kinds)
    start = (int(request.get("chapter") or 1) - 1) % m
    return [kinds[(start + i) % m] for i in range(IDEAS)]


def active(request: dict) -> bool:
    """Whether the brainstorm shows driver lines at all: at least two kinds are available (with one, every idea is the edge's, as before)."""
    return len(available(request)) >= 2


def label(request: dict) -> str:
    """The three kinds as one word for the run log, in the ideas' order (`want-fear-edge`)."""
    return "-".join(assign(request))


def text(request: dict, w: dict[str, Any]) -> str:
    """The driver block of the brainstorm prompt: a lead, one line for each idea, and the sentence that the spotlight tie still meets the
    protagonist. Empty when fewer than two kinds are available."""
    if not active(request):
        return ""
    lines = [w["driver_line"].format(n=n, driver=w["driver_kinds"][kind]) for n, kind in enumerate(assign(request), 1)]
    return "\n".join([w["driver_lead"], *lines, w["driver_meets"]])
