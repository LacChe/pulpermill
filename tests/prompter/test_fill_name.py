"""A Characters fill names the person: the card's `name` value is the one current value the prompt shows, so two characters filled from the
same example chapter are asked for different people. Step 2 adds the check that the reply keeps that name."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_fill_wording import CARDS, MODES, prompt, req  # noqa: E402

LINE = "This card is for the person the writer named"


def named(name, **over):
    return req("characters", values={"id": "c0000009", "name": name}, **over)


def test_the_name_appears_in_a_chapter_only_prompt():
    text = prompt(named("Teodora", **MODES["chapter"]))
    assert f"{LINE} Teodora." in text
    assert text.index("The example chapter:") < text.index(LINE), "the line comes after the inputs block"


def test_two_requests_that_differ_only_in_name_give_different_prompts():
    a, b = prompt(named("Teodora", **MODES["chapter"])), prompt(named("Imre", **MODES["chapter"]))
    assert a != b and f"{LINE} Teodora." in a and f"{LINE} Imre." in b


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_blank_name_gives_the_old_prompt(blank):
    old = prompt(req("characters", values={}, **MODES["chapter"]))
    assert LINE not in old
    assert prompt(named(blank, **MODES["chapter"])) == old


@pytest.mark.parametrize("mode", list(MODES))
def test_the_line_appears_in_all_three_modes(mode):
    text = prompt(named("Teodora", **MODES[mode]))
    assert f"{LINE} Teodora." in text
    assert text.count(LINE) == 1


def test_no_other_value_of_the_card_is_shown():
    values = {"id": "c0000009", "name": "Teodora", "fear": "being ordinary", "wants": [{"id": "w1", "text": "to be taken seriously"}]}
    text = prompt(req("characters", values=values, **MODES["chapter"]))
    assert "being ordinary" not in text and "to be taken seriously" not in text and "c0000009" not in text
    assert prompt(req("characters", values={"name": "Teodora"}, **MODES["chapter"])) == text


@pytest.mark.parametrize("card", [c for c in CARDS if c != "characters"])
def test_the_other_cards_prompts_are_unchanged(card):
    blank = prompt(req(card, values={}, **MODES["chapter"]))
    with_name = prompt(req(card, values={"name": "Teodora"}, **MODES["chapter"]))
    assert with_name == blank and LINE not in blank


def test_a_re_fill_of_a_non_character_card_still_equals_a_blank_one():
    held = {"name": "Tern Station", "everyday_life": "Air is rationed and taxed."}
    assert prompt(req("world", values=held)) == prompt(req("world", values={}))


# ---- step 2: the reply keeps the typed name ----------------------------------------------------------------------------------------

from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter.mill import fill  # noqa: E402


def reply_for(request, **over):
    import json
    value = json.loads(fill.script(request, Kit(request))[0])
    value.update(over)
    return value


def test_a_matching_name_passes():
    request = named("Teodora", **MODES["chapter"])
    assert fill.fill_problem(request, reply_for(request)) is None
    assert fill.fill_problem(request, reply_for(request, name="teodora.")) is None, "case and punctuation do not matter"


def test_a_different_name_returns_the_problem():
    request = named("Teodora", **MODES["chapter"])
    problem = fill.fill_problem(request, reply_for(request, name="Imre"))
    assert problem and "Teodora" in problem and "name field" in problem


def test_a_missing_name_in_the_reply_is_a_mismatch():
    request = named("Teodora", **MODES["chapter"])
    value = reply_for(request)
    del value["name"]
    assert "Teodora" in (fill.fill_problem(request, value) or "")


def test_a_blank_typed_name_does_not_trigger_the_check():
    request = req("characters", values={}, **MODES["chapter"])
    assert fill.fill_problem(request, reply_for(request, name="Anyone")) is None
    assert fill.fill_problem(named("  ", **MODES["chapter"]), reply_for(request, name="Anyone")) is None


def test_the_fake_engine_keeps_the_typed_name():
    request = named("Teodora", **MODES["chapter"])
    assert reply_for(request)["name"] == "Teodora"
