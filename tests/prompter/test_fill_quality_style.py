"""Step 3a: the Style fill says what each field is for and what a good note is, and every Style field is filled (the four notes included).
The first group reads the wording file alone; the second builds the real Style prompt."""
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORDING = yaml.safe_load((ROOT / "pulpermill/prompter/mill/text/en/fill.yaml").read_text(encoding="utf-8"))
SCHEMA = yaml.safe_load((ROOT / "pulpermill/schema/text/en/style.yaml").read_text(encoding="utf-8"))
FIELDS, STYLE = WORDING["fields"]["style"], WORDING["cards"]["style"]
NOTES = ["narrator_note", "sentences_note", "stance_note", "dialogue_note"]
CHOICES = [k for k, f in SCHEMA["fields"].items() if f.get("options")]
FREE = ["lens", "genre"]
CARD_TEXT = " ".join([STYLE["intro"], STYLE["scope"], *STYLE["specific"]])


def test_every_style_field_is_still_described():
    assert set(FIELDS) == set(NOTES + CHOICES + FREE)


@pytest.mark.parametrize("key", NOTES)
def test_each_note_is_always_filled_and_names_one_concrete_habit(key):
    text = FIELDS[key]
    assert "always filled" in text and "one concrete habit" in text
    assert "agrees with the choice" in text and "invents no trait the writer's text did not suggest" in text
    assert "pulls against nothing the writer asked for" in text


def test_nothing_in_the_style_wording_lets_a_field_stay_out():
    everything = " ".join([*FIELDS.values(), CARD_TEXT]).lower()
    for phrase in ("leave it out", "stay out", "stays out", "adds nothing", "nothing to say"):
        assert phrase not in everything, phrase
    assert "fill every field" in CARD_TEXT.lower()


@pytest.mark.parametrize("key", [k for k in CHOICES if k not in ("person", "tense")])
def test_each_free_choice_says_what_it_is_for_and_how_to_pick(key):
    text = FIELDS[key]
    assert "the middle one when nothing points either way" in text and "agrees with the rest of the voice" in text
    assert len(text) > len(re.split(r"(?<=\.) ", text)[0]) + 20


@pytest.mark.parametrize("key", ["person", "tense"])
def test_person_and_tense_are_committed_to_from_the_writers_text(key):
    assert "commit to" in FIELDS[key] and "every chapter" in FIELDS[key]


def test_the_lens_is_derived_from_what_the_text_dwells_on_and_is_never_a_subject():
    lens = FIELDS["lens"]
    assert "what the writer's text dwells on" in lens and "A lens is never a subject or a theme" in lens and "keep the writer's intent" in lens


def test_the_genre_is_a_tradition_or_a_feeling_in_a_few_words():
    genre = FIELDS["genre"]
    assert "A tradition or a feeling" in genre and "in a few words" in genre and "requires no particular event and names no one" in genre


def test_the_card_says_what_it_is_for_and_that_the_choices_read_as_one_voice():
    assert "voice of the whole story" in CARD_TEXT and "the choices agree with one another" in CARD_TEXT
    assert "the whole set reads as one voice" in CARD_TEXT and "the middle option when nothing points either way" in CARD_TEXT


def test_the_style_wording_carries_no_example_value_from_the_schema():
    text = yaml.safe_dump({"f": FIELDS, "c": STYLE}).lower()
    for key in FREE:
        for sample in SCHEMA["fields"][key]["examples"]["good"] + SCHEMA["fields"][key]["examples"]["avoid"]:
            assert sample.lower() not in text, sample


def _build():
    pytest.importorskip("starlette"); pytest.importorskip("uvicorn"); pytest.importorskip("requests")
    sys.path.insert(0, str(Path(__file__).parent))
    import test_fill_wording as w
    return w


@pytest.mark.parametrize("mode", ["note", "chapter", "both"])
def test_the_style_prompt_keeps_the_pinned_sentences_and_asks_for_every_field(mode):
    w = _build()
    text = w.prompt(w.req("style", **w.MODES[mode]))
    for pinned in ("describe the voice itself and leave the name out", "Person and tense are rules for every chapter. Read them from the narration of the example chapter",
                   "holds no name of any person, place or thing, and no event", "Fill every field.", "always filled"):
        assert pinned in text, pinned
    for gone in ("stay out unless", "Leave it out when"):
        assert gone not in text, gone


def test_the_style_prompt_still_explains_every_answer_word():
    w = _build()
    text = w.prompt(w.req("style"))
    for key in CHOICES:
        for option, spec in SCHEMA["fields"][key]["options"].items():
            assert f'"{option}":' in text and spec["expand"].replace("{name}", "the person") in text, (key, option)
