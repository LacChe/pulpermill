"""Repeat avoidance, step 3 (Plan 7): the gate on the brainstorm's ideas. One label call over the three ideas, each idea screened against the labelled earlier
chapters, ideas that match too much dropped, and the decider judging the survivors only (three, two, or one chosen without a call). The real flow on the
fake engine; neutral placeholder text; no model."""
import json

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

from test_decide_flow import BRAINSTORM, OPTIONS, everyone  # noqa: E402
from test_label_flow import chaptered  # noqa: E402
from test_select import base, choose_request, names_of_steps, run_plan  # noqa: E402

from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter.mill import decide, plan, repeat  # noqa: E402
from pulpermill.prompter.mill.common import ENDINGS, load_text  # noqa: E402

COMPARED = ("aim_kind", "obstacle_source", "obstacle_party", "turning_kind", "closing_hook", "motive_kind")        # the six an idea can match (its outcome is set by its number)


def earlier_print(request: dict) -> dict:
    return {"aim_kind": "obtain", "obstacle_source": "person", "obstacle_party": plan.label_names(request)[0], "turning_kind": "refusal",
            "outcome": "other", "closing_hook": "new_task", "motive_kind": "recognition", "turning_note": "A door stays shut."}


def earlier_reply(request: dict) -> str:
    """The label reply for the earlier chapters: every chapter has the same fingerprint, and its outcome says nothing, so it never matches."""
    return json.dumps({"prints": [{"n": n, **earlier_print(request)} for n, _ in plan.label_items(request)]})


def idea_entry(request: dict, n: int, matching: int) -> dict:
    """An idea's label entry that matches the earlier chapters on its first `matching` fields of COMPARED and says `other` (or `none`) on the rest."""
    mine = earlier_print(request)
    out = {"n": n, "turning_note": "An idea.", "outcome": "other"}
    for i, key in enumerate(COMPARED):
        out[key] = mine[key] if i < matching else ("none" if key == "obstacle_party" else "other")
    return out


def gate_reply(request: dict, *matching: int) -> str:
    return json.dumps({"prints": [idea_entry(request, n, m) for n, m in enumerate(matching, 1)]})


def decide_reply(request: dict, survivors: list[tuple[int, str]], wanted_place: int, places: list[int]) -> str:
    """The decider's reply when `survivors` are judged: the option at brainstorm place `wanted_place` is best on every criterion, another is worst."""
    order = decide.order_of(survivors, request)
    letters = decide.LABELS[:len(survivors)]
    best = letters[order.index(places.index(wanted_place))]
    worst = next(letter for letter in letters if letter != best)
    return json.dumps({k: {"held": f"Held {k}.", **{letter: f"Phrase {k} {letter}." for letter in letters}, "best": best, "worst": worst} for k in decide.criteria_for(request)})


def run(request: dict, matching: tuple[int, ...], wanted: int | None = None, gate: str | None = None):
    """A whole call: the label step over the earlier chapters, the brainstorm of three options, the gate's labels, the decider (when two or more ideas are
    left; `wanted` is the place it picks), the plan. `matching` is how many labels each idea shares with the earlier chapters (or `gate` is the label reply as written, and `matching` says how
    many labels each idea is meant to share, so the scripted decider fits the survivors)."""
    texts = plan.script(request, Kit(request))
    at = (1 if request.get("choose") else 0) + 1                    # the brainstorm's place in the scripted texts
    beat = json.loads(texts[at + 1])
    if "idea" in beat:
        beat["idea"] = 1
    dropped = [p for p, m in enumerate(matching, 1) if m >= repeat.T]
    alive = [p for p in (1, 2, 3) if p not in dropped] or [min((1, 2, 3), key=lambda p: (matching[p - 1], p))]
    middle = [BRAINSTORM, gate or gate_reply(request, *matching)]
    if len(alive) >= 2:
        middle.append(decide_reply(request, [OPTIONS[p - 1] for p in alive], wanted or alive[0], alive))
    all_texts = texts[:at - 1] + [earlier_reply(request)] + middle + [everyone(request, json.dumps(beat))] + texts[at + 2:]
    return run_plan(request, *all_texts) + (all_texts,)


