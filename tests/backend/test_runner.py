"""The generic runner on its own, with a small test prompter: the fit and squeeze before the first token, the two-attempt rule and its
retry line, the language check, cancel, progress, and the run record."""
import json

import pytest

from pulpermill.backend import runner
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.engine.base import CancelFlag
from pulpermill.backend.errors import BackendError, Cancelled
from pulpermill.backend.pipelines import RunContext
from pulpermill.prompter import Flow, Step
from pulpermill.prompts import budget

SCHEMA = {"type": "object", "properties": {"fits": {"type": "boolean"}, "message": {"type": "string"}},
          "required": ["fits", "message"], "additionalProperties": False}
GOOD = json.dumps({"fits": True, "message": ""})
ENGLISH = ("She walked down to the river and the water was cold against her feet, and she did not look back at the house "
           "that had been her home for all of those years, because there was nothing left in it for her to keep.")
FRENCH = ("Elle descendit jusqu'à la rivière et l'eau était froide contre ses pieds, et elle ne regarda pas la maison qui "
          "avait été la sienne pendant toutes ces années, parce qu'il n'y avait plus rien dans cette maison pour elle.")
CHINESE = "她走到河边，水很冷，她没有回头看那座已经住了很多年的房子，因为那里面再也没有什么值得她留下的东西了。"


class Steps(Flow):
    """A flow that runs the steps it is given, in order."""

    def __init__(self, *steps: Step):
        self.steps = steps

    def next(self, results):
        return self.steps[len(results)] if len(results) < len(self.steps) else None

    def worst_case(self):
        return list(self.steps)

    def reply(self, results):
        return {"results": results}


def json_step(text="Decide whether it fits.", name="think", **kw):
    return Step(name, kw.pop("text_fn", lambda f: text), "json", kw.pop("max_output", 400), kw.pop("grammar", SCHEMA), **kw)


def text_step(text="Write something.", name="write", **kw):
    return Step(name, lambda f: text, "text", kw.pop("max_output", 400), **kw)


def make(engine=None, **config):
    engine = engine or FakeEngine()
    stages: list = []
    ctx = RunContext(engine, CancelFlag(), stages.append, Config(**config))
    return ctx, engine, stages


def run(ctx, *steps, language="en"):
    return runner.run_flow(ctx, Steps(*steps), language)


def test_a_valid_first_reply_is_used_once_and_constrained():
    ctx, engine, stages = make()
    engine.script(GOOD)
    assert run(ctx, json_step()) == [{"fits": True, "message": ""}]
    assert engine.calls == 1 and engine.constraints == [SCHEMA]
    assert stages == [{"name": "think", "index": 1, "of": 1}]


def test_a_raw_newline_inside_a_json_string_is_used_on_the_first_attempt():
    ctx, engine, _ = make()
    engine.script('{"fits": true, "message": "line one\nline two\tend"}', GOOD)
    assert run(ctx, json_step()) == [{"fits": True, "message": "line one\nline two\tend"}]
    assert engine.calls == 1 and [len(p["attempts"]) for p in ctx.notes["passes"]] == [1]


def test_bad_json_retries_once_with_the_problem_and_without_the_first_reply():
    ctx, engine, _ = make()
    engine.script("this is not json at all", GOOD)
    run(ctx, json_step())
    second = engine.prompts[1]
    assert second.startswith("Decide whether it fits.") and "could not be used" in second and "not valid JSON" in second
    assert "this is not json at all" not in second and "could not be used" not in engine.prompts[0]
    assert [len(p["attempts"]) for p in ctx.notes["passes"]] == [2]


def test_two_failures_are_bad_output():
    ctx, engine, _ = make()
    engine.script('{"fits": "yes", "message": ""}', "{}")
    with pytest.raises(BackendError) as e:
        run(ctx, json_step())
    assert e.value.kind == "bad_output" and engine.calls == 2


def test_a_cut_off_reply_is_a_shape_failure():
    ctx, engine, _ = make()
    engine.script('{"fits": true, "message": "It is a good', GOOD)
    run(ctx, json_step())
    assert ctx.notes["passes"][0]["attempts"][0]["problem"].count("cut off") == 1


def test_the_steps_own_check_counts_as_a_shape_failure():
    ctx, engine, _ = make()
    engine.script(GOOD, GOOD)
    with pytest.raises(BackendError):
        run(ctx, json_step(check=lambda v: "fits must be false here"))
    assert "fits must be false here" in engine.prompts[1]


