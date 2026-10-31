"""Tests for the card renderers (phase 3). No model, no GPU. Run from the repository root: python -m pytest tests/prompts"""
import copy
import json
import re
from pathlib import Path

import yaml

from pulpermill.prompts import (Report, assemble, planner_blocks, render_cast, render_code_numbers, render_entanglements,
                                render_scene, render_setup, render_standing, render_story_so_far, render_style,
                                render_world, writer_blocks)
from pulpermill.prompts import textfiles as tx
from pulpermill.prompts.render import clip, fill, groups_in_play

FIXTURE = Path(__file__).parent / "fixtures" / "salt-coast-generate.json"


def generate_request():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def plan_request():
    """The planner's request, made from the same story: the page sends the same cards plus the spotlight tie and the earlier beats."""
    req = generate_request()
    req["call"] = "plan"
    for key in ("previous_ending", "beat"):
        req.pop(key, None)
    req["spotlight"] = req["ties"][0]["id"]
    req["earlier_beats"] = [{"chapter": 4, "where": "The Shop", "when": "Friday night", "aim": "Learn who the board's clerk reports to", "plan": "A late visit."},
                            {"chapter": 3, "where": "The Docks", "when": "Monday noon", "aim": "Keep the key out of sight", "plan": "A quiet errand."}]
    req["retry"] = None
    return req


def parked(reason):
    """A test of renderer code for a story idea the redesign removed (P0): kept for prompt design, which decides what to reuse."""
    import pytest
    return pytest.mark.skip(reason=f"PARKED(prompt-design): {reason}")


def named(req):
    """The ties and holdings of a request with each id replaced by the name it stands for, as the renderer reads them."""
    names = {c["id"]: c["name"] for c in req["cast"]}
    for key in ("places", "objects", "powers"):
        names.update({i["id"]: i["name"] for i in req["world"].get(key, [])})
    return {"ties": [{**x, "tie_from": names[x["tie_from"]], "tie_to": names[x["tie_to"]]} for x in req["ties"]],
            "holdings": [{**x, "holdee": names[x["holdee"]], "held_by": names[x["held_by"]]} for x in req["holdings"]]}


