"""Step 2 of the fill-quality plan: Entanglements and Setup see the related characters in full (planner scope: sketch, wants, fear, flaw,
values, competence, vulnerability, history), not as the short brief. Behaviors, speech, age and appearance stay out (ties do not need them),
no id and no raw option key reaches the model, and the larger related block still fits the context."""
import copy
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "backend"))

from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter.mill import fill  # noqa: E402
from pulpermill.prompts import budget, tokens  # noqa: E402

from test_fill_wording import CARDS, RELATED, WORLD, ids_in, prompt, raw_option_pair, req  # noqa: E402

DERIVED = ["entanglements", "setup"]


def person(n: int, **over) -> dict:
    p = {"id": f"c{n:07d}", "name": f"Person{n}", "sex": "female", "age": f"{20 + n} years", "appearance": f"AppearanceMark{n} tall and thin",
         "sketch": f"SketchMark{n} keeps a ledger and a secret.",
         "wants": [{"id": f"w{n}0", "text": f"WantMark{n} to be left alone"}, {"id": f"w{n}1", "text": "to be needed"}],
         "fear": f"FearMark{n} being found out", "flaw": f"FlawMark{n} that asking is weakness",
         "values": [{"id": f"v{n}0", "text": f"ValueMark{n} keeps promises"}],
         "behaviors": [{"id": f"b{n}0", "state": "under pressure", "tendency": f"BehaviorMark{n} goes quiet"}],
         "competence": f"CompetenceMark{n} keeps accounts",
         "speech": f"SpeechMark{n} short and dry",
         "vulnerability": f"VulnerabilityMark{n} anyone who mentions the old debt",
         "history": f"HistoryMark{n} raised on the docks"}
    p.update(over)
    return p


def with_cast(card: str, count: int) -> dict:
    request = req(card)
    cast = [person(n) for n in range(1, count + 1)]
    request["related"]["characters"] = cast
    if card == "entanglements":
        request["related"]["world"] = WORLD
    return request


@pytest.mark.parametrize("card", DERIVED)
def test_a_derived_card_sees_each_characters_sketch_and_vulnerability_in_full(card):
    text = prompt(with_cast(card, 3))
    for n in (1, 2, 3):
        for mark in ("Sketch", "Want", "Fear", "Flaw", "Value", "Competence", "Vulnerability", "History"):
            assert f"{mark}Mark{n}" in text, (card, mark, n)


@pytest.mark.parametrize("card", DERIVED)
def test_behaviors_speech_age_and_appearance_stay_out_of_the_related_block(card):
    text = prompt(with_cast(card, 2))
    for mark in ("Behavior", "Speech", "Appearance"):
        assert f"{mark}Mark1" not in text, (card, mark)
    assert "21 years" not in text


@pytest.mark.parametrize("card", DERIVED)
def test_the_people_are_set_apart_from_each_other_and_carry_no_id_or_raw_option_key(card):
    request = with_cast(card, 3)
    text = prompt(request)
    for ident in ids_in(request):
        assert ident not in text, ident
    assert raw_option_pair(text) is None
    first, second = text.index("SketchMark1"), text.index("SketchMark2")
    assert "\n\n" in text[first:second], "one blank line between one person and the next"


def test_a_card_that_reads_no_characters_is_not_changed_by_the_related_block():
    for card in ("style", "characters", "world"):
        text = prompt(req(card))
        assert "SketchMark" not in text and "Person1" not in text


def test_the_old_brief_is_still_available_to_the_code_that_uses_it():
    from pulpermill.prompts import render as r
    brief = r.render_person_brief(person(1))
    assert "WantMark1" in brief and "FearMark1" in brief and "SketchMark1" not in brief


def test_the_fill_version_moved_with_the_prompt():
    assert fill.VERSION == "fill-4"


@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
@pytest.mark.parametrize("count", [3, 6])
@pytest.mark.parametrize("card", DERIVED)
def test_three_or_six_full_characters_fit_the_context_without_any_squeeze(card, count):
    request = with_cast(card, count)
    flow = fill.build_flow(request, Kit(request))
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert factor == 1.0 and all(m.ok for m in measures)