def test_repair_mode_writes_free_first_and_constrains_the_retry():
    ctx, engine, _ = make(constrain="repair")
    engine.script("oops", GOOD)
    run(ctx, json_step())
    assert engine.constraints == [None, SCHEMA]
    ctx, engine, _ = make(constrain="repair")
    engine.script(GOOD)
    run(ctx, json_step())
    assert engine.constraints == [None] and engine.calls == 1


def test_a_text_step_is_never_constrained():
    ctx, engine, _ = make()
    engine.script(ENGLISH)
    assert run(ctx, text_step()) == [ENGLISH] and engine.constraints == [None]


def test_the_step_names_its_sampling_and_the_story_language_picks_the_prose_set():
    ctx, engine, _ = make()
    engine.script(CHINESE, GOOD, ENGLISH, GOOD)
    run(ctx, text_step(sampling="prose"), json_step(sampling="structured"), language="zh")
    assert engine.params == [ctx.config.prose_zh, ctx.config.structured]
    ctx, engine, _ = make()
    engine.script(ENGLISH, GOOD)
    run(ctx, text_step(sampling="prose"), json_step(sampling="thinking"), language="en")
    assert engine.params == [ctx.config.prose, ctx.config.thinking]


def test_too_long_is_answered_before_any_inference():
    ctx, engine, _ = make()
    with pytest.raises(BackendError) as e:
        run(ctx, json_step("word " * (budget.input_limit(400) + 500)))
    assert e.value.kind == "too_long" and engine.calls == 0


def test_every_step_is_fitted_before_the_first_token():
    """The second step, which reads the first one's reply, is too big at its worst case: nothing is written at all."""
    ctx, engine, _ = make()
    big = text_step(text="word " * (budget.input_limit(400) + 500), name="later")
    with pytest.raises(BackendError) as e:
        run(ctx, json_step(), big)
    assert e.value.kind == "too_long" and engine.calls == 0


def test_the_squeeze_is_the_fullest_at_which_every_step_fits_and_is_recorded():
    ctx, engine, _ = make()
    room = budget.input_limit(400)
    engine.script(GOOD)
    run(ctx, json_step(text_fn=lambda f: "word " * int((room + 2000) * f)))
    assert ctx.notes["squeeze"] == 0.85 and len(engine.prompts[0].split()) == int((room + 2000) * 0.85)


def test_stop_is_not_retried():
    ctx, engine, _ = make()
    engine.fail_next(Cancelled())
    with pytest.raises(Cancelled):
        run(ctx, json_step())
    assert engine.calls == 1


def test_stop_between_attempts_ends_the_call():
    ctx, engine, _ = make()
    engine.script("nope")
    ctx.cancel.set()
    with pytest.raises(Cancelled):
        run(ctx, json_step())
    assert engine.calls == 0


def test_a_reply_in_the_wrong_language_is_retried_once():
    ctx, engine, _ = make()
    engine.script(json.dumps({"fits": False, "message": CHINESE * 2}), json.dumps({"fits": False, "message": ENGLISH}))
    assert run(ctx, json_step())[0]["message"] == ENGLISH
    assert "language" in engine.prompts[1]
    ctx, engine, _ = make()
    engine.script(*[json.dumps({"fits": False, "message": ENGLISH})] * 2)
    with pytest.raises(BackendError) as e:
        run(ctx, json_step(), language="zh-Hans")
    assert e.value.kind == "bad_output"


def test_a_step_that_says_it_is_not_in_the_story_language_is_not_checked():
    ctx, engine, _ = make()
    engine.script(json.dumps({"fits": False, "message": FRENCH}))
    run(ctx, json_step(language=False))
    assert engine.calls == 1


def test_free_text_in_the_wrong_language_or_empty_is_retried():
    ctx, engine, _ = make()
    engine.script(FRENCH, ENGLISH)
    assert run(ctx, text_step()) == [ENGLISH] and engine.calls == 2
    ctx, engine, _ = make()
    engine.script("   ", ENGLISH)
    assert run(ctx, text_step()) == [ENGLISH]


def test_the_note_is_left_out_when_it_would_not_fit_and_the_engines_count_is_used_without_the_tokenizer_files():
    ctx, engine, _ = make()
    real = runner.tokens.available
    runner.tokens.available = lambda: False                      # one word, one token, as the fake engine counts
    try:
        engine.script("bad", GOOD)
        run(ctx, json_step("word " * (budget.input_limit(400) - 2)))
        assert "could not be used" not in engine.prompts[1]
        with pytest.raises(BackendError) as e:
            run(ctx, json_step("word " * (budget.input_limit(400) + 5)))
        assert e.value.kind == "too_long"
    finally:
        runner.tokens.available = real


