"""The decider: the decide step between the brainstorm and the plan, in the real plan flow on the fake engine. The plan is then
built on the one option the decider picked (the option with the highest total of best and worst marks), shown as idea 1 with its own combination; the plan reply's schema is unchanged. Neutral placeholder
text throughout. No model."""
import json

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

from test_select import base, choose_request, names_of_steps, run_plan  # noqa: E402

from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter.mill import advance, decide, plan  # noqa: E402
from pulpermill.prompter.mill.common import load_text  # noqa: E402

BRAINSTORM = ("Here are the options for this chapter.\n\n"
              "**Option 1: First (Combination 1)**\nThe protagonist wants a first thing. A says no, and the two clash at the first place.\n\n"
              "**Option 2: Second (Combination 2)**\nThe protagonist wants a second thing. B says no, and the two clash at the second place.\n\n"
              "**Option 3: Third (Combination 3)**\nThe protagonist wants a third thing. C says no, and the two clash at the third place.\n")
OPTIONS = decide.parse_options(BRAINSTORM)


def reply_for(request: dict, wanted: int) -> str:
    """A decider reply in which the option that stood at place `wanted` (from 1) in the brainstorm is best on every criterion and another is worst,
    whatever letter the shuffle gave them."""
    order = decide.order_of(OPTIONS, request)
    letters = decide.LABELS[:len(OPTIONS)]
    best = letters[order.index(wanted - 1)]
    worst = next(letter for letter in letters if letter != best)
    return json.dumps({k: {"held": f"Held {k}.", **{letter: f"Phrase {k} {letter}." for letter in letters}, "best": best, "worst": worst} for k in decide.criteria_for(request)})


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


def test_a_decider_reply_that_cannot_be_used_falls_back_to_a_random_option_and_the_notes_say_so(monkeypatch):
    monkeypatch.setattr(decide.random, "choice", lambda seq: min(seq))           # the random option is the one at the lowest place, so the test can say which
    request = choose_request()
    texts = texts_for(request, wanted=3)
    broken = texts[:2] + ["not json", "still not json"] + texts[3:]
    flow, reply, ctx, engine = run_plan(request, *broken)
    assert engine.calls == 7 and names_of_steps(ctx) == ["select", "brainstorm", "decide", "plan", "advance_aim", "advance_pressure"]      # decide took two attempts
    planned = engine.prompts[4]
    assert "a first thing" in planned.split("## The idea for this chapter\n")[1].split("## Your task")[0] and "a third thing" not in planned.split("## Your task")[0].split("## The idea")[1]
    notes = ctx.notes["flow"]
    assert (notes["decide"], notes["decide_pick"], notes["decide_combo"]) == ("fallback", 1, 1)
    assert reply["picked"] == run_plan(request, *first_texts_of(request))[1]["picked"]        # the same plan as one built on the first option


def test_the_picked_option_is_the_one_with_the_best_marks_and_the_run_notes_carry_the_totals_and_marks(monkeypatch):
    request = base()
    flow, _, ctx, _ = run_plan(request, *texts_for(request, wanted=2))
    notes = ctx.notes["flow"]
    assert (notes["decide"], notes["decide_pick"], notes["decide_tied"], notes["decide_sampling"]) == ("on", 2, 1, "structured")
    assert notes["decide_s2"] == 1 and notes["decide_s1"] + notes["decide_s2"] + notes["decide_s3"] == 0         # best on the one criterion; one other option is worst on it
    for criterion in decide.criteria_for(request):
        best, worst = notes[f"decide_{criterion}_best"], notes[f"decide_{criterion}_worst"]
        assert best.endswith("2") and best[0] in "ABC" and worst[0] in "ABC" and worst[0] != best[0]       # the best of every criterion is the option at place 2


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
    wrong = BRAINSTORM.replace("Combination 3", "Combination 4")                            # the select step made three combinations: there is no fourth
    no_use = {k: v for k, v in json.loads(texts[2]).items() if k != plan.IDEA_USE}          # no brainstorm: the plan grammar has no `idea_use`
    texts[1:3] = [wrong, wrong, json.dumps(no_use)]                                          # the count check refuses it twice, so the plan goes ahead without a brainstorm
    _, _, ctx, engine = run_plan(request, *texts)
    assert "decide" not in names_of_steps(ctx) and ctx.notes["flow"]["decide"] == "none" and ctx.notes["flow"]["brainstorm_fallback"] is True and engine.calls == 6


