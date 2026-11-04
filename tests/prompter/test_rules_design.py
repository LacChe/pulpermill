"""C1, the design rules in what the `mill` prompter asks for and accepts (rules 3 to 7; rules 1 and 2 are in test_coverage_*.py). Replies are
scripted: the checks run on them as the runner runs them, and a few go through the real server and runner on the fake engine. No model.

What a test here cannot prove (it needs a model, see the report): that a plan really collides the aim with the tie (rule 4), and that a chapter
really is interesting (rule 3). These tests prove the prompts ask for both, in the words the design calls for, and that the checks refuse the
replies that give up on them."""
import copy
import json
import re

import pytest

from test_coverage_support import (GENERATE, MARIT, PID, PLAN, SUVI, TIE_A, TIE_B, flow_for, generate_request, plan_request, prompts, sections)
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.kit import Kit
from pulpermill.prompter.mill import generate as gen, plan as mill_plan
from pulpermill.prompts import budget
from pulpermill.schema.shifts import MAX_SHIFTS_PER_CHAPTER
from server_harness import post, running, wait_idle
from story_sizes import inflate

STYLE = {"person": "first", "tense": "past", "humor": "dry", "pacing": "brisk"}


def plan_with(**changes) -> dict:
    request = plan_request(lambda q: q.update(style=STYLE))
    request.update(changes)
    return request


def gen_with(**changes) -> dict:
    request = generate_request(lambda q: q["beat"].update(aim="Suvi wants the ledger out before dawn."))
    request["style"] = STYLE
    request["chapter_count"] = 20
    request.update(changes)
    return request


def good_plan(request: dict) -> dict:
    return json.loads(mill_plan.script(request, Kit(request))[1])


def plan_check(request: dict):
    return flow_for("plan", request)[0].next(["A brainstorm of three options."]).check          # the plan step comes after the brainstorm


def shifts_check(request: dict):
    flow, _ = flow_for("generate", request)
    return flow.next(["The chapter.", {"happened": "Something happened here.", "changed": "Something changed."}]).check


def edge_entry(handle: str, edge: str) -> dict:
    return {"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": handle, "values": {"edge": edge}}]}}


# ---- rule 7: every chapter is designed in four points ---------------------------------------------------------------------------

def without_point(plan: str, n: int) -> str:
    return re.sub(rf"Act {n}:.*?(?=Act {n + 1}:|$)", "", plan, flags=re.S)


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_rule7_the_plan_check_accepts_four_points_and_rejects_each_missing_one(n):
    request = plan_with()
    check, good = plan_check(request), good_plan(request)
    assert check(good) is None
    assert f"Act {n}" in good["plan"] and f"Act {n}" not in without_point(good["plan"], n)
    problem = check({**good, "plan": without_point(good["plan"], n)})
    assert problem and f"Act {n}" in problem and "\n" not in problem, problem


def test_rule7_a_point_with_no_content_and_points_out_of_order_are_rejected():
    request = plan_with()
    check, good = plan_check(request), good_plan(request)
    empty = "Act 1: Suvi and Marit meet at the quay. Act 2: Act 3: A costly choice turns it. Act 4: A new state for both."
    shuffled = "Act 2: The conflict grows between Suvi and Marit. Act 1: Suvi and Marit meet at dawn. Act 3: A costly choice turns it. Act 4: A new state."
    assert "Act 2" in check({**good, "plan": empty})
    assert check({**good, "plan": shuffled})
    assert check({**good, "plan": "Suvi and Marit argue on the quay and make peace, and both are changed by it."})      # no points at all