def test_the_problem_is_short_and_one_line():
    assert runner.short("bad\n" + "x " * 600).count("…") == 1 and len(runner.short("bad\n" + "x " * 600)) <= runner.PROBLEM_CHARS
    assert "\n" not in runner.short("a\nb")


def test_progress_counts_steps_from_one_and_says_how_many_when_it_is_known():
    ctx, engine, stages = make()
    engine.script(ENGLISH, GOOD)
    run(ctx, text_step(name="write"), json_step(name="events"))
    assert stages == [{"name": "write", "index": 1, "of": 2}, {"name": "events", "index": 2, "of": 2}]

    class Long(Steps):
        def worst_case(self):
            return [self.steps[0]]                               # the flow ran more steps than it said
    ctx, engine, stages = make()
    engine.script(ENGLISH, GOOD)
    runner.run_flow(ctx, Long(text_step(name="write"), json_step(name="events")), "en")
    assert stages[-1] == {"name": "events", "index": 2, "of": None}


def test_a_step_name_the_contract_could_not_carry_is_refused_when_the_step_is_made():
    with pytest.raises(ValueError):
        Step("a sentence with spaces", lambda f: "x", "text", 10)
    with pytest.raises(ValueError):
        Step("ok", lambda f: "x", "json", 10)                    # json needs a grammar
    with pytest.raises(ValueError):
        Step("ok", lambda f: "x", "text", 10, sampling="warm")


def test_an_engine_loaded_with_another_n_ctx_is_refused_at_startup():
    runner.check_n_ctx(FakeEngine())
    with pytest.raises(RuntimeError, match="n_ctx"):
        runner.check_n_ctx(FakeEngine(n_ctx=8192))


# ---- Step.attempts and Step.fallback (I2) -------------------------------------------------------------------------------------------

def test_a_step_can_ask_for_more_attempts_and_each_retry_carries_the_last_problem():
    ctx, engine, _ = make()
    engine.script("no", "still no", "nope", GOOD)
    assert run(ctx, json_step(attempts=4)) == [{"fits": True, "message": ""}]
    assert engine.calls == 4 and [len(p["attempts"]) for p in ctx.notes["passes"]] == [4]
    assert all("could not be used" in p for p in engine.prompts[1:]) and engine.prompts[3].count("could not be used") == 1
    assert [a["constrained"] for a in ctx.notes["passes"][0]["attempts"]] == [True] * 4


def test_the_default_is_still_two_attempts_then_bad_output():
    assert json_step().attempts == 2 and json_step().fallback is None
    ctx, engine, _ = make()
    engine.script("a", "b", GOOD)
    with pytest.raises(BackendError) as e:
        run(ctx, json_step())
    assert e.value.kind == "bad_output" and engine.calls == 2


def test_after_the_last_refused_attempt_the_fallback_value_stands_in_and_is_marked():
    ctx, engine, _ = make()
    engine.script("a", "b", "c")
    out = run(ctx, json_step(attempts=3, fallback=lambda: {"fits": False, "message": "from code"}))
    assert out == [{"fits": False, "message": "from code"}] and engine.calls == 3
    entry = ctx.notes["passes"][0]
    assert entry["fallback"] is True and len(entry["attempts"]) == 3 and all("problem" in a for a in entry["attempts"])


def test_a_step_that_succeeds_never_calls_its_fallback_and_is_not_marked():
    ctx, engine, _ = make()
    engine.script("a", GOOD)
    called = []
    run(ctx, json_step(attempts=3, fallback=lambda: called.append(1)))
    assert called == [] and "fallback" not in ctx.notes["passes"][0]


def test_a_failing_fallback_is_bad_output_and_a_stop_is_never_a_fallback():
    ctx, engine, _ = make()
    engine.script("a", "b")
    with pytest.raises(BackendError) as e:
        run(ctx, json_step(fallback=lambda: 1 / 0))
    assert e.value.kind == "bad_output"
    ctx, engine, _ = make()
    engine.script("a")
    ctx.cancel.set()
    with pytest.raises(Cancelled):
        run(ctx, json_step(fallback=lambda: {}))


def test_a_text_step_can_have_a_fallback_too():
    ctx, engine, _ = make()
    engine.script("", "")
    assert run(ctx, text_step(fallback=lambda: "from code")) == ["from code"]


def test_a_step_with_a_bad_attempts_or_fallback_is_refused_when_it_is_made():
    for bad in (0, -1, 1.5, True):
        with pytest.raises(ValueError):
            json_step(attempts=bad)
    with pytest.raises(ValueError):
        json_step(fallback="not callable")
