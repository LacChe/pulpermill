"""Tests for the card renderers. No model, no GPU. Run from the repository root: python -m pytest tests/prompts"""
import copy
import json
import re
from pathlib import Path

from pulpermill.prompts import (Report, render_origin_history, render_cast, render_entanglements, render_history, render_scene, render_setup, render_shift,
                                render_spotlight, render_story_so_far, render_style, render_world)
from pulpermill.prompts import render
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
    assert fill("{a}: {b} Next move: {c}", {"a": "X", "b": "Y", "c": "Z"}) == "X: Y. Next move: Z"


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
    assert "How it holds power: Licensing every boat" in text
    assert "The Dockhands' Brotherhood, as ordinary people feel it: A hush" in text
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


def test_a_tie_edge_follows_a_colon_so_a_phrase_or_a_sentence_reads_alike():
    text = render_entanglements(named(generate_request()), ["Suvi", "Aino", "Pekka"], scope="writer")
    assert "Drives Suvi: She wants to know whom he reports to." in text
    ties = {"ties": [{"tie_from": "Suvi", "tie_to": "Aino", "bond": "owes her since the fire", "edge": "to care for him"}]}
    assert "Suvi toward Aino: owes her since the fire. Drives Suvi: to care for him." in render_entanglements(ties, scope="planner")


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


def test_origin_history_is_the_disruption_alone_for_chapters_after_the_first():
    setup = dict(generate_request()["setup"], normal="The shop opened at six.", disruption="Someone broke in.")
    two = render_origin_history(setup, 2)
    assert two.startswith("Where the story began: Someone broke in.")
    assert "origin history" in two and "story so far" in two and "begins from where the story so far leaves off" in two
    assert "shop opened" not in two
    assert render_origin_history(setup, 8) == render_origin_history(setup, 2)
    assert not NEGATIVE.search(two) and not re.search(r"\b(goal|stakes)\b", two)


def test_origin_history_is_empty_for_chapter_one_and_when_there_is_no_disruption():
    setup = dict(generate_request()["setup"], disruption="Someone broke in.")
    assert render_origin_history(setup, 1) == ""
    assert render_origin_history({k: v for k, v in setup.items() if k != "disruption"}, 3) == ""
    assert render_origin_history(dict(setup, disruption="  "), 3) == ""


def test_origin_history_clips_a_long_disruption_like_chapter_one_does():
    cap = tx.limits()["setup"]["disruption"]
    report = Report()
    text = render_origin_history({"disruption": "A fire took the harbor. " * 200}, 2, report=report)
    assert report and len(text) < cap + 400


def test_the_last_chapter_is_said_to_be_the_last():
    text = render_setup(generate_request()["setup"], 8, 8)
    assert "This is the last chapter" in text and "open nothing new" in text


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
    for scope_text in (writer, planner):          # the one statement about people beyond the cast: the reason, the method and the scale
        assert "The cast is fixed" in scope_text and "what they do or by one telling detail" in scope_text
        assert "none of them has a name; only places, events and things do" in scope_text
        assert scope_text.count("The cast is fixed") == 1
    assert planner in writer


def test_the_writer_is_told_that_people_outside_the_spotlight_tie_are_supporting():
    cast = [{"id": "c0000001", "name": "Suvi"}, {"id": "c0000002", "name": "Aino"}]
    note = "People outside the spotlight tie are supporting: they can pull on the tie or react to it, and the scene stays about the tie."
    assert note in render_cast(cast, scope="writer")
    assert note not in render_cast(cast, scope="planner")


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
    assert len(text) < 2400          # the aim and the plan are clipped: unclipped they alone are over 4,000 characters


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
    assert planner.startswith("What has happened so far, and what each chapter changed.")
    assert "how its collision came out" in planner.split("\n", 1)[0]
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


def test_a_changed_line_of_500_characters_is_shown_whole_for_latest_and_older_chapters():
    line = ("The aim now stands at the stone and the tie to Marit is strained. " * 8).strip()[:499].rsplit(" ", 1)[0] + "."
    events = [{"chapter": n, "happened": f"Event {n}.", "changed": line} for n in (1, 2, 3, 4)]
    report = Report()
    text = render_history(events, 5, scope="planner", keep_full=2, report=report)
    assert text.count(line) == 4 and not report.clips and "…" not in text


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


def test_an_empty_patch_has_nothing_to_say():
    assert render_shift({"beat": 2, "card": "entanglements", "patch": {}}) == "In chapter 2, the ties and holdings changed:"


