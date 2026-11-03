"""The opt-in trace (trace.py): one line per attempt of every step, used or refused, with the full prompt each time; soft problems a
prompter accepted reach the line through `logging`; the file is off by default and never fails a call. No model, no server."""
import json
import threading
from pathlib import Path

from pulpermill.backend import runner, trace
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.engine.base import CancelFlag
from pulpermill.backend.launch import trace_file
from pulpermill.backend.pipelines import RunContext
from pulpermill.prompter.mill import common

from test_runner import ENGLISH, GOOD, Steps, json_step, text_step

FIELDS = {"t", "call", "step", "attempt", "constrained", "prompt", "reply", "used", "problem", "output_tokens", "seconds"}


def make(path=None, **config):
    engine = FakeEngine()
    ctx = RunContext(engine, CancelFlag(), [].append, Config(trace_path=str(path) if path else None, **config))
    ctx.notes["call"] = "generate"
    return ctx, engine


def run(ctx, *steps):
    return runner.run_flow(ctx, Steps(*steps), "en")


def rows(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines()]


def test_off_by_default_and_nothing_is_written(tmp_path):
    ctx, engine = make(None)
    engine.script(GOOD)
    run(ctx, json_step())
    assert Config().trace_path is None and trace.for_config(ctx.config) is None and list(tmp_path.iterdir()) == []


def test_a_used_first_attempt_is_one_line_with_every_field(tmp_path):
    path = tmp_path / "trace.jsonl"
    ctx, engine = make(path)
    engine.script(GOOD)
    run(ctx, json_step(text="Decide whether it fits."))
    [row] = rows(path)
    assert set(row) == FIELDS and row["call"] == "generate" and row["step"] == "think" and row["attempt"] == 1
    assert row["used"] is True and row["problem"] is None and row["reply"] == GOOD and row["prompt"] == "Decide whether it fits."
    assert row["constrained"] is True and row["t"].endswith("Z") and row["output_tokens"] >= 1 and row["seconds"] >= 0


def test_every_attempt_is_a_line_with_the_full_prompt_each_time(tmp_path):
    path = tmp_path / "trace.jsonl"
    ctx, engine = make(path)
    engine.script("not json", GOOD)
    run(ctx, json_step(text="Decide whether it fits."))
    first, second = rows(path)
    assert (first["attempt"], first["used"], second["attempt"], second["used"]) == (1, False, 2, True)
    assert "not valid JSON" in first["problem"] and first["reply"] == "not json" and second["problem"] is None
    assert first["prompt"] == "Decide whether it fits." and second["prompt"].startswith("Decide whether it fits.") and "could not be used" in second["prompt"]


def test_a_refused_step_leaves_both_attempts_before_the_error(tmp_path):
    path = tmp_path / "trace.jsonl"
    ctx, engine = make(path)
    engine.script(ENGLISH, ENGLISH)
    try:
        run(ctx, text_step(name="write", check=lambda v: "the opening repeats the last chapter"))
    except Exception as e:
        assert getattr(e, "kind", "") == "bad_output"
    first, second = rows(path)
    assert not first["used"] and not second["used"] and first["problem"] == "the opening repeats the last chapter" and first["reply"] == ENGLISH


def test_every_step_of_a_flow_is_traced(tmp_path):
    path = tmp_path / "trace.jsonl"
    ctx, engine = make(path)
    engine.script(GOOD, GOOD)
    run(ctx, json_step(name="one"), json_step(name="two"))
    assert [(r["step"], r["attempt"]) for r in rows(path)] == [("one", 1), ("two", 1)]


def test_a_soft_problem_accepted_on_a_used_attempt_reaches_its_line(tmp_path):
    path = tmp_path / "trace.jsonl"
    ctx, engine = make(path)
    engine.script(ENGLISH)

    def soft_check(value):
        common.note_soft("generate", "write", "the ending repeats the last chapter")      # the prompter's own helper; no backend import
        return None
    run(ctx, text_step(name="write", check=soft_check))
    [row] = rows(path)
    assert row["used"] is True and row["problem"] is None and row["soft"] == ["accepted: the ending repeats the last chapter"]


def test_a_soft_note_from_another_thread_or_outside_an_attempt_is_not_on_the_line(tmp_path):
    path = tmp_path / "trace.jsonl"
    ctx, engine = make(path)
    engine.script(GOOD)
    common.note_soft("generate", "write", "before the attempt")
    other = threading.Thread(target=lambda: common.note_soft("generate", "write", "another call"))

    def quiet(value):
        other.start()
        other.join()
        return None
    run(ctx, json_step(check=quiet))
    [row] = rows(path)
    assert "soft" not in row


def test_a_trace_that_cannot_be_written_never_fails_the_call(tmp_path):
    ctx, engine = make(tmp_path / "no-such-folder" / "trace.jsonl")
    engine.script(GOOD)
    assert run(ctx, json_step()) == [{"fits": True, "message": ""}]
    assert trace.for_config(ctx.config).failed is not None


def test_the_debug_file_still_works_beside_the_trace(tmp_path):
    debug, path = tmp_path / "debug.jsonl", tmp_path / "trace.jsonl"
    ctx, engine = make(path, debug_path=str(debug))
    engine.script("not json", GOOD)
    run(ctx, json_step())
    assert len(rows(debug)) == 1 and len(rows(path)) == 2


def test_the_trace_is_a_fallback_ready_line_and_never_marks_fallback_by_default(tmp_path):
    path = tmp_path / "trace.jsonl"
    t = trace.Trace(str(path))
    t.record(call="plan", step="plan", attempt=2, constrained=True, prompt="p", reply="r", used=True, problem=None, tokens=3, seconds=1.0, fallback=True)
    t.record(call="plan", step="plan", attempt=1, constrained=True, prompt="p", reply="r", used=True, problem=None, tokens=3, seconds=1.0)
    first, second = rows(path)
    assert first["fallback"] is True and "fallback" not in second


def test_the_launcher_puts_the_trace_beside_the_run_log_and_is_off_by_default():
    assert trace_file("/w/runs.jsonl", False) is None
    assert trace_file("/w/runs.jsonl", True) == "/w/pulpermill-trace.jsonl"
    assert trace_file(None, True) == "./pulpermill-trace.jsonl" and trace_file("/w/runs.jsonl", True, "/x/t.jsonl") == "/x/t.jsonl"