@pytest.mark.parametrize("count", [10, 12, 15, 18, 20])
@pytest.mark.parametrize("where", ["first", "middle", "last"])
def test_rule7_four_points_are_asked_for_and_checked_at_every_chapter_count_and_position(count, where):
    chapter = {"first": 1, "middle": (count + 1) // 2, "last": count}[where]
    request = plan_with(chapter=chapter, chapter_count=count, setup={**PLAN["setup"], "chapter_count": count})
    if chapter == 1:
        request.update(earlier_beats=[], earlier_events=[])
    prompt = prompts("plan", request)["plan"]
    for label in ("Act 1", "Act 2", "Act 3", "Act 4"):
        assert label in prompt
    assert "starting point" in prompt and "climax or turning point" in prompt and "end point" in prompt and f"chapter {chapter} of {count}" in prompt
    check, good = plan_check(request), good_plan(request)
    assert check(good) is None                                                          # the same four points suit a story of any length
    assert check({**good, "plan": without_point(good["plan"], 4)})


def test_rule7_the_writer_gets_the_plan_and_moves_through_its_four_points_without_printing_the_labels():
    prompt = prompts("generate", gen_with())["write"]
    plan_section = sections(prompt)["The plan for this chapter"]
    assert gen_with()["beat"]["plan"] in plan_section
    assert "four points, Act 1 to Act 4" in plan_section and "no labels, no headings" in plan_section


# ---- rule 4 (what a test can see of it): the aim is concrete and collides with the spotlight tie --------------------------------

@pytest.mark.parametrize("aim", ["Get the guild clerk to sign the permit before the auditor arrives", "Suvi needs to reach the cellar before the clerk does",
                                 "Suvi wants to learn who took the ledger from the cellar"])
def test_rule4_the_plan_check_accepts_a_concrete_aim(aim):
    request = plan_with(earlier_beats=[])
    assert plan_check(request)({**good_plan(request), "aim": aim}) is None


@pytest.mark.parametrize("aim", ["", "   ", "Win", "Feel better about her mother", "Understand her mother", "Suvi wants to come to terms with the past.",
                                 "She needs to forgive herself."])
def test_rule4_the_plan_check_rejects_an_empty_or_abstract_aim(aim):
    request = plan_with(earlier_beats=[])
    problem = plan_check(request)({**good_plan(request), "aim": aim})
    assert problem and "aim" in problem.lower() and "\n" not in problem, (aim, problem)


def test_rule4_the_planner_prompt_asks_for_a_collision_of_the_aim_with_the_spotlight_tie_and_names_both_ends():
    prompt = prompts("plan", plan_with())["plan"]
    assert "collision" in prompt and "runs straight into the spotlight tie" in prompt and "moves the story forward" in prompt
    assert "Marit" in sections(prompt)["The tie in the spotlight"] and "Name both ends of the spotlight tie, Marit and Suvi" in prompt
    check, good = plan_check(plan_with()), good_plan(plan_with())
    assert check({**good, "plan": good["plan"].replace("Marit", "the mother")}), "a plan that leaves the spotlight tie's other end out is refused"


# ---- rule 6: the spotlight tie's edge and the protagonist's aim each end in a new state ---------------------------------------------

def test_rule6_the_shifts_check_rejects_a_chapter_that_leaves_the_edge_unchanged_and_accepts_one_that_replaces_it():
    request = gen_with()
    check = shifts_check(request)
    assert request["beat"]["spotlight"] == TIE_A and request["ties"][0]["edge"] == "to bring her daughter home"
    assert check({"shifts": [edge_entry("ties.1", "to forgive her daughter and let her stay")]}) is None
    unchanged = ({"shifts": []},
                 {"shifts": [{"card": "characters", "target": "Suvi", "patch": {"sketch": "Changed."}}]},                      # other cards moved, the tie did not
                 {"shifts": [edge_entry("ties.2", "to hide the ledger for good")]},                                         # another tie's edge is not the spotlight's
                 {"shifts": [edge_entry("ties.1", "To bring her daughter home.")]},                                         # the same edge, said again
                 {"shifts": [{"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": "ties.1", "values": {"bond": "mother, still"}}]}}]},
                 {"shifts": [{"card": "entanglements", "patch": {"ties": [{"op": "remove", "id": "ties.1"}]}}]})
    for reply in unchanged:
        problem = check(reply)
        assert problem and "ties.1" in problem and "Marit toward Suvi" in problem and "\n" not in problem, reply