# ---- Sentence ends (A6) ---------------------------------------------------------------------------------------------

from pulpermill.prompts.render import (render_person_brief, render_earlier_beats, sentence, tidy)  # noqa: E402

_TERM = "[.!?…。！？]"


def _boundary_story(stop: str):
    """One of every card, with each stored value made unique and ending in `stop` (or in nothing)."""
    v = lambda tag: f"Zq{tag}x{stop}"       # noqa: E731
    person = {"name": "Suvi", "sex": "female", "age": 34, "appearance": v("app"), "sketch": v("sk"), "wants": [{"text": v("w1")}, {"text": v("w2")}],
              "fear": v("fear"), "flaw": v("flaw"), "values": [{"text": v("v1")}, {"text": v("v2")}],
              "behaviors": [{"state": v("bs"), "tendency": v("bt")}], "competence": v("comp"), "vulnerability": v("vul"),
              "speech": v("sp"), "history": v("hist")}
    world = {"name": "Coast", "era_and_technology": v("era"), "everyday_life": v("life"), "history": v("whist"),
             "places": [{"name": "Dock", "description": v("pd"), "effect": v("pe")}],
             "objects": [{"name": "Key", "description": v("od"), "significance": v("os"), "held_by": "Suvi"}],
             "powers": [{"name": "Board", "nature": v("pn"), "hold": v("ph"), "felt": v("pf")}],
             "rules": [{"statement": v("rs"), "cost": v("rc"), "when_broken": v("rw")}],
             "terms": [{"term": "Toll", "meaning": v("t1")}, {"term": "Fee", "meaning": v("t2")}]}
    ties = {"ties": [{"tie_from": "Suvi", "tie_to": "Board", "bond": v("bond"), "edge": v("edge")}], "holdings": [{"held_by": "Suvi", "holdee": "Key"}]}
    setup = {"protagonist": "Suvi", "normal": v("norm"), "disruption": v("disr")}
    events = [{"chapter": 1, "happened": v("hap1"), "changed": v("chg1")}, {"chapter": 2, "happened": v("hap2"), "changed": v("chg2")},
              {"chapter": 3, "happened": v("hap3"), "changed": v("chg3")}]
    beat = {"where": v("where"), "when_time": v("when"), "cast": ["Suvi"], "spotlight": v("spot"), "aim": v("aim"), "plan": v("plan")}
    tie = {"tie_from": "Suvi", "tie_to": "Aino", "bond": v("sbond"), "edge": v("sedge")}
    shift = {"chapter": 2, "card": "characters", "target": "c1", "patch": {"fear": v("sf"), "wants": [{"op": "add", "values": {"text": v("sa")}}]}}
    style = {"person": "third", "tense": "past", "genre": v("genre"), "lens": v("lens"), "narrator_note": v("nn"), "sentences_note": v("sn"),
             "stance_note": v("st"), "dialogue_note": v("dn")}
    return person, world, ties, setup, events, beat, tie, shift, style


def _render_every_card(stop: str) -> list[tuple[str, str]]:
    person, world, ties, setup, events, beat, tie, shift, style = _boundary_story(stop)
    out = [("person writer", render_cast([person], scope="writer")), ("person planner", render_cast([person], scope="planner")),
           ("world writer", render_world(world, scope="writer", place="Dock")), ("world planner", render_world(world, scope="planner")),
           ("ties writer", render_entanglements(ties, ["Suvi", "Board"], scope="writer")),
           ("ties planner", render_entanglements(ties, ["Suvi"], scope="planner")),
           ("setup", render_setup(setup, 1, 12)), ("history writer", render_history(events, 4, scope="writer", keep_full=1)),
           ("history planner", render_history(events, 4, scope="planner", keep_full=1)), ("story so far", render_story_so_far(events, 4, keep_full=1)),
           ("scene writer", render_scene(beat, scope="writer")), ("scene planner", render_scene(beat, scope="planner")),
           ("spotlight", render_spotlight(tie, [person], scope="planner")), ("person brief", render_person_brief(person)),
           ("style", render_style(style, scope="writer")), ("shift", render_shift(shift, {"c1": "Suvi"}))]
    return out


def _values(stop: str) -> list[str]:
    found = set()
    for card in _boundary_story(stop):
        stack = [card]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, str) and node.startswith("Zq"):
                found.add(node)
    return sorted(found)


