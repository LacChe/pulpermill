"""B2, the judge call: the prompt of every model-judged rule, the polarity and whole-list rules, the once-each check, and the whole call
through the real server and runner on a scripted fake engine (no model)."""
import json
import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "backend"))

from pulpermill import contract  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter import load_prompter  # noqa: E402
from pulpermill.prompter.mill import common, judge  # noqa: E402
from pulpermill.prompts import budget, textfiles as tx, tokens  # noqa: E402
from pulpermill.schema import CARDS  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
JUDGES = [v for v in VECTORS if v["valid"] and v["data"]["call"] == "judge"]


def values_for(card: str, rule_fields: list[str]) -> dict:
    """Plausible values for the fields a rule looks at: text for a scalar, three items with ids for a list."""
    spec = tx.schema_text(card)["fields"]
    out = {}
    for key in rule_fields:
        item_fields = (spec.get(key) or {}).get("item_fields")
        if item_fields:
            out[key] = [{"id": f"x{key[:2]}{n:05d}", **{k: f"{k} {n}" for k in item_fields if k not in ("tie_from", "tie_to", "holdee", "held_by")}} for n in (1, 2, 3)]
            if key == "ties":
                for n, t in enumerate(out[key], 1):
                    t.update(tie_from="c0000001", tie_to="c0000002")
            if key == "holdings":
                for t in out[key]:
                    t.update(holdee="o0000001", held_by="c0000001")
        else:
            out[key] = f"A text for {key}."
    return out


def judge_request(card: str, rule_id: str, fields: list[str]) -> dict:
    values = values_for(card, fields)
    if card == "characters":
        values.update(id="c0000001", name="Imre")
    related = {"characters": [{"id": "c0000001", "name": "Imre"}, {"id": "c0000002", "name": "Teodora"}], "world": {"objects": [{"id": "o0000001", "name": "The Lattice"}]}} \
        if card == "entanglements" else {}
    return {"call": "judge", "schema_version": 3, "language": "en", "card": card, "instance": "c0000001" if card == "characters" else None,
            "rules": [{"id": rule_id, "fields": fields}], "values": values, "related": related}


MODEL_RULES = [(card, rule.id, list(rule.fields)) for card, entry in CARDS.items() if card in ("style", "characters", "world", "entanglements", "setup")
               for rule in entry[3] if rule.needs_model]


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


# ---- the prompt of every model-judged rule ---------------------------------------------------------------------------------------

def test_every_model_judged_rule_is_covered_and_has_a_polarity_that_exists():
    assert len(MODEL_RULES) >= 20
    w = common.load_text("judge")
    known = {rid for _, rid, _ in MODEL_RULES}
    assert set(w["ok_when_no"]) <= known and set(w["fires_when_none_ok"]) <= known


@pytest.mark.parametrize("card,rule_id,fields", MODEL_RULES, ids=[r for _, r, _ in MODEL_RULES])
def test_each_rules_prompt_holds_its_question_its_items_with_handles_and_the_once_each_instruction(card, rule_id, fields):
    request = judge_request(card, rule_id, fields)
    kit = Kit(request)
    flow = judge.build_flow(request, kit)
    assert flow.steps, rule_id                                              # the rule has something to look at
    rule, handles = flow.steps[0]
    text = flow.prompt(rule, handles)
    question = tx.schema_text(card)["rules"][rule_id]["judge_prompt"]
    assert question.split(".")[0].split("?")[0][:40] in text
    for handle in handles:
        assert f"\n{handle}: " in text, handle
    for ident in ids_in(request):
        assert ident not in text, ident
    assert "exactly once, in the order listed" in text and "Reply with the JSON object only" in text
    assert not re.search(r"\b(rewrite|suggest|propose)\b", text.split("The question:")[1].split("The items")[0], re.I)    # the call answers, it does not rewrite


# ---- polarity and whole-list rules ----------------------------------------------------------------------------------------------

def test_a_question_asked_so_that_yes_is_the_problem_tells_the_model_which_way_ok_goes():
    request = judge_request("world", "object_unowned", ["objects"])
    flow = judge.build_flow(request, Kit(request))
    assert "Set ok to true when your answer to the question is no" in flow.prompt(*flow.steps[0])
    request = judge_request("world", "object_has_stakes", ["objects"])
    flow = judge.build_flow(request, Kit(request))
    assert "Set ok to true when your answer to the question is yes" in flow.prompt(*flow.steps[0])


def test_items_are_shown_as_prose_with_their_names_and_without_ids():
    request = judge_request("entanglements", "tie_edge_is_live", ["ties"])
    text = (lambda f: f.prompt(*f.steps[0]))(judge.build_flow(request, Kit(request)))
    assert "ties.1: Imre toward Teodora, bond: bond 1. Edge: edge 1" in text
    request = judge_request("characters", "behavior_is_tendency", ["behaviors"])
    text = (lambda f: f.prompt(*f.steps[0]))(judge.build_flow(request, Kit(request)))
    assert "behaviors.1: when state 1, they tendency 1" in text and "The card is the Character card of Imre." in text


