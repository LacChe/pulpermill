"""A12: a chapter or a plan is not thrown away for a soft problem. Hard problems refuse every attempt; soft ones (an echoed opening, a name
on no card) refuse the first attempt, ride the retry line to the model, and are let through on the last. An accepted echo is trimmed to
whole sentences. The checks are driven directly and through the backend's runner (prompts patched: only the checks are under test)."""
import logging
from types import SimpleNamespace

import pytest

from pulpermill.backend import runner
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.engine.base import CancelFlag
from pulpermill.backend.errors import BackendError
from pulpermill.backend.pipelines import RunContext
from pulpermill.prompter.base import Flow
from pulpermill.prompter.mill import common, generate as gen, plan

from test_names_and_echo import ECHO, ENDING, FRESH, generate_request, vector

KIT = SimpleNamespace(grammar=SimpleNamespace(plan_beat=lambda: {"type": "object"}))
SOFT_NAME = "Later she met Zorblax at the gate and told Zorblax to wait."


def filler(words: int) -> str:
    nouns = ["lantern", "harbour", "orchard", "bridge", "cellar", "furnace", "meadow", "tavern", "quarry", "market"]
    out, n = [], 0
    while n < words:
        a, b = nouns[len(out) % 10], nouns[(len(out) * 3 + 1) % 10]
        out.append(f"The {a} stayed quiet while the wind moved over the {b} and nobody said a word.")
        n += 17
    return " ".join(out)


def request():
    r = generate_request(chapter=2, previous_ending=ENDING)
    return r


def write_check(req=None):
    flow = gen.GenerateFlow(req or request(), SimpleNamespace(grammar=None))
    return flow, flow._step(0, []).check


def count_words(text):
    return len(text.split())


# ---- the chapter: two tiers ------------------------------------------------------------------------------------------------

def test_a_chapter_with_only_an_unknown_person_fails_the_first_check_and_passes_the_second():
    req = request()
    req.pop("previous_ending")
    body = FRESH + " " + SOFT_NAME + " " + filler(200)
    _, check = write_check(req)
    first = check(body)
    assert first and "Zorblax" in first
    assert check(body) is None


def test_the_plain_write_problem_is_still_strict_and_tolerates_soft_only_on_request():
    req = request()
    req.pop("previous_ending")
    body = FRESH + " " + SOFT_NAME
    assert "Zorblax" in gen.write_problem(req, body)
    assert gen.write_problem(req, body, tolerate_soft=True) is None
    hard, soft = gen.write_findings(req, body)
    assert hard is None and [k for k, _ in soft] == ["unknown_person"]


def test_a_chapter_far_over_the_cap_fails_both_check_calls():
    req = request()
    req.pop("previous_ending")
    body = filler(gen.OVERSHOOT_WORDS + 300)
    _, check = write_check(req)
    assert check(body) and check(body)
    assert gen.write_problem(req, body, tolerate_soft=True)


def test_an_empty_chapter_fails_both_attempts_through_the_runner(monkeypatch):
    monkeypatch.setattr(gen, "write_prompt", lambda request, factor=1.0: "Write the chapter.")
    ctx, engine = context()
    engine.script("", "   ")
    with pytest.raises(BackendError) as e:
        runner.run_flow(ctx, WriteOnly(gen.GenerateFlow(request(), SimpleNamespace(grammar=None))), "en")
    assert e.value.kind == "bad_output" and engine.calls == 2


def test_an_echo_that_survives_both_attempts_is_trimmed_to_whole_sentences_on_the_soft_accept():
    req = request()
    body = ECHO + " " + filler(450)
    flow, check = write_check(req)
    assert "repeating the end" in check(body)
    assert check(body) is None and flow.echo_accepted
    text = flow.reply([body, {"happened": "x", "changed": "y"}, {"shifts": []}])["chapter_text"]
    first_new = ECHO.split(". ", 1)[1]
    assert text.startswith(first_new) and "deposited the applewood" not in text and text.endswith(body.strip()[-40:])
    assert text == body[len(ECHO.split(". ", 1)[0]) + 2:]               # nothing but the repeated sentence went, and whitespace stayed