def test_a_brainstorm_cut_off_by_the_token_cap_is_judged_on_its_whole_options_only():
    cut = BRAINSTORM + "\n**Option 4: Fourth (Combination 1)**\nThe protagonist wants a fourth thing and"
    request = base()
    texts = texts_for(request, wanted=2)
    texts[0] = cut
    flow, _, ctx, engine = run_plan(request, *texts)
    assert ctx.notes["flow"]["decide_options"] == 3 and "fourth thing" not in engine.prompts[1]


def test_in_choose_mode_the_decide_prompt_shows_each_option_with_its_combination_and_plain_mode_does_not():
    request = choose_request()
    flow, _, ctx, engine = run_plan(request, *texts_for(request, wanted=1))
    prompt = engine.prompts[2]
    section = prompt.split("## The options to judge\n")[1].split("## Your task")[0]
    assert section.count("It is built on:") == 3 and section.count("How they may collide:") == 3 and "combination" not in section.lower()
    assert all(c["tie_words"] in section for c in flow.combos) and "## The tie in the spotlight" not in prompt
    assert "Under each option you see the tie and the rule or object it is built on" in prompt
    plain = base()
    _, _, _, plain_engine = run_plan(plain, *texts_for(plain, wanted=1))
    assert "It is built on:" not in plain_engine.prompts[1] and "Under each option you see" not in plain_engine.prompts[1]


def test_the_worst_case_decide_step_carries_the_longest_combinations():
    from pulpermill.prompter.mill import select
    request = choose_request()
    steps = plan.build_flow(request, Kit(request)).worst_case()
    assert [s.name for s in steps][:3] == ["select", "brainstorm", "decide"]
    text = steps[2].text(1.0)
    assert text.count("It is built on:") == 3 and text.count("How they may collide: " + select.REASON_STAND_IN.strip()) == 3      # the longest reason of each combination


@pytest.mark.parametrize("wanted", (1, 2, 3))
def test_the_plan_prompt_after_a_decision_says_the_picked_ideas_outcome_stands_for_every_position(wanted):
    w = load_text("plan")
    for request in (base(), choose_request()):
        at = 2 if request.get("choose") else 1
        flow, reply, ctx, engine = run_plan(request, *texts_for(request, wanted=wanted))
        planned = engine.prompts[at + 1]
        assert ctx.notes["flow"]["decide_pick"] == wanted
        for number, key in ((1, "outcome_reached"), (2, "outcome_lost"), (3, "outcome_gave_up")):
            assert (w[key] in planned) == (number == wanted), (wanted, key)
        assert "how it ends" in planned


def test_a_flow_without_the_decider_adds_no_outcome_line(monkeypatch):
    monkeypatch.setattr(decide, "ON", False)
    request = choose_request()
    texts = plan.script(request, Kit(request))
    texts[1] = BRAINSTORM
    flow, reply, ctx, engine = run_plan(request, *texts)
    w = load_text("plan")
    assert not any(w[key] in engine.prompts[2] for key in ("outcome_reached", "outcome_lost", "outcome_gave_up"))


@pytest.mark.parametrize("wanted", (1, 2, 3))
def test_the_plan_reply_carries_the_planned_outcome_of_the_picked_option_for_every_position(wanted):
    for request in (base(), choose_request()):
        flow, reply, ctx, engine = run_plan(request, *texts_for(request, wanted=wanted))
        assert reply["outcome"] == {1: "reached", 2: "lost", 3: "gave_up"}[wanted]


def test_without_the_decider_the_outcome_follows_the_idea_number_in_choose_mode_only(monkeypatch):
    monkeypatch.setattr(decide, "ON", False)
    request = choose_request()
    texts = plan.script(request, Kit(request))
    texts[1] = BRAINSTORM
    flow, reply, ctx, engine = run_plan(request, *texts)
    assert reply["outcome"] == "reached"             # the scripted plan names idea 1
    request = base()
    flow, reply, ctx, engine = run_plan(request, *plan.script(request, Kit(request)))
    assert "outcome" not in reply                    # no idea number, so nothing fixes the ending


# ---- the aim gate ----------------------------------------------------------------------------------------------------------

GATE_LINE = load_text("plan")["problems"]["aim_same_obstacle"]
SECOND_AIM = "Reach place_b with item_b before deadline_b."


