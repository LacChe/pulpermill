"""Conformance: every request in tests/shared/contract-vectors.json goes through the real server code, the runner, the stub prompter and
the fake engine, and what comes back is read with contract.parse_reply."""
import json
import time
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

from pulpermill import contract
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.kit import Kit
from pulpermill.prompter.stub import script

from server_harness import post, running, wait_idle

VECTORS = json.loads((Path(__file__).parents[2] / "tests/shared/contract-vectors.json").read_text())["requests"]
MODEL_CALLS = {"fill", "judge", "style_fit", "plan", "generate"}
VALID = [v for v in VECTORS if v["valid"] and v["data"]["call"] in MODEL_CALLS]


def scripted(engine: FakeEngine, request: dict) -> None:
    engine.script(*script(request["call"], request, Kit(request)))


@pytest.mark.parametrize("vector", VALID, ids=lambda v: v["name"])
def test_every_model_call_in_the_vectors_is_answered_on_the_stub_prompter(vector):
    request = vector["data"]
    engine = FakeEngine()
    scripted(engine, request)
    with running(engine=engine, run=None) as (base, _):
        response = post(base, request)
        body = response.json()
        assert response.status_code == 200 and body["ok"] is True, body
        reply = contract.parse_reply(request["call"], body)
        assert reply.ok is True
        assert wait_idle(base)
    assert engine.calls == len(script(request["call"], request, Kit(request)))


def test_every_call_is_covered_by_a_vector():
    assert {v["data"]["call"] for v in VALID} == MODEL_CALLS


def test_status_calls_and_job_calls_are_answered_by_the_server_itself():
    with running(run=None) as (base, _):
        for v in VECTORS:
            if v["valid"] and v["data"]["call"] in ("status", "job", "cancel"):
                body = post(base, v["data"]).json()
                contract.parse_reply(v["data"]["call"], body)


def _generate():
    return next(v["data"] for v in VALID if v["data"]["call"] == "generate")


def _fill():
    return next(v["data"] for v in VALID if v["data"]["call"] == "fill")


def test_generate_carries_shifts_with_ids_the_page_sent():
    request = _generate()
    engine = FakeEngine()
    scripted(engine, request)
    with running(engine=engine, run=None) as (base, _):
        body = post(base, request).json()
    shifts = body["shifts"]
    assert {s["card"] for s in shifts} == {"characters", "world", "entanglements"}
    sent = {i["id"] for p in request["cast"] for k in ("wants", "behaviors") for i in p.get(k, [])} | {t["id"] for t in request["ties"]} | {pl["id"] for pl in request["world"]["places"]}
    used = {op["id"] for s in shifts for ops in s["patch"].values() if isinstance(ops, list) for op in ops if "id" in op}
    assert used and used <= sent
    assert next(s for s in shifts if s["card"] == "characters")["target"] in {p["id"] for p in request["cast"]}


def test_a_status_call_while_busy_reports_the_stage_as_an_object():
    request = _generate()
    engine = FakeEngine(seconds_per_token=0.02, tokens_per_call=200)       # the first step is free text: slow words, then Stop
    with running(engine=engine, run=None) as (base, _):
        import threading
        job = {**request, "job_id": "job-status-1"}
        threading.Thread(target=lambda: post(base, job, timeout=30), daemon=True).start()
        stage = None
        for _ in range(200):
            body = post(base, {"call": "status"}).json()
            if body.get("stage"):
                stage = body
                break
            time.sleep(0.02)
        assert stage and stage["state"] == "busy"
        parsed = contract.parse_reply("status", stage)
        assert parsed.stage.name == "write" and parsed.stage.index == 1 and parsed.stage.of == 3
        post(base, {"call": "cancel", "job_id": "job-status-1"})
        assert wait_idle(base)


