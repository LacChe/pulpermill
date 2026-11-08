"""Step 3c: the World fill says what each field is for and what a good value does (no sample values), matches the schema's list limits, and keeps the
pinned sentences. The first group reads the wording file alone; the second builds the real World prompt."""
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORDING = yaml.safe_load((ROOT / "pulpermill/prompter/mill/text/en/fill.yaml").read_text(encoding="utf-8"))
SCHEMA = yaml.safe_load((ROOT / "pulpermill/schema/text/en/world.yaml").read_text(encoding="utf-8"))
FIELDS, ITEMS, CARD = WORDING["fields"]["world"], WORDING["item_fields"]["world"], WORDING["cards"]["world"]
CARD_TEXT = " ".join([CARD["intro"], CARD["scope"], *CARD["specific"]])
LISTS = ["places", "objects", "powers", "rules", "terms"]
UNCAPPED = ["places", "objects"]          # schema/world.py marks these uncapped; the other lists stop at MAX_ITEMS (five)


def test_every_world_field_and_list_item_field_keeps_a_meaning_sentence():
    assert set(FIELDS) == set(SCHEMA["fields"])
    for field, spec in SCHEMA["fields"].items():
        for item in (spec.get("item_fields") or {}):
            assert ITEMS[field][item], (field, item)
    assert all(len(v) > 20 for v in FIELDS.values())


def test_the_wording_matches_the_schemas_list_limits():
    from_schema = _uncapped_in_schema()
    if from_schema is not None:
        assert from_schema == set(UNCAPPED)
    for key in LISTS:
        assert "Up to five" in FIELDS[key], key
    for key in UNCAPPED:
        assert "more only when the writer lists more" in FIELDS[key], key
    assert "Places and things go past five only when the writer lists more" in CARD_TEXT
    assert "Groups, rules and terms take at most five each" in CARD_TEXT and "no limit" not in CARD_TEXT


def _uncapped_in_schema():
    src = (ROOT / "pulpermill/schema/world.py").read_text(encoding="utf-8")
    found = set(re.findall(r"^    (\w+): list\[\w+\] = spec\([^\n]*uncapped=True", src, re.M))
    return found or None


def test_era_is_facts_only_and_keeps_every_stated_number_and_technology():
    era = FIELDS["era_and_technology"]
    assert "Facts only" in era and "Every number and every technology the writer states stays" in era
    assert "no mood" in era and "no comparison to a real period" in era.lower()


def test_everyday_life_needs_friction():
    assert "friction" in FIELDS["everyday_life"] and "what people struggle for or fight over" in FIELDS["everyday_life"]


def test_a_place_effect_says_what_people_do_say_or_risk_and_invented_places_meet_the_same_bar():
    assert "what people do, say or risk differently there" in FIELDS["places"] and "mood or atmosphere is not an effect" in FIELDS["places"]
    assert "Places you invent meet the same bar as places the writer lists" in FIELDS["places"]
    assert "Mood or atmosphere is not an effect" in ITEMS["places"]["effect"]


def test_every_object_is_something_someone_could_want_and_has_no_owner_or_location():
    objects = FIELDS["objects"]
    assert "something someone could want or fight over" in objects and "no thing is only decoration" in objects
    assert "A thing has no owner and no location here" in objects and "fight over" in ITEMS["objects"]["significance"]


def test_a_group_is_met_in_daily_life_and_its_hold_uses_the_five_kinds():
    powers = FIELDS["powers"]
    assert "(force, money, law, belief, numbers)" in powers and "some friction" in powers and "never what it currently plans or wants" in powers
    assert "one or two of exactly these words: force, money, law, belief, numbers" in ITEMS["powers"]["hold"]
    assert "concrete way an ordinary person meets it in a day" in ITEMS["powers"]["felt"] and "one plain sentence" in ITEMS["powers"]["nature"]


def test_a_rule_has_a_concrete_cost_a_broken_kind_and_can_put_anyone_in_a_dilemma():
    rules = FIELDS["rules"]
    assert "a dilemma" in rules and "A rule with no price gives way to one that has a price" in rules
    assert "something concrete that someone loses or risks" in ITEMS["rules"]["cost"]
    for kind in ("impossible", "punished", "shamed", "side effect"):
        assert kind in ITEMS["rules"]["when_broken"]


def test_terms_are_invented_or_local_words_and_a_common_word_is_not_redefined():
    assert "invented for or particular to this world" in FIELDS["terms"] and "A common word is not redefined" in FIELDS["terms"]


def test_the_card_says_what_it_is_for_and_that_every_field_is_filled():
    assert "places and rules need effects and costs" in CARD_TEXT and "every thing needs someone who wants it" in CARD_TEXT and "Every field is filled" in CARD_TEXT


def test_the_pinned_world_sentences_stay():
    for sentence in ("keep the thing and leave the owner and the location out", "they are written later as holdings", "what the group is planning or about to do",
                     "No character's name appears anywhere on this card.", "The card names no character and never says who holds, knows or wants something"):
        assert sentence in CARD_TEXT, sentence
    assert "naming no individual" in FIELDS["history"]


def test_the_world_wording_has_no_sample_value_and_no_story_word():
    text = yaml.safe_dump({"f": FIELDS, "i": ITEMS, "c": CARD}).lower()
    samples = []
    for field in SCHEMA["fields"].values():
        samples += (field.get("examples") or {}).get("good", []) + (field.get("examples") or {}).get("avoid", [])
        for item in (field.get("item_fields") or {}).values():
            samples += (item.get("examples") or {}).get("good", []) + (item.get("examples") or {}).get("avoid", [])
    assert samples
    for sample in samples:
        assert sample.lower() not in text, sample
    for word in "bakery baker bread oven dough applewood apple fog weather pim orla corbin thimble hollow loafcast".split():
        assert not re.search(rf"\b{word}\b", text), word


def _build():
    pytest.importorskip("starlette"); pytest.importorskip("uvicorn"); pytest.importorskip("requests")
    sys.path.insert(0, str(Path(__file__).parent))
    import test_fill_wording as w
    return w


@pytest.mark.parametrize("mode", ["note", "chapter", "both"])
def test_the_world_prompt_carries_the_new_wording_and_the_pinned_sentences(mode):
    w = _build()
    text = w.prompt(w.req("world", **w.MODES[mode]))
    for needed in (FIELDS["places"], FIELDS["powers"], FIELDS["rules"], ITEMS["powers"]["hold"], ITEMS["rules"]["cost"], w.SCOPE["world"],
                   "keep the thing and leave the owner and the location out", "what the group is planning or about to do", "naming no individual"):
        assert needed in text, needed[:40]
    assert "no limit" not in text