def _check_boundaries(stop: str):
    seen = 0
    for where, text in _render_every_card(stop):
        for value in _values(stop):
            for m in re.finditer(re.escape(value), text):
                seen += 1
                end = m.end()
                tail = text[end:end + 2]
                ok = value[-1] in ".!?…。！？" or (tail[:1] and tail[0] in ".!?…。！？;,:)\n") or end == len(text) or text[end] == "\n"
                assert ok, f"{where}: {value!r} runs into {text[end:end + 25]!r}"
    assert seen > 40


def test_no_value_runs_into_the_next_sentence_when_it_has_no_final_stop():
    _check_boundaries("")


def test_no_value_runs_into_the_next_sentence_when_it_ends_in_a_stop():
    _check_boundaries(".")


def test_no_stop_is_doubled_in_either_mode():
    for stop in ("", ".", "?", "!", "…", "。"):
        for where, text in _render_every_card(stop):
            assert not re.search(r"(?<![.\d])\.\.(?!\.)", text), f"{where}: doubled stop"
            assert not re.search(r"[?!…。！？]\.", text), f"{where}: a stop after a stop"


def test_the_three_lines_that_ran_together_now_read_properly():
    person = {"name": "Suvi", "sex": "female", "fear": "Being found out", "flaw": "She hoards what she knows"}
    text = render_cast([person], scope="planner")
    assert "Suvi avoids and protects herself from: Being found out. Suvi holds a false belief or blind spot that sabotages her own aims: She hoards what she knows." in text
    world = {"name": "Coast", "rules": [{"statement": "Debts are written, never spoken", "cost": "A spoken debt is void.", "when_broken": "The board is shamed."}],
             "powers": [{"name": "The Board", "nature": "Seven men.", "hold": "It sets the tolls", "felt": "A fee"}]}
    out = render_world(world, scope="writer")
    assert "Debts are written, never spoken. Cost: A spoken debt is void. When broken: The board is shamed." in out
    assert "The Board: Seven men. How it holds power: It sets the tolls. How ordinary people feel it: A fee." in out


def test_a_value_that_already_ends_a_sentence_is_not_given_another_stop():
    for value in ('He said "go."', "Is it?", "Run!", "Wait…", "他走了。", "她问：“去哪？”", "(a note.)"):
        assert sentence(value) == value
        assert tidy(value + ".") == value, value
    assert sentence("A plain value") == "A plain value." and sentence('He called it "the Ledger"') == 'He called it "the Ledger".'
    person = {"name": "Suvi", "sex": "female", "fear": "Is it over?", "flaw": 'Says "never."', "wants": [{"text": "Is it safe?"}]}
    text = render_cast([person], scope="planner")
    assert "from: Is it over? Suvi" in text and 'her own aims: Says "never."' in text and "Is it safe?" in text and "?." not in text
    assert 'never.".' not in text


def test_chinese_values_keep_their_own_stops_and_get_an_english_one_only_when_bare():
    person = {"name": "Suvi", "fear": "被人发现。", "flaw": "她囤积秘密"}
    text = render_cast([person], scope="planner")
    assert "被人发现。 Suvi" in text and "。." not in text
    assert "她囤积秘密." in text


def test_a_clipped_value_ends_at_a_stop_or_in_an_ellipsis_and_reads_on():
    person = {"name": "Suvi", "sex": "female", "fear": "A fear that goes on and on without any end in sight, " * 20, "flaw": "Short"}
    text = render_cast([person], scope="planner", report=Report())
    assert "…" in text and "….." not in text and "…. " not in text
    zh = {"name": "Suvi", "fear": "他害怕。" * 80, "flaw": "x"}
    assert render_cast([zh], scope="planner").count("害怕。") >= 1


def test_the_beats_timeline_and_the_brief_take_values_with_or_without_stops():
    beats = [{"chapter": 1, "where": "The Docks.", "when_time": "Friday night."}]
    assert "Chapter 1: at The Docks, Friday night." in render_earlier_beats(beats)
    brief = render_person_brief({"name": "Suvi", "wants": [{"text": "Keep the shop."}, {"text": "Know why"}]})
    assert "Wants: Keep the shop; Know why." in brief


