"""The server against the fake engine, over real HTTP. No GPU, no model."""
import json
import logging
import threading
import time
from pathlib import Path

import pytest

try:
    import requests  # noqa: F401
    import starlette  # noqa: F401
    import uvicorn  # noqa: F401
except ImportError:  # the server's own dependencies are not installed: skip, as the tokenizer tests do
    pytest.skip("starlette, uvicorn and requests are needed", allow_module_level=True)

from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.errors import BackendError
from pulpermill.schema import contract

from server_harness import post, running, wait_idle

VECTORS = json.loads((Path(__file__).parents[2] / "web/tests/contract-vectors.json").read_text())
VALID = [r for r in VECTORS["requests"] if r["valid"]]
INVALID = [r for r in VECTORS["requests"] if not r["valid"]]


def _of(call):
    return next(v for v in VALID if v["data"]["call"] == call)["data"]


def test_every_valid_request_gets_a_valid_reply():
    with running() as (base, _):
        for vector in VALID:
            response = post(base, vector["data"])
            assert response.status_code == 200, vector["name"]
            body = response.json()
            assert body["ok"] is True, (vector["name"], body)
            contract.parse_reply(vector["data"]["call"], body)


def test_every_invalid_request_is_refused_as_bad_request():
    with running() as (base, _):
        for vector in INVALID:
            response = post(base, vector["data"])
            assert response.status_code == 400, vector["name"]
            error = response.json()["error"]
            assert error["kind"] == "bad_request" and error["detail"], vector["name"]


def test_a_body_that_is_not_json_is_bad_request():
    with running() as (base, _):
        response = post(base, None, raw=b"{not json")
        assert response.status_code == 400 and response.json()["error"]["kind"] == "bad_request"


def test_a_newer_schema_version_is_bad_request():
    request = _of("style_fit")
    with running() as (base, _):
        response = post(base, {**request, "schema_version": request["schema_version"] + 1})
        assert response.status_code == 400
        assert "version" in response.json()["error"]["detail"]


def test_preflight_is_answered_without_the_token_and_allows_the_page_headers():
    with running(Config(token="s3cret")) as (base, _):
        response = requests.options(f"{base}/api")
        assert response.status_code == 204
        allowed = response.headers["access-control-allow-headers"].lower()
        assert "x-pulpermill-token" in allowed and "ngrok-skip-browser-warning" in allowed and "content-type" in allowed
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["access-control-allow-methods"] == "POST"


def test_the_token_is_required_on_every_post_including_status():
    with running(Config(token="s3cret")) as (base, _):
        for body in ({"call": "status"}, _of("style_fit")):
            missing = post(base, body)
            wrong = post(base, body, token="nope")
            assert missing.status_code == wrong.status_code == 401
            assert missing.json() == {"ok": False, "error": {"kind": "unauthorized", "detail": ""}}
            assert missing.headers["access-control-allow-origin"] == "*"      # the page can read the 401
        assert post(base, {"call": "status"}, token="s3cret").json()["state"] == "idle"
        assert post(base, _of("style_fit"), token="s3cret").status_code == 200


def test_no_token_configured_means_none_is_asked_for():
    with running() as (base, _):
        assert post(base, {"call": "status"}).status_code == 200
        assert post(base, {"call": "status"}, token="anything").status_code == 200


def test_the_token_never_reaches_a_log_or_a_reply():
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    log = logging.getLogger("pulpermill")
    handler, old = Catch(), log.level
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    try:
        with running(Config(token="s3cret-value")) as (base, _):
            for token in ("s3cret-value", "wrong-guess"):
                for body in ({"call": "status"}, _of("style_fit"), {"call": "nope"}):
                    response = post(base, body, token=token)
                    assert "s3cret-value" not in response.text and "wrong-guess" not in response.text
    finally:
        log.removeHandler(handler)
        log.setLevel(old)
    assert records and not any("s3cret-value" in r or "wrong-guess" in r for r in records)
    assert "s3cret-value" not in Config(token="s3cret-value").describe()


def _slow():
    return FakeEngine(seconds_per_token=0.05, tokens_per_call=20)