def test_trimming_never_cuts_inside_a_sentence_and_only_the_repeated_ones_go():
    ending = "She set the lamp on the sill and watched the road for a long time. Nobody came."
    opening = "She set the lamp on the sill and watched the road for a long time. By dawn a cart had come up the hill. " + filler(450)
    text, dropped = common.trim_echo(opening, ending)
    assert dropped == 1 and text.startswith("By dawn a cart had come up the hill.") and text.endswith(opening[-30:])
    both = "She set the lamp on the sill and watched the road for a long time.\n\nShe set the lamp on the sill and watched the road for a long time! " + filler(450)
    text, dropped = common.trim_echo(both, ending)
    assert dropped == 2 and text.startswith("The ")


def test_a_chapter_that_trimming_would_leave_under_400_words_is_kept_whole():
    req = request()
    body = ECHO + " " + filler(300)
    flow, check = write_check(req)
    check(body)
    assert check(body) is None and flow.echo_accepted
    assert flow.reply([body, {}, {"shifts": []}])["chapter_text"] == body.strip()
    assert common.trim_echo(body, ENDING) == (body, 0)


def test_nothing_is_trimmed_unless_an_echo_was_soft_accepted():
    body = ECHO + " " + filler(450)
    flow = gen.GenerateFlow(request(), SimpleNamespace(grammar=None))
    assert flow.reply([body, {}, {"shifts": []}])["chapter_text"] == body.strip()        # no check ran
    flow, check = write_check()
    check(FRESH + " " + filler(450))                                                      # a clean first reply
    assert not flow.echo_accepted


def test_the_accepted_problem_and_the_trim_are_said_once_each_on_the_console_without_story_text(caplog):
    req = request()
    body = ECHO + " " + SOFT_NAME + " " + filler(450)
    flow, check = write_check(req)
    with caplog.at_level(logging.WARNING, logger="pulpermill"):
        check(body)
        check(body)
        flow.reply([body, {}, {"shifts": []}])
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("call=generate step=write soft problem")]
    assert len(lines) == 3 and any("accepted" in x and "repeating the end" in x for x in lines) and any("trimmed" in x for x in lines)
    assert any("Zorblax" in x for x in lines) and not any("lantern" in x or "applewood" in x for x in lines)


def test_counts_start_again_for_every_step_instance():
    req = request()
    req.pop("previous_ending")
    body = FRESH + " " + SOFT_NAME
    flow = gen.GenerateFlow(req, SimpleNamespace(grammar=None))
    one, two = flow._step(0, []).check, flow._step(0, []).check
    assert one(body) and one(body) is None
    assert two(body)                                    # a new step instance is on its first attempt
    assert common.Attempts().tick() is False


# ---- the plan: the same ----------------------------------------------------------------------------------------------------

def plan_request():
    return vector("plan", "a plan request")


def good_plan(req):
    names = plan.names_of(req)
    tie = next(t for t in req["ties"] if t["id"] == req["spotlight"])
    a, b = names[tie["tie_from"]], names[tie["tie_to"]]
    place = (req["world"].get("places") or [{}])[0].get("name") or "the square"
    return {"where": place, "when_time": "Day 9, early morning",
            "aim": f"Get the brass key from {b} before the harbour bell rings in round {req['chapter']}.",
            "plan": f"Act 1: {a} and {b} meet at {place} at first light. Act 2: the aim runs into the tie between {a} and {b}, and a quarrel breaks out. "
                    f"Act 3: a costly choice turns the scene when {a} gives something up. Act 4: the chapter ends with the tie and the aim in a new state."}


def plan_check(req):
    return plan.PlanFlow(req, KIT)._step().check


def test_a_plan_with_only_an_unknown_person_fails_the_first_check_and_passes_the_second():
    req = plan_request()
    beat = good_plan(req)
    assert plan.plan_problem(req, beat) is None
    named = {**beat, "plan": beat["plan"] + " Master Elmsworth, a stern clerk, oversees deliveries."}
    check = plan_check(req)
    first = check(named)
    assert first and "Master Elmsworth" in first
    assert check(named) is None
    assert "Master Elmsworth" in plan.plan_problem(req, named) and plan.plan_problem(req, named, tolerate_soft=True) is None


