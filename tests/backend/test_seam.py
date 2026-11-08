"""The seam's own pieces: the prompter loader, handles, the grammars, reply assembly and the stub's script."""
import json
from pathlib import Path

import pytest

from pulpermill import contract
from pulpermill.backend import assemble, grammar, shape
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.handles import Handles, Unresolved
from pulpermill.backend.kit import Kit
from pulpermill.backend.server import create_app
from pulpermill.prompter import CALLS, UnknownPrompter, known_prompters, load_prompter
from pulpermill.prompter.stub import script
from pulpermill.prompter.stub.stub import sample

VECTORS = json.loads((Path(__file__).parents[2] / "tests/shared/contract-vectors.json").read_text())["requests"]


def request(call, name=None):
    return next(v["data"] for v in VECTORS if v["valid"] and v["data"]["call"] == call and (name is None or v["name"] == name))


def test_the_stub_is_loaded_by_name_and_an_unknown_name_stops_startup_with_the_known_ones():
    stub = load_prompter("stub")
    assert stub.name == "stub" and stub.version and "stub" in known_prompters()
    assert Config().prompter == "stub"
    for bad in ("nope", "", "../stub", "Stub"):
        with pytest.raises(UnknownPrompter, match="stub"):
            load_prompter(bad)
    with pytest.raises(UnknownPrompter):
        create_app(Config(prompter="nope"), FakeEngine())


def test_the_stub_has_a_flow_for_every_call_and_nothing_else():
    for call in CALLS:
        req = request(call)
        flow = load_prompter("stub").flow(call, req, Kit(req))
        assert flow.worst_case() and flow.next([]) is not None
    with pytest.raises(ValueError):
        load_prompter("stub").flow("offstage", {}, None)


def test_the_stub_prompts_follow_the_squeeze():
    req = request("fill")
    flow = load_prompter("stub").flow("fill", req, Kit(req))
    step = flow.next([])
    assert len(step.text(0.5)) < len(step.text(1.0)) and step.text(1.0).startswith("Stub prompt")


def test_a_handle_stands_for_one_item_that_was_sent_and_nothing_else():
    req = request("generate")
    handles = Handles(req)
    suvi = handles.scope("characters", "Suvi")
    assert suvi.handles("wants") == ["wants.1"] and suvi.item("wants.1", "wants") == "w0000001" and suvi.of("wants", "w0000001") == "wants.1"
    for bad in ("wants.2", "wants.0", "wants", "ties.1", "nonsense", None):
        with pytest.raises(Unresolved):
            suvi.item(bad, "wants")
    with pytest.raises(Unresolved):
        handles.scope("characters", "Nobody")


def test_two_characters_with_one_name_are_told_apart():
    req = {**request("generate"), "cast": [{"id": "a1", "name": "Ana"}, {"id": "a2", "name": "Ana"}]}
    assert [s.label for s in Handles(req).of_card("characters")] == ["Ana", "Ana (2)"]
    assert Handles(req).scope("characters", "Ana (2)").target == "a2"


def test_the_shifts_grammar_names_only_the_ties_that_were_sent_and_their_edge():
    req = request("generate")
    kit = Kit(req)
    g = kit.grammar.shifts()
    text = json.dumps(g)
    assert "Marit" not in text and '"ties.2"' in text and "wants" not in text and "places" not in text and "holdings" not in text
    assert '"const": "replace"' in text and '"const": "add"' not in text and '"const": "remove"' not in text
    assert g["maxItems"] == 1
    ok = json.loads(script("generate", req, kit)[2])["shifts"]
    assert shape.problems(ok, g) == [] and kit.shifts_problem(ok) is None
    assert [s["card"] for s in ok] == ["entanglements"]
    ops = [op for s in ok for v in s["patch"].values() for op in v]
    assert {op["op"] for op in ops} == {"replace"} and all(set(op["values"]) == {"edge"} for op in ops)


def test_a_patch_has_no_property_for_a_list_with_no_items_but_still_offers_a_scalar():
    from pulpermill.backend import grammar
    req = request("generate")
    req = {**req, "cast": [{**c, "wants": [], "behaviors": []} if isinstance(c, dict) else c for c in req.get("cast") or []]}
    h = Handles(req)
    scope = h.of_card("characters")[0]
    props = grammar.patch("characters", scope, {})["properties"]
    assert "wants" not in props and "sketch" in props


