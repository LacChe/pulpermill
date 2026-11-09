"""combination-select, stage 2: the `select` step of the plan call (three combinations of a tie and a rule or object, picked before the
brainstorm), the brainstorm and the plan working from them, the reply's `picked`, and the trace. The real flow on the fake engine; no model."""
import copy
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
for sub in ("backend", "prompts"):
    sys.path.insert(0, str(ROOT / "tests" / sub))

from pulpermill import contract  # noqa: E402
from pulpermill.backend import runner  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.backend.engine.base import CancelFlag  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.backend.pipelines import RunContext  # noqa: E402
from pulpermill.backend.shape import problems as shape_problems  # noqa: E402
from pulpermill.prompter.mill import plan, select  # noqa: E402
from pulpermill.prompter.mill.common import load_text  # noqa: E402
from pulpermill.prompts import budget, tokens  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]


def base() -> dict:
    """The contract's plan request with no earlier events, so the flow has no label step (Plan 7); `with_events` gives it back its events."""
    request = copy.deepcopy(next(v["data"] for v in VECTORS if v["valid"] and v["name"] == "a plan request"))
    request["earlier_events"] = []
    return request


def with_events(request: dict) -> dict:
    """The same request with the contract's earlier events, so a chapter 2+ flow runs the label step before the brainstorm."""
    vector = next(v["data"] for v in VECTORS if v["valid"] and v["name"] == "a plan request")
    return {**request, "earlier_events": copy.deepcopy(vector["earlier_events"])}


def options_of(world: dict) -> list[dict]:
    """The rules and objects of a world as the page sends them in `pressure_options`: in words, with ids."""
    return ([{"id": r["id"], "kind": "rule", "statement": r.get("statement", ""), "cost": r.get("cost", ""), "when_broken": r.get("when_broken", "")} for r in world.get("rules", [])]
            + [{"id": o["id"], "kind": "object", "name": o["name"], "description": o.get("description", ""), "significance": o.get("significance", "")} for o in world.get("objects", [])])


def choose_request(options: bool = True) -> dict:
    """A chapter-2 plan request that asks to choose: three people, four ties among them (and one to a group), two rules and objects."""
    request = base()
    request["choose"] = True
    first, second = request["cast"][0]["id"], request["cast"][1]["id"]
    request["cast"].append({**copy.deepcopy(request["cast"][0]), "id": "c0000003", "name": "Orin"})
    request["ties"] += [{"id": "t3000001", "tie_from": first, "tie_to": "c0000003", "bond": "rival", "edge": "to out-trade her"},
                        {"id": "t3000002", "tie_from": second, "tie_to": "c0000003", "bond": "neighbour", "edge": "to borrow a lamp"}]
    if options:
        request["pressure_options"] = options_of(request["world"])
    return request


def ids_in(node, out=None):
    out = set() if out is None else out
    if isinstance(node, dict):
        if isinstance(node.get("id"), str):
            out.add(node["id"])
        for v in node.values():
            ids_in(v, out)
    elif isinstance(node, list):
        for v in node:
            ids_in(v, out)
    return out


def run_plan(request, *texts, **config):
    kit = Kit(request)
    engine = FakeEngine()
    engine.script(*texts)
    ctx = RunContext(engine, CancelFlag(), [].append, Config(**config))
    ctx.notes["call"] = "plan"
    flow = plan.build_flow(request, kit)
    return flow, flow.reply(runner.run_flow(ctx, flow, "en")), ctx, engine


def names_of_steps(ctx):
    return [p["step"] for p in ctx.notes["passes"]]


# ---- What may be chosen ----------------------------------------------------------------------------------------------------------

def test_the_candidates_are_the_ties_among_the_cast_and_the_options_the_page_sent():
    request = choose_request()
    ties, options = select.candidates(request)
    assert [t["id"] for t in ties] == ["t1000001", "t3000001", "t3000002"], "the tie to a group is no candidate"
    assert [o["id"] for o in options] == ["r0000001", "o0000001"]
    assert select.is_on(request) is True


