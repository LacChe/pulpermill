"""Tests for the card renderers. No model, no GPU. Run from the repository root: python -m pytest tests/prompts"""
import copy
import json
import re
from pathlib import Path

from pulpermill.prompts import (Report, render_cast, render_entanglements, render_history, render_scene, render_setup, render_shift,
                                render_spotlight, render_story_so_far, render_style, render_world)
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


# ---- Setup, the story so far ------------------------------------------------------------------------------

def test_chapter_one_carries_the_normal_and_the_break_and_later_chapters_do_not():
    setup = dict(generate_request()["setup"], normal="The shop opened at six.", disruption="Someone broke in.")
    one = render_setup(setup, 1, 8)
    five = render_setup({k: v for k, v in setup.items() if k not in ("normal", "disruption")}, 5, 8)
    assert "The shop opened at six." in one and "Someone broke in." in one and "chapter 1 of 8" in one
    assert "shop opened" not in five and "chapter 5 of 8" in five


def test_the_last_chapter_is_said_to_be_the_last():
    text = render_setup(generate_request()["setup"], 8, 8)
    assert "last chapter" in text


def test_older_chapters_shrink_to_their_changed_line():
    text = render_story_so_far(generate_request()["earlier_events"], 5, keep_full=3)
    assert "Earlier chapters, in brief:" in text and "Chapter 1: Suvi knows someone has been in the shop at night." in text
    assert "finds the shop's stock miscounted" not in text           # chapter 1 is only its changed line
    assert "Chapter 4. Aino warns Suvi" in text and "By its end: The cellar story is false" in text
    assert "What changed for the protagonist" not in text and "Set up:" not in text


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
        if key.startswith(("portraits_", "offstage_")) and isinstance(value, str):
            assert not NEGATIVE.search(value), f"{key}: {value}"


def test_limits_cover_every_field_the_renderers_clip():
    limits = tx.limits()
    for group, keys in {"characters": ("sketch", "fear", "flaw", "competence", "vulnerability", "speech", "history", "want_item", "value_item",
                                       "behavior_state", "behavior_tendency", "max_behaviors"),
                        "world": ("name", "era_and_technology", "everyday_life", "history", "place_description", "place_effect", "object_description",
                                  "object_significance", "power_nature", "power_hold", "power_felt", "rule_statement", "rule_cost",
                                  "rule_when_broken", "term_meaning"),
                        "entanglements": ("bond", "edge"),
                        "setup": ("normal", "disruption"),
                        "scene": ("where", "when_time", "aim", "plan"),
                        "events": ("happened", "changed", "full_chapters_writer", "full_chapters_planner")
                        }.items():
        for key in keys:
            assert isinstance(limits[group][key], int) and limits[group][key] > 0, f"{group}.{key}"
    assert "appearance" not in limits["characters"]                      # fixed fields have no cap
    assert set(limits["setup"]) == {"normal", "disruption"}              # the schema dropped goal and stakes


def test_no_renderer_or_limit_reads_a_field_the_schema_dropped():
    root = Path(__file__).resolve().parents[2] / "pulpermill" / "prompts"
    for name in ("render.py", "limits.yaml", "text/en/frames.yaml"):
        text = (root / name).read_text(encoding="utf-8")
        assert not re.search(r"\b(goal|stakes)\b", text), name


def test_the_schema_text_i_own_has_no_placeholder_left():
    root = Path(__file__).resolve().parents[2] / "pulpermill" / "schema" / "text" / "en"
    for name in ("outline.yaml", "shifts.yaml"):
        assert "TODO prompt design" not in (root / name).read_text(encoding="utf-8"), name


def test_new_wording_uses_positive_phrasing():
    for key, value in tx.prompt_text("frames").items():
        if key.startswith(("scene_", "spotlight_", "history_", "shift_")):
            assert not NEGATIVE.search(value), f"{key}: {value}"
    beats = tx.schema_text("outline")["fields"]["beats"]
    assert not NEGATIVE.search(beats["lead_in"] + beats["item_template"])


# ---- Setup: the protagonist's name, no goal and no stakes -----------------------------------------------------------

def test_setup_names_the_protagonist_and_reads_no_goal_or_stakes():
    setup = {"protagonist": "c0000001", "stakes": "Everything.", "goal": "Win."}
    text = render_setup(setup, 3, 8, protagonist_name="Suvi")
    assert "The story follows Suvi." in text and "c0000001" not in text
    assert "Everything" not in text and "Win." not in text and "chapter 3 of 8" in text


