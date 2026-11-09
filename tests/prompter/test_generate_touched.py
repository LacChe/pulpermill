"""Plan 6, step 2: the ties a chapter touched besides the spotlight tie. `touch_candidates` is plain code over the request, the model step `ties_touched`
names the touched ones by handle, code keeps only handles it offered, and the flow runs the step only when there are candidates. The next file of tests (below) covers rewriting the touched ties."""
import copy
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
for sub in ("backend", "prompts", "e2e"):
    sys.path.insert(0, str(ROOT / "tests" / sub))

from pulpermill import contract  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter.mill import generate as gen  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
EVENTS = {"happened": "Suvi hid the ledger from Marit on the stairs, and Dov told her the board knew.", "changed": "Suvi kept the ledger. She now goes after Dov's key before dawn."}


def base() -> dict:
    return copy.deepcopy(next(v["data"] for v in VECTORS if v["valid"] and v["name"] == "a generate request"))


def person(cid: str, name: str) -> dict:
    return {"id": cid, "name": name, "age": 40, "sex": "male", "appearance": "Tall.", "sketch": "A porter.", "wants": [], "fear": "", "flaw": "", "values": [], "behaviors": []}


def tie(tid: str, a: str, b: str, bond: str = "friend of", edge: str = "to keep the peace") -> dict:
    return {"id": tid, "tie_from": a, "tie_to": b, "bond": bond, "edge": edge}


def request(*extra_ties: dict, cast: bool = True, **changes) -> dict:
    """The vector request (Suvi c1 and Marit c2 on stage, the Board g1 a group, t1000001 the spotlight tie, t1000002 Suvi toward the Board), plus Dov c3 on stage
    when `cast`, plus `extra_ties`."""
    req = base()
    if cast:
        req["cast"].append(person("c0000003", "Dov"))
    req["ties"] += list(extra_ties)
    req.update(changes)
    return req


@pytest.fixture(autouse=True)
def touching(monkeypatch):
    monkeypatch.setattr(gen, "TOUCH_CAP", 4)


def ids(ties: list[dict]) -> list[str]:
    return [t["id"] for t in ties]


# ---- touch_candidates ---------------------------------------------------------------------------------------------------------

def test_candidates_are_the_other_ties_on_stage_and_never_the_spotlight_tie():
    req = request(tie("t1000003", "c0000003", "c0000001"))
    assert ids(gen.touch_candidates(req)) == ["t1000002", "t1000003"]            # Suvi toward the Board (a group), Dov toward Suvi; t1000001 is the spotlight


def test_a_tie_needs_a_from_end_on_stage_and_a_to_end_on_stage_or_a_group():
    off_stage_from = tie("t1000003", "c0000009", "c0000001")
    off_stage_to = tie("t1000004", "c0000001", "c0000009")
    a_group_to = tie("t1000005", "c0000003", "g0000001")
    req = request(off_stage_from, off_stage_to, a_group_to)
    assert ids(gen.touch_candidates(req)) == ["t1000002", "t1000005"]
    assert ids(gen.touch_candidates(request(a_group_to, cast=False))) == ["t1000002"]       # Dov is not on stage: his tie is out, Suvi's tie to the Board stays


def test_a_tie_that_starts_at_a_group_is_skipped():
    req = request(tie("t1000003", "g0000001", "c0000001"), tie("t1000004", "g0000001", "c0000003"))
    assert ids(gen.touch_candidates(req)) == ["t1000002"]


def test_the_candidates_are_capped_in_list_order(monkeypatch):
    many = [tie(f"t10001{n:02d}", "c0000003", "c0000001") for n in range(6)]
    req = request(*many)
    assert gen.TOUCH_CAP == 4 and ids(gen.touch_candidates(req)) == ["t1000002", "t1000100", "t1000101", "t1000102"]
    monkeypatch.setattr(gen, "TOUCH_CAP", 2)
    assert ids(gen.touch_candidates(req)) == ["t1000002", "t1000100"]


def test_a_beat_that_carries_cast_ids_counts_them_as_on_stage():
    req = request(tie("t1000003", "c0000009", "c0000001"))
    assert ids(gen.touch_candidates(req)) == ["t1000002"]
    req["beat"]["cast"] = ["c0000009"]
    assert ids(gen.touch_candidates(req)) == ["t1000002", "t1000003"]


