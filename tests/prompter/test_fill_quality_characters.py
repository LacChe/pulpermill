"""Step 3b: the Characters fill says what each field is for and what a good value does (no sample values), asks for up to five of each list, and
keeps the pinned sentences. The first group reads the wording file alone; the second builds the real Characters prompt."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORDING = yaml.safe_load((ROOT / "pulpermill/prompter/mill/text/en/fill.yaml").read_text(encoding="utf-8"))
SCHEMA = yaml.safe_load((ROOT / "pulpermill/schema/text/en/characters.yaml").read_text(encoding="utf-8"))
FIELDS, ITEMS, CARD = WORDING["fields"]["characters"], WORDING["item_fields"]["characters"], WORDING["cards"]["characters"]
CARD_TEXT = " ".join([CARD["intro"], CARD["scope"], *CARD["specific"]])
LISTS = ["wants", "values", "behaviors"]


def test_every_characters_field_and_list_item_field_keeps_a_meaning_sentence():
    assert set(FIELDS) == set(SCHEMA["fields"])
    assert {(f, k) for f, d in ITEMS.items() for k in d} == {("wants", "text"), ("values", "text"), ("behaviors", "state"), ("behaviors", "tendency")}
    assert all(len(v) > 20 for v in FIELDS.values())


@pytest.mark.parametrize("key", LISTS)
def test_each_list_asks_for_up_to_five_items(key):
    assert "Up to five" in FIELDS[key]


def test_wants_are_specific_to_the_person_distinct_and_in_the_writers_words():
    wants = FIELDS["wants"]
    assert "could not sit unchanged on another person's card" in wants and "no two say the same in other words" in wants
    assert "(time, safety, loyalty, pride)" in wants and "in the writer's own words" in wants
    assert "none names a person, an object or a place, and none is a concrete aim" in wants
    assert "never fewer than two" in wants and "never fewer than two" in CARD_TEXT
    assert "never a single word" in ITEMS["wants"]["text"] and "never a concrete aim" in ITEMS["wants"]["text"]


def test_values_keep_the_limit_the_writer_stated():
    assert "how or how far" in FIELDS["values"] and "a limit the writer stated stays in the writer's own words" in FIELDS["values"]
    assert "never a single word" in ITEMS["values"]["text"] and "held dear" in ITEMS["values"]["text"]


def test_fear_is_an_avoidance_and_flaw_is_a_false_belief_not_a_slogan_or_a_behavior():
    assert "name the avoidance" in FIELDS["fear"]
    flaw = FIELDS["flaw"]
    assert "false belief" in flaw and "not as a slogan or a behavior" in flaw and "write the belief behind it" in flaw


def test_behaviors_states_are_moods_or_pressures_and_one_is_calm():
    behaviors = FIELDS["behaviors"]
    assert "a mood or a pressure, never an activity or a topic" in behaviors and "calm or happy" in behaviors and "a leaning" in behaviors
    assert "never an activity, a topic or a particular event" in ITEMS["behaviors"]["state"] and "never a single act" in ITEMS["behaviors"]["tendency"]


def test_sketch_vulnerability_and_history_are_written_in_this_persons_terms():
    assert "could not be copied onto another person's card" in FIELDS["sketch"] and "one contradiction" in FIELDS["sketch"]
    vuln = FIELDS["vulnerability"]
    assert "a specific place where someone could press" in vuln and "tied to the fear or the shame" in vuln
    history = FIELDS["history"]
    assert "two or three sentences of events and conditions" in history and "explains the flaw or a want" in history
    assert "becomes the condition it created for this person, never a named or described person" in history


def test_competence_is_concrete_skills_the_story_could_reward():
    assert "concrete skills that the story could reward" in FIELDS["competence"]


def test_the_card_says_what_it_is_for_and_that_every_field_is_filled():
    assert "Later steps read this card" in CARD_TEXT and "Every field is filled" in CARD_TEXT and "as specific as one the writer stated" in CARD_TEXT


def test_the_pinned_character_sentences_stay():
    for sentence in ("A want is a broad desire", "so no want names one", "Fear, flaw, vulnerability and values say four different things", "Copy every stated fact exactly",
                     "The card names no other person, place or object and no relationship"):
        assert sentence in CARD_TEXT, sentence


def test_the_characters_wording_has_no_sample_value_and_no_story_word():
    import re
    text = yaml.safe_dump({"f": FIELDS, "i": ITEMS, "c": CARD}).lower()
    samples = []
    for key, field in SCHEMA["fields"].items():
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
def test_the_characters_prompt_carries_the_new_wording_and_the_pinned_sentences(mode):
    w = _build()
    text = w.prompt(w.req("characters", **w.MODES[mode]))
    for needed in (FIELDS["wants"], FIELDS["flaw"], FIELDS["history"], ITEMS["wants"]["text"], ITEMS["behaviors"]["state"], "A want is a broad desire", "Copy every stated fact exactly",
                   "Fear, flaw, vulnerability and values say four different things", w.SCOPE["characters"], "Later steps read this card"):
        assert needed in text, needed[:40]
    assert "Two to five" not in text
