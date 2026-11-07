"""The end-of-story call's backend half: what the grammar lets a model write, and what assemble turns into the contract's reply. Driven with
the vectors' finish request and its characters (Suvi has a want and a behaviour with ids, Marit has none)."""
import copy
import json
from pathlib import Path

import pytest

from pulpermill.backend import assemble, grammar
from pulpermill.backend.handles import Handles, Unresolved
from pulpermill.backend.kit import Kit
from pulpermill.backend.shape import problems

REPO = Path(__file__).resolve().parents[2]
VECTORS = json.loads((REPO / "tests" / "shared" / "contract-vectors.json").read_text(encoding="utf-8"))["requests"]
REQUEST = next(r["data"] for r in VECTORS if r["name"] == "a finish request carries the summaries and the base characters")


def entry(target="Suvi", **patch) -> dict:
    return {"card": "characters", "target": target, "patch": patch or {"fear": "Being left with nobody to tell"}}


def test_a_character_entry_is_turned_into_the_contract_shape_with_the_id_that_was_sent():
    out = assemble.finish_shifts([entry()], Handles(REQUEST))
    assert out == [{"card": "characters", "target": "c0000001", "patch": {"fear": "Being left with nobody to tell"}}]


def test_a_list_item_is_pointed_at_by_its_handle_and_comes_back_as_its_id():
    out = assemble.finish_shifts([entry(wants=[{"op": "replace", "id": "wants.1", "values": {"text": "To let her mother in"}}])], Handles(REQUEST))
    assert out[0]["patch"] == {"wants": [{"op": "replace", "id": "w0000001", "values": {"text": "To let her mother in"}}]}


def test_nobody_changing_is_a_valid_end_and_an_empty_patch_is_left_out():
    assert assemble.finish_shifts([], Handles(REQUEST)) == []
    assert assemble.finish_shifts([{"card": "characters", "target": "Suvi", "patch": {}}], Handles(REQUEST)) == []


def test_every_person_may_have_an_entry_however_many_there_are():
    request = copy.deepcopy(REQUEST)
    request["characters"] = [{"id": f"c{n:07d}", "name": f"Person {n}", "sketch": "x"} for n in range(1, 11)]
    request["protagonist"] = "c0000001"
    out = assemble.finish_shifts([entry(f"Person {n}", fear="New fear") for n in range(1, 11)], Handles(request))
    assert len(out) == 10      # more than the seven a chapter may hold: the last beat is exempt


@pytest.mark.parametrize("bad,match", [
    ([entry(), entry(flaw="Another")], "two entries"),
    ([entry("Nobody")], "not a card you were shown"),
    ([{"card": "characters", "patch": {"fear": "x"}}], "a character is needed"),
    ([{"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": "ties.1", "values": {"edge": "x"}}]}}], "only the characters"),
    ([{"card": "world", "patch": {"history": "x"}}], "only the characters"),
    ([entry(name="Suvi Two")], "fixed"),
    ([entry(age=40)], "fixed"),
    ([entry(wants=[{"op": "replace", "id": "wants.9", "values": {"text": "x"}}])], "handles you were shown"),
    ([entry(wants=[{"op": "replace", "id": "behaviors.1", "values": {"text": "x"}}])], "handles you were shown"),
    ([entry(fear=3)], "wrong type"),
    ("not a list", "must be a list"),
])
def test_a_bad_draft_is_refused_with_one_plain_line(bad, match):
    with pytest.raises(Unresolved, match=match):
        assemble.finish_shifts(bad, Handles(REQUEST))


def test_the_kit_says_the_problem_in_one_line_and_nothing_when_it_is_fine():
    kit = Kit(REQUEST)
    assert kit.finish_problem([entry()]) is None
    assert "two entries" in kit.finish_problem([entry(), entry(flaw="x")])


def test_the_grammar_offers_each_person_their_own_entry_and_nothing_else():
    schema = Kit(REQUEST).grammar.finish()
    assert schema["type"] == "array" and schema["maxItems"] == 2
    targets = {v["properties"]["target"]["const"] for v in schema["items"]["anyOf"]}
    assert targets == {"Suvi", "Marit"}
    assert all(v["properties"]["card"] == {"const": "characters"} for v in schema["items"]["anyOf"])
    by_name = {v["properties"]["target"]["const"]: v["properties"]["patch"]["properties"] for v in schema["items"]["anyOf"]}
    assert by_name["Suvi"]["wants"]["items"]["properties"]["id"]["enum"] == ["wants.1"]       # her own items only
    assert "wants" not in by_name["Marit"] and "fear" in by_name["Marit"]                     # a person with no items cannot have one replaced
    assert not {"name", "age", "sex", "appearance", "id"} & set(by_name["Suvi"])               # fixed fields are not offered


def test_what_the_grammar_allows_passes_assemble_and_a_second_person_is_not_forced_into_the_first_ones_items():
    kit = Kit(REQUEST)
    schema = kit.grammar.finish()
    good = [entry(wants=[{"op": "replace", "id": "wants.1", "values": {"text": "x"}}]), entry("Marit", flaw="She lets go")]
    assert problems({"shifts": good}, {"type": "object", "properties": {"shifts": schema}, "required": ["shifts"], "additionalProperties": False}) == []
    stray = [entry("Marit", wants=[{"op": "replace", "id": "wants.1", "values": {"text": "x"}}])]
    assert problems({"shifts": stray}, {"type": "object", "properties": {"shifts": schema}, "required": ["shifts"], "additionalProperties": False})


def test_a_request_with_no_characters_has_an_empty_list_grammar():
    schema = grammar.finish({"characters": []}, Handles({"characters": []}))
    assert schema["maxItems"] == 0


def test_the_reply_is_built_by_call_name():
    reply = assemble.reply("finish", {"shifts": [entry()]}, Handles(REQUEST))
    assert reply["ok"] is True and reply["shifts"][0]["target"] == "c0000001"