def test_status_answers_fast_while_a_slow_call_runs_and_a_second_call_is_busy():
    with running(engine=_slow()) as (base, engine):
        result = {}
        thread = threading.Thread(target=lambda: result.update(r=post(base, _of("generate"), timeout=30)))
        thread.start()
        time.sleep(0.3)
        started = time.monotonic()
        status = post(base, {"call": "status"}).json()
        assert time.monotonic() - started < 0.5
        assert status["state"] == "busy"
        busy = post(base, _of("style_fit"))
        assert busy.status_code == 503 and busy.json()["error"]["kind"] == "busy"
        thread.join(timeout=30)
        assert result["r"].status_code == 200
        assert wait_idle(base)
        assert "stage" not in post(base, {"call": "status"}).json()


def test_a_call_that_runs_long_is_answered_as_a_stream_the_page_can_still_read():
    config = Config(stream_after=0.2, heartbeat=0.1)
    with running(config, engine=FakeEngine(seconds_per_token=0.05, tokens_per_call=20)) as (base, _):
        response = post(base, _of("generate"), timeout=30)
        assert response.status_code == 200 and response.text.startswith(" ")
        contract.parse_reply("generate", response.json())
        assert wait_idle(base)


def test_a_failure_in_a_streamed_call_still_reaches_the_page_as_the_contracts_error():
    def boom(model, ctx):
        time.sleep(0.5)
        raise BackendError("bad_output", "")
    with running(Config(stream_after=0.1, heartbeat=0.1), run=boom) as (base, _):
        body = post(base, _of("generate"), timeout=30).json()
        assert body["ok"] is False and body["error"]["kind"] == "bad_output"
        assert wait_idle(base)


def test_stop_during_a_streamed_call_still_cancels_inference():
    with running(Config(stream_after=0.1, heartbeat=0.1), engine=FakeEngine(seconds_per_token=0.2, tokens_per_call=200)) as (base, engine):
        with pytest.raises(requests.exceptions.ReadTimeout):
            post(base, _of("generate"), timeout=0.1)
        assert wait_idle(base, seconds=10) and engine.cancelled_calls >= 1


def test_the_stage_moves_through_write_events_shifts():
    with running(engine=FakeEngine(seconds_per_token=0.03)) as (base, _):
        seen = []
        thread = threading.Thread(target=lambda: post(base, _of("generate"), timeout=30))
        thread.start()
        while thread.is_alive():
            stage = post(base, {"call": "status"}).json().get("stage")
            if stage and (not seen or seen[-1] != stage):
                seen.append(stage)
            time.sleep(0.01)
        assert seen == ["write", "events", "shifts"], seen


def test_stop_cancels_inference_and_idle_comes_only_after_it_has_ended():
    with running(engine=FakeEngine(seconds_per_token=0.05)) as (base, engine):
        engine.tokens_per_call = 200
        # The canned pipeline asks for 5 tokens a pass, so make each pass long enough to catch.
        engine.seconds_per_token = 0.2
        with pytest.raises(requests.exceptions.ReadTimeout):
            post(base, _of("generate"), timeout=0.5)              # the page's Stop: the connection is closed
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if post(base, {"call": "status"}).json()["state"] == "idle":
                assert engine.active is False                     # idle was not reported before inference ended
                break
            time.sleep(0.01)
        else:
            raise AssertionError("never went back to idle")
        assert engine.cancelled_calls >= 1
        assert engine.calls == engine.finished


def test_a_call_can_be_made_again_after_stop():
    with running(engine=FakeEngine(seconds_per_token=0.2)) as (base, engine):
        with pytest.raises(requests.exceptions.ReadTimeout):
            post(base, _of("generate"), timeout=0.5)
        assert wait_idle(base)
        engine.seconds_per_token = 0.0
        assert post(base, _of("generate"), timeout=10).status_code == 200


def test_a_failure_a_pipeline_raises_becomes_the_contracts_error_and_the_lock_is_released():
    with running() as (base, engine):
        for kind in ("bad_output", "too_long", "server", "busy", "stopped"):
            engine.fail_next(BackendError(kind, "words"))
            response = post(base, _of("style_fit"))
            assert response.status_code == contract.HTTP_STATUS[kind], kind
            assert response.json()["error"]["kind"] == kind
            assert wait_idle(base)
        assert post(base, _of("style_fit")).status_code == 200


def test_an_unexpected_exception_is_a_server_error_without_internals_and_the_lock_is_released():
    with running() as (base, engine):
        engine.fail_next(RuntimeError("CUDA out of memory at /secret/path"))
        response = post(base, _of("style_fit"))
        assert response.status_code == 500
        error = response.json()["error"]
        assert error["kind"] == "server" and "secret" not in error["detail"] and "CUDA" not in error["detail"]
        assert wait_idle(base)
        assert post(base, _of("style_fit")).status_code == 200