def test_a_request_with_only_the_spotlight_tie_has_no_candidates():
    req = base()
    req["ties"] = [t for t in req["ties"] if t["id"] == "t1000001"]
    assert gen.touch_candidates(req) == []


# ---- the step and the handles it returns -------------------------------------------------------------------------------------------

def test_the_prompt_shows_the_facts_and_each_candidate_with_its_handle_and_names_and_no_ids():
    req = request(tie("t1000003", "c0000003", "c0000001", bond="porter to", edge="to learn what Suvi hides"))
    kit = Kit(req)
    text = gen.build_flow(req, kit)._touched_step(EVENTS).text(1.0)
    for needed in (f"chapter {req['chapter']}", EVENTS["happened"], EVENTS["changed"], "ties.2: Suvi toward The Board, bond: clerk of",
                   "ties.3: Dov toward Suvi, bond: porter to. Edge: to learn what Suvi hides", "Standing in the same scene is not enough", "An empty list is a valid answer", "touched"):
        assert needed in text, needed
    assert "ties.1" not in text and "Marit toward Suvi" not in text                                # the spotlight tie is not offered
    assert not [i for i in ("t1000001", "t1000002", "t1000003", "c0000001", "c0000003", "g0000001") if i in text]


def test_the_step_is_a_json_step_with_a_small_grammar_and_an_empty_fallback():
    req = request()
    flow = gen.build_flow(req, Kit(req))
    step = flow._touched_step(EVENTS)
    assert step.name == "ties_touched" and step.kind == "json" and step.max_output == gen.TOUCHED_TOKENS and step.attempts == gen.JUDGE_ATTEMPTS
    assert list(step.grammar["properties"]) == ["touched"] and step.grammar["required"] == ["touched"]
    item = step.grammar["properties"]["touched"]["items"]
    assert list(item["properties"]) == ["tie", "reason"] and item["required"] == ["tie", "reason"] and item["additionalProperties"] is False
    assert step.fallback() == {"touched": []} and flow.notes["ties_touched_fallback"] is True


def test_unknown_handles_are_dropped_and_known_ones_kept_once_in_the_replys_order():
    req = request(tie("t1000003", "c0000003", "c0000001"))
    kit = Kit(req)
    reply = {"touched": [{"tie": "ties.3", "reason": "a"}, {"tie": "ties.1", "reason": "the spotlight tie is not a candidate"}, {"tie": "ties.9", "reason": "b"},
                         {"tie": "ties.2", "reason": "c"}, {"tie": "ties.3", "reason": "again"}, {"tie": 7, "reason": "d"}, "ties.2", {"reason": "e"}]}
    assert gen.touched_handles(req, kit, reply) == ["ties.3", "ties.2"]
    for odd in (None, {}, {"touched": None}, {"touched": "ties.2"}, "ties.2", [], {"touched": []}):
        assert gen.touched_handles(req, kit, odd) == []


# ---- the flow ------------------------------------------------------------------------------------------------------------------

def run_to_the_judge(req: dict):
    """A flow driven through write, events, shifts, check and judge with the module's own good replies; returns (flow, results, the step after the judge)."""
    kit = Kit(req)
    flow = gen.build_flow(req, kit)
    text, events, shifts, check, judge, *_ = gen.script(req, kit)
    results = [text, json.loads(events), json.loads(shifts)]
    assert flow.next(results).name == "edge_check"
    results.append(json.loads(check))
    assert flow.next(results).name == "advance_edge"
    results.append(json.loads(judge))
    return flow, results, flow.next(results)


def test_the_touched_step_runs_after_the_judge_when_there_are_candidates_and_the_ties_it_names_come_next():
    req = request(tie("t1000003", "c0000003", "c0000001"))
    flow, results, step = run_to_the_judge(req)
    assert step.name == "ties_touched"
    results.append({"touched": [{"tie": "ties.3", "reason": "Dov told Suvi the board knew."}, {"tie": "ties.8", "reason": "no such tie"}]})
    step = flow.next(results)
    assert step.name == "tie_edge" and "Dov toward Suvi" in step.text(1.0)                  # the unknown handle is dropped; the one known tie is rewritten next
    assert flow.touched == ["ties.3"] and flow.notes["ties_touched"] == 1


