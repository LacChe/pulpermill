"""The shift cap (P0 A14): one entry per card that appeared in the chapter (the beat's cast, the World, the Entanglements), at most 7.
The page runs no rule for it; the backend refuses a bad draft in pulpermill/backend/assemble.py, which turns a prompter's draft shifts into
the contract's, and the constant lives in the schema. These tests drive that code with the page's own generate request."""
import copy
import json

import pytest
from helpers import REPO

from pulpermill.backend import assemble
from pulpermill.backend.handles import Handles, Unresolved
from pulpermill.schema.shifts import MAX_SHIFTS_PER_CHAPTER, RULES

VECTORS = json.loads((REPO / "tests" / "shared" / "contract-vectors.json").read_text(encoding="utf-8"))["requests"]
REQUEST = next(r["data"] for r in VECTORS if r["name"] == "a generate request")


def request_with(people: int) -> dict:
    """The generate request with exactly `people` characters in the beat's cast."""
    req = copy.deepcopy(REQUEST)
    base = req["cast"]
    cast = []
    for n in range(people):
        person = copy.deepcopy(base[n % len(base)])
        person["id"], person["name"] = f"c{n}", f"Person {chr(65 + n)}"
        cast.append(person)
    req["cast"] = cast
    return req


def entry(card, target=None, patch=None):
    patch = patch or {"characters": {"fear": "fire"}, "world": {"history": "A flood."},
                      "entanglements": {"ties": [{"op": "replace", "id": "ties.1", "values": {"edge": "to hold on"}}]}}[card]
    return {"card": card, "target": target, "patch": patch}


def one_each(req: dict) -> list[dict]:
    return [entry("characters", p["name"]) for p in req["cast"]] + [entry("world"), entry("entanglements")]


def test_the_cap_is_five_people_plus_the_world_and_the_entanglements():
    assert MAX_SHIFTS_PER_CHAPTER == 5 + 2
    rule = next(r for r in RULES if r.id == "shifts_per_chapter_max")
    assert rule.params == {"group_by": "beat", "max": MAX_SHIFTS_PER_CHAPTER}


@pytest.mark.parametrize("people", [1, 3, 5])
def test_one_entry_per_card_that_appeared_is_accepted_up_to_seven(people):
    req = request_with(people)
    out = assemble.shifts(one_each(req), Handles(req))
    assert len(out) == people + 2 and len(out) <= MAX_SHIFTS_PER_CHAPTER
    assert {e["card"] for e in out} == {"characters", "world", "entanglements"}
    assert {e["target"] for e in out if e["card"] == "characters"} == {p["id"] for p in req["cast"]}


def test_seven_entries_for_a_full_cast_of_five_are_accepted():
    req = request_with(5)
    assert len(assemble.shifts(one_each(req), Handles(req))) == MAX_SHIFTS_PER_CHAPTER


def test_an_eighth_entry_is_refused():
    req = request_with(5)
    drafts = one_each(req) + [entry("world", patch={"history": "Again."})]
    assert len(drafts) == MAX_SHIFTS_PER_CHAPTER + 1
    with pytest.raises(Unresolved):
        assemble.shifts(drafts, Handles(req))


def test_the_cap_itself_refuses_more_entries_than_seven_when_the_request_sent_more_than_five_people():
    req = request_with(6)                                  # a request the page never sends; the cap is still enforced
    with pytest.raises(Unresolved, match="at most 7"):
        assemble.shifts(one_each(req), Handles(req))


def test_two_entries_for_the_same_card_are_refused():
    req = request_with(2)
    twice_world = [entry("world"), entry("world", patch={"history": "Again."})]
    with pytest.raises(Unresolved, match="two entries"):
        assemble.shifts(twice_world, Handles(req))
    twice_person = [entry("characters", "Person A"), entry("characters", "Person A", {"fear": "water"})]
    with pytest.raises(Unresolved, match="two entries"):
        assemble.shifts(twice_person, Handles(req))


def test_a_character_entry_whose_target_is_not_in_the_beats_cast_is_refused():
    req = request_with(2)
    with pytest.raises(Unresolved):
        assemble.shifts([entry("characters", "Somebody Else")], Handles(req))
    with pytest.raises(Unresolved):
        assemble.shifts([entry("characters", None)], Handles(req))
