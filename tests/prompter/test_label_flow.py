"""Repeat avoidance, step 2 (Plan 7): the label step over the earlier chapters, the "already used" table in the brainstorm and plan prompts, and
the flow around them. The real flow on the fake engine; neutral placeholder text; no model."""
import json

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

from test_decide_flow import BRAINSTORM, everyone, reply_for  # noqa: E402
from test_select import base, choose_request, names_of_steps, run_plan, with_events  # noqa: E402

from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter.mill import plan, repeat  # noqa: E402
from pulpermill.prompter.mill.common import load_text  # noqa: E402

EVENTS = [{"chapter": n, "happened": f"Things happened in chapter {n}.", "changed": f"Ending number {n}"} for n in (1, 2, 3, 4, 5)]


def chaptered(request: dict, last: int = 6, events=EVENTS) -> dict:
    """A request for chapter `last` with earlier events for the chapters before it and a beat with an aim for each."""
    earlier = [e for e in events if e["chapter"] < last]
    beats = [{"chapter": e["chapter"], "where": "The Quay", "when": "Morning", "aim": f"Chase number {e['chapter']} across the harbour", "plan": "x"} for e in earlier]
    return {**request, "chapter": last, "chapter_count": max(last + 2, 8), "earlier_events": earlier, "earlier_beats": beats}


def prints_reply(chapters, **over) -> str:
    entry = {"turning_note": "A door stays shut.", "aim_kind": "obtain", "obstacle_source": "person", "obstacle_party": "none", "turning_kind": "refusal",
             "outcome": "lost", "closing_hook": "new_task", "motive_kind": "recognition", **over}
    return json.dumps({"prints": [{"n": n, **entry} for n in chapters]})


def run_with(request: dict, *texts):
    return run_plan(request, *texts)


# ---- the step ---------------------------------------------------------------------------------------------------------------------

def test_no_earlier_events_means_no_label_step_and_chapter_one_neither():
    request = base()
    assert plan.label_items(request) == [] and plan.build_flow(request, Kit(request)).next([]).name == "brainstorm"
    first = {**with_events(base()), "chapter": 1, "earlier_beats": [], "earlier_events": with_events(base())["earlier_events"]}
    assert plan.label_items(first) == []                    # events of chapters before this one only


def test_the_label_step_describes_the_last_k_earlier_chapters_each_by_its_number():
    request = chaptered(base())
    assert [n for n, _ in plan.label_items(request)] == [3, 4, 5]
    assert plan.label_items(request)[0][1] == "Things happened in chapter 3. Ending number 3.\nThe aim the chapter was planned around: Chase number 3 across the harbour."
    flow = plan.build_flow(request, Kit(request))
    step = flow.next([])
    assert step.name == "label" and step.kind == "json" and step.attempts <= 2 and step.fallback() == {}
    assert "Text 3\nThings happened in chapter 3." in step.text(1.0) and "Text 5\n" in step.text(1.0) and "Text 2\n" not in step.text(1.0)


def test_the_names_list_is_the_cast_the_groups_the_rules_and_the_objects_in_words():
    request = base()
    names = plan.label_names(request)
    cast = [c["name"] for c in request["cast"]]
    assert set(cast) <= set(names) and len(names) == len(set(names))
    world = request["world"]
    assert all(g["name"] in names for g in world.get("powers", [])) and all(o["name"] in names for o in world.get("objects", []))
    assert all(x["statement"].rstrip(".!?")[:plan.NAME_MAX].strip() in names for x in world.get("rules", []))
    assert all(not n.endswith((".", "!", "?")) for n in names)


# ---- the flow ---------------------------------------------------------------------------------------------------------------------

def test_the_flow_runs_label_then_brainstorm_then_plan_and_the_reply_is_the_plan():
    request = chaptered(base())
    texts = plan.script(request, Kit(request))
    flow, reply, ctx, engine = run_with(request, *texts)
    assert names_of_steps(ctx)[:3] == ["label", "brainstorm", "plan"] and engine.calls == len(texts)
    assert reply["beat"]["plan"] == json.loads(texts[2])["plan"] and "idea_use" not in reply["beat"]
    assert ctx.notes["flow"]["label"] == "on" and ctx.notes["flow"]["label_chapters"] == 3
    assert [r["chapter"] for r in flow.used] == [3, 4, 5] and len(flow.earlier_prints) == 3


