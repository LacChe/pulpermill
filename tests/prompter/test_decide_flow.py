"""The decider (Plan 1), step 3: the decide step between the brainstorm and the plan, in the real plan flow on the fake engine. The plan is then
built on the one option the decider picked, shown as idea 1 with its own combination; the plan reply's schema is unchanged. Neutral placeholder
text throughout. No model."""
import json

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

from test_select import base, choose_request, names_of_steps, run_plan  # noqa: E402

from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter.mill import decide, plan  # noqa: E402

BRAINSTORM = ("Here are the options for this chapter.\n\n"
              "**Option 1: First (Combination 1)**\nThe protagonist wants a first thing. A says no, and the two clash at the first place.\n\n"
              "**Option 2: Second (Combination 2)**\nThe protagonist wants a second thing. B says no, and the two clash at the second place.\n\n"
              "**Option 3: Third (Combination 3)**\nThe protagonist wants a third thing. C says no, and the two clash at the third place.\n")
OPTIONS = decide.parse_options(BRAINSTORM)


def reply_for(request: dict, wanted: int, **entry) -> str:
    """A decider reply that picks the option that stood at place `wanted` (from 1) in the brainstorm, whatever letter the shuffle gave it."""
    order = decide.order_of(OPTIONS, request)
    letters = decide.LABELS[:len(OPTIONS)]
    row = {"weakest": "It is thin in the middle.", "loss": 2, "irreversible": True, "opposed": False, **entry}
    return json.dumps({"options": [{"label": letter, **row} for letter in letters], "pick": letters[order.index(wanted - 1)]})


def everyone(request: dict, text: str) -> str:
    """A scripted plan reply that names every person of the cast, so it fits whichever combination's tie the picked option belongs to."""
    beat = json.loads(text)
    beat["plan"] += " " + " ".join(f"{c['name']} is there." for c in request["cast"])
    return json.dumps(beat)


def texts_for(request: dict, wanted: int = 3, idea: int = 1) -> list[str]:
    """The scripted reply of a choose or plain plan call, with a brainstorm of three options on lines and the decider's reply after it."""
    texts = plan.script(request, Kit(request))
    at = 1 if request.get("choose") else 0
    beat = json.loads(texts[at + 1])
    if "idea" in beat:
        beat["idea"] = idea
    return texts[:at] + [BRAINSTORM, reply_for(request, wanted), everyone(request, json.dumps(beat))] + texts[at + 2:]


def first_texts_of(request: dict) -> list[str]:
    texts = plan.script(request, Kit(request))
    texts[2] = everyone(request, texts[2])
    return texts


def test_in_choose_mode_the_plan_is_built_on_the_picked_option_alone_as_idea_one_with_its_own_combination():
    request = choose_request()
    flow, reply, ctx, engine = run_plan(request, *texts_for(request, wanted=3))
    assert names_of_steps(ctx) == ["select", "brainstorm", "decide", "plan", "advance_aim", "advance_pressure"] and engine.calls == 6
    planned = engine.prompts[3]
    section = planned.split("## The idea for this chapter\n")[1].split("## Your task")[0]
    assert section.startswith("Idea 1\n") and "a third thing" in section and "a first thing" not in section and "a second thing" not in section
    assert "Option 3" not in section and "Combination 3" not in planned and "Combination 2" not in planned          # the numbers it had are gone
    assert "## The combination\n" in planned and "Combination 1" in planned and "## The three combinations" not in planned
    assert "Three ideas for this chapter" not in planned and "Choose one idea" not in planned
    assert "The idea above is the one chosen for this chapter, and it belongs to the combination above" in planned and "Begin your reply with idea: 1" in planned
    assert "## The options to judge" in engine.prompts[2] and all(t in engine.prompts[2] for t in ("a first thing", "a second thing", "a third thing"))


def test_the_timeline_records_the_picked_options_own_tie_and_rule_or_object_not_the_first_ones():
    request = choose_request()
    _, decided, ctx, _ = run_plan(request, *texts_for(request, wanted=3))
    undecided_texts = plan.script(request, Kit(request))
    beat = json.loads(undecided_texts[2]); beat["idea"] = 3
    undecided_texts[2] = everyone(request, json.dumps(beat))           # the same plan, said to build on combination 3 of the three shown
    _, third, _, _ = run_plan(request, *undecided_texts)
    first_texts = plan.script(request, Kit(request))
    first_texts[2] = everyone(request, first_texts[2])
    _, first, _, _ = run_plan(request, *first_texts)
    assert decided["picked"] == third["picked"] != first["picked"]
    notes = ctx.notes["flow"]
    assert (notes["decide"], notes["decide_options"], notes["decide_pick"], notes["decide_combo"]) == ("on", 3, 3, 3)
    assert sorted(int(n) for n in notes["decide_order"].split("-")) == [1, 2, 3]


