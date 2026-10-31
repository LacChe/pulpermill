"""Handles: a short code for each list item a request sent, so the model points at an item without ever seeing an id, and the way back
from what the model said to the ids the page sent. Only what the request sent can be pointed at; anything else is unusable.

A handle is "<list key>.<position from 1>", for example `ties.2`, scoped to the card it is in (a card, or one character). A
character, which is the target of a patch, is named by a label: its name, with " (2)" and so on when two share one."""
from dataclasses import dataclass, field
from typing import Any

from . import cards


class Unresolved(ValueError):
    """The model referred to something the request did not send. The message is one plain line a model can act on."""


@dataclass
class Scope:
    card: str
    target: str | None                    # the id of the character, for a Characters card
    label: str | None                     # what the model calls the target
    lists: dict[str, list[str | None]]    # list key -> the item ids in the order sent (None for an item sent without one)
    scalars: list[str] = field(default_factory=list)   # keys that hold a plain value

    def handle(self, key: str, position: int) -> str:
        return f"{key}.{position}"

    def handles(self, key: str) -> list[str]:
        """The handles of the items of one list that have an id (only those can be replaced or removed)."""
        return [self.handle(key, n) for n, i in enumerate(self.lists.get(key, []), 1) if i]

    def of(self, key: str, item_id: str) -> str:
        """The handle of the item with this id, for a prompter showing the item to the model."""
        for n, i in enumerate(self.lists.get(key, []), 1):
            if i == item_id:
                return self.handle(key, n)
        raise KeyError(item_id)

    def item(self, handle: Any, key: str | None = None) -> str:
        """The id the handle stands for. `key`, when given, is the list the handle must be in."""
        name, _, number = str(handle).rpartition(".")
        if not name or not number.isdigit() or (key is not None and name != key):
            raise Unresolved(f"{handle!r} is not one of the handles you were shown{f' for {key}' if key else ''}")
        n = int(number)
        ids = self.lists.get(name)
        if ids is None or not 1 <= n <= len(ids) or not ids[n - 1]:
            raise Unresolved(f"{handle!r} is not one of the handles you were shown")
        return ids[n - 1]


class Handles:
    def __init__(self, request: dict):
        self.scopes: list[Scope] = []
        seen: dict[str, int] = {}
        for sent in cards.cards_sent(request):
            label = None
            if sent.card == "characters":
                base = str(sent.values.get(cards.label_key("characters")) or "").strip() or f"{sent.card} {len(self.scopes) + 1}"
                seen[base] = seen.get(base, 0) + 1
                label = base if seen[base] == 1 else f"{base} ({seen[base]})"
            lists = {}
            for key in cards.list_fields(sent.card):
                items = sent.values.get(key)
                if isinstance(items, list):
                    lists[key] = [i.get("id") if isinstance(i, dict) and isinstance(i.get("id"), str) and i.get("id") else None for i in items]
            scalars = [k for k, v in sent.values.items() if k != "id" and k not in lists and v not in (None, "", [], {})]
            self.scopes.append(Scope(sent.card, sent.target, label, lists, scalars))

    def scope(self, card: str, label: str | None = None) -> Scope:
        """The scope of a card the request sent; for Characters, the one the model calls `label`."""
        for s in self.scopes:
            if s.card == card and (card != "characters" or s.label == label):
                return s
        raise Unresolved(f"{label or card!r} is not a card you were shown" if label or card != "characters" else "a character is needed")

    def of_card(self, card: str) -> list[Scope]:
        return [s for s in self.scopes if s.card == card]

    def only(self) -> Scope:
        """The scope of a fill or a judge, which is about one card."""
        return self.scopes[0]
