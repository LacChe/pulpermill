"""Repeat avoidance, step 1 (Plan 7): the fingerprint vocabulary, the validator, `matches` and `screen`, the label call's grammar, check and
prompt. Pure: no model and no flow. Everything is neutral placeholder text."""
import pytest

from pulpermill.prompter.mill import repeat
from pulpermill.prompter.mill.common import load_text

NAMES = ["Ada", "Bram", "The Guild", "The Gate"]


def fp(**over):
    base = {"aim_kind": "obtain", "obstacle_source": "person", "obstacle_party": "Ada", "turning_kind": "refusal", "outcome": "lost",
            "closing_hook": "new_task", "motive_kind": "recognition", "turning_note": "A door stays shut."}
    return {**base, **over}


# ---- the validator ----------------------------------------------------------------------------------------------------------------

def test_clean_keeps_a_valid_fingerprint_whole():
    assert repeat.clean(fp(), NAMES) == fp()
    assert list(repeat.clean(fp(), NAMES)) == list(repeat.KEYS)


def test_clean_sets_an_invalid_or_missing_value_to_other_and_a_bad_party_to_none():
    out = repeat.clean({"aim_kind": "wander", "turning_kind": 7, "obstacle_party": "Nobody", "outcome": "lost"}, NAMES)
    assert out["aim_kind"] == "other" and out["turning_kind"] == "other"
    assert out["obstacle_source"] == "other" and out["closing_hook"] == "other" and out["motive_kind"] == "other"             # missing
    assert repeat.clean(fp(motive_kind="wanderlust"), NAMES)["motive_kind"] == "other" and repeat.clean(fp(motive_kind=3), NAMES)["motive_kind"] == "other"
    assert out["obstacle_party"] == "none"                                                   # not on the list
    assert out["outcome"] == "lost" and out["turning_note"] == ""


def test_clean_reads_the_party_in_the_list_s_own_spelling_and_a_non_object_as_all_other():
    assert repeat.clean(fp(obstacle_party="  the guild "), NAMES)["obstacle_party"] == "The Guild"
    assert repeat.clean(fp(obstacle_party="Ada"), [])["obstacle_party"] == "none"            # no names given: nothing can be named
    empty = repeat.clean("not a dict", NAMES)
    assert all(empty[k] == "other" for k in repeat.VALUES) and empty["obstacle_party"] == "none"


def test_clean_trims_and_cuts_the_note():
    assert repeat.clean(fp(turning_note="  a  b\n c "), NAMES)["turning_note"] == "a b c"
    assert len(repeat.clean(fp(turning_note="x" * 1000), NAMES)["turning_note"]) == repeat.NOTE_MAX


def test_the_vocabularies_are_the_planned_ones_and_end_in_other_where_the_plan_says():
    assert repeat.OUTCOMES[:3] == ("reached", "lost", "gave_up")
    assert repeat.MOTIVE_KINDS == ("recognition", "closeness", "protection", "avoidance", "duty", "order", "curiosity", "gain", "other")
    assert all(v[-1] == "other" for v in repeat.VALUES.values())
    assert set(repeat.FIELDS) | {repeat.NOTE} == set(repeat.KEYS) and repeat.NOTE not in repeat.FIELDS and len(repeat.FIELDS) == 7 and repeat.FIELDS[-1] == "motive_kind" and repeat.KEYS[-1] == repeat.NOTE
    assert (repeat.K, repeat.T) == (3, 4)


# ---- matches ----------------------------------------------------------------------------------------------------------------------

def test_equal_fingerprints_match_on_all_seven_fields_and_the_note_is_not_compared():
    assert repeat.matches(fp(), fp(turning_note="A different sentence.")) == 7
    assert repeat.matched(fp(), fp()) == repeat.FIELDS


def test_unequal_fields_do_not_match_and_the_names_of_the_matching_ones_come_back_in_order():
    other = fp(aim_kind="keep", turning_kind="bargain", closing_hook="deadline", motive_kind="duty")
    assert repeat.matches(fp(), other) == 3
    assert repeat.matched(fp(), other) == ("obstacle_source", "obstacle_party", "outcome")


