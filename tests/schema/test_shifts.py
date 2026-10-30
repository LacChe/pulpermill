"""The shift layer (P2): validate_patch, shiftable_fields, and the shared vectors in tests/shared/overlay-vectors.json.
Python never applies a patch (the overlay is page code, P0 A6); it only checks that the patches in the vectors are valid or
invalid as labelled, and that the vectors are well formed."""
import json
import pytest
from typing import Literal
from helpers import *
from pulpermill.schema import shifts
from pulpermill.schema.common import Item, spec
from pulpermill.schema.shifts import validate_patch, shiftable_fields, MAX_SHIFTS_PER_CHAPTER, PatchProblem

VECTORS = json.loads((REPO / "tests" / "shared" / "overlay-vectors.json").read_text(encoding="utf-8"))
OVERLAY = VECTORS["overlay"]
VALIDATION = VECTORS["patch_validation"]
KINDS = {"characters", "world", "entanglements"}


def codes(card_id, patch):
    return sorted((p.code, p.field) for p in validate_patch(card_id, patch))


# ---------------------------------------------------------------- the vectors
def test_the_vector_file_has_the_two_sections_and_the_rules():
    assert set(VECTORS) == {"about", "overlay_rules", "overlay", "patch_validation"}
    assert VECTORS["overlay_rules"] and all(isinstance(r, str) for r in VECTORS["overlay_rules"])


def test_every_overlay_case_is_well_formed():
    names = [c["name"] for c in OVERLAY]
    assert len(names) == len(set(names))
    for c in OVERLAY:
        assert set(c) == {"name", "why", "beats", "base", "shifts", "chapter", "expected"}, c["name"]
        assert set(c["base"]) <= KINDS and set(c["expected"]) == set(c["base"]), c["name"]
        assert isinstance(c["chapter"], int) and c["chapter"] >= 1, c["name"]
        for e in c["shifts"]:
            assert set(e) == {"beat", "card", "target", "patch"}, c["name"]
            assert e["beat"] in c["beats"] and e["card"] in KINDS, c["name"]
            assert e["card"] in c["base"], (c["name"], "a shift for a card the case has no base for")
            assert (e["target"] is not None) == (e["card"] == "characters"), c["name"]
            if e["target"] is not None:
                assert e["target"] in {x["id"] for x in c["base"]["characters"]}, c["name"]


def test_every_patch_in_the_overlay_cases_is_valid():
    for c in OVERLAY:
        for e in c["shifts"]:
            assert validate_patch(e["card"], e["patch"]) == [], (c["name"], e["patch"])


def test_the_overlay_cases_cover_what_the_spec_lists():
    names = {c["name"] for c in OVERLAY}
    for wanted in ("scalar_set_then_set_again_later_wins", "list_add_then_replace_the_added_item", "list_remove_the_added_item",
                   "replace_changes_only_the_keys_it_carries", "an_entry_for_chapter_3_is_not_seen_for_chapter_3",
                   "an_entry_for_chapter_3_is_seen_for_chapter_4", "replace_of_an_id_that_does_not_exist_changes_nothing",
                   "remove_of_an_id_that_does_not_exist_changes_nothing", "two_characters_with_different_targets_do_not_affect_each_other",
                   "no_shifts_returns_the_base_cards_unchanged", "tie_edge_change", "holding_holder_change"):
        assert wanted in names, wanted
    # chapter 3 is wanted for 3 and 4 with the same entries
    by = {c["name"]: c for c in OVERLAY}
    a, b = by["an_entry_for_chapter_3_is_not_seen_for_chapter_3"], by["an_entry_for_chapter_3_is_seen_for_chapter_4"]
    assert a["shifts"] == b["shifts"] and (a["chapter"], b["chapter"]) == (3, 4) and a["expected"] != b["expected"]


def test_an_overlay_expected_state_differs_from_its_base_only_when_a_shift_should_show():
    unchanged = {c["name"] for c in OVERLAY if c["expected"] == c["base"]}
    assert {"no_shifts_returns_the_base_cards_unchanged", "an_entry_for_chapter_3_is_not_seen_for_chapter_3",
            "replace_of_an_id_that_does_not_exist_changes_nothing", "chapter_1_always_sees_the_base_cards"} <= unchanged


@pytest.mark.parametrize("case", VALIDATION, ids=[c["name"] for c in VALIDATION])
def test_patch_validation_vectors(case):
    assert set(case) == {"name", "card", "patch", "problems"}
    expected = sorted((p["code"], p["field"]) for p in case["problems"])
    assert codes(case["card"], case["patch"]) == expected


