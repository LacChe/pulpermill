"""B2, the style_fit call: the prompt, the check, and the whole call through the real server and runner on a scripted fake engine (no model)."""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "backend"))

from pulpermill import contract  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter import load_prompter  # noqa: E402
from pulpermill.prompter.mill import style_fit as sf  # noqa: E402
from pulpermill.prompts import budget  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
FITS = [v for v in VECTORS if v["valid"] and v["data"]["call"] == "style_fit"]


def request(**over) -> dict:
    r = {"call": "style_fit", "schema_version": 3, "language": "en",
         "style": {"person": "first", "tense": "past", "distance": "deep", "diction": "ornate", "humor": "dry"},
         "protagonist": {"id": "c0000001", "name": "Suvi", "sex": "female", "sketch": "A clerk who never says what she feels.", "fear": "being seen",
                         "flaw": "believes silence is safety", "speech": "clipped, never finishes a thought",
                         "behaviors": [{"id": "b1", "state": "feels watched", "tendency": "go quiet"}]}}
    r.update(over)
    return r


def test_the_prompt_compares_the_protagonist_with_the_voice_in_prose():
    text = sf.build_prompt(request())
    for needed in ("Narrate in the first person", "Tell the story in the past tense", "Who Suvi is: A clerk who never says what she feels.", "being seen",
                   "believes silence is safety", "clipped, never finishes a thought", "feels watched", "go quiet", "A preference is not a conflict",
                   "in English", "Compare the protagonist's sketch, fear, flaw, speech and behaviours"):
        assert needed in text, needed
    assert "c0000001" not in text and "b1" not in text
    assert "person: first" not in text and "distance: deep" not in text and "humor: dry" not in text


def test_only_a_real_conflict_is_flagged_and_the_prompt_says_where_the_line_is():
    text = sf.build_prompt(request())
    assert "A conflict is something in the protagonist that makes the chosen voice impossible or self-contradicting to sustain" in text
    assert "a shy protagonist in the first person fits" in text and "Say that the voice does not fit only when you can name the trait and the choice" in text
    assert "In the third person the narrator stands apart" in text


@pytest.mark.parametrize("language,name", [("zh", "Simplified Chinese"), ("de", "German")])
def test_the_message_is_asked_for_in_the_writers_language(language, name):
    assert f"sentences in {name}" in sf.build_prompt(request(language=language))


def test_a_protagonist_with_only_a_name_is_still_a_valid_prompt():
    text = sf.build_prompt(request(protagonist={"id": "c0000001", "name": "Suvi"}))
    assert "Nothing more is known of the protagonist than the name Suvi." in text


def test_the_check_wants_a_message_when_the_voice_does_not_fit():
    r = request()
    assert sf.style_fit_problem(r, {"fits": True, "message": ""}) is None
    assert sf.style_fit_problem(r, {"fits": False, "message": "Suvi never says what she feels, which meets a deep first person."}) is None
    assert "Suvi" in sf.style_fit_problem(r, {"fits": False, "message": "  "})


def test_the_step_and_the_reply():
    r = request()
    flow = sf.build_flow(r, Kit(r))
    step = flow.next([])
    assert step.name == "style_fit" and step.kind == "json" and step.sampling == "structured" and step.language
    assert flow.next([{"fits": True, "message": ""}]) is None
    assert flow.reply([{"fits": False, "message": "Look at X."}]) == {"fits": False, "message": "Look at X."}
    assert flow.reply([{"fits": True, "message": "stray words"}]) == {"fits": True, "message": ""}
    assert budget.input_limit(step.max_output) > 10000


def test_a_long_protagonist_is_squeezed_but_the_voice_stays():
    long = request(protagonist={"id": "c0000001", "name": "Suvi", "sketch": "A clerk who never says what she feels. " * 80, "speech": "clipped. " * 80})
    big, small = sf.build_prompt(long, 1.0), sf.build_prompt(long, 0.3)
    assert len(small) < len(big) and "Narrate in the first person" in small and "A preference is not a conflict" in small


@pytest.mark.parametrize("vector", FITS, ids=lambda v: v["name"])
def test_every_style_fit_vector_is_answered_through_the_real_server_on_the_mill_prompter(vector):
    r = vector["data"]
    engine = FakeEngine()
    engine.script(*sf.script(r, Kit(r)))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        body = post(base_url, r).json()
        assert body["ok"] is True and contract.parse_reply("style_fit", body).fits is True
        assert wait_idle(base_url)
    assert engine.calls == 1 and engine.prompts[0].startswith("You check whether a story's chosen voice")


def test_a_conflict_reply_without_a_message_is_asked_for_again():
    r = request()
    engine = FakeEngine()
    engine.script(json.dumps({"fits": False, "message": ""}), json.dumps({"fits": False, "message": "Suvi never says what she feels; the deep first person needs it."}))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        body = post(base_url, r).json()
        assert body["ok"] is True and body["fits"] is False and "Suvi" in body["message"]
        assert wait_idle(base_url)
    assert engine.calls == 2 and "which trait of Suvi" in engine.prompts[1]


def test_the_version_follows_the_wording():
    assert "+style_fit:style_fit-1:" in load_prompter("mill").version