# ---- The scene ------------------------------------------------------------------------------------------------------

def beat_in_words(**changes):
    req = generate_request()
    tie = {**req["ties"][0], "tie_from": "Suvi", "tie_to": "Aino"}
    beat = dict(req["beat"], cast=["Suvi", "Aino", "Pekka"], spotlight=tie)
    beat.update(changes)
    return beat


def leaked(text):
    ids = all_ids(generate_request()) | {"c0000001", "c0000002", "t10000", "g1"}
    return [i for i in ids if i in text]


def test_a_scene_tells_place_time_cast_spotlight_aim_and_plan_in_prose():
    text = render_scene(beat_in_words(), scope="writer")
    for must in ("The chapter opens at The Docks.", "The time is Tuesday, just after the shop opens.",
                 "The people on stage are Suvi, Aino and Pekka.", "The tie in the spotlight is Suvi toward Aino: She tolerates him and half-trusts him.",
                 "The protagonist is after this: Get Pekka to say where the ledger is.", "The plan for the chapter: Suvi presses Pekka"):
        assert must in text
    assert text.index("opens at") < text.index("The time") < text.index("on stage") < text.index("spotlight") < text.index("after this") < text.index("The plan")
    assert not leaked(text) and "when_time" not in text and "{" not in text


def test_the_writers_scene_begins_in_motion_and_the_planners_does_not():
    writer = render_scene(beat_in_words(), scope="writer")
    planner = render_scene(beat_in_words(), scope="planner")
    assert "already in motion" in writer and "already in motion" not in planner
    assert "by role only" in writer and "by role only" in planner         # minor characters appear by role, with no names
    assert planner in writer


def test_a_scene_with_empty_values_leaves_no_empty_label():
    text = render_scene({"where": "", "when_time": None, "cast": [], "spotlight": "", "aim": "Keep the key", "plan": ""}, scope="planner")
    assert text == "The protagonist is after this: Keep the key."
    assert "on stage" not in text and "plan for" not in text and "  " not in text
    assert render_scene({}, scope="planner") == ""
    assert render_scene(beat_in_words(spotlight="Aino's wish to be trusted"), scope="planner").count("Aino's wish to be trusted.") == 1


def test_a_scene_takes_cast_cards_and_clips_what_is_over_its_cap():
    report = Report()
    cast = [{"id": "c0000001", "name": "Suvi"}, {"id": "c0000002", "name": "Aino"}]
    long = "The aim goes on for a good while. " * 30
    text = render_scene(beat_in_words(cast=cast, aim=long, plan=long * 3), scope="writer", report=report)
    assert "The people on stage are Suvi and Aino." in text and not leaked(text)
    assert {c.split(":")[0] for c in report.clips} == {"beat.aim", "beat.plan"}
    assert len(text) < 2200


def test_a_scene_rejects_a_scope_it_does_not_know():
    import pytest
    with pytest.raises(ValueError):
        render_scene(beat_in_words(), scope="judge")


# ---- The spotlight tie ----------------------------------------------------------------------------------------------

def spotlight_inputs():
    req = generate_request()
    return {**req["ties"][0], "tie_from": "Suvi", "tie_to": "Aino"}, req["cast"]


def test_the_spotlight_says_who_stands_toward_whom_and_what_drives_them():
    tie, cast = spotlight_inputs()
    text = render_spotlight(tie, cast, scope="writer")
    assert "Suvi toward Aino: She tolerates him and half-trusts him." in text
    assert "What drives Suvi in this tie: She wants to know whom he reports to." in text
    assert "The two people at its ends, in brief:" in text
    assert "Suvi avoids and protects herself from" in text and "Aino avoids and protects himself from" in text
    assert "Pekka" not in text and not leaked(text) and "themselves" not in text


def test_the_planners_briefs_add_each_ends_sketch_and_the_writers_do_not():
    tie, cast = spotlight_inputs()
    planner = render_spotlight(tie, cast, scope="planner")
    writer = render_spotlight(tie, cast, scope="writer")
    assert "Who Suvi is:" in planner and "Who Aino is:" in planner
    assert "Who Suvi is:" not in writer and "Who Aino is:" not in writer