def aim_verdict(link: str, new_obstacle: str) -> str:
    return json.dumps({"reason": "Reason.", "link": link, "new_obstacle": new_obstacle})


def gate_run(link: str, new_obstacle: str, again=("drifts", "yes")):
    """A chapter-2 plain plan flow whose aim judge says (link, new_obstacle); a second plan with a different aim and a second verdict are scripted too,
    and are used only when the gate asks for them."""
    request = base()
    texts = texts_for(request, wanted=2)
    first = json.loads(texts[2])
    second = everyone(request, json.dumps({**first, "aim": SECOND_AIM}))
    return (request, *run_plan(request, *texts[:3], aim_verdict(link, new_obstacle), second, aim_verdict(*again)))


@pytest.mark.parametrize("link,new_obstacle,gated", [("continues", "no", True), ("continues", "yes", False), ("drifts", "no", False), ("drifts", "yes", False)])
def test_the_aim_gate_reads_only_the_two_labels(link, new_obstacle, gated):
    assert advance.aim_gate({"link": link, "new_obstacle": new_obstacle}) is gated
    for unreadable in (None, {}, {"link": "continues"}, {"link": "continues", "new_obstacle": "maybe"}, "continues"):
        assert advance.aim_gate(unreadable) is False


def test_a_continuing_aim_with_no_new_obstacle_sends_the_plan_back_once_with_the_gate_line():
    request, flow, reply, ctx, engine = gate_run("continues", "no")
    assert names_of_steps(ctx) == ["brainstorm", "decide", "plan", "advance_aim", "plan", "advance_aim"] and engine.calls == 6
    assert GATE_LINE not in engine.prompts[2] and GATE_LINE in engine.prompts[4] and load_text("plan")["retry_close"] in engine.prompts[4]
    assert reply["beat"]["aim"] == SECOND_AIM and ctx.notes["flow"]["aim_replanned"] is True
    assert ctx.notes["flow"]["aim_link"] == "drifts"                       # the second verdict is the one recorded


def test_the_second_verdict_is_accepted_whatever_it_says_and_the_plan_is_never_made_a_third_time():
    request, flow, reply, ctx, engine = gate_run("continues", "no", again=("continues", "no"))
    assert names_of_steps(ctx) == ["brainstorm", "decide", "plan", "advance_aim", "plan", "advance_aim"] and engine.calls == 6
    assert reply["beat"]["aim"] == SECOND_AIM and ctx.notes["flow"]["aim_new"] == "no"


@pytest.mark.parametrize("link,new_obstacle", [("continues", "yes"), ("drifts", "no"), ("drifts", "yes")])
def test_any_other_verdict_leaves_the_plan_alone(link, new_obstacle):
    request, flow, reply, ctx, engine = gate_run(link, new_obstacle)
    assert names_of_steps(ctx) == ["brainstorm", "decide", "plan", "advance_aim"] and engine.calls == 4
    assert "aim_replanned" not in ctx.notes["flow"] and reply["beat"]["aim"] != SECOND_AIM


def test_the_first_chapter_has_no_aim_judge_and_so_no_gate():
    request = base()
    request["chapter"], request["earlier_beats"], request["earlier_events"] = 1, [], []
    flow, reply, ctx, engine = run_plan(request, *texts_for(request, wanted=2))
    assert "advance_aim" not in names_of_steps(ctx) and "aim_replanned" not in ctx.notes["flow"]


def test_the_gate_works_with_a_pressure_judge_after_it_and_in_choose_mode():
    request = choose_request()
    texts = texts_for(request, wanted=2)
    at = 2
    second = everyone(request, json.dumps({**json.loads(texts[at + 1]), "aim": SECOND_AIM}))
    pressure = texts[-1]
    flow, reply, ctx, engine = run_plan(request, *texts[:at + 2], aim_verdict("continues", "no"), second, aim_verdict("drifts", "yes"), pressure)
    assert names_of_steps(ctx) == ["select", "brainstorm", "decide", "plan", "advance_aim", "plan", "advance_aim", "advance_pressure"]
    assert reply["beat"]["aim"] == SECOND_AIM and reply["outcome"] == "lost" and "picked" in reply
    assert SECOND_AIM in engine.prompts[7]                                  # the pressure judge reads the plan that stands