def test_rule6_the_writer_and_the_events_step_ask_for_the_change_the_check_looks_for():
    texts = prompts("generate", gen_with())
    assert "the protagonist wanting something new and the tie standing differently" in texts["write"]
    assert "what the protagonist wants and what drives the tie now as a result" in texts["events"]
    assert "its edge was: to bring her daughter home" in texts["shifts"] and "The new edge must differ from the old one" in texts["shifts"]
    plan_text = prompts("plan", plan_with())["plan"]
    assert "must each have moved to a distinctly new state" in plan_text and "Say in Act 4 what the protagonist wants now and what now drives Marit in the tie" in plan_text
    assert "must grow out of how the collision ended" in plan_text


def seven_cast(request: dict) -> dict:
    request = copy.deepcopy(request)
    names = ["Nell", "Odo", "Pia"]
    request["cast"] += [{**copy.deepcopy(MARIT), "id": f"c000000{n}", "name": name} for n, name in zip((3, 4, 5), names)]
    return request


def test_rule6_a_chapter_never_has_more_than_seven_shift_entries():
    assert MAX_SHIFTS_PER_CHAPTER == 7
    request = seven_cast(gen_with())
    kit, check = Kit(request), shifts_check(seven_cast(gen_with()))
    assert len(kit.handles.of_card("characters")) == 5
    assert kit.grammar.shifts()["maxItems"] == 7                                       # five people, the world and the ties: seven cards at most
    labels = [s.label for s in kit.handles.of_card("characters")]
    entries = [{"card": "characters", "target": label, "patch": {"sketch": "Changed by the chapter."}} for label in labels]
    entries += [{"card": "world", "patch": {"everyday_life": "Changed by the chapter."}}, edge_entry("ties.1", "to let her daughter go")]
    assert len(entries) == 7 and kit.shifts_problem(entries) is None and check({"shifts": entries}) is None
    too_many = entries + [{"card": "world", "patch": {"era_and_technology": "Changed again."}}]
    assert len(too_many) == 8 and kit.shifts_problem(too_many), "eight entries are refused"
    assert check({"shifts": too_many})
    small = Kit(gen_with())                                                            # two people: four cards at most, never more than seven
    assert small.grammar.shifts()["maxItems"] == 4
    assert "at most seven entries" in prompts("generate", seven_cast(gen_with()))["shifts"]


# ---- rule 5: minor characters never carry the plot and appear only by role --------------------------------------------------------

def on_stage(prompt: str) -> str:
    return re.search(r"The people on stage are ([^.]*)\.", prompt).group(1)


@pytest.mark.parametrize("count", [1, 2, 5])
def test_rule5_the_writer_prompt_lists_only_the_cast_as_people_on_stage(count):
    request = seven_cast(gen_with())
    request["cast"] = request["cast"][:count]
    listed = on_stage(prompts("generate", request)["write"])
    cast = [p["name"] for p in request["cast"]]
    assert listed == (cast[0] if count == 1 else " and ".join([", ".join(cast[:-1]), cast[-1]]) if count > 2 else " and ".join(cast)), listed
    for name in ("The Board", "Nell", "Odo", "Pia", "Marit"):
        assert (name in listed) == (name in cast), name                                # a group, or a person not in the cast, is never on stage


def test_rule5_the_writer_prompt_tells_the_model_once_to_refer_to_everyone_else_by_what_they_do_without_a_name():
    prompt = prompts("generate", gen_with())["write"]
    plan_section = sections(prompt)["The plan for this chapter"]
    assert "The cast is fixed, and a name for anyone else would be a new character the reader has to keep track of" in plan_section
    assert "Refer to anyone else by what they do or by one telling detail, in the narration and in what people say to them" in plan_section
    assert "none of them has a name; only places, events and things do" in plan_section
    craft = sections(prompt)["How to write it"]
    assert "cast is fixed" not in craft and "by role" not in craft and "Only the people on stage act" not in craft           # said once, in the plan block
    assert "[offstage]" in sections(prompt)["Ties and holdings"]                          # people and groups outside the cast are marked as elsewhere