def decide_prompt(engine) -> str:
    return next(p for p in engine.prompts if "## The options to judge" in p)


# ---- three survivors ---------------------------------------------------------------------------------------------------------------

def test_three_survivors_run_the_decider_on_all_three_and_the_notes_carry_the_matches():
    request = chaptered(base())
    flow, reply, ctx, engine, texts = run(request, (1, 2, 3), wanted=2)
    assert names_of_steps(ctx)[:5] == ["label", "brainstorm", "label", "decide", "plan"] and engine.calls == len(texts)
    notes = ctx.notes["flow"]
    assert notes["repeat"] == "on" and (notes["repeat_m1"], notes["repeat_m2"], notes["repeat_m3"]) == (1, 2, 3) and notes["repeat_dropped"] == 0 and notes["repeat_avoid"] is False
    assert notes["decide"] == "on" and notes["decide_options"] == 3 and notes["decide_pick"] == 2 and reply["outcome"] == ENDINGS[2]
    assert all(t in decide_prompt(engine) for t in ("a first thing", "a second thing", "a third thing")) and flow.avoid_fields == []
    assert load_text("plan")["avoid_line"][:30] not in engine.prompts[-1]


def test_the_gate_labels_the_three_ideas_and_the_outcome_comes_from_the_number_not_the_model():
    request = chaptered(base())
    flow, reply, ctx, engine, texts = run(request, (1, 2, 3), wanted=1)
    prompt = engine.prompts[2]                                              # the gate's label call: after the label step and the brainstorm
    assert prompt.startswith(load_text("plan")["label_role"][:40]) and all(f"Text {n}\n" in prompt for n in (1, 2, 3))
    assert "Option 1" not in prompt and "a first thing" in prompt and "a third thing" in prompt
    assert [p["outcome"] for p in flow.earlier_prints] == ["other"] * 3


# ---- two survivors ------------------------------------------------------------------------------------------------------------------

def test_an_idea_that_matches_too_much_is_dropped_and_the_decider_sees_two_under_the_letters_a_and_b():
    request = chaptered(base())
    flow, reply, ctx, engine, texts = run(request, (5, 0, 1), wanted=3)
    shown = decide_prompt(engine)
    assert "a first thing" not in shown and "a second thing" in shown and "a third thing" in shown
    assert "Option A" in shown and "Option B" in shown and "Option C" not in shown
    notes = ctx.notes["flow"]
    assert notes["repeat_dropped"] == 1 and notes["repeat_m1"] == 5 and notes["decide_options"] == 2 and notes["decide"] == "on"
    assert notes["decide_pick"] == 3 and notes["decide_s3"] in (1, 0, -1) and "decide_s1" not in notes and sorted(notes["decide_order"].split("-")) == ["2", "3"]
    assert reply["outcome"] == ENDINGS[3] == "gave_up"                    # the third idea's own number, though it was the second one judged
    assert "a third thing" in engine.prompts[-1].split("## The idea for this chapter\n")[1].split("## Your task")[0]


def test_in_choose_mode_the_picked_ideas_own_combination_is_the_one_the_plan_carries():
    request = chaptered(choose_request())
    flow, reply, ctx, engine, texts = run(request, (5, 0, 1), wanted=3)
    assert flow.decision.position == 3 and flow.decision.combo == 3 and flow._shown == [flow.combos[2]]
    assert reply["picked"] == {"spotlight": flow.combos[2]["tie_id"], "pressure": flow.combos[2]["pressure_id"]} and reply["outcome"] == "gave_up"
    shown = decide_prompt(engine)
    assert "Option A" in shown and "Option B" in shown and "Option C" not in shown
    assert flow.combos[0]["reason"] not in shown or flow.combos[0]["reason"] == flow.combos[2]["reason"]       # the dropped idea's combination is not shown


@pytest.mark.parametrize("wanted, ending", [(2, "lost"), (3, "gave_up")])
def test_the_ending_follows_the_ideas_place_in_the_brainstorm_not_its_place_among_the_survivors(wanted, ending):
    request = chaptered(base())
    flow, reply, ctx, engine, texts = run(request, (4, 0, 0), wanted=wanted)
    assert flow.decision.position == wanted and reply["outcome"] == ending == ENDINGS[wanted]