def test_patch_validation_covers_every_case_the_spec_lists():
    names = [c["name"] for c in VALIDATION]
    assert len(names) == len(set(names))
    assert any(not c["problems"] for c in VALIDATION)
    seen = {p["code"] for c in VALIDATION for p in c["problems"]}
    # no shiftable field has a fixed set of options yet, so bad_option is tested on a synthetic card below
    assert seen == {"fixed_field", "unknown_field", "identity_field", "bad_type", "missing_id", "empty_patch",
                    "missing_value", "unknown_item_field", "bad_operation", "empty_values", "empty_list"}


# ---------------------------------------------------------------- validate_patch
def test_problems_carry_a_code_a_field_and_a_message():
    (p,) = validate_patch("characters", {"name": "X"})
    assert isinstance(p, PatchProblem) and (p.code, p.field) == ("fixed_field", "name") and p.message.strip()


def test_a_patch_for_a_card_that_cannot_be_shifted_is_refused():
    for card_id in ("style", "setup", "outline", "nope"):
        assert [p.code for p in validate_patch(card_id, {"fear": "x"})] == ["unknown_card"]


def test_validate_patch_does_not_change_the_patch():
    patch = {"fear": "x", "wants": [{"op": "add", "id": "e5f6a7b8", "values": {"text": "y"}}]}
    before = json.dumps(patch)
    assert validate_patch("characters", patch) == [] and json.dumps(patch) == before


def test_a_bool_is_not_a_number_and_a_number_is_not_text():
    assert codes("characters", {"fear": True}) == [("bad_type", "fear")]
    assert codes("characters", {"fear": None}) == [("bad_type", "fear")]


def test_it_reports_every_problem_not_only_the_first():
    got = codes("characters", {"name": "X", "nickname": "N", "fear": 3})
    assert got == [("bad_type", "fear"), ("fixed_field", "name"), ("unknown_field", "nickname")]


def test_an_add_may_set_identity_fields_and_a_replace_may_not():
    add = {"ties": [{"op": "add", "id": "t2", "values": {"tie_from": "a", "tie_to": "b", "bond": "x", "edge": "y"}}]}
    rep = {"ties": [{"op": "replace", "id": "t1", "values": {"tie_from": "a", "tie_to": "b"}}]}
    assert validate_patch("entanglements", add) == []
    assert codes("entanglements", rep) == [("identity_field", "ties.tie_from"), ("identity_field", "ties.tie_to")]


def test_the_item_id_is_not_an_item_field():
    assert codes("characters", {"wants": [{"op": "replace", "id": "a", "values": {"id": "b"}}]}) == [("unknown_item_field", "wants.id")]


def test_a_missing_id_is_reported_for_a_blank_or_non_text_id():
    for bad in ("", "  ", None, 5):
        assert codes("world", {"places": [{"op": "remove", "id": bad}]}) == [("missing_id", "places")]


def test_a_wrong_option_is_refused_and_a_field_added_to_a_card_later_is_shiftable(monkeypatch):
    """No shiftable field has a fixed set of options yet, so this uses a synthetic card. It also shows that nothing in
    shifts.py names a field: a card that gains one is shiftable with no other change."""
    class Mood(Item):
        label: str = spec("text", None, "note")
        tone: Literal["calm", "angry"] = spec("select", None, "note")
        pinned_to: str = spec("text", None, "note", identity=True)

    class Mock(Item):
        title: str = spec("text", "g", "free", fixed=True)
        mood: Literal["calm", "angry"] = spec("select", "g", "axis")
        weight: int = spec("number", "g", "free")
        moods: list[Mood] = spec(None, "g", "pairs", repeat=True)

    from pulpermill.schema import CARDS
    monkeypatch.setitem(CARDS, "mock", (Mock, [], [], [], {}))
    monkeypatch.setattr(shifts, "SHIFT_CARDS", shifts.SHIFT_CARDS + ["mock"])
    assert validate_patch("mock", {"mood": "angry", "weight": 3}) == []
    assert codes("mock", {"mood": "furious"}) == [("bad_option", "mood")]
    assert codes("mock", {"mood": 3}) == [("bad_type", "mood")]
    assert codes("mock", {"weight": "3"}) == [("bad_type", "weight")]
    assert codes("mock", {"title": "x"}) == [("fixed_field", "title")]
    op = {"op": "replace", "id": "m1", "values": {"tone": "furious"}}
    assert codes("mock", {"moods": [op]}) == [("bad_option", "moods.tone")]
    assert codes("mock", {"moods": [{**op, "values": {"pinned_to": "x"}}]}) == [("identity_field", "moods.pinned_to")]
    by_key = {f["key"]: f for f in shiftable_fields("mock")}
    assert list(by_key) == ["mood", "weight", "moods"]
    assert by_key["mood"] == {"key": "mood", "type": "scalar", "options": ["calm", "angry"]}
    assert by_key["moods"]["item_fields"] == ["label", "tone"] and by_key["moods"]["identity_fields"] == ["pinned_to"]
    assert by_key["moods"]["item_options"] == {"tone": ["calm", "angry"]}