def test_a_spotlight_end_that_is_a_group_or_not_in_the_cast_gets_no_brief():
    req = generate_request()
    tie = {**req["ties"][2], "tie_from": "Aino", "tie_to": "The Harbour Board"}
    text = render_spotlight(tie, req["cast"], scope="planner")
    assert "Aino toward The Harbour Board" in text and "Who Aino is:" in text and "Harbour Board wants" not in text
    assert render_spotlight(tie, [], scope="planner").count("\n") == 0               # nobody in the cast: the tie alone


def test_a_spotlight_given_ids_reads_them_through_the_names():
    req = generate_request()
    names = {c["id"]: c["name"] for c in req["cast"]} | {"g1": "The Harbour Board"}
    text = render_spotlight(req["ties"][2], req["cast"], scope="writer", names=names)
    assert "Aino toward The Harbour Board" in text and not leaked(text)


def test_a_spotlight_with_empty_values_and_over_cap_values():
    tie, cast = spotlight_inputs()
    bare = render_spotlight({**tie, "bond": "", "edge": ""}, [], scope="writer")
    assert bare == "This chapter puts one tie in the spotlight: Suvi toward Aino." and "drives" not in bare
    report = Report()
    long = "She weighs every word she says to him. " * 20
    text = render_spotlight({**tie, "edge": long, "bond": long}, cast, scope="planner", report=report)
    assert {c.split(":")[0] for c in report.clips} >= {"tie.bond", "tie.edge"} and len(text) < 3000


# ---- The history of changes -----------------------------------------------------------------------------------------

def test_history_tells_what_happened_and_what_changed_and_shrinks_the_old():
    events = generate_request()["earlier_events"]
    planner = render_history(events, 5, scope="planner", keep_full=2)
    assert planner.startswith("What has happened so far, and what each chapter changed:")
    assert "Chapter 1: Suvi knows someone has been in the shop at night." in planner and "finds the shop's stock miscounted" not in planner
    assert "Chapter 4. Aino warns Suvi" in planner and "By its end: The cellar story is false" in planner
    writer = render_history(events, 5, scope="writer", keep_full=2)
    assert writer.startswith("The story so far:") and writer.split("\n", 1)[1] == planner.split("\n", 1)[1]
    assert render_story_so_far(events, 5, keep_full=2) == writer


def test_history_leaves_out_the_current_and_later_chapters_and_an_empty_record_is_empty():
    events = generate_request()["earlier_events"]
    assert "Chapter 4" not in render_history(events, 4, scope="writer", keep_full=9) and "Chapter 3" in render_history(events, 4, scope="writer", keep_full=9)
    assert render_history([], 3, scope="planner", keep_full=2) == "" and render_history(events, 1, scope="writer", keep_full=2) == ""
    assert render_history([{"happened": "No chapter number."}], 3, scope="writer", keep_full=2) == ""


def test_history_with_empty_values_and_over_cap_values():
    report = Report()
    long = "Something happened in this chapter. " * 40
    events = [{"chapter": 1, "happened": "", "changed": ""}, {"chapter": 2, "happened": long, "changed": long}]
    text = render_history(events, 3, scope="planner", keep_full=2, report=report)
    assert "By its end:" in text and text.count("By its end:") == 1               # chapter 1 has no changed line to show
    assert any("events.2" in c for c in report.clips) and len(text) < 2500


# ---- A recorded change (no caller yet) ------------------------------------------------------------------------------

def test_a_shift_entry_reads_as_prose_with_names_and_no_ids():
    entry = {"beat": 3, "card": "characters", "target": "c0000001",
             "patch": {"fear": "Losing the shop", "wants": [{"op": "add", "values": {"text": "Find the ledger"}}, {"op": "remove", "id": "w0000001"},
                                                            {"op": "replace", "id": "w0000009", "values": {"text": "Keep the key hidden"}}]}}
    text = render_shift(entry, {"c0000001": "Suvi", "w0000001": "Keep the peace"})
    assert text.startswith("In chapter 3, the character Suvi changed:") and "fear is now Losing the shop." in text
    assert "wants gains: Find the ledger." in text and "wants no longer includes Keep the peace." in text
    assert "an earlier entry becomes Keep the key hidden." in text and "w0000009" not in text and "c0000001" not in text


def test_a_shift_for_the_world_has_no_target_and_an_empty_patch_has_nothing_to_say():
    text = render_shift({"beat": 2, "card": "world", "patch": {"everyday_life": "Quiet now."}})
    assert text == "In chapter 2, the world changed: everyday life is now Quiet now."
    assert render_shift({"beat": 2, "card": "entanglements", "patch": {}}) == "In chapter 2, the ties and holdings changed:"