def test_an_empty_list_is_a_no_op():
    flow, results, step = run_to_the_judge(request())
    assert step.name == "ties_touched"
    results.append({"touched": []})
    assert flow.next(results) is None and flow.touched == [] and flow.notes["ties_touched"] == 0 and "ties_touched_fallback" not in flow.notes


def test_the_step_is_skipped_when_there_are_no_candidates(monkeypatch):
    req = base()
    req["ties"] = [t for t in req["ties"] if t["id"] == "t1000001"]
    flow, _, step = run_to_the_judge(req)
    assert step is None and flow.touched == [] and "ties_touched" not in flow.notes
    monkeypatch.setattr(gen, "TOUCH_CAP", 0)
    flow, _, step = run_to_the_judge(request())
    assert step is None


def test_the_step_still_runs_when_the_shifts_replaced_no_edge_but_other_ties_are_on_stage():
    req = request()
    flow = gen.build_flow(req, Kit(req))
    step = flow.next(["a chapter", {"happened": "x", "changed": "y"}, {"shifts": []}])         # no edge replaced: no check, no judge, then the touched step
    assert step.name == "ties_touched"
    assert flow.next(["a chapter", {"happened": "x", "changed": "y"}, {"shifts": []}, {"touched": []}]) is None


def test_the_pressure_judge_still_runs_last_after_the_touched_step():
    req = request()
    rule = req["world"]["rules"][0]
    req["pressure"] = {"kind": "rule", "statement": rule["statement"], "cost": rule["cost"], "when_broken": rule["when_broken"]}
    req["beat"]["pressure"] = rule["id"]
    texts = gen.script(req, Kit(req))
    assert len(texts) == 10 and json.loads(texts[5])["touched"] and json.loads(texts[9])["effect"] == "acts"           # the touched reply and the first tie's three come before the pressure reply
    flow, results, step = run_to_the_judge(req)
    assert step.name == "ties_touched"
    results.append({"touched": []})
    pressure = flow.next(results)
    assert pressure.name == "advance_pressure"
    results.append({"reason": "It cost one of them something.", "effect": "acts"})
    assert flow.next(results) is None and flow.notes["pressure_effect"] == "acts"


def test_the_worst_case_holds_the_new_step_only_when_there_are_candidates(monkeypatch):
    names = [s.name for s in gen.build_flow(request(), Kit(request())).worst_case()]
    assert names[:9] == ["write", "events", "shifts", "edge_check", "advance_edge", "shifts", "edge_check", "advance_edge", "ties_touched"]
    assert names[9:] == ["tie_edge", "edge_check", "tie_edge", "advance_edge"]                    # the one candidate: its edge, the check, the edge sent back once, the judge
    monkeypatch.setattr(gen, "TOUCH_CAP", 0)
    assert "ties_touched" not in [s.name for s in gen.build_flow(request(), Kit(request())).worst_case()]


def test_the_script_has_a_reply_for_the_new_step_only_when_there_are_candidates(monkeypatch):
    req = request()
    texts = gen.script(req, Kit(req))
    assert len(texts) == 9 and json.loads(texts[5]) == {"touched": [{"tie": "ties.2", "reason": json.loads(texts[5])["touched"][0]["reason"]}]}
    assert json.loads(texts[6])["edge"] and json.loads(texts[6])["bond"] == "" and json.loads(texts[7])["ok"] == "yes" and json.loads(texts[8])["move"] == "redirects"
    monkeypatch.setattr(gen, "TOUCH_CAP", 0)
    assert len(gen.script(req, Kit(req))) == 5


# ---- step 3: rewriting the touched ties ----------------------------------------------------------------------------------------

TWO = lambda: request(tie("t1000003", "c0000003", "c0000001", bond="porter to", edge="to learn what Suvi hides"))          # candidates: ties.2 (Suvi toward the Board), ties.3 (Dov toward Suvi)
NAMES_BOTH = {"touched": [{"tie": "ties.2", "reason": "The board pressed Suvi about the ledger."}, {"tie": "ties.3", "reason": "Dov told Suvi the board knew."}]}
EDGE = lambda edge, bond="": {"edge": edge, "bond": bond}
OK, NO = {"reason": "A want with a target.", "ok": "yes"}, {"reason": "The edge is a mood.", "ok": "no"}
MOVE = lambda move: {"old_object": "a", "new_object": "b", "reason": "r", "move": move}