def test_cancel_stops_the_call_and_the_page_fetches_the_stop():
    request = {**_generate(), "job_id": "job-cancel-1"}
    engine = FakeEngine(seconds_per_token=0.02, tokens_per_call=200)
    with running(engine=engine, run=None) as (base, _):
        import threading
        threading.Thread(target=lambda: post(base, request, timeout=30), daemon=True).start()
        for _ in range(200):
            if post(base, {"call": "status"}).json()["state"] == "busy":
                break
            time.sleep(0.02)
        assert post(base, {"call": "cancel", "job_id": "job-cancel-1"}).json()["state"] == "cancelled"
        assert wait_idle(base)
        fetched = post(base, {"call": "job", "job_id": "job-cancel-1"})
        assert fetched.json()["error"]["kind"] == "stopped"
        assert engine.cancelled_calls == 1


def test_a_reply_that_is_not_usable_is_asked_for_again_and_then_used():
    request = _fill()
    engine = FakeEngine()
    good = script("fill", request, Kit(request))[0]
    engine.script("this is not json", good)
    with running(engine=engine, run=None) as (base, _):
        response = post(base, request)
        assert response.status_code == 200
        contract.parse_reply("fill", response.json())
        assert wait_idle(base)
        app_runs = None
    assert engine.calls == 2
    assert "could not be used" in engine.prompts[1] and "could not be used" not in engine.prompts[0]
    assert engine.constraints[1] is not None                       # the retry is constrained


def test_two_unusable_replies_are_bad_output():
    request = _fill()
    engine = FakeEngine()
    engine.script("nope", "still nope")
    with running(engine=engine, run=None) as (base, _):
        response = post(base, request)
        assert response.status_code == 502 and response.json()["error"]["kind"] == "bad_output"


def test_a_call_that_cannot_fit_is_too_long_before_any_inference():
    request = {**_fill(), "note": "word " * 60000}
    engine = FakeEngine()
    with running(engine=engine, run=None) as (base, _):
        response = post(base, request)
        assert response.status_code == 413 and response.json()["error"]["kind"] == "too_long"
        assert wait_idle(base)
    assert engine.calls == 0


def test_a_story_that_cannot_fit_is_too_long_before_the_chapter_is_written():
    request = {**_generate(), "previous_ending": "word " * 100000}
    engine = FakeEngine()
    with running(engine=engine, run=None) as (base, _):
        assert post(base, request).status_code == 413
    assert engine.calls == 0


def test_a_call_that_fits_only_when_squeezed_is_squeezed_and_answered():
    request = {**_fill(), "note": "word " * 17000}              # about 17,000 tokens, one a word: over the 15,084 allowed as written, under it at 0.85
    engine = FakeEngine()
    engine.script(script("fill", request, Kit(request))[0])
    with running(engine=engine, run=None) as (base, _):
        response = post(base, request)
        assert response.status_code == 200, response.text
        assert wait_idle(base)
    assert len(engine.prompts[0]) < 17000 * 5 * 0.9                  # the prompt was clipped


def test_a_judge_with_items_asks_per_rule_and_answers_with_the_ids_sent():
    request = {**next(v["data"] for v in VALID if v["data"]["call"] == "judge"), "card": "world", "instance": None,
               "rules": [{"id": "place_acts_on_people", "fields": ["places"]}, {"id": "nothing_to_ask", "fields": ["terms"]}],
               "values": {"places": [{"id": "p1", "name": "A", "description": "d", "effect": "e"}, {"id": "p2", "name": "B", "description": "d", "effect": "e"}]}}
    engine = FakeEngine()
    engine.script(*script("judge", request, Kit(request)))
    with running(engine=engine, run=None) as (base, _):
        body = post(base, request).json()
        assert wait_idle(base)
    reply = contract.parse_reply("judge", body)
    assert [r.rule for r in reply.results] == ["place_acts_on_people", "nothing_to_ask"]
    assert [(h.field, h.item) for h in reply.results[0].hits] == [("places", "p1")] and reply.results[1].hits == []
    assert engine.calls == 1                                  # the rule with nothing to look at was not asked