def test_other_and_none_never_match_even_when_both_sides_have_them():
    a = fp(aim_kind="other", obstacle_party="none", closing_hook="other", motive_kind="other")
    assert repeat.matches(a, a) == 3
    assert not {"aim_kind", "obstacle_party", "closing_hook", "motive_kind"} & set(repeat.matched(a, a))


def test_the_motive_matches_by_equality_like_the_other_fields_and_other_never_does():
    assert repeat.matched(fp(), fp(aim_kind="keep"))[-1] == "motive_kind" and repeat.matches(fp(), fp(motive_kind="duty")) == 6
    assert "motive_kind" not in repeat.matched(fp(motive_kind="other"), fp(motive_kind="other"))


def test_matches_is_symmetric():
    a, b = fp(), fp(aim_kind="keep", outcome="reached")
    assert repeat.matches(a, b) == repeat.matches(b, a) == 5


# ---- screen -----------------------------------------------------------------------------------------------------------------------

def test_screen_gives_each_idea_its_best_match_and_the_fields_of_that_pairing():
    near = fp(aim_kind="keep", outcome="reached", closing_hook="deadline", motive_kind="duty")             # 3 with the idea
    far = fp(aim_kind="keep", obstacle_source="rule", obstacle_party="Bram", turning_kind="bargain", outcome="reached", closing_hook="deadline", motive_kind="duty")
    got = repeat.screen([fp()], [far, near])
    assert got == [repeat.Screen(3, ("obstacle_source", "obstacle_party", "turning_kind"))]
    assert repeat.screen([fp()], [far]) == [repeat.Screen(0, ())]


def test_screen_looks_only_at_the_last_k_earlier_chapters():
    same = fp()
    different = fp(aim_kind="keep", obstacle_source="rule", obstacle_party="Bram", turning_kind="bargain", outcome="reached", closing_hook="deadline", motive_kind="duty")
    old = [same] + [different] * repeat.K                                              # the match is the K+1-th from the end
    assert repeat.screen([fp()], old)[0].matches == 0
    assert repeat.screen([fp()], [same] + [different] * (repeat.K - 1))[0].matches == 7


def test_screen_skips_chapters_with_no_fingerprint():
    assert repeat.screen([fp()], [None, fp(), None])[0].matches == 7
    assert repeat.screen([fp()], [None, None]) == [repeat.Screen(0, ())]
    assert repeat.screen([fp()], []) == [repeat.Screen(0, ())]


def test_screen_gives_an_idea_with_no_fingerprint_nothing():
    assert repeat.screen([None, fp()], [fp()]) == [repeat.Screen(0, ()), repeat.Screen(7, repeat.FIELDS)]


def test_a_tie_between_two_chapters_keeps_the_more_recent_ones_fields():
    # both match the idea on three fields, but not the same three
    older = fp(aim_kind="keep", obstacle_source="rule", obstacle_party="Bram", motive_kind="duty")             # matches on turning_kind, outcome, closing_hook
    newer = fp(turning_kind="bargain", outcome="reached", closing_hook="deadline", motive_kind="duty")         # matches on aim_kind, obstacle_source, obstacle_party
    assert repeat.screen([fp()], [older, newer])[0] == repeat.Screen(3, ("aim_kind", "obstacle_source", "obstacle_party"))
    assert repeat.screen([fp()], [newer, older])[0] == repeat.Screen(3, ("turning_kind", "outcome", "closing_hook"))


def test_too_similar_is_at_least_t():
    assert repeat.too_similar(repeat.Screen(repeat.T, ())) and not repeat.too_similar(repeat.Screen(repeat.T - 1, ()))


# ---- the label call -----------------------------------------------------------------------------------------------------------------

def reply(*prints):
    return {"prints": [{"n": n, **p} for n, p in prints]}


