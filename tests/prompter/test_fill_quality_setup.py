"""Step 3e: the Setup fill keeps the normal short (the card sends only about 700 characters of it onward), builds it from the cards without the character
card's own labels, and makes the disruption one past event that stands on its own. The first group reads the wording file alone; the second builds the prompt."""
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORDING = yaml.safe_load((ROOT / "pulpermill/prompter/mill/text/en/fill.yaml").read_text(encoding="utf-8"))
SCHEMA = yaml.safe_load((ROOT / "pulpermill/schema/text/en/setup.yaml").read_text(encoding="utf-8"))
FIELDS, CARD = WORDING["fields"]["setup"], WORDING["cards"]["setup"]
CARD_TEXT = " ".join([CARD["intro"], CARD["scope"], *CARD["specific"]])
LEAVE_OUT = ["nothing to say", "something to say", "is left out", "stays empty", "stay empty", "leave those fields out", "leave it out"]


def test_every_setup_field_keeps_a_meaning_sentence_and_chapter_count_is_unchanged():
    assert set(FIELDS) == set(SCHEMA["fields"])
    assert all(len(v) > 20 for v in FIELDS.values())
    assert FIELDS["chapter_count"] == "How many chapters the story runs, a whole number."


def test_the_wording_cap_for_the_normal_is_the_schemas_cap():
    src = (ROOT / "pulpermill/schema/setup.py").read_text(encoding="utf-8")
    caps = {k: int(v) for k, v in re.findall(r"^    (normal|disruption): str = spec\([^\n]*cap=(\d+)", src, re.M)}
    assert caps == {"normal": 700, "disruption": 700}
    assert "at most about 700 characters" in FIELDS["normal"]


def test_the_normal_is_a_short_concrete_day_built_from_the_cards_without_their_labels():
    normal = FIELDS["normal"]
    assert "five or six sentences" in normal and "the card keeps no more than that" in normal
    assert "routines, places and people from the world and the ties" in normal and "no more people and places than the cards hold" in normal
    assert "through what the day contains" in normal and "never in the card's own words for their wants, fear or flaw" in normal
    assert "what that normal gave them" in normal and "so that the disruption has something to threaten" in normal


def test_the_disruption_is_one_past_event_that_stands_on_its_own():
    disruption = FIELDS["disruption"]
    assert "one event in the past tense that ends on the event itself, with no closing line about how things stand afterwards" in disruption
    assert "lands on something the normal gave the protagonist" in disruption and "one of the protagonist's ties" in disruption
    assert "Every later chapter's planning reads it too" in disruption and "understandable on its own" in disruption


def test_the_protagonist_is_the_person_named_else_the_one_the_wants_and_ties_pull_hardest():
    protagonist = FIELDS["protagonist"]
    assert "the person the note names" in protagonist and "the person whose wants and ties pull hardest" in protagonist and "existing characters" in protagonist


def test_the_card_says_what_it_is_for_and_that_every_field_is_filled():
    assert "the disruption feeds the planning of every chapter, so it must be an event that stands on its own" in CARD_TEXT and "Every field is filled" in CARD_TEXT


def test_the_pinned_setup_sentences_stay():
    for sentence in ("It contains no ending, no outcome and no plan", "Do not restate the character card", "chapter_count is exactly that number",
                     "The protagonist is one of the existing characters; create no new person, place or thing, and write no plan and no ending"):
        assert sentence in CARD_TEXT, sentence


def test_nothing_in_the_setup_wording_lets_a_field_stay_out():
    text = " ".join([CARD_TEXT, *FIELDS.values()]).lower()
    for phrase in LEAVE_OUT:
        assert phrase not in text, phrase


def test_the_setup_wording_has_no_sample_value_and_no_story_word():
    text = " ".join([CARD_TEXT, *FIELDS.values()]).lower()
    samples = []
    for field in SCHEMA["fields"].values():
        samples += (field.get("examples") or {}).get("good", []) + (field.get("examples") or {}).get("avoid", [])
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
def test_the_setup_prompt_carries_the_new_wording_and_the_pinned_sentences(mode):
    w = _build()
    text = w.prompt(w.req("setup", **w.MODES[mode]))
    for needed in (FIELDS["normal"], FIELDS["disruption"], FIELDS["protagonist"], w.SCOPE["setup"], "Do not restate the character card", "It contains no ending, no outcome and no plan",
                   "chapter_count is exactly that number", "stands on its own"):
        assert needed in text, needed[:40]
    for phrase in LEAVE_OUT:
        assert phrase not in text.lower(), phrase
