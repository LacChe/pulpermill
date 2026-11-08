"""The fill contract: every prompt asks for every field (the grammar requires them and the check refuses an empty one), and in every input
mode it tells the model to keep the writer's own words. The first group reads the wording file alone; the second builds real prompts."""
import sys
from pathlib import Path

import pytest
import yaml

TEXT = Path(__file__).resolve().parents[2] / "pulpermill" / "prompter" / "mill" / "text" / "en" / "fill.yaml"
WORDING = yaml.safe_load(TEXT.read_text(encoding="utf-8"))
MODE_KEYS = ["note_only", "chapter_only", "both"]
KEEP_WORDS = "keep those words and their specifics on the card; do not shorten them into a label"
LEAVE_OUT = ["nothing to say", "something to say", "is left out", "stays empty", "stay empty", "leave those fields out"]
# the Style note fields still say "Leave it out when ..." in their own field text; step 3a rewrites that, so it is not checked here
OUTPUT_ONLY = LEAVE_OUT + ["leave it out"]


def test_the_output_line_asks_for_every_field_and_lets_none_be_left_out():
    out = WORDING["output"]
    assert "every field of the card" in out and "invent what it leaves open" in out and "up to five items" in out
    assert "plain prose" in out and "no field holds an id, a label or a note to the writer" in out.lower()
    for phrase in OUTPUT_ONLY:
        assert phrase not in out.lower(), phrase


@pytest.mark.parametrize("key", MODE_KEYS)
def test_each_input_mode_line_keeps_the_writers_own_words(key):
    assert KEEP_WORDS in WORDING[key]


def test_the_mode_lines_keep_the_sentences_other_tests_pin():
    assert "Use it exactly as the writer meant it" in WORDING["note_only"]
    assert "work out what this card holds" in WORDING["chapter_only"]
    assert "The note decides" in WORDING["both"]


def test_the_related_lead_says_the_cards_are_material_not_to_be_changed():
    assert "material to build on, not to change" in WORDING["related_lead"]


def _prompt_helpers():
    pytest.importorskip("starlette")
    pytest.importorskip("uvicorn")
    pytest.importorskip("requests")
    sys.path.insert(0, str(Path(__file__).parent))
    import test_fill_wording as w
    return w


@pytest.mark.parametrize("mode", ["note", "chapter", "both"])
@pytest.mark.parametrize("card", ["style", "characters", "world", "entanglements", "setup"])
def test_the_prompt_of_every_card_asks_for_every_field_and_never_allows_leaving_one_out(card, mode):
    w = _prompt_helpers()
    text = w.prompt(w.req(card, **w.MODES[mode]))
    assert WORDING["output"] in text and text.rstrip().endswith(WORDING["output"])
    for phrase in LEAVE_OUT:
        assert phrase not in text.lower(), phrase


@pytest.mark.parametrize("mode,key", [("note", "note_only"), ("chapter", "chapter_only"), ("both", "both")])
@pytest.mark.parametrize("card", ["style", "characters", "world", "entanglements", "setup"])
def test_the_keep_the_writers_words_line_reaches_every_card_in_every_input_mode(card, mode, key):
    w = _prompt_helpers()
    text = w.prompt(w.req(card, **w.MODES[mode]))
    assert WORDING[key] in text and KEEP_WORDS in text


@pytest.mark.parametrize("card", ["entanglements", "setup"])
def test_a_derived_card_sees_its_related_cards_as_material_not_to_change(card):
    w = _prompt_helpers()
    assert WORDING["related_lead"] in w.prompt(w.req(card))
