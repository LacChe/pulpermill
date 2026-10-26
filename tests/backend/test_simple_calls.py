"""fill, judge and style_fit through the shared call, with scripted replies on the fake engine."""
import json
from pathlib import Path

import pytest

from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.engine.base import CancelFlag
from pulpermill.backend.errors import BackendError
from pulpermill.backend.pipelines import RunContext, simple
from pulpermill.schema import contract

VECTORS = {r["name"]: r["data"] for r in json.loads((Path(__file__).parents[2] / "web/tests/contract-vectors.json").read_text())["requests"]
           if r["valid"]}


def vector(name):
    return contract.parse_request(VECTORS[f"the page's {name} request"])


def ctx_with(*outputs):
    engine = FakeEngine()
    engine.script(*outputs)
    return RunContext(engine, CancelFlag(), lambda stage: None, Config()), engine


def test_fill_returns_the_models_values_and_passes_the_contract():
    ctx, engine = ctx_with(json.dumps({"protagonist": "Suvi", "goal": "Find the ledger."}))
    reply = simple.fill(vector("fill_setup"), ctx)
    assert reply == {"ok": True, "values": {"protagonist": "Suvi", "goal": "Find the ledger."}}
    contract.parse_reply("fill", reply)
    assert engine.constraints[0]["properties"]["protagonist"]["enum"] == ["Suvi"]       # a link can only name what was sent
    assert "Suvi must find the ledger." in engine.prompts[0]


def test_fill_may_come_back_empty_and_a_name_outside_the_list_is_retried():
    ctx, _ = ctx_with("{}")
    assert simple.fill(vector("fill_setup"), ctx)["values"] == {}
    ctx, engine = ctx_with(json.dumps({"protagonist": "Nobody"}), json.dumps({"protagonist": "Suvi"}))
    reply = simple.fill(vector("fill_setup"), ctx)
    assert reply["values"] == {"protagonist": "Suvi"} and engine.calls == 2
    assert "Nobody" in engine.prompts[1] and "protagonist" in engine.prompts[1]     # the problem names the field; the reply is not copied wholesale


def test_fill_that_fails_twice_is_bad_output():
    ctx, _ = ctx_with("[]", "not json")
    with pytest.raises(BackendError) as e:
        simple.fill(vector("fill_setup"), ctx)
    assert e.value.kind == "bad_output"


def test_a_character_fill_reads_its_list_fields():
    ctx, _ = ctx_with(json.dumps({"name": "Suvi", "age": 31, "sex": "female", "wants": [{"text": "the ledger"}]}))
    reply = simple.fill(vector("fill_character"), ctx)
    contract.parse_reply("fill", reply)
    assert reply["values"]["wants"] == [{"text": "the ledger"}]


def test_judge_gives_one_result_per_rule_and_each_pass_is_measured_first():
    request = vector("judge_world")
    ctx, engine = ctx_with(json.dumps({"hits": [{"field": "everyday_life", "item": None}]}))
    reply = simple.judge(request, ctx)
    contract.parse_reply("judge", reply)
    assert [r["rule"] for r in reply["results"]] == [rule.id for rule in request.rules]
    assert reply["results"][0]["hits"] == [{"field": "everyday_life", "item": None, "key": None}]
    ctx, _ = ctx_with(json.dumps({"hits": []}))
    assert simple.judge(request, ctx)["results"][0]["hits"] == []


def test_judge_with_a_field_the_rule_did_not_ask_about_is_retried():
    ctx, engine = ctx_with(json.dumps({"hits": [{"field": "elsewhere", "item": None}]}), json.dumps({"hits": []}))
    assert simple.judge(vector("judge_world"), ctx)["results"][0]["hits"] == [] and engine.calls == 2


def test_style_fit_both_ways():
    ctx, _ = ctx_with(json.dumps({"fits": True, "message": "ignored"}))
    assert simple.style_fit(vector("style_fit"), ctx) == {"ok": True, "fits": True, "message": ""}
    ctx, _ = ctx_with(json.dumps({"fits": False, "message": "  Look at how guarded she is.  "}))
    reply = simple.style_fit(vector("style_fit"), ctx)
    assert reply == {"ok": True, "fits": False, "message": "Look at how guarded she is."}
    contract.parse_reply("style_fit", reply)


def test_a_message_in_the_wrong_language_is_retried():
    english = "She keeps everyone at arm's length and never says what she wants, so a first person voice will feel like it is hiding something from the reader."
    request = contract.parse_request({**VECTORS["the page's style_fit request"], "language": "zh-Hans"})
    ctx, engine = ctx_with(json.dumps({"fits": False, "message": english}), json.dumps({"fits": False, "message": "她总是把人拒之门外，从不说出自己想要什么，所以第一人称的叙述会让读者觉得她在隐瞒什么。"}))
    reply = simple.style_fit(request, ctx)
    assert "她" in reply["message"] and engine.calls == 2


def test_a_prompt_that_is_too_long_is_refused_before_inference():
    base = VECTORS["the page's fill_setup request"]
    request = contract.parse_request({**base, "note": "word " * 20000})
    ctx, engine = ctx_with()
    with pytest.raises(BackendError) as e:
        simple.fill(request, ctx)
    assert e.value.kind == "too_long" and engine.calls == 0