def test_choose_mode_runs_select_then_label_then_brainstorm_and_results_stay_aligned():
    request = chaptered(choose_request())
    texts = plan.script(request, Kit(request))
    flow, reply, ctx, engine = run_with(request, *texts)
    assert names_of_steps(ctx)[:4] == ["select", "label", "brainstorm", "plan"] and engine.calls == len(texts)
    assert reply["picked"]["spotlight"] and ctx.notes["flow"]["select"] == "on" and ctx.notes["flow"]["label_chapters"] == 3
    assert [s.name for s in flow.worst_case()][:3] == ["select", "label", "brainstorm"]


def decided_texts(request: dict, wanted: int = 2) -> list[str]:
    """A scripted call with a label reply, a brainstorm of three options on lines, the decider's reply and the plan."""
    texts = plan.script(request, Kit(request))
    at = 1 if request.get("choose") else 0
    beat = json.loads(texts[at + 2])
    if "idea" in beat:
        beat["idea"] = 1
    gate = prints_reply([1, 2, 3], aim_kind="other", obstacle_source="other", turning_kind="other", closing_hook="other", motive_kind="other")       # no idea repeats anything
    return texts[:at + 1] + [BRAINSTORM, gate, reply_for(request, wanted), everyone(request, json.dumps(beat))] + texts[at + 3:]


def test_with_the_decider_the_results_after_the_label_step_stay_aligned():
    for request in (chaptered(base()), chaptered(choose_request())):
        texts = decided_texts(request)
        flow, reply, ctx, engine = run_with(request, *texts)
        order = names_of_steps(ctx)
        assert order.count("label") == 2 and order.index("label") < order.index("brainstorm")
        assert [n for n in order if n in ("label", "brainstorm", "decide", "plan")][1:5] == ["brainstorm", "label", "decide", "plan"] and engine.calls == len(texts)
        assert reply["outcome"] == "lost" and flow.decision is not None and flow.decision.position == 2


# ---- the fallback ---------------------------------------------------------------------------------------------------------------------

def test_a_label_step_that_fails_every_attempt_leaves_no_table_and_never_fails_the_call():
    request = chaptered(base())
    texts = plan.script(request, Kit(request))
    flow, reply, ctx, engine = run_with(request, "not json", "still not json", *texts[1:])
    assert names_of_steps(ctx)[:3] == ["label", "brainstorm", "plan"] and engine.calls == len(texts) + 1
    assert flow.used == [] and flow.earlier_prints == [None, None, None] and ctx.notes["flow"]["label"] == "fallback" and ctx.notes["flow"]["label_chapters"] == 0
    assert reply["beat"]["plan"] and all(load_text("plan")["used_lead"] not in p for p in engine.prompts[2:])         # no table in the brainstorm or the plan
    assert load_text("plan")["brainstorm_used"] not in engine.prompts[2]


def test_a_reply_with_the_wrong_number_of_entries_is_refused_and_asked_again():
    request = chaptered(base())
    texts = plan.script(request, Kit(request))
    flow, reply, ctx, engine = run_with(request, prints_reply([3]), *texts)
    assert names_of_steps(ctx)[:3] == ["label", "brainstorm", "plan"] and engine.calls == len(texts) + 1       # the retry is inside the step
    assert "exactly 3 entries" in engine.prompts[1] and len(flow.used) == 3 and ctx.notes["flow"]["label"] == "on"


# ---- the table --------------------------------------------------------------------------------------------------------------------

def table_lines(prompt: str) -> list[str]:
    block = prompt.split(load_text("plan")["used_lead"] + "\n", 1)[1]
    return [line for line in block.split("\n\n")[0].split("\n") if line.startswith("Chapter ")]