def test_the_grammar_asks_for_exactly_count_entries_with_the_vocabularies_as_enums():
    g = repeat.grammar(3)
    arr = g["properties"]["prints"]
    assert arr["minItems"] == arr["maxItems"] == 3 and g["required"] == ["prints"]
    props = arr["items"]["properties"]
    assert list(props)[:2] == ["n", "turning_note"] and set(props) == {"n", *repeat.KEYS}
    assert props["turning_kind"]["enum"] == list(repeat.TURNING_KINDS) and "enum" not in props["obstacle_party"]
    assert props["motive_kind"]["enum"] == list(repeat.MOTIVE_KINDS) and list(props)[-1] == "motive_kind" and arr["items"]["required"] == list(props)


def test_the_check_wants_one_entry_per_text_and_does_not_refuse_odd_values():
    assert repeat.label_problem(reply((1, fp()), (2, fp())), 2) is None
    assert repeat.label_problem(reply((1, {"aim_kind": "nonsense"})), 1) is None
    for bad in ({}, {"prints": "x"}, reply((1, fp())), {"prints": [1, 2]}):
        assert "exactly 2" in repeat.label_problem(bad, 2)


def test_read_matches_entries_by_their_number_and_cleans_them():
    items = [(4, "text four"), (5, "text five")]
    got = repeat.read(reply((5, fp(aim_kind="keep")), (4, fp(aim_kind="bogus"))), items, NAMES)
    assert got[0]["aim_kind"] == "other" and got[1]["aim_kind"] == "keep"


def test_read_takes_entries_in_order_when_the_numbers_are_not_usable():
    items = [(4, "a"), (5, "b")]
    value = {"prints": [fp(aim_kind="keep"), fp(aim_kind="persuade")]}
    assert [p["aim_kind"] for p in repeat.read(value, items, NAMES)] == ["keep", "persuade"]
    dup = reply((4, fp(aim_kind="keep")), (4, fp(aim_kind="persuade")))
    assert [p["aim_kind"] for p in repeat.read(dup, items, NAMES)] == ["keep", "persuade"]


def test_read_gives_none_for_every_text_after_a_fallback():
    assert repeat.read({}, [(1, "a"), (2, "b")], NAMES) == [None, None]


def test_the_step_has_a_small_attempt_count_and_a_neutral_last_resort():
    step = repeat.label_step({"language": "en"}, [(1, "one"), (2, "two")], NAMES)
    assert step.name == "label" and step.kind == "json" and step.attempts == repeat.LABEL_ATTEMPTS <= 2
    assert step.fallback() == {} and repeat.read(step.fallback(), [(1, "one"), (2, "two")], NAMES) == [None, None]
    assert step.check(reply((1, fp()), (2, fp()))) is None and step.check({}) is not None


def test_the_prompt_carries_the_texts_the_names_the_values_and_no_ids():
    prompt = repeat.build_label_prompt({"language": "en"}, [(2, "Text about a gate."), (3, "Text about a ledger.")], NAMES)
    assert "Text 2\nText about a gate." in prompt and "Text 3\nText about a ledger." in prompt
    for name in NAMES:
        assert name in prompt
    for values in repeat.VALUES.values():
        assert ", ".join(values) in prompt
    assert "English" in prompt and "exactly 2 entries" in prompt
    w = load_text("plan")
    assert w["label_motive_kind"].format(values=", ".join(repeat.MOTIVE_KINDS)) in prompt and "why the protagonist wants what they go after" in prompt
    assert "closing_hook and motive_kind" in prompt and prompt.index("For closing_hook") < prompt.index("For motive_kind") < prompt.index("For turning_note")


def test_the_prompt_says_so_when_no_names_are_given_and_squeezes_the_texts():
    long = "A sentence goes here. " * 100
    full = repeat.build_label_prompt({}, [(1, long)], [])
    assert load_text("plan")["label_no_names"] in full
    assert len(repeat.build_label_prompt({}, [(1, long)], [], 0.5)) < len(full)


def test_the_worst_case_text_fits_what_the_prompt_reads():
    assert len(repeat.LABEL_STAND_IN) >= repeat.TEXT_LIMIT


@pytest.mark.parametrize("key", [k for k in load_text("plan") if k.startswith("label_")])
def test_every_label_wording_key_is_a_non_empty_string(key):
    assert isinstance(load_text("plan")[key], str) and load_text("plan")[key].strip()