def test_choose_runs_the_select_step_with_one_pair_and_only_no_tie_or_no_choose_leaves_todays_flow():
    few = base()
    few["choose"] = True
    assert len(select.candidates(few)[0]) == 1 and not select.candidates(few)[1]
    assert select.is_on(few) is True, "one tie is enough: the picks may repeat the pair"
    flow = plan.build_flow(few, Kit(few))
    assert "select" not in flow.notes and [s.name for s in flow.worst_case()][:2] == ["select", "brainstorm"]
    assert flow.next([]).name == "select"
    no_tie = base()
    no_tie["choose"] = True
    no_tie["ties"] = []
    assert select.is_on(no_tie) is False and plan.build_flow(no_tie, Kit(no_tie)).notes["select"] == "few"
    plain = base()
    assert "select" not in plan.build_flow(plain, Kit(plain)).notes and select.is_on(plain) is False
    no_choose = choose_request()
    no_choose["choose"] = False
    assert select.is_on(no_choose) is False and plan.build_flow(no_choose, Kit(no_choose)).next([]).name == "brainstorm"
    assert select.is_on(choose_request(options=False)) is True


def test_the_check_accepts_repeats_when_pairs_are_scarce_and_refuses_them_when_three_distinct_pairs_exist():
    def picks(*pairs, options=True):
        return {"picks": [{"reason": "r", "tie": t, **({"pressure": o} if options else {})} for t, o in pairs]}
    assert select.select_problem(picks((1, 1), (1, 1), (1, 1), options=False), 1, 0) is None, "one pair: all three may be it"
    assert select.select_problem(picks((1, 1), (2, 1), (1, 1), options=False), 2, 0) is None, "two pairs: two different are enough"
    assert select.select_problem(picks((1, 1), (1, 1), (1, 1), options=False), 2, 0), "two pairs exist: one is too few"
    assert select.select_problem(picks((1, 1), (1, 2), (1, 1)), 1, 2) is None
    assert "at least 2 different" in select.select_problem(picks((1, 1), (1, 1), (1, 1)), 1, 2)
    assert select.select_problem(picks((1, 1), (2, 2), (1, 1)), 3, 2), "six pairs exist: three different are needed"
    assert select.select_problem(picks((1, 1), (2, 2), (3, 1)), 3, 2) is None
    assert select.grammar(1, 0)["properties"]["picks"]["minItems"] == 3 == select.grammar(1, 0)["properties"]["picks"]["maxItems"]


def test_a_cast_of_two_with_one_tie_and_one_rule_runs_select_and_the_brainstorm_writes_three_ideas():
    request = base()
    request["choose"] = True
    request["pressure_options"] = options_of(request["world"])[:1]
    texts = plan.script(request, Kit(request))
    assert len(json.loads(texts[0])["picks"]) == 3 and {(p["tie"], p["pressure"]) for p in json.loads(texts[0])["picks"]} == {(1, 1)}
    flow, reply, ctx, engine = run_plan(request, *texts)
    assert names_of_steps(ctx)[:3] == ["select", "brainstorm", "plan"]
    assert "Option 3" in engine.prompts[2] or "Option 3" in texts[1]
    assert "the two ideas still differ in aim, obstacle, person or place" in engine.prompts[1]
    assert reply["picked"]["spotlight"] == select.candidates(request)[0][0]["id"]


# ---- The prompt, the grammar and the check -------------------------------------------------------------------------------------------