def all_ids(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "id" and isinstance(v, str):
                found.add(v)
            all_ids(v, found)
    elif isinstance(node, list):
        for v in node:
            all_ids(v, found)
    return found


def whole(req_blocks):
    return assemble(req_blocks)


# ---- The tools ------------------------------------------------------------------------------------------------------

def test_fill_drops_a_clause_with_an_empty_token():
    assert fill("{a}: {b} Next move: {c}", {"a": "X", "b": "Y", "c": ""}) == "X: Y"
    assert fill("{a}: {b} Next move: {c}", {"a": "X", "b": "Y", "c": "Z"}) == "X: Y Next move: Z"


def test_fill_does_not_double_a_full_stop():
    assert fill("{a}. Right now, {b}", {"a": "Alike.", "b": "x"}) == "Alike. Right now, x"


def test_clip_cuts_at_a_sentence_and_says_so():
    report = Report()
    text = "One sentence is here. A second sentence follows it. A third sentence runs on and on."
    out = clip(text, 55, "test", report)
    assert out == "One sentence is here. A second sentence follows it."
    assert report.clips and "test" in report.clips[0]


def test_clip_leaves_a_short_text_alone():
    report = Report()
    assert clip("short", 100, "t", report) == "short" and not report


# ---- Style ----------------------------------------------------------------------------------------------------------

def test_style_writer_has_the_hard_rules_and_each_directive():
    style = generate_request()["style"]
    text = render_style(style, scope="writer")
    texts = tx.schema_text("style")["fields"]
    directives = tx.prompt_text("style_directives")["directives"]
    assert texts["person"]["options"]["first"]["expand"] in text
    assert texts["tense"]["options"]["past"]["expand"] in text
    for key in ("distance", "humor", "pacing", "rhythm", "diction", "attitude", "amount", "directness"):
        value = style[key]
        assert texts[key]["options"][value]["expand"] + " " + directives[key][value] in text
    assert "About the narrator: The narrator is Suvi" in text
    assert "Pekka never finishes" in text
    assert "Let this decide what the narrator notices, in every scene." in text
    assert text.count("\n\n") == 1                   # the schema's two paragraphs


def test_style_planner_sees_only_tone_and_no_directives():
    style = generate_request()["style"]
    text = render_style(style, scope="planner")
    assert "Harbour noir" in text and "She notices what people do with their hands" in text
    assert tx.schema_text("style")["fields"]["humor"]["options"]["dry"]["expand"] in text
    assert "Sentence length" not in text and "understatement and exact observation" not in text   # no directive for the planner
    assert tx.schema_text("style")["fields"]["rhythm"]["options"]["varied"]["expand"] not in text


def test_an_empty_style_axis_leaves_the_model_to_decide():
    text = render_style({"person": "third", "tense": "", "humor": ""}, scope="writer")
    assert "third person" in text and "tense" not in text.lower()


# ---- People ---------------------------------------------------------------------------------------------------------

def test_writer_portrait_has_everything_and_planner_portrait_does_not():
    cast = generate_request()["cast"]
    writer = render_cast(cast, scope="writer")
    planner = render_cast(cast, scope="planner")
    for must in ("is 34 years old", "salt-cracked hands", "Short, flat sentences", "recount the till", "Reads a ledger", "Grew up behind the counter"):
        assert must in writer
    for must in ("Counts everything twice", "Being the one who lets the shop fall", "Reads a ledger", "Grew up behind the counter"):
        assert must in planner
    for gone in ("34 years old", "salt-cracked", "Short, flat sentences", "recount the till"):
        assert gone not in planner
    assert "show the choice" in writer and "show the choice" not in planner


def test_a_long_field_is_clipped_but_the_fixed_appearance_never_is():
    cast = copy.deepcopy(generate_request()["cast"][:1])
    cast[0]["sketch"] = "A sentence of some length goes here. " * 40
    cast[0]["appearance"] = "A long appearance sentence goes on here. " * 40
    report = Report()
    text = render_cast(cast, scope="writer", report=report)
    assert any("sketch" in c for c in report.clips) and not any("appearance" in c for c in report.clips)
    assert text.count("A long appearance sentence goes on here.") == 40


# ---- World ----------------------------------------------------------------------------------------------------------

def test_writer_world_has_the_beats_place_in_full_and_the_other_places_by_name():
    req = generate_request()
    text = render_world(req["world"], scope="writer", place="The Docks", in_play=groups_in_play(named(req)))
    assert "Wet planks, coal dust" in text and "A narrow harbour shop" not in text
    assert "Other places in The Salt Coast: The Shop and The Board House." in text
    assert "Rent is due on the first of the week" in text and "Cost: A missed week" in text
    assert text.index("Rent is due") < text.index("dock repairs were paid") < text.index("floods on the spring tide")      # in the order sent
    assert "first-day visit" in text                   # the writer sees terms
    assert "Used in" not in text and "Not used" not in text and "known only to a few" not in text


def test_a_group_out_of_play_shows_only_how_it_is_felt():
    req = generate_request()
    text = render_world(req["world"], scope="writer", place="The Docks", in_play=groups_in_play(named(req)))
    assert "It holds power by Licensing every boat" in text
    assert "The Dockhands' Brotherhood: Ordinary people feel it as a hush" in text
    assert "Slowing the work down" not in text


def test_planner_world_has_every_place_and_no_terms():
    text = render_world(plan_request()["world"], scope="planner")
    for must in ("Wet planks", "A narrow harbour shop", "A grey stone building"):
        assert must in text
    assert "first-day visit" not in text and "Used in" not in text and "Not used" not in text


# ---- Entanglements --------------------------------------------------------------------------------------------------

def test_writer_entanglements_mark_whoever_is_offstage():
    req = generate_request()
    text = render_entanglements(named(req), ["Suvi", "Aino", "Pekka"], scope="writer")
    assert "Aino toward The Harbour Board [offstage]" in text and "marked [offstage]" in text
    assert "Suvi toward Aino" in text and "Aino [offstage]" not in text
    assert "Pekka holds or controls The ledger." in text
    assert text.index("Ties") < text.index("Who holds")


@parked("knowledge was removed from Entanglements (P0)")
def test_one_knowledge_item_lists_everyone_who_stands_towards_it():
    text = render_entanglements(generate_request()["entanglements"], ["Suvi", "Aino", "Pekka"], scope="writer")
    assert "The cellar under the shop floods on the spring tide. Misled about it: Suvi." in text
    assert "The ledger is in Pekka's rooms. Suspects it: Aino." in text
    line = next(l for l in text.splitlines() if l.startswith("The dock repairs"))
    assert "Knows it: Pekka, Aino." in line and "Misled about it: The Harbour Board." in line
    assert line.endswith("They believe instead: The board paid for the dock repairs."), line


@parked("pressures were removed from Entanglements (P0)")
def test_a_pressure_with_no_next_move_has_no_empty_label():
    text = render_entanglements(generate_request()["entanglements"], ["Suvi"], scope="writer")
    assert "from the season" in text and not re.search(r"Next move:\s*(\n|$)", text)


def test_planner_entanglements_have_no_offstage_marks():
    assert "[offstage]" not in render_entanglements(named(plan_request()), ["Suvi"], scope="planner")


def test_pronouns_agree_with_the_person_in_the_portrait():
    cast = generate_request()["cast"]
    text = render_cast(cast, scope="writer")
    assert "Suvi avoids and protects herself from" in text and "Aino avoids and protects himself from" in text
    assert "sabotages her own aims" in text and "sabotages his own aims" in text
    assert "themselves" not in text
    assert "when she is calm and the shop is quiet, the tendency is to recount the till" in text
    other = [dict(cast[0], sex="other")]
    assert "protects themselves from" in render_cast(other, scope="writer") and "sabotages their own aims" in render_cast(other, scope="writer")


def test_a_value_that_starts_with_a_function_word_continues_the_sentence_and_a_name_keeps_its_capital():
    from pulpermill.prompts.render import soften
    assert soften("She wants to know") == "she wants to know" and soften("The board closed it") == "the board closed it"
    assert soften("Ines learns the name") == "Ines learns the name" and soften("I know") == "I know"
    text = render_entanglements(named(generate_request()), ["Suvi", "Aino", "Pekka"], scope="writer")
    assert "Right now, she wants to know whom he reports to." in text


def test_punctuation_is_tidy_around_the_lines_the_renderers_make():
    req = generate_request()
    world = render_world(req["world"], scope="writer")
    ent = render_entanglements(named(req), ["Suvi"], scope="writer")
    for text in (world, ent):
        assert ".)." not in text and "  " not in text and " ." not in text and ",," not in text


# ---- Setup, standing, the story so far ------------------------------------------------------------------------------

def test_chapter_one_carries_the_normal_and_the_break_and_later_chapters_do_not():
    setup = dict(generate_request()["setup"], normal="The shop opened at six.", disruption="Someone broke in.")
    one = render_setup(setup, None, 1, 8)
    five = render_setup({k: v for k, v in setup.items() if k not in ("normal", "disruption")}, None, 5, 8)
    assert "The shop opened at six." in one and "Someone broke in." in one and "chapter 1 of 8" in one
    assert "shop opened" not in five and "chapter 5 of 8" in five


def test_the_last_chapter_is_said_to_be_the_last():
    text = render_setup(generate_request()["setup"], None, 8, 8)
    assert "last chapter" in text


@parked("the standing record was replaced by shifts (P0 A1)")
def test_standing_is_marked_as_newer_than_the_cards():
    text = render_standing(generate_request()["standing"])
    assert "newer than their portrait" in text and "follow this" in text
    assert "Suvi now believes Pekka sold the ledger's location to the board; has decided to keep the key to herself." in text
    assert render_standing([]) == ""


def test_older_chapters_shrink_to_their_changed_line():
    text = render_story_so_far(generate_request()["earlier_events"], 5, keep_full=3)
    assert "Earlier chapters, in brief:" in text and "Chapter 1: Suvi knows someone has been in the shop at night." in text
    assert "finds the shop's stock miscounted" not in text           # chapter 1 is only its changed line
    assert "Chapter 4. Aino warns Suvi" in text and "By its end: The cellar story is false" in text
    assert "What changed for the protagonist" not in text and "Set up:" not in text


# ---- The scene ------------------------------------------------------------------------------------------------------

def scene(**over):
    req = generate_request()
    beat = dict(req["beat"], **over)
    return render_scene(beat, protagonist="Suvi", sex="female", open_plants=req["open_plants"], available_reveals=req["available_reveals"])


@parked("the old beat (collision goal, shift, ends_on) was reshaped (P0)")
def test_the_scene_reads_as_a_situation_with_the_writers_own_words():
    text = scene()
    assert "The chapter opens at The Docks, Tuesday, just after the shop opens." in text
    assert "Time has passed since the last chapter: Three days later." in text
    assert "Suvi, Aino and Pekka are there." in text
    assert "What Suvi is after: Get Pekka to say where the ledger is." in text
    assert "choose" not in text and "one way" not in text, "the scene sets no fixed choice"
    assert "By the end of the chapter something is different, and the scene's own events are what make it so." in text
    assert "This chapter is harder" in text
    assert "stops on this moment: Suvi finds her own initials" in text
    assert text.rstrip().endswith("yours to invent.")


@parked("reveals, plants and the offstage move were removed (P0)")
def test_the_scene_carries_what_the_beat_names():
    text = scene()
    assert "The belief: The cellar under the shop floods on the spring tide." in text and "The truth: The cellar was sealed" in text
    assert "Who learns it: Suvi and Aino." in text
    assert "Set this up for later" in text and "Pekka keeps a locked back room" in text
    assert "A second lock on the cellar's inner door, set up in chapter 4" in text
    assert "While the cast were elsewhere, the board closed the east market gate." in text
    assert "The pressure in focus is: The board wants the ledger" in text
    assert "Let it meet what Suvi is after, and let the scene decide how that goes" in text
    assert "carries into the next chapter" in text


@parked("the old beat was reshaped (P0)")
def test_the_scene_leaves_out_what_the_beat_does_not_name():
    text = scene(reveal_rule="", reveal_learners=[], plant="", payoff=[], offstage_did="", offstage_reach="",
                 spotlight="", when_gap="")
    for gone in ("learns that", "Set this up", "Pay off", "While the cast", "pressure in focus", "Time has passed"):
        assert gone not in text
    assert "Who learns it" not in scene(reveal_learners=[]), "who learns a reveal is read from the chapter afterwards"


# ---- Whole prompts' material ----------------------------------------------------------------------------------------

@parked("blocks.py is parked story prompt code")
def test_writer_blocks_come_in_a_fixed_order_and_leak_nothing():
    req = generate_request()
    blocks = writer_blocks(req)
    assert [n for n, _ in blocks] == ["style", "world", "people", "entanglements", "standing", "story", "last_ending", "scene"]
    text = assemble(blocks)
    for id_ in all_ids(req):
        assert not re.search(rf"(?<![\w']){re.escape(id_)}(?![\w'])", text), f"id {id_} leaked"
    for bad in ("{", "}", "None", "null", "undefined", "[object"):
        assert bad not in text, bad
    assert not re.search(r"(Next move|Cost|When broken|Why it matters|Right now,|What it does to people there):?\s*(\n|$)", text)
    assert text.index("Where they stand now.") < text.index("Where the story stands")


@parked("blocks.py is parked story prompt code")
def test_planner_blocks_come_in_a_fixed_order_and_leak_nothing():
    req = plan_request()
    blocks = planner_blocks(req)
    assert [n for n, _ in blocks] == ["tone", "world", "people", "entanglements", "standing", "story", "offstage", "code"]
    text = assemble(blocks)
    for id_ in all_ids(req):
        assert not re.search(rf"(?<![\w']){re.escape(id_)}(?![\w'])", text), f"id {id_} leaked"
    for bad in ("{", "}", "None", "null", "undefined"):
        assert bad not in text, bad
    assert "Aino is feeding the board names (from Aino" in text                # the planner sees every pressure
    assert "Plan around it." in text and "Plants still open" in text and "Pekka has not appeared yet" in text
    assert "People believe: The cellar under the shop floods on the spring tide. The truth: The cellar was sealed" in text


@parked("code numbers (plants, reveals, legal shifts) were removed (P0)")
def test_code_numbers_say_what_is_allowed():
    req = plan_request()
    assert "Either kind of chapter is allowed." in render_code_numbers(req)
    req["legal_shifts"] = ["easier"]
    req["open_plants"] = []
    req["available_reveals"] = []
    text = render_code_numbers(req)
    assert "This chapter may be: easier." in text and "No plants are open." in text and "No hidden truth" in text


def test_a_second_render_is_identical():
    req = generate_request()
    assert assemble(writer_blocks(req)) == assemble(writer_blocks(copy.deepcopy(req)))


# ---- The wording files ----------------------------------------------------------------------------------------------

NEGATIVE = re.compile(r"\b(don't|do not|never|avoid|without|must not)\b", re.I)


def test_every_style_option_has_one_directive_and_no_directive_is_orphaned():
    options = {k: set(v["options"]) for k, v in tx.schema_text("style")["fields"].items() if "options" in v}
    directives = tx.prompt_text("style_directives")["directives"]
    skipped = {"person", "tense"}                                         # hard rules; no directive
    assert set(directives) == set(options) - skipped
    for key, found in directives.items():
        assert set(found) == options[key], key
        assert all(isinstance(v, str) and v.strip() for v in found.values())
    assert len(directives["attitude"]) == 7                              # seven separate lines


def test_style_directives_and_writer_frames_use_positive_phrasing():
    for key, found in tx.prompt_text("style_directives")["directives"].items():
        for option, line in found.items():
            assert not NEGATIVE.search(line), f"{key}.{option}: {line}"
    frames = tx.prompt_text("frames")
    for key, value in frames.items():
        if key.startswith(("scene_", "portraits_", "knowledge_", "standing_", "offstage_", "previous_")) and isinstance(value, str):
            assert not NEGATIVE.search(value), f"{key}: {value}"


@parked("reveals and rule status were removed (P0)")
def test_a_hidden_rule_is_a_thing_that_comes_to_light_and_a_myth_is_a_truth_behind_a_belief():
    hidden = scene(reveal_rule="The dock repairs were paid for by the shopkeepers, not the board.", reveal_learners=["Suvi"])
    assert "something hidden comes to light: The dock repairs were paid for by the shopkeepers, not the board." in hidden
    assert "Who learns it: Suvi." in hidden and "The truth:" not in hidden and "The belief:" not in hidden


def test_limits_cover_every_field_the_renderers_clip():
    limits = tx.limits()
    for group, keys in {"characters": ("sketch", "fear", "flaw", "competence", "vulnerability", "speech", "history", "want_item", "value_item",
                                       "behavior_state", "behavior_tendency", "max_behaviors"),
                        "world": ("name", "era_and_technology", "everyday_life", "history", "place_description", "place_effect", "object_description",
                                  "object_significance", "power_nature", "power_hold", "power_felt", "rule_statement", "rule_cost",
                                  "rule_when_broken", "rule_truth", "term_meaning"),
                        "entanglements": ("bond", "edge", "pressure_what", "next_move", "fact"),
                        "setup": ("normal", "disruption", "goal", "stakes"),
                        "events": ("happened", "changed", "full_chapters_writer", "full_chapters_planner"),
                        "beat": ("field",),
                        "standing": ("field",), "code": ("plant",), "offstage": ("field",)}.items():
        for key in keys:
            assert isinstance(limits[group][key], int) and limits[group][key] > 0, f"{group}.{key}"
    assert "appearance" not in limits["characters"]                      # fixed fields have no cap


# ---- The page's own sample requests ---------------------------------------------------------------------------------

VECTORS = Path(__file__).resolve().parents[2] / "tests" / "shared" / "contract-vectors.json"


def vector(name):
    return next(r["data"] for r in json.loads(VECTORS.read_text(encoding="utf-8"))["requests"] if r["name"] == name)


@parked("uses blocks.py, which is parked story prompt code")
def test_the_pages_nearly_empty_requests_render_without_junk():
    for name, make in (("the page's generate request", writer_blocks), ("the page's plan request", planner_blocks)):
        text = assemble(make(vector(name)))
        for bad in ("{", "}", "None", "null", "undefined", "NaN"):
            assert bad not in text, (name, bad)
        assert not re.search(r":\s*\n\s*\n", text), name                  # no lead-in left hanging over nothing
        assert "Suvi" in text


def test_a_beat_with_almost_nothing_still_gives_a_scene():
    text = render_scene({"id": "b1", "chapter": 1, "cast": ["Suvi"], "spotlight": ""}, protagonist="Suvi", sex="female")
    assert "Suvi is there." in text and text.rstrip().endswith("yours to invent.")
    assert "stops on this moment" not in text and "None" not in text