def reply_for(rule_id, card, fields, oks):
    request = judge_request(card, rule_id, fields)
    flow = judge.build_flow(request, Kit(request))
    handles = flow.steps[0][1]
    return flow.reply([{"checks": [{"item": h, "ok": ok} for h, ok in zip(handles, oks)]}])["results"][0]["hits"]


def test_a_per_item_rule_hits_each_failed_item_and_a_whole_list_rule_fires_only_when_none_passes():
    assert reply_for("object_has_stakes", "world", ["objects"], [True, False, False]) == [
        {"field": "objects", "item": "objects.2", "key": None}, {"field": "objects", "item": "objects.3", "key": None}]
    assert reply_for("object_has_stakes", "world", ["objects"], [True, True, True]) == []
    assert reply_for("behaviors_include_calm", "characters", ["behaviors"], [False, True, False]) == []          # one calm state is enough
    assert reply_for("behaviors_include_calm", "characters", ["behaviors"], [False, False, False]) == [{"field": "behaviors", "item": None, "key": None}]
    assert reply_for("wants_conflict", "characters", ["wants"], [False, False, False]) == [{"field": "wants", "item": None, "key": None}]
    assert reply_for("wants_conflict", "characters", ["wants"], [True, False, False]) == []


def test_a_rule_with_nothing_to_look_at_has_no_step_and_no_hits():
    request = judge_request("world", "object_has_stakes", ["objects"])
    request["values"] = {"name": "Tern Station"}
    flow = judge.build_flow(request, Kit(request))
    assert flow.steps == [] and flow.next([]) is None and flow.reply([]) == {"results": [{"rule": "object_has_stakes", "hits": []}]}


# ---- the check -------------------------------------------------------------------------------------------------------------------

def test_the_check_wants_each_item_answered_exactly_once():
    request = judge_request("world", "object_has_stakes", ["objects"])
    step = judge.build_flow(request, Kit(request)).next([])
    a, b, c = "objects.1", "objects.2", "objects.3"
    ok = lambda *items: {"checks": [{"item": i, "ok": True} for i in items]}
    assert step.check(ok(a, b, c)) is None and step.check(ok(c, a, b)) is None
    assert "left out objects.3" in step.check(ok(a, b, b))
    assert "objects.2 came up more than once" in step.check(ok(a, b, b, c))
    assert step.kind == "json" and step.sampling == "structured" and step.language is False


# ---- squeeze and fit ---------------------------------------------------------------------------------------------------------------

@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
def test_every_rule_step_at_its_heaviest_fits_the_context():
    request = judge_request("world", "object_has_stakes", ["objects", "places"])
    request["values"]["objects"] = [{"id": f"o{n:07d}", "name": f"Thing {n}", "description": "Long. " * 400, "significance": "Long. " * 400} for n in range(1, 13)]
    request["rules"] = [{"id": "object_has_stakes", "fields": ["objects"]}, {"id": "object_unowned", "fields": ["objects"]}]
    flow = judge.build_flow(request, Kit(request))
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert len(measures) == 2 and all(m.ok for m in measures)
    assert all(len(s.text(0.3)) <= len(s.text(1.0)) for s in flow.worst_case())


# ---- the whole call --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("vector", JUDGES, ids=lambda v: v["name"])
def test_every_judge_vector_is_answered_through_the_real_server_on_the_mill_prompter(vector):
    request = vector["data"]
    engine = FakeEngine()
    engine.script(*judge.script(request, Kit(request)))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        response = post(base_url, request)
        body = response.json()
        assert response.status_code == 200 and body["ok"] is True, body
        assert [r.rule for r in contract.parse_reply("judge", body).results] == [r["id"] for r in request["rules"]]
        assert wait_idle(base_url)
    assert engine.calls >= 1 and engine.prompts[0].startswith("You are a careful reviewer")


def test_several_rules_on_one_card_are_asked_one_step_each():
    request = judge_request("world", "object_has_stakes", ["objects"])
    request["rules"] = [{"id": "object_has_stakes", "fields": ["objects"]}, {"id": "object_unowned", "fields": ["objects"]}, {"id": "history_no_people", "fields": ["history"]}]
    request["values"]["history"] = "A famine."
    engine = FakeEngine()
    engine.script(*judge.script(request, Kit(request)))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        body = post(base_url, request).json()
        assert body["ok"] is True and [r["rule"] for r in body["results"]] == ["object_has_stakes", "object_unowned", "history_no_people"]
        assert wait_idle(base_url)
    assert engine.calls == 3


def test_the_version_follows_the_wording():
    assert "+judge:judge-1:" in load_prompter("mill").version