def test_the_select_prompt_numbers_ties_and_rules_in_words_with_no_ids_and_no_single_spotlight():
    request = choose_request()
    prompt = select.build_select_prompt(request)
    assert "1. Marit and Suvi: mother (edge: to bring her daughter home)" in prompt
    assert "3. " in prompt.split("The ties you may choose:")[1].split("The rules and objects")[0]
    rules = prompt.split("The rules and objects you may choose:")[1]
    assert "1. (rule) " in rules and "2. (object) " in rules and "The ledger" in rules
    first_rule = next(o for o in options_of(request["world"]) if o["kind"] == "rule")
    assert "When broken: " + first_rule["when_broken"] in rules, "a rule is listed with what follows its breaking"
    assert all(i not in prompt for i in ids_in(request)), "no id reaches a prompt"
    assert "## The tie in the spotlight" not in prompt and "## The combinations you may choose from" in prompt and "picks" in prompt


def test_the_grammar_has_exactly_three_picks_and_the_right_integer_ranges_and_the_check_refuses_what_it_should():
    grammar = select.grammar(3, 2)
    picks = grammar["properties"]["picks"]
    assert picks["minItems"] == picks["maxItems"] == 3 and list(picks["items"]["properties"]) == ["reason", "tie", "pressure"]
    assert picks["items"]["properties"]["tie"]["enum"] == [1, 2, 3] and picks["items"]["properties"]["pressure"]["enum"] == [1, 2]
    assert "pressure" not in select.grammar(3, 0)["properties"]["picks"]["items"]["properties"]
    good = {"picks": [{"reason": "a", "tie": 1, "pressure": 1}, {"reason": "b", "tie": 2, "pressure": 1}, {"reason": "c", "tie": 1, "pressure": 2}]}
    assert shape_problems(good, grammar) == [] and select.select_problem(good, 3, 2) is None
    same = {"picks": [good["picks"][0], good["picks"][1], {**good["picks"][0], "reason": "again"}]}
    assert "Picks 1 and 3 are the same tie with the same rule or object" in select.select_problem(same, 3, 2)
    out = {"picks": [good["picks"][0], good["picks"][1], {"reason": "c", "tie": 4, "pressure": 1}]}
    assert "Pick 3" in select.select_problem(out, 3, 2) and shape_problems(out, grammar)
    assert select.select_problem({"picks": good["picks"][:2]}, 3, 2) and select.select_problem({}, 3, 2)
    assert select.select_problem({"picks": [{**p, "reason": ""} if n == 1 else p for n, p in enumerate(good["picks"])]}, 3, 2)
    with_reason = lambda text: {"picks": [{**p, "reason": text} if n == 0 else p for n, p in enumerate(good["picks"])]}
    assert select.select_problem(with_reason("x" * 550), 3, 2) is None and select.select_problem(with_reason("x" * 700), 3, 2) is None
    assert "at most 700 characters" in select.select_problem(with_reason("x" * 750), 3, 2) and select.select_problem(with_reason("x" * 701), 3, 2)
    assert len(select.REASON_STAND_IN) == select.REASON_MAX == 700, "the worst case shown to the model is as long as a reason may be"
    assert "at most 700 characters" in select.build_select_prompt(choose_request())


# ---- The flow --------------------------------------------------------------------------------------------------------------------------

def test_with_choose_on_the_steps_run_select_brainstorm_plan_judges_and_the_worst_case_names_the_same():
    request = choose_request()
    texts = plan.script(request, Kit(request))
    assert len(texts) == 3 and len(json.loads(texts[0])["picks"]) == 3 and json.loads(texts[2])["idea"] == 1
    flow, reply, ctx, engine = run_plan(request, *texts)
    assert names_of_steps(ctx) == ["select", "brainstorm", "plan"] and engine.calls == 3
    assert [s.name for s in flow.worst_case()] == ["select", "brainstorm", "decide", "plan"]
    assert "select" not in [s.name for s in plan.build_flow(base(), Kit(base())).worst_case()]


