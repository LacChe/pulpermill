"""The finish call (the end of the story): the prompt, the check, the fallback, and the whole call through the real server and runner on a scripted
fake engine (no model)."""
import copy
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
for sub in ("backend", "prompts"):
    sys.path.insert(0, str(ROOT / "tests" / sub))

from pulpermill import contract  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter import load_prompter  # noqa: E402
from pulpermill.prompter.mill import finish as fin  # noqa: E402
from pulpermill.prompts import budget, tokens  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
FINISHES = [v for v in VECTORS if v["valid"] and v["data"]["call"] == "finish"]
BASE = next(v["data"] for v in FINISHES if v["name"] == "a finish request carries the summaries and the base characters")


def request(**over) -> dict:
    return {**copy.deepcopy(BASE), **over}


def test_the_prompt_reads_the_summaries_and_the_people_by_name_and_handle():
    text = fin.build_prompt(request(), Kit(request()))
    for needed in ("The story follows Suvi.", "Suvi kept the Archive and kept her counsel.", "A ledger went missing on the quay.",
                   "Chapter 1. Suvi hid the ledger in the quay stores and Marit found her there.", "By its end: Suvi now owes her mother an answer.",
                   "Chapter 2. Suvi told Marit where the ledger was", "By its end: Suvi has let her mother in.",
                   "Suvi: An archivist who keeps score.", "wants.1: To be left alone with the records", "behaviors.1: When cornered — she goes quiet and counts",
                   "fear: Being found out", "Marit: Suvi's mother, a fisher.", "at most one entry for each person",
                   "sketch, wants, fear, flaw, values, behaviors, competence, vulnerability, speech, history",
                   "A person the story did not truly change gets no entry", "Write every value in English"):
        assert needed in text, needed
    for hidden in ("c0000001", "c0000002", "w0000001", "h0000001", "Ink on her cuffs", "age", "appearance:"):
        assert hidden not in text, hidden


def test_every_chapter_is_in_order_and_nothing_but_the_records_is_read():
    events = [{"chapter": n, "happened": f"Event number {n} took place.", "changed": f"Change number {n} stood."} for n in (3, 1, 2)]
    text = fin.build_prompt(request(events=events), Kit(request(events=events)))
    assert text.index("Chapter 1.") < text.index("Chapter 2.") < text.index("Chapter 3.")
    assert "chapter_text" not in text and "Dusk came early" not in text


@pytest.mark.parametrize("language,name", [("zh", "Simplified Chinese"), ("de", "German")])
def test_the_values_are_asked_for_in_the_storys_language(language, name):
    r = request(language=language)
    assert f"Write every value in {name}" in fin.build_prompt(r, Kit(r))


def test_a_long_story_is_squeezed_but_the_task_stays_and_no_chapter_is_dropped():
    r = request(events=[{"chapter": n, "happened": "A long happening. " * 80, "changed": "A long change. " * 40} for n in range(1, 11)])
    big, small = fin.build_prompt(r, Kit(r), 1.0), fin.build_prompt(r, Kit(r), 0.3)
    assert len(small) < len(big)
    assert all(f"Chapter {n}." in small for n in range(1, 11)) and "A person the story did not truly change gets no entry" in small


def test_the_step_and_the_reply():
    r = request()
    flow = fin.build_flow(r, Kit(r))
    step = flow.next([])
    assert step.name == "finish" and step.kind == "json" and step.sampling == "structured" and step.language and step.attempts == 2
    assert flow.next([{"shifts": []}]) is None
    shifts = [{"card": "characters", "target": "Suvi", "patch": {"fear": "x"}}]
    assert flow.reply([{"shifts": shifts}]) == {"shifts": shifts}


def test_the_check_refuses_two_entries_for_one_person_and_the_last_resort_is_no_shifts():
    r = request()
    flow = fin.build_flow(r, Kit(r))
    step = flow.next([])
    two = {"shifts": [{"card": "characters", "target": "Suvi", "patch": {"fear": "x"}}, {"card": "characters", "target": "Suvi", "patch": {"flaw": "y"}}]}
    assert "two entries" in step.check(two)
    assert step.check({"shifts": [{"card": "characters", "target": "Suvi", "patch": {"fear": "x"}}]}) is None
    assert step.fallback() == {"shifts": []} and flow.notes["finish_fallback"] is True


@pytest.mark.parametrize("vector", FINISHES, ids=lambda v: v["name"])
def test_every_finish_vector_is_answered_through_the_real_server_on_the_mill_prompter(vector):
    r = vector["data"]
    engine = FakeEngine()
    engine.script(*fin.script(r, Kit(r)))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        body = post(base_url, r).json()
        assert body["ok"] is True, body
        reply = contract.parse_reply("finish", body)
        assert len(reply.shifts) == 1 and reply.shifts[0].target == "c0000001"       # the id that was sent, not the name the model used
        assert wait_idle(base_url)
    assert engine.calls == 1 and engine.prompts[0].startswith("A story has been told from its first chapter to its last.")


def test_a_refused_reply_is_asked_again_with_the_plain_line_and_then_the_second_is_used():
    r = request()
    twice = {"card": "characters", "target": "Suvi", "patch": {"fear": "x"}}
    engine = FakeEngine()
    engine.script(json.dumps({"shifts": [twice, twice]}), json.dumps({"shifts": [twice]}))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        body = post(base_url, r).json()
        assert body["ok"] is True and len(body["shifts"]) == 1
        assert wait_idle(base_url)
    assert engine.calls == 2 and "Suvi has two entries" in engine.prompts[1]


def test_when_no_reply_can_be_used_the_call_still_answers_with_no_shifts():
    r = request()
    bad = json.dumps({"shifts": [{"card": "characters", "target": "Nobody", "patch": {"fear": "x"}}]})
    engine = FakeEngine()
    engine.script(bad, bad)
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        body = post(base_url, r).json()
        assert body == {"ok": True, "shifts": []}
        assert wait_idle(base_url)
    assert engine.calls == 2


def test_the_version_follows_the_wording():
    assert "+finish:finish-1:" in load_prompter("mill").version


def test_the_largest_story_fits_the_budget():
    """Twelve chapters of long records and a big cast, every text at its cap: the prompt fits at some squeeze, as the runner needs."""
    if not tokens.available():
        pytest.skip("the Gemma tokenizer files are not installed")
    import story_sizes as cases
    big = request(characters=cases.inflate({"cast": copy.deepcopy(BASE["characters"])}, cast=12, chapters=1)["cast"],
                  events=[{"chapter": n, "happened": cases.prose(2400, n), "changed": cases.prose(2400, n + 3)} for n in range(1, 13)])
    big["protagonist"] = big["characters"][0]["id"]
    flow = fin.build_flow(big, Kit(big))
    steps = flow.worst_case()
    assert len(steps) == 1
    _, factor, _ = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in steps])
    assert 0 < factor <= 1.0
    assert budget.measure(budget.Sized("finish", steps[0].text(factor), steps[0].max_output)).ok
    ten = request(events=[{"chapter": n, "happened": cases.prose(1100, n), "changed": cases.prose(600, n)} for n in range(1, 11)])
    assert budget.measure(budget.Sized("finish", fin.build_prompt(ten, Kit(ten)), fin.MAX_OUTPUT)).ok       # ten chapters at their caps fit as they are