def to_touched(req: dict):
    """A flow driven to the point where the touched step's reply is next; returns (flow, results)."""
    flow, results, step = run_to_the_judge(req)
    assert step.name == "ties_touched"
    return flow, results


def feed(flow, results: list, *values) -> list:
    """The step names the flow asks for as each value is given in turn (the last is None when the chain is over). The steps themselves are in `feed.steps`."""
    asked, feed.steps = [], []
    for value in values:
        results.append(value)
        step = flow.next(results)
        feed.steps.append(step)
        asked.append(step.name if step else None)
    return asked


def test_the_operation_carries_the_bond_only_when_it_is_there_and_new():
    t = tie("t1000003", "c0000003", "c0000001", bond="porter to")
    assert gen.tie_operation("ties.3", t, "to learn more", "") == {"op": "replace", "id": "ties.3", "values": {"edge": "to learn more"}}
    assert gen.tie_operation("ties.3", t, "to learn more", "porter to") == {"op": "replace", "id": "ties.3", "values": {"edge": "to learn more"}}
    assert gen.tie_operation("ties.3", t, "to learn more", "rival of")["values"] == {"edge": "to learn more", "bond": "rival of"}


def test_the_merge_adds_operations_to_the_one_entanglements_entry_or_makes_one_and_never_changes_its_input():
    spotlight = {"op": "replace", "id": "ties.1", "values": {"edge": "to settle"}}
    entries = [{"card": "entanglements", "patch": {"ties": [spotlight]}}]
    mine = [gen.tie_operation("ties.2", {}, "to hold", ""), gen.tie_operation("ties.3", {}, "to learn", "")]
    before = copy.deepcopy(entries)
    merged = gen.merge_ties(entries, mine)
    assert entries == before and len(merged) == 1 and merged[0]["patch"]["ties"] == [spotlight, *mine]
    assert gen.merge_ties([], mine) == [{"card": "entanglements", "patch": {"ties": mine}}]                         # no entry (the shifts fell back): a new one
    assert gen.merge_ties([{"card": "entanglements", "patch": {}}], mine) == [{"card": "entanglements", "patch": {"ties": mine}}]
    assert gen.merge_ties(entries, [gen.tie_operation("ties.1", {}, "again", "")]) == before                         # a handle already replaced is left alone
    assert gen.merge_ties(None, []) == []


def test_the_tie_edge_prompt_names_the_tie_the_old_edge_and_bond_the_facts_and_the_reason_and_has_no_must_differ_and_no_handle():
    req = TWO()
    flow, results = to_touched(req)
    results.append(NAMES_BOTH)
    step = flow.next(results)
    text = step.text(1.0)
    assert step.name == "tie_edge" and step.attempts == gen.SHIFTS_ATTEMPTS and step.max_output == gen.TIE_EDGE_TOKENS and step.sampling == "structured"
    for needed in ("Suvi toward The Board", "Its bond was: clerk of", "to keep the board from finding the ledger gone", "Why the chapter touched this tie: The board pressed Suvi about the ledger.",
                   "write the old edge again", "concrete person, thing, place or deadline"):
        assert needed in text, needed
    assert "must differ" not in text and "spotlight" not in text.lower() and "ties.2" not in text and "t1000002" not in text and "ties list" not in text
    assert list(step.grammar["properties"]) == ["edge", "bond"] and step.grammar["required"] == ["edge", "bond"]
    assert step.check({"edge": "", "bond": ""}) and step.check({"edge": "to hold the board off", "bond": ""}) is None and step.fallback() == {"edge": "", "bond": ""}


def test_two_touched_ties_are_rewritten_in_order_each_with_a_check_and_a_judge_and_a_same_verdict_leaves_the_tie_out():
    req = TWO()
    flow, results = to_touched(req)
    asked = feed(flow, results, NAMES_BOTH, EDGE("to bury the ledger before the board counts"), OK, MOVE("redirects"),            # ties.2 is rewritten and kept
                 EDGE("to learn what Suvi hides"), OK, MOVE("same"))                                                           # ties.3 comes back the same: left out
    assert asked == ["tie_edge", "edge_check", "advance_edge", "tie_edge", "edge_check", "advance_edge", None]
    assert flow.tie_ops == [{"op": "replace", "id": "ties.2", "values": {"edge": "to bury the ledger before the board counts"}}]
    assert flow.notes["ties_touched"] == 2 and flow.notes["ties_rewritten"] == 1 and flow.notes["ties_same"] == 1
    shifts = flow.reply(results)["shifts"]
    assert len(shifts) == 1 and [op["id"] for op in shifts[0]["patch"]["ties"]] == ["ties.1", "ties.2"]                          # one patch: the spotlight tie and ties.2