def test_a_plan_that_lacks_a_required_part_fails_both_check_calls():
    req = plan_request()
    beat = good_plan(req)
    for broken in ({**beat, "where": ""}, {**beat, "plan": "Act 1: they meet. Act 2: they quarrel."}, {**beat, "aim": ""}):
        check = plan_check(req)
        assert check(broken) and check(broken)


def test_a_plan_with_both_a_hard_and_a_soft_problem_reports_the_hard_one_on_the_last_attempt(caplog):
    req = plan_request()
    broken = {**good_plan(req), "plan": "Act 1: Master Elmsworth waits. Act 2: Master Elmsworth leaves."}
    check = plan_check(req)
    assert check(broken)
    with caplog.at_level(logging.WARNING, logger="pulpermill"):
        line = check(broken)
    assert line and "Master Elmsworth" not in line.split("Act")[0] and not [r for r in caplog.records if "soft problem" in r.getMessage()]


def test_the_plan_uses_the_soft_reply_on_the_second_attempt_through_the_runner_and_says_so_once(monkeypatch, caplog):
    req = plan_request()
    named = {**good_plan(req), "plan": good_plan(req)["plan"] + " Master Elmsworth, a stern clerk, oversees deliveries."}
    import json
    monkeypatch.setattr(plan, "build_prompt", lambda request, factor=1.0: "Plan the chapter.")
    ctx, engine = context()
    engine.script(json.dumps(named), json.dumps(named))
    with caplog.at_level(logging.WARNING, logger="pulpermill"):
        [value] = runner.run_flow(ctx, plan.PlanFlow(req, KIT), "en")
    assert value == named and engine.calls == 2 and "Master Elmsworth" in engine.prompts[1]          # the retry line carried the problem
    assert len([r for r in caplog.records if r.getMessage().startswith("call=plan step=plan soft problem accepted")]) == 1


def test_a_hard_plan_problem_still_ends_bad_output_through_the_runner(monkeypatch):
    import json
    req = plan_request()
    monkeypatch.setattr(plan, "build_prompt", lambda request, factor=1.0: "Plan the chapter.")
    ctx, engine = context()
    bad = json.dumps({**good_plan(req), "where": ""})
    engine.script(bad, bad)
    with pytest.raises(BackendError) as e:
        runner.run_flow(ctx, plan.PlanFlow(req, KIT), "en")
    assert e.value.kind == "bad_output"


def test_the_chapter_is_used_after_a_second_attempt_with_only_soft_problems_through_the_runner(monkeypatch):
    monkeypatch.setattr(gen, "write_prompt", lambda request, factor=1.0: "Write the chapter.")
    req = request()
    req.pop("previous_ending")
    body = FRESH + " " + SOFT_NAME + " " + filler(200)
    ctx, engine = context()
    engine.script(body, body)
    [text] = runner.run_flow(ctx, WriteOnly(gen.GenerateFlow(req, SimpleNamespace(grammar=None))), "en")
    assert text == body and engine.calls == 2 and "Zorblax" in engine.prompts[1]


def test_the_versions_were_bumped():
    from pulpermill.prompter.mill import VERSION
    assert VERSION == "mill-0.2" and plan.VERSION == "plan-3" and gen.VERSION == "generate-5"


# ---- helpers ---------------------------------------------------------------------------------------------------------------

def context():
    engine = FakeEngine()
    return RunContext(engine, CancelFlag(), [].append, Config()), engine


class WriteOnly(Flow):
    """Runs only the write step of a generate flow, so the runner's attempts drive the flow's own check."""

    def __init__(self, inner):
        self.inner = inner

    def next(self, results):
        return None if results else self.inner._step(0, [])

    def worst_case(self):
        return [self.inner._step(0, [])]

    def reply(self, results):
        return results
