"""The debug capture through the real server: the console line for a bad_output, the launcher flag, and the run log's privacy."""
import json
import logging
from pathlib import Path

import pytest

try:
    import requests  # noqa: F401
    import starlette  # noqa: F401
    import uvicorn  # noqa: F401
except ImportError:
    pytest.skip("starlette, uvicorn and requests are needed", allow_module_level=True)

from pulpermill.backend import pipelines, server
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.launch import debug_file

from server_harness import post, running, wait_idle
from test_runlog import FILL, lines

SECRET = "Secretname-the-model-wrote-this"


def test_a_bad_output_names_the_step_and_with_debug_on_the_problem(tmp_path, caplog):
    config = Config(log_path=str(tmp_path / "runs.jsonl"), debug_path=str(tmp_path / "debug.jsonl"))
    with caplog.at_level(logging.INFO, logger="pulpermill"):
        with running(config, FakeEngine(), run=pipelines.run) as (base, _):
            assert post(base, FILL).json()["error"]["kind"] == "bad_output"
            assert wait_idle(base)
    [line] = [r.getMessage() for r in caplog.records if "result=bad_output" in r.getMessage() and "step=" in r.getMessage()]
    assert line.startswith("call=fill result=bad_output step=fill problem=") and len(line.split("problem=")[1]) <= 200


def test_without_debug_the_console_names_the_step_but_no_problem_line(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="pulpermill"):
        with running(Config(log_path=str(tmp_path / "runs.jsonl")), FakeEngine(), run=pipelines.run) as (base, _):
            post(base, FILL)
            assert wait_idle(base)
    [line] = [r.getMessage() for r in caplog.records if "result=bad_output step=" in r.getMessage()]
    assert "problem=" not in line and not (tmp_path / "debug.jsonl").exists()


def test_the_console_line_for_a_call_with_no_refused_step_still_reads():
    assert server._bad_output_line("plan", {}, Config()) == "call=plan result=bad_output step=?"


def test_through_the_server_the_debug_file_has_the_call_and_the_run_log_has_no_text(tmp_path):
    runs, debug = tmp_path / "runs.jsonl", tmp_path / "debug.jsonl"
    engine = FakeEngine()
    engine.script(f"{SECRET} one", f"{SECRET} two")
    with running(Config(log_path=str(runs), debug_path=str(debug)), engine, run=pipelines.run) as (base, _):
        assert post(base, FILL).status_code == 502
        assert wait_idle(base)
    refused = [json.loads(x) for x in debug.read_text(encoding="utf-8").splitlines()]
    assert [r["call"] for r in refused] == ["fill", "fill"] and SECRET in refused[0]["reply"] and refused[0]["problem"]
    assert SECRET not in runs.read_text(encoding="utf-8")
    assert lines(runs)[1]["result"] == "bad_output"


def test_a_call_that_succeeds_leaves_no_debug_file(tmp_path):
    debug = tmp_path / "debug.jsonl"
    with running(Config(debug_path=str(debug))) as (base, _):
        assert post(base, FILL).status_code == 200
        assert wait_idle(base)
    assert not debug.exists()


def test_the_launcher_flag_puts_the_debug_file_beside_the_run_log_and_is_off_by_default():
    assert debug_file("/kaggle/working/pulpermill-runs.jsonl", False) is None
    assert debug_file("/kaggle/working/pulpermill-runs.jsonl", True) == str(Path("/kaggle/working") / "pulpermill-debug.jsonl")
    assert debug_file("/x/runs.jsonl", True, "/y/mine.jsonl") == "/y/mine.jsonl"
