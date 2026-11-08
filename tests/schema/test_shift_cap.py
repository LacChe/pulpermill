"""What a chapter's shifts may hold (P0 A14): one entry, for the Entanglements, replacing the edge of ties. The page runs no rule for it; the
backend refuses a bad draft in pulpermill/backend/assemble.py, which turns a prompter's draft shifts into the contract's. These tests drive
that code with the page's own generate request. The constant MAX_SHIFTS_PER_CHAPTER is the most entries one beat may hold in a project; the
Characters entries written after the last chapter share the last beat."""
import copy
import json

import pytest
from helpers import REPO

from pulpermill.backend import assemble
from pulpermill.backend.handles import Handles, Unresolved
from pulpermill.schema.shifts import CHAPTER_SHIFT_CARDS, MAX_SHIFTS_PER_CHAPTER, RULES

VECTORS = json.loads((REPO / "tests" / "shared" / "contract-vectors.json").read_text(encoding="utf-8"))["requests"]
REQUEST = next(r["data"] for r in VECTORS if r["name"] == "a generate request")


def edges(*ops) -> dict:
    return {"card": "entanglements", "patch": {"ties": list(ops) or [{"op": "replace", "id": "ties.1", "values": {"edge": "to hold on"}}]}}


def test_the_cap_rule_is_by_beat_and_a_chapter_changes_only_the_entanglements():
    assert MAX_SHIFTS_PER_CHAPTER == 7
    rule = next(r for r in RULES if r.id == "shifts_per_chapter_max")
    assert rule.params == {"group_by": "beat", "max": MAX_SHIFTS_PER_CHAPTER, "except": "last_beat"}
    cast = next(r for r in RULES if r.id == "shift_target_in_cast")
    assert cast.params["except"] == "last_beat"      # a character who left the story early may still have changed over all of it
    assert CHAPTER_SHIFT_CARDS == ["entanglements"]


def test_an_entanglements_entry_that_replaces_an_edge_is_accepted():
    out = assemble.shifts([edges()], Handles(REQUEST))
    assert [e["card"] for e in out] == ["entanglements"] and out[0]["target"] is None


def test_a_chapter_with_no_shifts_is_accepted():
    assert assemble.shifts([], Handles(REQUEST)) == []


@pytest.mark.parametrize("entry", [
    {"card": "characters", "target": "Person A", "patch": {"fear": "fire"}},
    {"card": "world", "patch": {"history": "A flood."}},
])
def test_a_chapter_cannot_shift_characters_or_the_world(entry):
    with pytest.raises(Unresolved, match="only the edge and the bond of ties"):
        assemble.shifts([entry], Handles(REQUEST))


@pytest.mark.parametrize("op", [
    {"op": "replace", "id": "ties.1", "values": {"edge": "to hold on", "tie_to": "someone else"}},
    {"op": "replace", "id": "ties.1", "values": {"strength": "x"}},
    {"op": "remove", "id": "ties.1"},
])
def test_a_chapter_changes_only_the_edge_and_bond_of_a_tie(op):
    with pytest.raises(Unresolved, match="only the edge and the bond of ties"):
        assemble.shifts([edges(op)], Handles(REQUEST))


def test_a_chapter_may_replace_the_bond_with_the_edge():
    out = assemble.shifts([edges({"op": "replace", "id": "ties.1", "values": {"edge": "to hold on", "bond": "a new bond"}})], Handles(REQUEST))
    assert out[0]["patch"]["ties"][0]["values"] == {"edge": "to hold on", "bond": "a new bond"}


def test_holdings_do_not_change_in_a_chapter():
    with pytest.raises(Unresolved, match="only the edge and the bond of ties"):
        assemble.shifts([{"card": "entanglements", "patch": {"holdings": [{"op": "remove", "id": "holdings.1"}]}}], Handles(REQUEST))


def test_two_entries_for_the_entanglements_are_refused():
    with pytest.raises(Unresolved, match="two entries"):
        assemble.shifts([edges(), edges()], Handles(REQUEST))