def test_an_earlier_beat_shows_the_tie_and_the_pressure_it_was_about_and_without_them_reads_as_before():
    plain = [{"chapter": 1, "where": "The Docks", "when_time": "Friday night"}]
    old = render_earlier_beats(plain)
    assert old.endswith("Chapter 1: at The Docks, Friday night.")
    both = render_earlier_beats([{**plain[0], "tie": "Orla Fennick and Pim Tallowby", "pressure": "Debts are written, never spoken."}])
    assert both.endswith("Chapter 1: at The Docks, Friday night. It was about Orla Fennick and Pim Tallowby. It put this to work: Debts are written, never spoken.")
    assert render_earlier_beats([{**plain[0], "tie": "Orla Fennick and Pim Tallowby"}]).endswith("It was about Orla Fennick and Pim Tallowby.")
    assert render_earlier_beats([{**plain[0], "pressure": "The ledger"}]).endswith("Friday night. It put this to work: The ledger.")
    assert render_earlier_beats([{**plain[0], "tie": "", "pressure": None}]) == old, "an empty tie or pressure is as good as none"


# ---- the pressure (world-pressure-2) ------------------------------------------------------------------------------------------------

RULE_PRESSURE = {"kind": "rule", "statement": "Debts are written, never spoken.", "cost": "A spoken debt is void.", "when_broken": "The board is shamed."}
OBJECT_PRESSURE = {"kind": "object", "name": "The ledger", "description": "Green cloth cover.", "significance": "Names who owes the board."}


def test_a_pressure_is_one_kind_sentence_and_the_element_in_words_once():
    rule = render.render_pressure(RULE_PRESSURE)
    sentence, element = rule.split("\n")
    assert "the rule below is a part of the collision" in sentence and "The rule itself stays as it is." in sentence and "object below" not in sentence
    assert element == "Debts are written, never spoken. Cost: A spoken debt is void. When broken: The board is shamed."
    thing = render.render_pressure(OBJECT_PRESSURE).split("\n")
    assert "the object below is a part of the collision" in thing[0] and "rule below" not in thing[0]
    assert thing[1] == "The ledger: Green cloth cover. Why it matters: Names who owes the board."


def test_a_rules_element_shows_its_consequence_unless_it_is_empty():
    assert "When broken: The board is shamed." in render.pressure_element(RULE_PRESSURE)
    assert render.pressure_element(dict(RULE_PRESSURE, when_broken="")) == "Debts are written, never spoken. Cost: A spoken debt is void."
    assert render.pressure_element(OBJECT_PRESSURE) == "The ledger: Green cloth cover. Why it matters: Names who owes the board."
    assert render.pressure_element(None) == ""


def test_no_pressure_or_an_odd_one_renders_nothing():
    for odd in (None, {}, "r0000001", {"kind": "place", "name": "x"}, {"kind": "rule"}):
        assert render.render_pressure(odd) == ""


def test_the_element_is_clipped_to_the_one_cap():
    long = dict(RULE_PRESSURE, statement="Nobody may cross the river after dark, whatever their business. " * 10, cost="")
    element = render.render_pressure(long).split("\n")[1]
    assert len(element) <= tx.limits()["pressure"]["element"] and element.endswith(".")


def test_the_world_leaves_out_the_pressure_element_once_and_only_that_one():
    world = generate_request()["world"]
    rule = world["rules"][0]
    plain = render.render_world(world, scope="writer")
    assert rule["statement"] in plain
    cut = render.render_world(world, scope="writer", without={"kind": "rule", "statement": rule["statement"]})
    assert rule["statement"] not in cut and all(r["statement"] in cut for r in world["rules"][1:])
    thing = world["objects"][0]
    cut = render.render_world(world, scope="planner", without={"kind": "object", "name": thing["name"]})
    assert thing["description"] not in cut and all(o["description"] in cut for o in world["objects"][1:])
    twice = {**world, "rules": [world["rules"][0], dict(world["rules"][0])]}                      # two items alike: only the first match goes
    assert render.render_world(twice, scope="writer", without={"kind": "rule", "statement": rule["statement"]}).count(rule["statement"]) == 1
    assert render.render_world(world, scope="writer", without=None) == plain
    assert render.render_world(world, scope="writer", without={"kind": "object", "name": rule["statement"]}) == plain      # a name that is no item's leaves it be


def test_the_scene_block_shows_the_pressure_next_to_the_beat():
    beat = {"where": "The Archive", "when_time": "Dusk", "aim": "Get the ledger out.", "plan": "Suvi hides it.", "cast": []}
    plain = render.render_scene(beat, scope="writer")
    pressed = render.render_scene({**beat, "pressure": RULE_PRESSURE}, scope="writer")
    assert pressed.startswith(plain.split("\n")[0]) and "Cost: A spoken debt is void." in pressed and "make the rule below" not in plain
    assert render.render_scene({**beat, "pressure": "r0000001"}, scope="writer") == plain          # an id is not words: nothing is shown
