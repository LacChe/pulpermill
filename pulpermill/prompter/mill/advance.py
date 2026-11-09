"""The running aim: the aims of the earlier chapters and how each ended, read from a `plan` request. `earlier_aims` lists the aims
(chapter, aim) and `chain` joins each with the chapter's `changed` line from `earlier_events`; plan.py shows them as the running aim in the
brainstorm and plan prompts. This module once held the judges that read these (the aim, edge, edge-check and pressure
judges); they were removed, and what is left is these two readers. Names, never ids; no wording lives here."""
from pulpermill.prompts import render as r


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