# ---------------------------------------------------------------- shiftable_fields
def test_shiftable_fields_are_every_card_field_that_is_not_fixed():
    for cid in KINDS:
        model = CARDS[cid][0]
        expected = [n for n, f in fields_of(model).items() if not f.json_schema_extra.get("fixed")]
        assert [f["key"] for f in shiftable_fields(cid)] == expected, cid
    chars = {f["key"] for f in shiftable_fields("characters")}
    assert chars.isdisjoint({"name", "age", "sex", "appearance"})
    assert chars == {"sketch", "wants", "fear", "flaw", "values", "behaviors", "competence", "vulnerability", "speech", "history"}


def test_each_shiftable_field_says_scalar_or_list_and_lists_name_their_item_fields():
    chars = {f["key"]: f for f in shiftable_fields("characters")}
    assert chars["fear"] == {"key": "fear", "type": "scalar", "options": None}
    assert chars["wants"]["type"] == "list" and chars["wants"]["options"] is None
    assert chars["wants"]["item_fields"] == ["text"] and chars["wants"]["identity_fields"] == []
    assert chars["behaviors"]["item_fields"] == ["state", "tendency"]
    ent = {f["key"]: f for f in shiftable_fields("entanglements")}
    assert ent["ties"]["item_fields"] == ["bond", "edge"] and ent["ties"]["identity_fields"] == ["tie_from", "tie_to"]
    assert ent["holdings"]["item_fields"] == ["held_by"] and ent["holdings"]["identity_fields"] == ["holdee"]
    world = {f["key"]: f for f in shiftable_fields("world")}
    assert world["places"]["item_fields"] == ["name", "description", "effect"]
    assert world["rules"]["item_fields"] == ["statement", "cost", "when_broken"]


def test_shiftable_fields_of_a_card_that_cannot_be_shifted_is_empty():
    for cid in ("style", "setup", "outline", "shifts", "nope"):
        assert shiftable_fields(cid) == []


def test_everything_shiftable_passes_validation_and_nothing_else_does():
    """The two functions agree: a scalar patch built from shiftable_fields is accepted, and every other key is refused."""
    for cid in KINDS:
        keys = {f["key"] for f in shiftable_fields(cid)}
        for key in set(fields_of(CARDS[cid][0])) - keys:
            assert [p.code for p in validate_patch(cid, {key: "x"})] == ["fixed_field"], (cid, key)
        for f in shiftable_fields(cid):
            if f["type"] == "list":
                assert validate_patch(cid, {f["key"]: [{"op": "remove", "id": "x"}]}) == [], (cid, f["key"])


# ---------------------------------------------------------------- the record itself
def test_the_cap_is_seven_and_the_rule_uses_it():
    assert MAX_SHIFTS_PER_CHAPTER == 7
    rule = {r.id: r for r in CARDS["shifts"][3]}["shifts_per_chapter_max"]
    assert rule.params["max"] == MAX_SHIFTS_PER_CHAPTER and rule.params["group_by"] == "beat"


def test_shifts_hold_no_pairs_beyond_the_three_cards():
    assert shifts.SHIFT_CARDS == ["characters", "world", "entanglements"]
    assert set(options_of(fields_of(shifts.ShiftEntry)["card"])) == set(shifts.SHIFT_CARDS)


def test_a_project_round_trips_with_shifts_and_the_old_names_are_not_in_its_json():
    from pulpermill.schema.project import Project
    from test_project import sample
    p = sample(Project)
    text = p.model_dump_json()
    assert '"shifts"' in text
    assert Project.model_validate_json(text) == p