def test_the_brainstorm_and_the_plan_carry_the_three_combinations_instead_of_one_spotlight():
    request = choose_request()
    texts = plan.script(request, Kit(request))
    flow, reply, ctx, engine = run_plan(request, *texts)
    brainstorm, planned = engine.prompts[1], engine.prompts[2]
    for prompt in (brainstorm, planned):
        assert "## The three combinations" in prompt and "Combination 1" in prompt and "Combination 3" in prompt and "## The tie in the spotlight" not in prompt
        assert all(i not in prompt for i in ids_in(request))
        assert "is a part of that chapter's collision, whether or not it has anything to do with the aim or the tie to begin with" in prompt
        assert "is kept at its price, bent, or broken, with what follows its breaking" in prompt
    assert "one idea for each, in order: idea 1 is built on combination 1" in brainstorm
    assert "Choose one idea and build the plan on it alone" in planned and "Begin your reply with idea" in planned and "combine two" not in planned


def test_the_plans_idea_becomes_picked_with_the_ids_from_the_request_and_the_reply_is_a_valid_plan_reply():
    request = choose_request()
    texts = plan.script(request, Kit(request))
    flow, reply, ctx, engine = run_plan(request, *texts)
    first = json.loads(texts[0])["picks"][0]
    ties, options = select.candidates(request)
    assert reply["picked"] == {"spotlight": ties[first["tie"] - 1]["id"], "pressure": options[first["pressure"] - 1]["id"]}
    assert "idea" not in reply["beat"] and "idea_use" not in reply["beat"]
    assert contract.parse_reply("plan", {"ok": True, **reply}).picked.spotlight == reply["picked"]["spotlight"]
    second = json.loads(texts[2])
    second["idea"] = 2
    flow, reply2, ctx, engine = run_plan(request, texts[0], texts[1], json.dumps(second), *texts[3:])
    pick = json.loads(texts[0])["picks"][1]
    assert reply2["picked"] == {"spotlight": ties[pick["tie"] - 1]["id"], "pressure": options[pick["pressure"] - 1]["id"]} and ctx.notes["flow"]["idea"] == 2


def test_the_plan_check_names_the_two_people_of_the_chosen_tie_and_asks_for_an_idea():
    request = choose_request()
    flow = plan.build_flow(request, Kit(request))
    picks = {"picks": [{"reason": "a", "tie": 1, "pressure": 1}, {"reason": "b", "tie": 1, "pressure": 2}, {"reason": "c", "tie": 3, "pressure": 1}]}
    assert flow.next([]).name == "select" and flow.next([picks]).name == "brainstorm"
    step = flow.next([picks, "x" * 200])
    assert step.name == "plan"
    beat = json.loads(plan.script(request, Kit(request))[2])
    assert step.check({**beat, "idea": 1}) is None
    absent = step.check({**beat, "idea": 3})
    assert absent and "Orin" in absent, "idea 3 is the tie between Marit and Orin, so the plan has to name Orin"
    assert step.check({k: v for k, v in beat.items() if k != "idea"}) == load_text("plan")["problems"]["idea_missing"]
    assert flow.notes["select"] == "on" and flow.notes["select_ties"] == 2 and flow.notes["select_pressures"] == 2


def test_a_select_that_cannot_be_used_leaves_todays_flow_on_the_pages_own_pair_and_no_picked():
    request = choose_request()
    texts = plan.script(request, Kit(request))
    beat = {k: v for k, v in json.loads(texts[2]).items() if k != "idea"}          # without a choice there is no idea to give
    flow, reply, ctx, engine = run_plan(request, "not json", "not json", texts[1], json.dumps(beat))
    assert engine.calls == 4, "two refused attempts at the select step, then the brainstorm and the plan"
    assert "picked" not in reply and flow.combos is None and ctx.notes["flow"]["select"] == "fallback"
    assert "## The tie in the spotlight" in engine.prompts[3] and "## The three combinations" not in engine.prompts[3]