def test_rule5_the_planner_prompt_gives_minor_characters_a_role_and_never_the_plot():
    task = sections(prompts("plan", plan_with())["plan"])["Your task"]
    assert "The cast is fixed, so the plan names only people from the cards" in task
    assert "Anyone else appears by what they do or one telling detail" in task and "never carries the plot" in task
    assert "by role" not in task


# ---- the chapter's position (first, middle, last) and the plan are in the writer prompt ---------------------------------------------

def test_rule7_the_writer_prompt_carries_the_plan_and_where_the_chapter_stands():
    first = gen_with(chapter=1, earlier_events=[], previous_ending=None,
                     setup={"protagonist": PID, "normal": "Tides and ledgers.", "disruption": "The ledger is gone.", "chapter_count": 20})
    middle, last = gen_with(chapter=10), gen_with(chapter=20)
    p_first, p_mid, p_last = (prompts("generate", r)["write"] for r in (first, middle, last))
    for prompt, chapter in ((p_first, 1), (p_mid, 10), (p_last, 20)):
        assert f"This is chapter {chapter} of 20." in prompt and f"chapter {chapter} of 20 of a story" in prompt
        assert first["beat"]["plan"] in prompt and first["beat"]["aim"] in prompt
    assert "Open the story where ordinary life was: Tides and ledgers." in p_first and "What just broke it: The ledger is gone." in p_first
    assert "This is the last chapter" in p_last and "settles what it set in motion" in p_last
    assert all("cannot be taken back" in p for p in (p_first, p_mid, p_last))
    assert "makes the next chapter matter" not in p_last and "makes the next chapter matter" in p_mid
    assert "last chapter" not in p_first.replace("How the last chapter ended", "") and "last chapter" not in p_mid.replace("How the last chapter ended", "")
    assert "Open the story" not in p_mid and "Open the story" not in p_last
    assert len({p_first, p_mid, p_last}) == 3


# ---- rule 3 (what a test can see of it): the writer is asked for an interesting story, in prose ---------------------------------------

def test_rule3_the_writer_is_asked_for_an_interesting_story_in_prose_not_for_a_list_to_cover():
    prompt = prompts("generate", gen_with())["write"]
    craft = sections(prompt)["How to write it"]
    assert "Make this a chapter someone wants to keep reading" in craft and "something is at stake" in craft and "specific detail and the surprising one" in craft
    assert not re.search(r"^\s*(?:[-*•]|\d+[.)])\s", prompt, flags=re.M), "the writer prompt holds a bulleted or numbered list"
    assert "no list of events" in prompt and prompt.rstrip().endswith("so that it reads whole and ends on a finished beat.")


# ---- the squeeze: what is never cut ---------------------------------------------------------------------------------------------------

def big_generate() -> dict:
    small = gen_with()
    request = inflate(small, cast=6, each=5, ties=6, chapters=18, chars=900)                     # chapter 19 of 20, with 18 earlier events
    request.update(beat=small["beat"], ties=request["ties"][:2], previous_ending=small["previous_ending"], style=STYLE, chapter=19, chapter_count=20)
    assert len(request["earlier_events"]) == 18
    return request


def big_plan() -> dict:
    small = plan_with()
    request = inflate(small, cast=6, each=5, ties=6, chapters=18, chars=900)
    request.update(ties=request["ties"][:2], style=STYLE, spotlight=small["spotlight"], chapter=19, chapter_count=20)
    assert len(request["earlier_events"]) == 18
    request["earlier_beats"] = [{"chapter": n, "where": "The Quay", "when": "Morning", "aim": f"Chase number {n} across the harbour", "plan": "x"} for n in range(1, 19)]
    return request


