"""The run record, and the server's last hardening: every error kind produced on purpose, through the real pipelines."""
import json
import time
from pathlib import Path

import pytest

try:
    import requests  # noqa: F401
    import starlette  # noqa: F401
    import uvicorn  # noqa: F401
except ImportError:
    pytest.skip("starlette, uvicorn and requests are needed", allow_module_level=True)

from pulpermill.backend import pipelines, runlog
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.errors import BackendError
from pulpermill.schema import contract

from server_harness import post, running, wait_idle

VECTORS = {r["name"]: r["data"] for r in json.loads((Path(__file__).parents[2] / "web/tests/contract-vectors.json").read_text())["requests"]
           if r["valid"]}
FILL = VECTORS["the page's fill_setup request"]


def lines(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines()]


def test_the_log_starts_with_the_settings_and_has_one_line_per_call(tmp_path):
    path = tmp_path / "runs.jsonl"
    with running(Config(log_path=str(path))) as (base, _):
        for _ in range(2):
            assert post(base, FILL).status_code == 200
            assert wait_idle(base)
    rows = lines(path)
    assert [r["record"] for r in rows] == ["settings", "call", "call"]
    settings = rows[0]
    assert set(settings["sampling"]) == {"prose", "prose_zh", "thinking", "structured"} and settings["constrain"] == "always"
    assert settings["sampling"]["structured"]["temperature"] == 0.2 and settings["model"]["n_ctx"] == 16384
    call = rows[1]
    assert call["call"] == "fill" and call["result"] == "ok" and call["seconds"] >= 0 and call["retries"] == 0


def test_a_real_pipeline_records_its_passes_and_a_retry(tmp_path):
    path = tmp_path / "runs.jsonl"
    engine = FakeEngine()
    engine.script("not json", json.dumps({"protagonist": "Suvi"}))
    with running(Config(log_path=str(path)), engine, run=pipelines.run) as (base, _):
        assert post(base, FILL).status_code == 200
        assert wait_idle(base)
    call = lines(path)[1]
    assert call["retries"] == 1
    [one] = call["passes"]
    assert one["prompt"] and one["version"] and one["prompt_tokens"] > 0
    assert [a["constrained"] for a in one["attempts"]] == [True, True] and one["attempts"][0]["failed"] and "problem" not in one["attempts"][0]


def test_bad_output_is_produced_by_a_model_that_never_answers_in_json_and_is_logged(tmp_path):
    path = tmp_path / "runs.jsonl"
    with running(Config(log_path=str(path)), FakeEngine(), run=pipelines.run) as (base, _):     # the fake's made-up words are not JSON
        response = post(base, FILL)
        assert response.status_code == 502 and response.json()["error"]["kind"] == "bad_output"
        assert wait_idle(base)
        assert post(base, {"call": "status"}).json()["state"] == "idle"
    call = lines(path)[1]
    assert call["result"] == "bad_output" and call["retries"] == 1


def test_the_log_holds_no_text_no_token_and_no_error_detail(tmp_path):
    path = tmp_path / "runs.jsonl"
    engine = FakeEngine()
    engine.script(json.dumps({"protagonist": "Suvi-Secretname"}), "x")
    with running(Config(log_path=str(path), token="tok-123"), engine, run=pipelines.run) as (base, _):
        post(base, FILL, token="tok-123")
        assert wait_idle(base, token="tok-123")
        engine.fail_next(RuntimeError("CUDA out of memory at /secret/path"))
        post(base, FILL, token="tok-123")
        assert wait_idle(base, token="tok-123")
    text = Path(path).read_text(encoding="utf-8")
    for forbidden in ("tok-123", "Suvi-Secretname", "/secret/path", "CUDA"):
        assert forbidden not in text
    assert json.loads(text.splitlines()[-1])["result"] == "server"


def test_every_error_kind_is_produced_on_purpose_and_each_leaves_the_server_idle(tmp_path):
    path = tmp_path / "runs.jsonl"
    seen = {}
    with running(Config(log_path=str(path), token="t", max_body_bytes=2000), FakeEngine(seconds_per_token=0.05, tokens_per_call=100), run=pipelines.run_canned) as (base, engine):
        seen["unauthorized"] = post(base, FILL).status_code                                         # no token
        seen["bad_request"] = post(base, {"call": "nope"}, token="t").status_code
        seen["too_large"] = post(base, {"call": "fill", "pad": "x" * 5000}, token="t").json()["error"]["kind"]
        engine.fail_next(BackendError("too_long", ""))
        seen["too_long"] = post(base, FILL, token="t").status_code
        engine.fail_next(RuntimeError("boom"))
        seen["server"] = post(base, FILL, token="t").status_code
        engine.fail_next(BackendError("bad_output", ""))
        seen["bad_output"] = post(base, FILL, token="t").status_code
        assert wait_idle(base, token="t")
    assert seen == {"unauthorized": 401, "bad_request": 400, "too_large": "bad_request", "too_long": 413, "server": 500, "bad_output": 502}
    results = [r["result"] for r in lines(path)[1:]]
    assert results == ["too_long", "server", "bad_output"]       # only calls that reached a pipeline are recorded


def slow(model, ctx):
    ctx.engine.generate("x", 400, cancel=ctx.cancel)       # a call that really spends time in the engine, and stops when told
    return pipelines.run_canned(model, ctx)


def test_busy_and_stopped_are_logged_and_a_busy_refusal_is_not_a_call(tmp_path):
    path = tmp_path / "runs.jsonl"
    generate = VECTORS["the page's generate request"] if "the page's generate request" in VECTORS else next(v for v in VECTORS.values() if v["call"] == "generate")
    with running(Config(log_path=str(path)), FakeEngine(seconds_per_token=0.05, tokens_per_call=400), run=slow) as (base, engine):
        import threading
        started = threading.Thread(target=lambda: _quietly(post, base, generate, timeout=1.0))
        started.start()
        time.sleep(0.4)                                      # the call is running now; the page below is "a second call"
        assert post(base, FILL).json()["error"]["kind"] == "busy"
        started.join()                                       # the first client gives up: that is Stop
        assert wait_idle(base)
    rows = lines(path)[1:]
    assert [r["result"] for r in rows] == ["stopped"]


def _quietly(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except requests.exceptions.RequestException:
        pass


def test_an_unwritable_log_never_fails_a_call(tmp_path):
    bad = tmp_path / "no" / "such" / "dir" / "runs.jsonl"
    with running(Config(log_path=str(bad))) as (base, _):
        assert post(base, FILL).status_code == 200
        assert wait_idle(base)
        assert post(base, FILL).status_code == 200


def test_stages_are_timed_and_the_inner_set_stage_still_hears_each_one():
    heard = []
    stages = runlog.Stages(heard.append)
    stages("write")
    time.sleep(0.02)
    stages("events")
    stages.close()
    assert heard == ["write", "events"]
    assert [s["stage"] for s in stages.done] == ["write", "events"] and stages.done[0]["seconds"] >= 0.02


def test_flags_are_kept_by_id_only():
    record = runlog.build("generate", 0, 1.234, "ok", [], {"flags": ["repetition: 'the same sentence the same'", "length: 2500 words"], "squeeze": 0.9, "words": 3000})
    assert record["flags"] == ["repetition", "length"] and record["squeeze"] == 0.9 and record["seconds"] == 1.23


def test_the_launcher_names_a_log_path_for_the_notebook():
    import inspect
    from pulpermill.backend import launch
    assert "pulpermill-runs.jsonl" in inspect.signature(launch.launch).parameters["log_path"].default