def test_the_earlier_chapters_tie_and_pressure_reach_all_three_prompts_and_only_the_select_prompt_asks_for_variety():
    request = choose_request()
    request["earlier_beats"][0].update(tie="Marit and Suvi", pressure="Debts are written, never spoken.")
    flow, reply, ctx, engine = run_plan(request, *plan.script(request, Kit(request)))
    select_prompt, brainstorm, planned = engine.prompts[:3]
    for prompt in (select_prompt, brainstorm, planned):
        assert "It was about Marit and Suvi." in prompt and "It put this to work: Debts are written, never spoken." in prompt
    assert "prefer a tie that the story has used the least lately" in select_prompt and "a rule or object that the story has used" not in select_prompt
    assert "only when the story gives a reason to" in select_prompt
    assert "the least lately" not in brainstorm and "the least lately" not in planned
    assert "the least lately" in select.build_select_prompt(choose_request(options=False)), "the variant with no rules or objects asks for variety too"


# ---- The trace and the run record --------------------------------------------------------------------------------------------------------

def test_the_trace_has_a_row_for_the_select_step_and_the_plan_row_keeps_the_idea(tmp_path):
    path = tmp_path / "trace.jsonl"
    request = choose_request()
    texts = plan.script(request, Kit(request))
    run_plan(request, *texts, trace_path=str(path))
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert [r["step"] for r in rows][:3] == ["select", "brainstorm", "plan"]
    select_row, plan_row = rows[0], rows[2]
    assert select_row["used"] is True and "picks" in select_row["reply"] and "The ties you may choose:" in select_row["prompt"]
    assert json.loads(plan_row["reply"])["idea"] == 1


def test_the_notes_hold_only_numbers_and_short_words():
    request = choose_request()
    flow, reply, ctx, engine = run_plan(request, *plan.script(request, Kit(request)))
    notes = ctx.notes["flow"]
    assert notes["select"] == "on" and notes["select_ties"] == 2 and notes["select_pressures"] == 2 and notes["idea"] == 1
    assert all(isinstance(v, (int, bool)) or (isinstance(v, str) and len(v) < 20) for v in notes.values())


@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
def test_the_worst_case_of_the_choose_flow_fits_the_context_for_a_large_story():
    from story_sizes import inflate
    request = inflate(with_events(base()), cast=6, each=5, ties=6, chapters=9, chars=900)
    request["choose"] = True
    request["pressure_options"] = options_of(request["world"])
    assert select.is_on(request)
    flow = plan.build_flow(request, Kit(request))
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert all(m.ok for m in measures) and factor <= 1.0
    assert [s.name for s in flow.worst_case()][:6] == ["select", "label", "brainstorm", "label", "decide", "plan"]


def test_the_select_prompt_carries_the_running_aim_and_asks_for_combinations_that_carry_its_next_step():
    request = with_events(choose_request())
    prompt = select.build_select_prompt(request)
    assert "The protagonist's running aim, chapter by chapter" in prompt and "Chapter 1 (the latest): aim: Suvi wants to learn who took the ledger." in prompt
    assert "Where the aim stands now, at the end of chapter 1: Suvi now knows the board is hunting her." in prompt
    assert "Choose combinations whose tie and rule or object can carry the next step of that aim" in prompt and "In each reason, say how" in prompt
    plain = select.build_select_prompt(choose_request(options=False))
    assert "can carry the next step of that aim" in plain          # the same line with no rules or objects to choose
    first = {**request, "chapter": 1, "earlier_beats": [], "earlier_events": []}
    assert "running aim" not in select.build_select_prompt(first)


@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
def test_the_chain_at_its_longest_still_fits_the_select_the_brainstorm_and_the_plan_prompts():
    """Nine earlier chapters, each with an aim of 300 characters and an ending line of 600 (their caps): the chain block adds this much to every planner prompt."""
    from story_sizes import inflate
    request = inflate(with_events(base()), cast=6, each=5, ties=6, chapters=9, chars=900)
    request["choose"] = True
    request["pressure_options"] = options_of(request["world"])
    request["earlier_beats"] = [{"chapter": n, "where": "The Quay", "when": "Morning", "aim": ("aim " * 75).strip(), "plan": "x"} for n in range(1, 10)]
    for e in request["earlier_events"]:
        e["changed"] = ("ending " * 85)[:600]
    assert len(plan.chain_text(request, load_text("plan"))) > 9 * 900
    flow = plan.build_flow(request, Kit(request))
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert all(m.ok for m in measures) and factor <= 1.0 and [m.name for m in measures][:6] == ["select", "label", "brainstorm", "label", "decide", "plan"]