# ---- one survivor ---------------------------------------------------------------------------------------------------------------------

def test_one_survivor_is_chosen_without_a_decider_call_and_the_notes_say_so():
    request = chaptered(base())
    flow, reply, ctx, engine, texts = run(request, (5, 6, 1))
    assert "decide" not in names_of_steps(ctx) and names_of_steps(ctx)[:4] == ["label", "brainstorm", "label", "plan"] and engine.calls == len(texts)
    notes = ctx.notes["flow"]
    assert notes["decide"] == "single" and notes["decide_pick"] == 3 and notes["decide_combo"] == 3 and notes["decide_options"] == 1 and notes["repeat_dropped"] == 2
    assert reply["outcome"] == "gave_up" and flow.avoid_fields == [] and notes["repeat_avoid"] is False
    section = engine.prompts[3].split("## The idea for this chapter\n")[1].split("## Your task")[0]
    assert section.startswith("Idea 1\n") and "a third thing" in section and "a first thing" not in section


def test_in_choose_mode_a_single_survivor_keeps_its_own_combination():
    request = chaptered(choose_request())
    flow, reply, ctx, engine, texts = run(request, (5, 5, 0))
    assert flow.decision.combo == 3 and flow._shown == [flow.combos[2]] and reply["picked"]["spotlight"] == flow.combos[2]["tie_id"]
    assert names_of_steps(ctx)[:5] == ["select", "label", "brainstorm", "label", "plan"]


# ---- every idea dropped ----------------------------------------------------------------------------------------------------------------

def test_when_every_idea_is_dropped_the_one_with_the_fewest_matches_stays_and_the_plan_must_change_what_it_shares():
    request = chaptered(base())
    flow, reply, ctx, engine, texts = run(request, (5, 4, 4))
    assert flow.decision.position == 2 and reply["outcome"] == "lost"                      # a tie between 2 and 3 goes to the lower place
    assert flow.avoid_fields == ["aim_kind", "obstacle_source", "obstacle_party", "turning_kind"]
    notes = ctx.notes["flow"]
    assert notes["repeat_avoid"] is True and notes["repeat_dropped"] == 3 and notes["decide"] == "single" and "decide" not in names_of_steps(ctx)
    prompt = engine.prompts[3]
    line = load_text("plan")["avoid_line"].format(aspects=", ".join(load_text("plan")["avoid_fields"][f] for f in flow.avoid_fields))
    assert line in prompt and "a second thing" in prompt


def test_the_avoid_line_is_in_the_plan_prompt_only_when_fields_were_kept():
    request = chaptered(base())
    flow = run(request, (5, 4, 4))[0]
    kept = plan.build_prompt(flow.request, 1.0, flow.brainstorm, None, True, 2, flow.used, flow.avoid_fields)
    assert load_text("plan")["avoid_line"][:30] in kept
    assert load_text("plan")["avoid_line"][:30] not in plan.build_prompt(flow.request, 1.0, flow.brainstorm, None, True, 2, flow.used)


# ---- the fallback, and no gate ----------------------------------------------------------------------------------------------------------

def test_a_gate_that_fails_every_attempt_lets_all_three_ideas_through_to_the_decider():
    request = chaptered(base())
    texts = plan.script(request, Kit(request))
    beat = json.loads(texts[2])
    order = decide.order_of(OPTIONS, request)
    best = decide.LABELS[order.index(1)]
    reply_text = json.dumps({k: {"held": "Held.", **{c: f"Phrase {c}." for c in "ABC"}, "best": best, "worst": decide.LABELS[order.index(0)]} for k in decide.criteria_for(request)})
    flow, reply, ctx, engine = run_plan(request, earlier_reply(request), BRAINSTORM, "not json", "still not json", reply_text, everyone(request, json.dumps(beat)), *texts[3:])
    assert names_of_steps(ctx)[:5] == ["label", "brainstorm", "label", "decide", "plan"]
    notes = ctx.notes["flow"]
    assert notes["repeat"] == "fallback" and notes["decide_options"] == 3 and "repeat_dropped" not in notes and flow.avoid_fields == []
    assert reply["outcome"] == ENDINGS[2]