def test_the_table_has_one_line_per_labelled_chapter_after_the_running_aim_in_both_prompts():
    request = chaptered(base())
    used = [{"chapter": n, **repeat.clean({"aim_kind": "keep", "obstacle_source": "group", "obstacle_party": "Marit", "turning_kind": "bargain", "outcome": "gave_up",
                                           "closing_hook": "new_task", "turning_note": f"Note {n}."}, ["Marit"])} for n in (3, 4, 5)]
    for prompt in (plan.build_brainstorm_prompt(request, 1.0, None, used), plan.build_prompt(request, 1.0, "", None, False, 0, used)):
        lines = table_lines(prompt)
        assert lines == [f"Chapter {n}: aim: keep; in the way: group (Marit); turning point: bargain; ended: gave up; left standing: new task. Note {n}." for n in (3, 4, 5)]
        assert prompt.index("Where the aim stands now") < prompt.index(load_text("plan")["used_lead"]) < prompt.index("## Your task")
    assert "(Marit)" not in plan.used_text([{**used[0], "obstacle_party": "none"}], load_text("plan"))


def test_the_brainstorm_asks_for_a_different_kind_only_when_the_table_is_shown():
    request = chaptered(base())
    used = [{"chapter": 5, **repeat.clean({}, [])}]
    rule = load_text("plan")["brainstorm_used"]
    assert rule in plan.build_brainstorm_prompt(request, 1.0, None, used)
    assert rule not in plan.build_brainstorm_prompt(request, 1.0, None, None) and rule not in plan.build_brainstorm_prompt(request, 1.0)
    first = {**request, "chapter": 1, "earlier_beats": [], "earlier_events": []}
    assert rule not in plan.build_brainstorm_prompt(first, 1.0, None, used)              # the rule is for chapter 2 and later
    assert load_text("plan")["used_lead"][:20] not in plan.build_prompt(request)


def test_a_squeeze_drops_the_table_and_its_rule_first_of_all():
    request = chaptered(base())
    used = [{"chapter": 5, **repeat.clean({}, [])}]
    squeezed = plan.build_brainstorm_prompt(request, 0.99, None, used)
    assert load_text("plan")["used_lead"] not in squeezed and load_text("plan")["brainstorm_used"] not in squeezed
    assert plan.build_brainstorm_prompt(request, 0.99, None, None) == squeezed
    assert load_text("plan")["used_lead"] not in plan.build_prompt(request, 0.99, "", None, False, 0, used)
    assert load_text("plan")["used_lead"] in plan.build_prompt(request, 1.0, "", None, False, 0, used)


def test_the_flow_shows_the_labelled_chapters_in_the_brainstorm_and_plan_prompts_it_sends():
    request = chaptered(base())
    texts = plan.script(request, Kit(request))
    flow, reply, ctx, engine = run_with(request, *texts)
    brainstorm_prompt, plan_prompt = engine.prompts[1], engine.prompts[2]
    for prompt in (brainstorm_prompt, plan_prompt):
        assert [line.split(":")[0] for line in table_lines(prompt)] == ["Chapter 3", "Chapter 4", "Chapter 5"]
        assert "turning point: refusal" in prompt and "Chapter 3 turns on a refusal at the door." in prompt
    assert load_text("plan")["brainstorm_used"] in brainstorm_prompt and load_text("plan")["brainstorm_used"] not in plan_prompt
    assert load_text("plan")["used_lead"] not in engine.prompts[0]          # the labeler does not see the table


# ---- the worst case and the script ------------------------------------------------------------------------------------------------------

def test_the_worst_case_counts_the_label_step_and_the_longest_table():
    request = chaptered(base())
    flow = plan.build_flow(request, Kit(request))
    steps = flow.worst_case()
    assert [s.name for s in steps] == ["label", "brainstorm", "label", "decide", "plan"]
    plain = plan.build_flow({**request, "earlier_events": []}, Kit(request)).worst_case()
    assert [s.name for s in plain] == ["brainstorm", "decide", "plan"]
    assert len(steps[1].text(1.0)) > len(plain[0].text(1.0)) and len(steps[4].text(1.0)) > len(plain[2].text(1.0))
    assert len(steps[0].text(1.0)) > repeat.TEXT_LIMIT