def test_a_reply_that_fails_the_contract_is_never_sent():
    def broken(model, ctx):
        return {"ok": True, "values": ["not", "a", "card"]}

    with running(run=broken) as (base, _):
        response = post(base, _of("fill"))
        assert response.status_code == 502 and response.json()["error"]["kind"] == "bad_output"
        assert wait_idle(base)


def test_every_error_kind_has_a_status():
    assert set(contract.HTTP_STATUS) == {"busy", "bad_request", "bad_output", "too_long", "stopped", "server", "unauthorized"}


# ---- Named calls: the answer is kept for the page to fetch ----------------------------------------------------------

def _named(call, job_id="job-aaaa-0001"):
    return {**_of(call), "job_id": job_id}


def test_a_named_call_goes_on_when_the_connection_drops_and_its_answer_can_be_fetched():
    with running(Config(stream_after=5), engine=FakeEngine(seconds_per_token=0.05, tokens_per_call=20)) as (base, engine):
        with pytest.raises(requests.exceptions.ReadTimeout):
            post(base, _named("generate"), timeout=0.2)
        assert post(base, {"call": "job", "job_id": "job-aaaa-0001"}).json()["state"] == "running"
        assert wait_idle(base, seconds=10) and engine.cancelled_calls == 0
        reply = post(base, {"call": "job", "job_id": "job-aaaa-0001"}).json()
        contract.parse_reply("generate", reply)
        assert post(base, {"call": "job", "job_id": "job-aaaa-0001"}).json() == reply      # fetching again still works


def test_an_unnamed_call_is_still_stopped_by_a_dropped_connection():
    with running(Config(stream_after=0.1, heartbeat=0.1), engine=FakeEngine(seconds_per_token=0.2, tokens_per_call=200)) as (base, engine):
        with pytest.raises(requests.exceptions.ReadTimeout):
            post(base, _of("generate"), timeout=0.1)
        assert wait_idle(base, seconds=10) and engine.cancelled_calls >= 1


def test_an_unknown_job_is_said_to_be_unknown_and_a_failed_job_keeps_its_error():
    def boom(model, ctx):
        raise BackendError("bad_output", "")
    with running(run=boom) as (base, _):
        assert post(base, {"call": "job", "job_id": "never-seen-1"}).json() == {"ok": True, "state": "unknown"}
        assert post(base, _named("generate", "job-bbbb-0002")).status_code == 502
        got = post(base, {"call": "job", "job_id": "job-bbbb-0002"})
        assert got.status_code == 502 and got.json()["error"]["kind"] == "bad_output"


def test_sending_a_named_call_again_does_not_start_it_twice():
    with running(engine=_slow()) as (base, engine):
        result = {}
        thread = threading.Thread(target=lambda: result.update(r=post(base, _named("generate", "job-cccc-0003"), timeout=30)))
        thread.start()
        time.sleep(0.3)
        again = post(base, _named("generate", "job-cccc-0003")).json()
        assert again["state"] == "running"
        thread.join(timeout=30)
        assert wait_idle(base)
        assert post(base, _named("generate", "job-cccc-0003")).json()["ok"] is True


def test_cancel_stops_a_named_call_and_its_stop_is_what_the_page_fetches():
    with running(engine=FakeEngine(seconds_per_token=0.2, tokens_per_call=200)) as (base, engine):
        thread = threading.Thread(target=lambda: post(base, _named("generate", "job-dddd-0004"), timeout=30))
        thread.start()
        time.sleep(0.3)
        assert post(base, {"call": "cancel", "job_id": "job-dddd-0004"}).json()["state"] == "cancelled"
        assert wait_idle(base, seconds=10) and engine.cancelled_calls >= 1
        thread.join(timeout=10)
        assert post(base, {"call": "job", "job_id": "job-dddd-0004"}).json()["error"]["kind"] == "stopped"


def test_only_the_newest_finished_jobs_are_kept():
    with running(Config(jobs_kept=2)) as (base, _):
        for n in range(4):
            assert post(base, _named("style_fit", f"job-keep-000{n}")).status_code == 200
        states = [post(base, {"call": "job", "job_id": f"job-keep-000{n}"}).json().get("state") for n in range(4)]
        assert states[:2] == ["unknown", "unknown"] and states[2:] == [None, None]