@pytest.mark.parametrize("factor", budget.SQUEEZES)
def test_squeeze_the_writer_keeps_the_plan_the_scene_the_spotlight_tie_and_the_style_rules_at_every_factor(factor):
    request = big_generate()
    full, squeezed = (sections(gen.write_prompt(request, f)) for f in (1.0, factor))
    beat = request["beat"]
    plan_section = squeezed["The plan for this chapter"]
    assert "This is chapter 19 of 20." in gen.write_prompt(request, factor)
    assert plan_section == full["The plan for this chapter"]
    for scene in (beat["plan"], beat["aim"], beat["when_time"], beat["where"]):         # the plan and the scene it plays in
        assert scene in plan_section
    assert squeezed["The tie in the spotlight"] == full["The tie in the spotlight"]
    assert "Marit toward Suvi" in squeezed["The tie in the spotlight"] and request["ties"][0]["edge"][:40] in squeezed["The tie in the spotlight"]
    assert squeezed["The voice of the story"] == full["The voice of the story"]
    assert "Narrate in the first person" in squeezed["The voice of the story"] and "Person and tense are rules" in squeezed["The voice of the story"]
    assert squeezed["How to write it"] == full["How to write it"] and squeezed["How the last chapter ended"] == full["How the last chapter ended"]


@pytest.mark.parametrize("factor", budget.SQUEEZES)
def test_squeeze_the_planner_keeps_the_spotlight_tie_the_style_and_the_task_at_every_factor(factor):
    request = big_plan()
    full, squeezed = (sections(mill_plan.build_prompt(request, f)) for f in (1.0, factor))
    assert squeezed["The tie in the spotlight"].split("\n")[0] == full["The tie in the spotlight"].split("\n")[0]
    assert "Marit toward Suvi" in squeezed["The tie in the spotlight"] and "What drives Marit in this tie" in squeezed["The tie in the spotlight"]
    assert squeezed["The tone of the story"] == full["The tone of the story"] and squeezed["Your task"] == full["Your task"]
    assert "Act 4" in squeezed["Your task"] and "collision" in squeezed["Your task"]


# ---- the whole call on scripted fake-engine replies ---------------------------------------------------------------------------------------

def test_rule7_a_plan_without_its_third_point_is_asked_for_again_with_the_line_and_then_used():
    request = plan_with()
    good = good_plan(request)
    engine = FakeEngine()
    texts = mill_plan.script(request, Kit(request))
    engine.script(texts[0], json.dumps({**good, "plan": without_point(good["plan"], 3)}), json.dumps(good), *texts[2:])
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        response = post(base_url, request)
        assert response.status_code == 200 and response.json()["beat"]["plan"] == good["plan"]
        assert wait_idle(base_url)
    assert engine.calls == 3 + len(texts[2:]) and "Your previous reply could not be used" in engine.prompts[2] and "Act 3" in engine.prompts[2]


def test_rule4_an_abstract_aim_is_asked_for_again_with_the_line_and_then_used():
    request = plan_with(earlier_beats=[])
    good = good_plan(request)
    engine = FakeEngine()
    engine.script(mill_plan.script(request, Kit(request))[0], json.dumps({**good, "aim": "Feel better about her mother"}), json.dumps(good))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        assert post(base_url, request).status_code == 200
        assert wait_idle(base_url)
    assert engine.calls == 3 and "state of mind" in engine.prompts[2]


def test_rule6_a_chapter_whose_shifts_leave_the_edge_unchanged_is_asked_for_again_with_the_line_and_then_used():
    request = gen_with()
    text, events, shifts, judge = gen.script(request, Kit(request))
    engine = FakeEngine()
    engine.script(text, events, json.dumps({"shifts": [edge_entry("ties.1", "to bring her daughter home")]}), shifts, judge)
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        response = post(base_url, request)
        assert response.status_code == 200 and response.json()["ok"] is True
        assert wait_idle(base_url)
    assert engine.calls == 5 and "replaces the edge of ties.1" in engine.prompts[3]