def test_the_script_has_a_valid_label_reply_for_each_chapter_the_step_describes():
    request = chaptered(base())
    items = plan.label_items(request)
    value = json.loads(plan.script(request, Kit(request))[0])
    assert repeat.label_problem(value, len(items)) is None
    prints = repeat.read(value, items, plan.label_names(request))
    assert all(p and p["obstacle_party"] != "none" for p in prints)
    assert len(plan.script({**request, "earlier_events": []}, Kit(request))) == len(plan.script(request, Kit(request))) - 1


# ---- Plan 9 step 3: the motive and the aim ----------------------------------------------------------------------------------------

def test_an_earlier_chapters_text_ends_with_its_planned_aim_when_the_beats_have_it_and_has_none_when_they_do_not():
    request = chaptered(base())
    items = dict(plan.label_items(request))
    assert all(text.endswith(f"The aim the chapter was planned around: Chase number {n} across the harbour.") for n, text in items.items())
    assert load_text("plan")["label_item_aim"].format(aim="x") == "The aim the chapter was planned around: x"
    no_beats = {**request, "earlier_beats": [b for b in request["earlier_beats"] if b["chapter"] != 4]}
    items = dict(plan.label_items(no_beats))
    assert "planned around" not in items[4] and "planned around" in items[3] and "planned around" in items[5]
    assert all("planned around" not in text for _, text in plan.label_items({**request, "earlier_beats": []}))


def test_the_label_call_over_the_earlier_chapters_reads_each_aim_and_asks_for_the_motive():
    request = chaptered(base())
    flow, reply, ctx, engine = run_with(request, *plan.script(request, Kit(request)))
    first = engine.prompts[0]
    assert "The aim the chapter was planned around: Chase number 3 across the harbour." in first and "For motive_kind" in first and "motive_kind" in first.split("## Your task")[1]
    assert all(row["motive_kind"] == "recognition" for row in flow.used)


def test_the_script_label_reply_carries_a_valid_motive_kind_for_each_earlier_chapter():
    request = chaptered(base())
    items = plan.label_items(request)
    prints = json.loads(plan.script(request, Kit(request))[0])["prints"]
    assert len(prints) == len(items) and all(p["motive_kind"] in repeat.MOTIVE_KINDS for p in prints) and repeat.label_problem({"prints": prints}, len(items)) is None
    assert all(print_["motive_kind"] != "other" for print_ in repeat.read({"prints": prints}, items, plan.label_names(request)))


def test_the_table_line_carries_the_motive_unless_it_says_other_and_the_brainstorm_asks_for_a_different_reason():
    request = chaptered(base())
    w = load_text("plan")
    row = {"chapter": 5, **repeat.clean({"aim_kind": "keep", "obstacle_source": "group", "obstacle_party": "Marit", "turning_kind": "bargain", "outcome": "gave_up",
                                         "closing_hook": "new_task", "motive_kind": "duty", "turning_note": "Note 5."}, ["Marit"])}
    lines = table_lines(plan.build_brainstorm_prompt(request, 1.0, None, [row]))
    assert lines == ["Chapter 5: aim: keep; in the way: group (Marit); turning point: bargain; ended: gave up; left standing: new task; driven by: duty. Note 5."]
    assert "driven by" not in plan.used_text([{**row, "motive_kind": "other"}], w) and "driven by" not in plan.used_text([{k: v for k, v in row.items() if k != "motive_kind"}], w)
    assert "driven by: closeness" in plan.used_text([{**row, "motive_kind": "closeness"}], w)
    assert "why the protagonist wanted it" in w["used_lead"] and "in why the protagonist wants it" in w["brainstorm_used"]
    assert w["avoid_fields"]["motive_kind"] == "why the protagonist wants it" and set(repeat.FIELDS) <= set(w["avoid_fields"])