# ---- Rules and objects the last chapters used are not offered ---------------------------------------------------------------

ALL = ["p1", "p2", "p3", "p4", "p5"]


@pytest.mark.parametrize("used,expected", [
    ([], ALL),                                         # chapter 1: nothing left out
    (["p1"], ["p2", "p3", "p4", "p5"]),                # one chapter: its pressure is left out
    (["p1", "p2"], ["p3", "p4", "p5"]),                # two chapters: both left out, three remain
    (["p9", "p1", "p2"], ["p3", "p4", "p5"]),          # only the last two count
    (["", "p2"], ["p1", "p3", "p4", "p5"]),            # a chapter with no pressure leaves nothing out
])
def test_the_last_two_chapters_pressures_are_left_out_when_three_remain(used, expected):
    assert select.offered_ids(ALL, used) == expected


def test_with_fewer_than_three_left_only_the_last_chapters_pressure_is_left_out_and_it_does_not_relax_further():
    four = ["p1", "p2", "p3", "p4"]
    assert select.offered_ids(four, ["p1", "p2"]) == ["p1", "p3", "p4"]         # two-chapter leaves two, so only p2 (the last) goes
    three = ["p1", "p2", "p3"]
    assert select.offered_ids(three, ["p1", "p2"]) == ["p1", "p3"]              # one-chapter leaves two, which stays: fewer than three is allowed
    assert "p2" not in select.offered_ids(three, ["p1", "p2"])                  # never re-admit the last chapter's pressure
    assert select.offered_ids(["p1", "p2"], ["p1", "p2"]) == ["p1"]


def test_a_world_with_one_option_offers_it_whatever_was_used():
    assert select.offered_ids(["p1"], ["p1", "p1"]) == ["p1"]
    assert select.offered_ids([], ["p1"]) == []


def request_with(n: int, used: list[str]) -> dict:
    request = choose_request()
    request["pressure_options"] = [{"id": f"x{i}", "kind": "rule", "statement": f"statement {i}", "cost": f"cost {i}", "when_broken": f"broken {i}"} for i in range(1, n + 1)]
    request["pressure_used"] = used
    return request


def test_the_select_prompt_lists_only_the_offered_options_and_numbers_read_back_through_the_filtered_list():
    request = request_with(5, ["x1", "x2"])
    ties, options = select.candidates(request)
    assert [o["id"] for o in options] == ["x3", "x4", "x5"]
    prompt = select.build_select_prompt(request)
    rules = prompt.split("The rules and objects you may choose:")[1]
    assert "1. (rule) " in rules and "statement 3" in rules and "statement 1" not in rules and "statement 2" not in rules
    value = {"picks": [{"reason": "r", "tie": 1, "pressure": 1}, {"reason": "r", "tie": 2, "pressure": 2}, {"reason": "r", "tie": 3, "pressure": 3}]}
    assert select.select_problem(value, len(ties), len(options)) is None
    assert [c["pressure_id"] for c in select.combos(request, value)] == ["x3", "x4", "x5"]       # number 1 is the first offered, not the first of the world
    assert select.select_problem({"picks": [{**value["picks"][0], "pressure": 4}] + value["picks"][1:]}, len(ties), len(options))     # 4 is outside the filtered list
    assert select.grammar(len(ties), len(options))["properties"]["picks"]["items"]["properties"]["pressure"]["enum"] == [1, 2, 3]


def test_a_request_without_a_history_is_offered_everything():
    request = request_with(3, [])
    request.pop("pressure_used")
    assert [o["id"] for o in select.candidates(request)[1]] == ["x1", "x2", "x3"]
