"""The brainstorm count check: a reply that has options but not exactly three is refused, so the retry fixes it. Neutral placeholder text
throughout. The flow tests run the real plan flow on the fake engine (no model)."""
import json

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

from test_decide_flow import BRAINSTORM, texts_for  # noqa: E402
from test_select import base, choose_request, names_of_steps, run_plan  # noqa: E402

from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter.mill import decide, plan  # noqa: E402
from pulpermill.prompter.mill.common import load_text  # noqa: E402

COUNT_LINE = load_text("plan")["problems"]["brainstorm_count"]
SHORT_LINE = load_text("plan")["problems"]["brainstorm_short"]


def idea(n: int, label: int | None = None) -> str:
    head = f"Option {n}" + (f": Combination {label}" if label else "")
    return f"{head}\nThe protagonist wants a thing. Someone says no, and the two clash at a place. It costs a favour and the collision ends.\n"


def reply(*numbers: int, labels: tuple[int, ...] | None = None) -> str:
    return "\n".join(idea(n, labels[i] if labels else None) for i, n in enumerate(numbers))


SIX = ("Combination 1\n" + reply(1, 2, 3) + "\nCombination 2\n" + reply(1, 2, 3))
SIX_FLAT = reply(1, 2, 3, 4, 5, 6)


def check_of(request: dict):
    return plan.build_flow(request, Kit(request))


def test_three_options_pass_and_six_options_are_refused():
    flow = check_of(base())
    assert flow._brainstorm_check(reply(1, 2, 3)) is None and flow._brainstorm_check(BRAINSTORM) is None
    assert flow._brainstorm_check(SIX_FLAT) == COUNT_LINE and flow._brainstorm_check(SIX) == COUNT_LINE
    assert flow._brainstorm_check(reply(1, 2)) == COUNT_LINE                                  # two options are refused as well


def test_three_options_of_which_the_last_is_cut_off_are_refused():
    flow = check_of(base())
    cut = reply(1, 2, 3).rstrip()[:-12]                                                       # the last idea ends mid-sentence
    assert not cut.rstrip().endswith(".") and flow._brainstorm_check(cut) == COUNT_LINE


def test_a_reply_the_parser_cannot_split_passes_and_a_short_one_is_still_refused_as_short():
    flow = check_of(base())
    one_line = plan.script(base(), Kit(base()))[0]                                            # the script's brainstorm is one line
    assert len(decide.parse_options(one_line)) < 2 and flow._brainstorm_check(one_line) is None
    assert flow._brainstorm_check("A long single idea with no header. " * 8) is None
    assert flow._brainstorm_check("Too short.") == SHORT_LINE


def test_in_choose_mode_three_options_must_carry_the_combination_numbers_one_two_three():
    request = choose_request()
    flow = check_of(request)
    flow.combos = [{"tie_id": f"t{i}", "tie_words": f"Tie {i}", "pressure_id": None, "pressure": None, "pressure_words": "", "reason": "r"} for i in (1, 2, 3)]
    assert flow._brainstorm_check(reply(1, 2, 3)) is None
    assert flow._brainstorm_check(reply(1, 2, 3, labels=(1, 2, 3))) is None
    assert flow._brainstorm_check(reply(1, 2, 3, labels=(1, 1, 2))) == COUNT_LINE            # [1, 1, 2]
    assert flow._brainstorm_check(SIX) == COUNT_LINE


def test_a_reply_of_six_options_is_asked_for_again_and_the_decider_then_runs_on_three():
    request = base()
    texts = texts_for(request)
    flow, out, ctx, engine = run_plan(request, SIX_FLAT, *texts)
    assert names_of_steps(ctx)[:3] == ["brainstorm", "decide", "plan"] and "brainstorm_fallback" not in ctx.notes["flow"]
    brainstorm_pass = [p for p in ctx.notes["passes"] if p["step"] == "brainstorm"][0]
    assert len(brainstorm_pass["attempts"]) == 2
    assert COUNT_LINE in engine.prompts[1] and COUNT_LINE not in engine.prompts[0]            # the retry carries the line, the first prompt does not
    assert engine.prompts[2].count("Option ") >= 3 and "Option 4" not in engine.prompts[2]    # the decider reads the second reply's three options


def test_two_bad_replies_end_in_the_fallback_and_the_plan_runs_without_a_brainstorm():
    request = base()
    texts = plan.script(request, Kit(request))
    plan_reply = json.loads(texts[1])
    plan_reply.pop(plan.IDEA_USE, None)
    flow, out, ctx, engine = run_plan(request, SIX_FLAT, SIX, json.dumps(plan_reply))
    assert ctx.notes["flow"]["brainstorm_fallback"] is True and ctx.notes["flow"]["decide"] == "none"
    assert names_of_steps(ctx) == ["brainstorm", "plan"] and COUNT_LINE in engine.prompts[1]
    assert "Option 4" not in engine.prompts[2] and out == {"beat": plan_reply}
