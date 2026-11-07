"""A10: the items a fill writes carry their key fields (grammar and backstop), every item field has a meaning sentence, and a bond reads from
the from end."""
import copy
import json
from pathlib import Path

import pytest

from pulpermill.backend import grammar
from pulpermill.backend.kit import Kit
from pulpermill.prompter.mill import common, fill
from pulpermill.prompts import textfiles as tx
from pulpermill.schema import CARDS

CHARS = [{"name": "Pim"}, {"name": "Orla"}]
WORLD = {"name": "Millbrook", "places": [{"name": "The Millpond"}], "objects": [{"name": "The Oven"}], "powers": [{"name": "The Parish Council"}]}


def request(card, **over):
    related = {"characters": CHARS, "world": WORLD} if card == "entanglements" else {"characters": CHARS} if card == "world" else {}
    r = {"call": "fill", "schema_version": 4, "language": "en", "card": card, "instance": None, "note": "A note.", "example_chapter": None,
         "values": {}, "related": related}
    r.update(over)
    return r


def item_of(schema, key):
    node = schema["properties"][key]["items"]
    return node if "properties" in node else node["anyOf"][0]


# ---- the grammar ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("card,key,fields", [
    ("entanglements", "ties", ["tie_from", "tie_to", "bond", "edge"]),
    ("entanglements", "holdings", ["holdee", "held_by"]),
    ("world", "rules", ["statement", "cost", "when_broken"]),
    ("world", "powers", ["name", "nature", "hold", "felt"]),
    ("world", "places", ["name", "description", "effect"]),
    ("world", "objects", ["name", "description", "significance"]),
    ("world", "terms", ["term", "meaning"]),
    ("characters", "wants", ["text"]),
    ("characters", "values", ["text"]),
    ("characters", "behaviors", ["state", "tendency"]),
])
def test_the_fill_grammar_requires_the_key_fields_of_every_list_item(card, key, fields):
    item = item_of(grammar.fill(request(card)), key)
    assert sorted(item["required"]) == sorted(fields) and item["additionalProperties"] is False


@pytest.mark.parametrize("card", ["style", "characters", "world", "entanglements", "setup"])
def test_the_cards_own_fields_are_all_required_and_a_list_may_be_empty(card):
    schema = grammar.fill(request(card))
    assert schema["required"] == list(schema["properties"])
    for node in schema["properties"].values():
        assert "minItems" not in node


def test_every_list_item_of_every_card_is_whole_as_the_schema_says():
    for card in CARDS:
        for key, field in CARDS[card][0].model_fields.items():
            try:
                needed = fill.item_required(card, key)
            except (IndexError, AttributeError, TypeError):
                continue
            item = item_of(grammar.fill(request(card)), key)
            assert set(item["required"]) == set(needed), (card, key)


def test_the_plan_grammar_is_still_all_required_and_a_shift_replace_still_holds_only_what_changed():
    plan = grammar.plan_beat({"cast": [{"name": "Pim"}], "world": WORLD})
    assert plan["required"] == list(plan["properties"])
    patch_ops = grammar._item_props("entanglements", "ties", ["bond"], {})
    assert list(patch_ops) == ["bond"]
    cleaned = grammar._clean({"type": "object", "properties": {"x": {"type": "array", "items": {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}}}}, None, False)
    assert cleaned["properties"]["x"]["items"]["required"] == [], "without item_required the old behaviour holds"


# ---- the backstop -----------------------------------------------------------------------------------------------------------

def world_reply(**rule):
    return {"name": "Millbrook", "rules": [{"statement": "Quiet at the Millpond.", "cost": "Nobody sings.", "when_broken": "The Council fines you.", **rule}]}


def test_the_empty_statement_of_the_test_7_world_file_is_refused_and_a_full_rule_passes():
    req = request("world")
    bad = world_reply(statement="", cost="Quiet at the Millpond", when_broken="Applewood is not wasted")
    line = fill.fill_problem(req, bad)
    assert line and "rules" in line and "statement" in line
    assert fill.fill_problem(req, world_reply()) is None


def test_an_empty_group_nature_and_an_empty_tie_end_are_named():
    req = request("world")
    line = fill.fill_problem(req, {"powers": [{"name": "The Council", "nature": "  ", "hold": "law", "felt": "fines"}]})
    assert line and "powers" in line and "nature" in line
    req = request("entanglements")
    line = fill.fill_problem(req, {"ties": [{"tie_from": "", "tie_to": "Orla", "bond": "mother", "edge": "to bring her home"}]})
    assert line and "ties" in line and "tie_from" in line
    line = fill.fill_problem(req, {"holdings": [{"holdee": "The Oven"}]})
    assert line and "holdings" in line and "held_by" in line


def test_every_refusal_text_is_plain_and_says_what_to_change():
    line = fill.fill_problem(request("world"), world_reply(statement=""))
    assert line == "Every item in rules needs a statement: write it for each item, or leave the item out."


# ---- the wording ------------------------------------------------------------------------------------------------------------

def test_every_field_inside_a_list_item_has_a_meaning_sentence():
    w = common.load_text("fill")["item_fields"]
    for card in CARDS:
        text = tx.schema_text(card)["fields"]
        for key, field in text.items():
            keys = field.get("item_fields")
            if not isinstance(keys, list) or not keys:
                continue
            assert set(w[card][key]) == set(keys), (card, key)
            assert all(isinstance(v, str) and len(v.split()) >= 4 for v in w[card][key].values()), (card, key)
    # nothing is orphaned: every wording entry points at a real item field
    for card, lists in w.items():
        for key, fields in lists.items():
            assert set(fields) == set(tx.schema_text(card)["fields"][key]["item_fields"]), (card, key)


def test_the_item_fields_are_printed_under_their_list():
    text = fill.field_guidance("world", ["rules", "powers"])
    rules = text.split("rules: ")[1].split("\n\n")[0]
    assert "Every item holds:" in rules and "  statement: The fact itself, in one plain sentence" in rules
    assert "  cost: " in rules and "  when_broken: " in rules
    powers = text.split("powers: ")[1]
    assert "  nature: " in powers and "  hold: " in powers and "  felt: " in powers


def test_the_bond_reads_from_the_from_end_and_the_edge_is_what_the_from_end_wants():
    prompt = fill.build_prompt(request("entanglements"), Kit(request("entanglements")))
    assert "reads from the from end" in prompt and "what the from end is to the to end" in prompt
    assert "mother" not in prompt                         # the direction is carried by the rule, with no sample tie
    assert "What the from end wants in this tie" in prompt
    # code cannot tell which way a bond reads, so no check exists for direction: the wording carries it