def test_the_plan_reply_schema_is_unchanged_and_any_idea_number_it_allows_is_the_one_idea_shown():
    request = choose_request()
    flow, _, _, _ = run_plan(request, *texts_for(request, wanted=2))
    step = flow._step()
    assert step.grammar["properties"]["idea"]["enum"] == [1, 2, 3]
    for idea in (1, 2, 3):
        assert flow._combo_of({"idea": idea}) is flow._shown[0]
    assert flow._combo_of({"idea": 4}) is None and flow._combo_of({"idea": True}) is None and flow._combo_of({}) is None
    _, reply, _, engine = run_plan(request, *texts_for(request, wanted=2, idea=2))        # a plan that says idea 2 is not refused, and records the pick
    assert engine.calls == 6 and reply["picked"] == run_plan(request, *texts_for(request, wanted=2, idea=1))[1]["picked"]


def test_without_choose_the_plan_is_told_to_build_on_the_one_idea_and_not_to_choose_among_ideas():
    request = base()
    flow, reply, ctx, engine = run_plan(request, *texts_for(request, wanted=2))
    assert names_of_steps(ctx) == ["brainstorm", "decide", "plan", "advance_aim"] and engine.calls == 4
    planned = engine.prompts[2]
    assert "Idea 1\n" in planned and "a second thing" in planned and "a first thing" not in planned and "a third thing" not in planned
    assert "The idea above is the one chosen for this chapter. Build the plan on it" in planned and "combine two" not in planned
    assert "Begin your reply with idea_use: one sentence that says what you take from the idea" in planned and "picked" not in reply
    assert ctx.notes["flow"]["decide_combo"] == 2 and ctx.notes["flow"]["decide_pick"] == 2


def test_a_decider_reply_that_cannot_be_used_falls_back_to_the_first_option_and_the_notes_say_so():
    request = choose_request()
    texts = texts_for(request, wanted=3)
    broken = texts[:2] + ["not json", "still not json"] + texts[3:]
    flow, reply, ctx, engine = run_plan(request, *broken)
    assert engine.calls == 7 and names_of_steps(ctx) == ["select", "brainstorm", "decide", "plan", "advance_aim", "advance_pressure"]      # decide took two attempts
    planned = engine.prompts[4]
    assert "a first thing" in planned.split("## The idea for this chapter\n")[1].split("## Your task")[0] and "a third thing" not in planned.split("## Your task")[0].split("## The idea")[1]
    notes = ctx.notes["flow"]
    assert (notes["decide"], notes["decide_pick"], notes["decide_combo"]) == ("fallback", 1, 1)
    assert reply["picked"] == run_plan(request, *first_texts_of(request))[1]["picked"]        # the first option is what planning did before the decider


def test_the_decider_is_off_when_the_flag_is_off_and_the_plan_carries_the_whole_brainstorm_as_before(monkeypatch):
    monkeypatch.setattr(decide, "ON", False)
    request = choose_request()
    texts = plan.script(request, Kit(request))
    texts[1] = BRAINSTORM
    flow, reply, ctx, engine = run_plan(request, *texts)
    assert names_of_steps(ctx) == ["select", "brainstorm", "plan", "advance_aim", "advance_pressure"] and "decide" not in ctx.notes["flow"]
    assert "## Three ideas for this chapter" in engine.prompts[2] and "a first thing" in engine.prompts[2] and "a third thing" in engine.prompts[2]
    assert "decide" not in [s.name for s in flow.worst_case()]


def test_fewer_than_two_options_or_a_combination_that_does_not_exist_keeps_the_flow_as_it_was_and_notes_none():
    request = choose_request()
    texts = plan.script(request, Kit(request))                                           # the scripted brainstorm is one paragraph: one option at most
    flow, _, ctx, engine = run_plan(request, *texts)
    assert "decide" not in names_of_steps(ctx) and ctx.notes["flow"]["decide"] == "none" and "Three ideas for this chapter" in engine.prompts[2]
    texts[1] = BRAINSTORM.replace("Combination 3", "Combination 4")                         # the select step made three combinations: there is no fourth
    _, _, ctx, engine = run_plan(request, *texts)
    assert "decide" not in names_of_steps(ctx) and ctx.notes["flow"]["decide"] == "none" and engine.calls == 5


def test_a_brainstorm_cut_off_by_the_token_cap_is_judged_on_its_whole_options_only():
    cut = BRAINSTORM + "\n**Option 4: Fourth (Combination 1)**\nThe protagonist wants a fourth thing and"
    request = base()
    texts = texts_for(request, wanted=2)
    texts[0] = cut
    flow, _, ctx, engine = run_plan(request, *texts)
    assert ctx.notes["flow"]["decide_options"] == 3 and "fourth thing" not in engine.prompts[1]