def test_a_reply_that_points_at_something_not_sent_is_not_usable():
    req = request("generate")
    kit = Kit(req)
    good = json.loads(script("generate", req, kit)[2])["shifts"]
    bad_handle = json.loads(json.dumps(good))
    bad_handle[0]["patch"]["ties"][0]["id"] = "ties.9"
    assert shape.problems(bad_handle, kit.grammar.shifts()) and kit.shifts_problem(bad_handle)
    twice = good + [good[0]]
    assert "two entries" in kit.shifts_problem(twice)
    people = [{"card": "characters", "target": "Suvi", "patch": {"fear": "fire"}}]
    assert shape.problems(people, kit.grammar.shifts()) and kit.shifts_problem(people)      # a chapter does not change people
    world = [{"card": "world", "patch": {"history": "A flood."}}]
    assert shape.problems(world, kit.grammar.shifts()) and kit.shifts_problem(world)         # nor the world
    bond = [{"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": "ties.1", "values": {"bond": "x"}}]}}]
    assert shape.problems(bond, kit.grammar.shifts())                                        # a bond alone is not a reply: the edge is required
    both = [{"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": "ties.1", "values": {"edge": "to leave", "bond": "x"}}]}}]
    assert not shape.problems(both, kit.grammar.shifts()) and kit.shifts_problem(both) is None   # an edge may carry a new bond
    ends = [{"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": "ties.1", "values": {"edge": "to leave", "tie_to": "x"}}]}}]
    assert shape.problems(ends, kit.grammar.shifts()) and kit.shifts_problem(ends)           # a tie's ends do not change
    assert kit.shifts_problem([{"card": "entanglements", "patch": {}}]) is None               # nothing changed: no entry
    assert assemble.shifts([{"card": "entanglements", "patch": {}}], kit.handles) == []


def test_assembled_shifts_carry_the_ids_the_page_sent_and_pass_the_contract():
    req = request("generate")
    kit = Kit(req)
    draft = {"chapter_text": "x", "events": {"happened": " Happened. ", "changed": " "}, "shifts": json.loads(script("generate", req, kit)[2])["shifts"]}
    out = assemble.reply("generate", draft, kit.handles)
    contract.parse_reply("generate", out)
    assert out["events"] == {"happened": "Happened.", "changed": None}
    ids = {op["id"] for s in out["shifts"] for v in s["patch"].values() if isinstance(v, list) for op in v if "id" in op}
    assert ids <= {"t1000001", "t1000002"} and "t1000001" in ids
    assert all(s["card"] == "entanglements" and s["target"] is None for s in out["shifts"])


def test_a_judge_hit_names_the_item_id_and_a_handle_that_was_not_sent_is_refused():
    req = {**request("judge"), "card": "world", "instance": None, "rules": [{"id": "r", "fields": ["places"]}],
           "values": {"name": "W", "places": [{"id": "p1", "name": "A", "description": "d", "effect": "e"}, {"id": "p2", "name": "B", "description": "d", "effect": "e"}]}}
    contract.parse_request(req)
    kit = Kit(req)
    scope = kit.handles.only()
    field = "places"
    ok = assemble.reply("judge", {"results": [{"rule": "r", "hits": [{"field": field, "item": f"{field}.1", "key": None}]}]}, kit.handles)
    assert ok["results"][0]["hits"][0]["item"] == scope.lists[field][0]
    with pytest.raises(Unresolved):
        assemble.reply("judge", {"results": [{"rule": "r", "hits": [{"field": field, "item": f"{field}.99", "key": None}]}]}, kit.handles)
    with pytest.raises(Unresolved):
        assemble.reply("judge", {"results": [{"rule": "r", "hits": [{"field": "other", "item": f"{field}.1", "key": None}]}]}, kit.handles)


def test_the_fill_and_plan_grammars_limit_links_to_the_names_sent():
    plan = request("plan")
    beat = grammar.plan_beat(plan)
    assert set(beat["required"]) == {"where", "when_time", "aim", "plan"} and beat["properties"]["where"]["enum"] == ["The Archive", "The Quay"]
    fill = grammar.fill(request("fill"))
    assert fill["properties"]["protagonist"]["enum"] == ["Suvi"] and fill["required"] == list(fill["properties"]) and shape.problems(sample(fill), fill) == []
    assert shape.problems({"protagonist": "Marit"}, fill)
    assert shape.problems({}, fill), "every field of the card is asked for"
    assert "id" not in json.dumps(grammar.fill({**request("fill"), "card": "characters", "instance": "c1"})["properties"]["wants"])


def test_the_samples_the_stub_makes_are_valid_for_their_grammars():
    for call in ("fill", "plan"):
        req = request(call)
        g = grammar.fill(req) if call == "fill" else grammar.plan_beat(req)
        assert shape.problems(sample(g), g) == []
    for card in ("style", "characters", "world", "entanglements", "setup"):
        req = {**request("fill"), "card": card, "instance": "c1" if card == "characters" else None}
        g = grammar.fill(req)
        assert shape.problems(sample(g), g) == [], card


def test_every_schema_field_that_may_be_shifted_has_a_grammar():
    from pulpermill.schema.shifts import SHIFT_CARDS, shiftable_fields
    req = request("generate")
    handles = Handles(req)
    for card in SHIFT_CARDS:
        scope = handles.of_card(card)[0]
        p = grammar.patch(card, scope, grammar.link_names(["Suvi"], req["world"]))
        # a scalar always; a list only when the scope sent items to replace
        assert set(p["properties"]) == {f["key"] for f in shiftable_fields(card) if f["type"] == "scalar" or scope.handles(f["key"])}