def test_the_judge_reads_the_touched_tie_and_not_the_spotlight_tie_or_the_planned_outcome():
    req = TWO()
    req["beat"]["outcome"] = "reached"
    flow, results = to_touched(req)
    results.append(NAMES_BOTH)
    flow.next(results)
    results.append(EDGE("to bury the ledger"))
    check = flow.next(results)
    assert check.name == "edge_check" and "from Suvi to The Board" in check.text(1.0) and "from Marit" not in check.text(1.0)
    results.append(OK)
    judge = flow.next(results)
    text = judge.text(1.0)
    assert judge.name == "advance_edge" and "Suvi toward The Board, bond: clerk of" in text and "to bury the ledger" in text and "Marit toward Suvi" not in text
    assert gen.planned_outcome_line(req["beat"]) and gen.planned_outcome_line(req["beat"]) not in text


def test_a_check_that_says_no_sends_the_edge_back_once_and_what_comes_back_is_accepted_without_another_check():
    flow, results = to_touched(TWO())
    asked = feed(flow, results, NAMES_BOTH, EDGE("to feel uneasy about the board"), NO)
    assert asked == ["tie_edge", "edge_check", "tie_edge"]
    retry = feed.steps[-1]
    assert "The edge is a mood." in retry.text(1.0) and flow.notes["tie_check_resent"] == 1
    results.append(EDGE("to keep the board from the ledger", "clerk of"))
    judge = flow.next(results)
    assert judge.name == "advance_edge" and "to keep the board from the ledger" in judge.text(1.0)                                # accepted: straight to the judge
    results.append(MOVE("complicates"))
    nxt = flow.next(results)
    assert nxt.name == "tie_edge" and "Dov toward Suvi" in nxt.text(1.0)
    assert flow.tie_ops == [{"op": "replace", "id": "ties.2", "values": {"edge": "to keep the board from the ledger"}}]       # the bond is the old one: left out


def test_a_retry_that_cannot_be_used_keeps_the_first_edge_and_a_tie_with_no_edge_stays_as_it_is():
    flow, results = to_touched(TWO())
    results.append(NAMES_BOTH)
    first = flow.next(results)
    results.append(EDGE("to feel uneasy"))
    flow.next(results)
    results.append(NO)
    retry = flow.next(results)
    assert retry.fallback() == {"edge": "to feel uneasy", "bond": ""}                                                         # the first reply stands if this pass fails
    results.append(retry.fallback())
    assert flow.next(results).name == "advance_edge"
    assert first.fallback() == {"edge": "", "bond": ""}
    flow, results = to_touched(TWO())
    asked = feed(flow, results, NAMES_BOTH, EDGE(""), EDGE("to learn what Suvi hides"), OK, MOVE("complicates"))               # ties.2 got no edge: no check, no judge for it
    assert asked == ["tie_edge", "tie_edge", "edge_check", "advance_edge", None] and [op["id"] for op in flow.tie_ops] == ["ties.3"]


def test_the_operations_make_a_new_entry_when_the_spotlight_shifts_fell_back():
    req = TWO()
    flow = gen.build_flow(req, Kit(req))
    results = ["a chapter", {"happened": "x", "changed": "y"}, {"shifts": []}]
    assert flow.next(results).name == "ties_touched"
    asked = feed(flow, results, NAMES_BOTH, EDGE("to bury the ledger"), OK, MOVE("reverses"), EDGE("to learn more"), OK, MOVE("resolves"))
    assert asked[-1] is None
    shifts = flow.reply(results)["shifts"]
    assert len(shifts) == 1 and shifts[0]["card"] == "entanglements" and [op["id"] for op in shifts[0]["patch"]["ties"]] == ["ties.2", "ties.3"]


