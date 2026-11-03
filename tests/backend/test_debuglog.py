"""The opt-in debug capture (debuglog.py): a refused attempt leaves its problem line and raw reply in a file, only when asked for,
and never at the run log's expense. These tests drive the runner directly (no web server needed); the server console line, the
launcher flag and the notebook are in test_debuglog_server.py."""
import json
import logging
from pathlib import Path

import pytest

from pulpermill.backend import debuglog, runlog
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.engine.base import CancelFlag
from pulpermill.backend.errors import BackendError
from pulpermill.backend.pipelines import RunContext
from pulpermill.prompter import Flow, Step

from test_runner import ENGLISH, GOOD, Steps, json_step, text_step

ROOT = Path(__file__).parents[2]
SECRET = "Secretname-the-model-wrote-this"


def make(path=None, prompts=False, engine=None):
    engine = engine or FakeEngine()
    ctx = RunContext(engine, CancelFlag(), [].append, Config(debug_path=str(path) if path else None, debug_prompts=prompts))
    ctx.notes["call"] = "generate"
    return ctx, engine


def run(ctx, *steps):
    from pulpermill.backend import runner
    return runner.run_flow(ctx, Steps(*steps), "en")


def rows(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines()]


def refuse_all(ctx, engine, *steps):
    with pytest.raises(BackendError) as e:
        run(ctx, *steps)
    assert e.value.kind == "bad_output"


def test_with_the_setting_off_nothing_is_written(tmp_path):
    ctx, engine = make(None)
    engine.script("not json", "still not json")
    refuse_all(ctx, engine, json_step())
    assert list(tmp_path.iterdir()) == [] and Config().debug_path is None and Config().debug_prompts is False
    assert debuglog.for_config(ctx.config) is None


def test_a_refused_attempt_writes_one_line_with_the_problem_and_the_raw_reply(tmp_path):
    path = tmp_path / "debug.jsonl"
    ctx, engine = make(path)
    engine.script(f"{SECRET} is not json", GOOD)
    run(ctx, json_step())                       # the first attempt is refused, the second is used
    [row] = rows(path)
    assert row["call"] == "generate" and row["step"] == "think" and row["attempt"] == 1 and row["constrained"] is True
    assert SECRET in row["reply"] and row["reply_cut"] is False and row["reply_chars"] == len(row["reply"])
    assert "not valid JSON" in row["problem"] and row["at"].endswith("Z") and "output_tokens" in row


def test_a_successful_attempt_writes_nothing(tmp_path):
    path = tmp_path / "debug.jsonl"
    ctx, engine = make(path)
    engine.script(GOOD)
    run(ctx, json_step())
    assert not path.exists()


def test_every_refused_attempt_is_a_line_and_the_token_count_is_given(tmp_path):
    path = tmp_path / "debug.jsonl"
    ctx, engine = make(path)
    engine.script(ENGLISH, ENGLISH)
    refuse_all(ctx, engine, text_step(name="write", check=lambda v: "the opening repeats the last chapter"))
    first, second = rows(path)
    assert (first["attempt"], second["attempt"]) == (1, 2) and first["constrained"] is False and first["step"] == "write"
    assert first["output_tokens"] == len(ENGLISH.split())      # the fake engine counts a word as a token


def test_the_problem_line_is_kept_in_full_not_shortened(tmp_path):
    path = tmp_path / "debug.jsonl"
    ctx, engine = make(path)
    long_problem = "the name " + "Zorblax " * 200 + "comes back twice"
    engine.script(ENGLISH, ENGLISH)
    refuse_all(ctx, engine, text_step(name="write", check=lambda v: long_problem))
    [first, _] = rows(path)
    assert first["problem"] == long_problem and len(first["problem"]) > 300 and "…" not in first["problem"]
    assert ctx.notes["passes"][0]["attempts"][0]["problem"].endswith("…")     # the retry line still carries the short one


def test_a_reply_over_the_limit_is_cut_and_says_so(tmp_path):
    path = tmp_path / "debug.jsonl"
    ctx, engine = make(path)
    big = "word " * 10_000
    assert len(big) > debuglog.REPLY_CHARS
    engine.script(big, big)
    refuse_all(ctx, engine, text_step(name="write", check=lambda v: "too long"))
    [first, _] = rows(path)
    assert first["reply_cut"] is True and len(first["reply"]) == debuglog.REPLY_CHARS and first["reply_chars"] == len(big)


def test_the_first_prompt_is_kept_only_when_asked_for_and_only_for_the_first_refusal(tmp_path):
    plain, with_prompts = tmp_path / "plain.jsonl", tmp_path / "prompts.jsonl"
    for path, prompts in ((plain, False), (with_prompts, True)):
        ctx, engine = make(path, prompts)
        engine.script(ENGLISH, ENGLISH)
        refuse_all(ctx, engine, text_step("Write the chapter now.", name="write", check=lambda v: "no"))
    assert all("prompt" not in r for r in rows(plain))
    first, second = rows(with_prompts)
    assert first["prompt"].startswith("Write the chapter now.") and "could not be used" not in first["prompt"] and "prompt" not in second


def test_an_unwritable_path_never_fails_the_call_and_is_said_once(tmp_path, caplog):
    bad = tmp_path / "no" / "such" / "dir" / "debug.jsonl"
    ctx, engine = make(bad)
    engine.script("not json", GOOD, "not json", "not json")
    with caplog.at_level(logging.WARNING, logger="pulpermill"):
        run(ctx, json_step())                   # refused once, then used: the call succeeds
        refuse_all(ctx, engine, json_step())    # a second call, refused twice
    said = [r for r in caplog.records if "debug file" in r.getMessage()]
    assert len(said) == 1 and not bad.exists()


def test_a_failing_capture_cannot_fail_the_call(tmp_path, monkeypatch):
    ctx, engine = make(tmp_path / "debug.jsonl")
    def boom(*a, **k):
        raise RuntimeError("the disk caught fire")
    monkeypatch.setattr(debuglog.DebugLog, "refused", boom)
    engine.script("not json", GOOD)
    assert run(ctx, json_step()) == [{"fits": True, "message": ""}]


def test_the_run_log_still_holds_no_problem_line_and_no_reply_text(tmp_path):
    path = tmp_path / "debug.jsonl"
    ctx, engine = make(path)
    engine.script(f"{SECRET} is not json", GOOD)
    run(ctx, json_step())
    record = runlog.build("generate", 0.0, 1.0, "ok", [], ctx.notes)
    text = json.dumps(record)
    assert SECRET not in text and "problem" not in text and record["passes"][0]["attempts"][0]["failed"] is True
    assert SECRET in path.read_text(encoding="utf-8")      # the debug file is where it is kept


def test_the_runlog_docstring_names_the_debug_file_as_the_exception():
    assert "debug_path" in runlog.__doc__ and "opt-in" in runlog.__doc__


def test_the_notebook_still_parses_and_turns_debug_on_in_the_launch_cell():
    nb = json.loads((ROOT / "notebooks" / "pulpermill_backend.ipynb").read_text(encoding="utf-8"))
    launch = [c for c in nb["cells"] if c["cell_type"] == "code" and "launch(" in "".join(c["source"])]
    source = "".join(launch[0]["source"])
    assert len(launch) == 1 and "debug=True" in source and "do not share or commit" in source