def test_no_labelled_earlier_chapters_means_no_gate_and_the_flow_of_step_two():
    request = chaptered(base())
    texts = plan.script(request, Kit(request))
    flow, reply, ctx, engine = run_plan(request, "x", "y", *texts[1:])                   # the earlier chapters could not be labelled
    assert names_of_steps(ctx)[:2] == ["label", "brainstorm"] and "repeat" not in ctx.notes["flow"]
    without = base()
    plain = plan.build_flow(without, Kit(without))
    assert plain._label_items == [] and plain.next([]).name == "brainstorm"


# ---- the decider on two options (pure) -----------------------------------------------------------------------------------------------------

def test_the_decider_works_for_two_options_and_reports_the_places_of_the_brainstorm():
    options = [OPTIONS[1], OPTIONS[2]]
    order = decide.order_of(options, {"chapter": 2})
    labels = decide.LABELS[:2]
    value = {"move": {"held": "h", "A": "a", "B": "b", "best": "A", "worst": "B"}}
    assert decide.decide_problem(value, 2) is None and decide.decide_problem({"move": {**value["move"], "best": "C"}}, 2) is not None
    assert list(decide.grammar(2)["properties"]["move"]["properties"]["best"]["enum"]) == list(labels) and decide.scores(value, 2) == [1, -1]
    got = decide.decide(options, order, value, flagged=[False, False], places=[2, 3])
    assert got.position in (2, 3) and got.places == (2, 3) and got.combo == options[got.position - 2][0]
    assert sorted(got.notes()["decide_order"].split("-")) == ["2", "3"] and "decide_s1" not in got.notes()
    fell = decide.decide(options, order, {}, places=[2, 3])
    assert fell.fell_back and fell.position in (2, 3) and fell.notes()["decide"] == "fallback"


def test_the_invented_flags_count_only_the_options_judged():
    only = decide.only([OPTIONS[2]], 0, [3], [True])                  # the third idea alone, flagged for naming a person on no card
    assert only.position == 3 and only.combo == OPTIONS[2][0] and only.single and only.invented == 1
    assert only.notes()["decide"] == "single" and only.notes()["decide_pick"] == 3 and only.notes()["decide_s3"] == 0
    assert decide.only(OPTIONS, 1).position == 2 and decide.only(OPTIONS, 1).places == (2,)


# ---- Plan 9 step 3: the motive joins the count -----------------------------------------------------------------------------------

def test_an_idea_that_repeats_the_motive_and_three_other_fields_is_dropped_at_t_four_and_without_the_motive_it_stays():
    assert repeat.T == 4 and len(repeat.FIELDS) == 7
    request = chaptered(base())
    with_motive = idea_entry(request, 1, 3)                                  # aim_kind, obstacle_source, obstacle_party
    with_motive["motive_kind"] = earlier_print(request)["motive_kind"]       # and the earlier chapters' motive: four in all
    gate = json.dumps({"prints": [with_motive, idea_entry(request, 2, 3), idea_entry(request, 3, 3)]})
    flow, reply, ctx, engine, texts = run(request, (4, 3, 3), gate=gate)
    notes = ctx.notes["flow"]
    assert (notes["repeat_m1"], notes["repeat_m2"], notes["repeat_m3"]) == (4, 3, 3) and notes["repeat_dropped"] == 1 and flow._alive == [1, 2]
    assert notes["repeat_threshold"] == "4 of 7" and notes["repeat_avoid"] is False
    assert "decide" in names_of_steps(ctx)                                    # the other two ideas go to the decider


def test_when_every_idea_is_dropped_the_motive_is_one_of_the_aspects_the_plan_must_change():
    request = chaptered(base())
    gate = json.dumps({"prints": [{**idea_entry(request, n, 4), "motive_kind": earlier_print(request)["motive_kind"]} for n in (1, 2, 3)]})
    flow, reply, ctx, engine, texts = run(request, (5, 5, 5), gate=gate)
    assert flow.avoid_fields[-1] == "motive_kind" and ctx.notes["flow"]["repeat_avoid"] is True
    assert load_text("plan")["avoid_fields"]["motive_kind"] in engine.prompts[3]