def test_a_merge_the_kit_refuses_drops_only_the_touched_ties():
    req = TWO()
    flow, results = to_touched(req)
    flow.kit.shifts_problem = lambda entries: "no" if sum(len(e["patch"]["ties"]) for e in entries) > 1 else None
    feed(flow, results, NAMES_BOTH, EDGE("to bury the ledger"), OK, MOVE("redirects"), EDGE("to learn more"), OK, MOVE("complicates"))
    assert flow.notes["ties_dropped"] is True and flow.notes["ties_rewritten"] == 0
    assert flow.reply(results)["shifts"] == results[2]["shifts"]                                                              # the spotlight tie's shifts alone


def test_no_tie_step_runs_for_ties_the_chapter_did_not_touch():
    flow, results = to_touched(TWO())
    assert feed(flow, results, {"touched": []}) == [None] and flow.tie_ops == [] and flow.reply(results)["shifts"] == results[2]["shifts"]


def run_through_the_server(req: dict, *replies):
    engine = FakeEngine()
    engine.script(*replies)
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        response = post(base_url, req)
        body = response.json()
        assert response.status_code == 200 and body["ok"] is True, body
        assert wait_idle(base_url)
    return contract.parse_reply("generate", body), engine


def test_a_fake_engine_run_with_several_people_gives_one_patch_for_the_spotlight_tie_and_the_touched_ties():
    req = TWO()
    text, events, shifts, check, judge, *_ = gen.script(req, Kit(req))
    names = json.dumps(NAMES_BOTH)
    first, second = json.dumps(EDGE("to bury the ledger before the board counts")), json.dumps(EDGE("to learn what Suvi hides"))
    reply, engine = run_through_the_server(req, text, events, shifts, check, judge, names, first, json.dumps(OK), json.dumps(MOVE("redirects")), second, json.dumps(OK), json.dumps(MOVE("same")))
    entries = [s for s in reply.shifts if s.card == "entanglements"]
    assert len(reply.shifts) == 1 and [op.id for op in entries[0].patch["ties"]] == [req["beat"]["spotlight"], "t1000002"]       # handles came back as the ids the page sent
    assert entries[0].patch["ties"][1].values["edge"] == "to bury the ledger before the board counts"
    assert engine.calls == 12 and "Dov toward Suvi" in engine.prompts[9]


def test_the_trace_shows_the_touched_step_and_per_tie_calls_only_for_touched_ties():
    from pulpermill.backend import runner
    from pulpermill.backend.engine.base import CancelFlag
    from pulpermill.backend.pipelines import RunContext
    req = TWO()
    text, events, shifts, check, judge, *_ = gen.script(req, Kit(req))
    engine = FakeEngine()
    engine.script(text, events, shifts, check, judge, json.dumps({"touched": [NAMES_BOTH["touched"][1]]}), json.dumps(EDGE("to learn more about the board")), json.dumps(OK), json.dumps(MOVE("complicates")))
    ctx = RunContext(engine, CancelFlag(), [].append, Config())
    ctx.notes["call"] = "generate"
    flow = gen.build_flow(req, Kit(req))
    reply = flow.reply(runner.run_flow(ctx, flow, "en"))
    assert [p["step"] for p in ctx.notes["passes"]] == ["write", "events", "shifts", "edge_check", "advance_edge", "ties_touched", "tie_edge", "edge_check", "advance_edge"]
    assert ctx.notes["flow"]["ties_touched"] == 1 and ctx.notes["flow"]["ties_rewritten"] == 1 and ctx.notes["flow"]["ties_same"] == 0
    assert [op["id"] for op in reply["shifts"][0]["patch"]["ties"]] == ["ties.1", "ties.3"]


@pytest.mark.skipif(not __import__("pulpermill.prompts.tokens", fromlist=["available"]).available(), reason="the tokenizer files are not installed")
def test_every_step_at_its_heaviest_fits_the_context_with_four_touched_ties(monkeypatch):
    from pulpermill.prompter.mill import advance
    from pulpermill.prompts import budget
    monkeypatch.setattr(advance, "ENFORCE", True)
    req = request(*[tie(f"t10001{n:02d}", "c0000003", "c0000001", edge="to keep going. " * 20) for n in range(6)])
    flow = gen.build_flow(req, Kit(req))
    steps = flow.worst_case()
    assert [s.name for s in steps][9:] == ["tie_edge", "edge_check", "tie_edge", "advance_edge"] * gen.TOUCH_CAP                  # four candidates, each could be touched
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert all(m.ok for m in measures) and len(measures) == len(steps)
