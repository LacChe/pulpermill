"""What the runner offers a prompter for one request: the handles of the items the request sent, the grammars that follow from the cards,
and a check for a shifts reply. Built once per call from the request. The prompter's README says how each is used."""
from typing import Any

from . import assemble, grammar
from .handles import Handles, Unresolved


class Kit:
    def __init__(self, request: dict):
        self.request = request
        self.handles = Handles(request)
        self.grammar = Grammars(request, self.handles)

    def shifts_problem(self, entries: Any) -> str | None:
        """None when `entries` (the shifts list, as the model wrote it) can be turned into valid contract entries, else one plain line."""
        try:
            assemble.shifts(entries, self.handles)
        except Unresolved as e:
            return str(e)
        return None


class Grammars:
    """The ready-made grammars (see grammar.py) and the small pieces for building any other."""
    text, maybe, one_of, list_of, obj, unique = (staticmethod(f) for f in (grammar.text, grammar.maybe, grammar.one_of,
                                                                          grammar.list_of, grammar.obj, grammar.unique))

    def __init__(self, request: dict, handles: Handles):
        self._request, self._handles = request, handles

    def fill(self) -> dict:
        return grammar.fill(self._request)

    def plan_beat(self) -> dict:
        return grammar.plan_beat(self._request)

    def shifts(self) -> dict:
        return grammar.shifts(self._request, self._handles)
