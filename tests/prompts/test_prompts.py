"""Tests for the prompts (phase 4). No model, no GPU. Run from the repository root: python -m pytest tests/prompts"""
import json
import re
from pathlib import Path

import yaml

from pulpermill.prompts import prompts as P
from pulpermill.prompts import schemas as S
from pulpermill.prompts import textfiles as tx
from pulpermill.schema import contract

from schema_lite import errors, valid
from test_render import all_ids, generate_request, plan_request

VECTORS = json.loads((Path(__file__).parents[2] / "web" / "tests" / "contract-vectors.json").read_text(encoding="utf-8"))
GOLDEN = {r["name"]: r["data"] for r in VECTORS["requests"] if r.get("golden")}
TEMPLATES = ("writer", "planner", "events", "shifts", "fill", "judge", "style_fit", "offstage", "end_story")


def golden(name):
    return GOLDEN[f"the page's {name} request"]


def no_leaks(text):
    assert not re.search(r"\{[a-z_]+\}", text), re.findall(r"\{[a-z_]+\}", text)
    assert "None" not in text and "null" not in text.lower().split("\n\n")[0]


# ---- Templates ------------------------------------------------------------------------------------------------------

def test_every_template_has_a_version_and_its_name():
    for name in TEMPLATES:
        t = tx.template(name)
        assert t["name"] == name and t["version"].startswith(f"{name}-"), name


def test_writer_wording_has_no_negative_phrases():
    w = tx.template("writer")
    for part in (w["craft"], *w["jobs"].values(), *w["hints"].values(), w["reminder"], w["tail_middle"], w["tail_last"]):
        assert not re.search(r"\b(don't|do not|never|avoid|without|must not)\b", part, re.I), part


# ---- The writer -----------------------------------------------------------------------------------------------------

def test_a_chapter_is_two_sections():
    assert P.writer_plan() == ["open_press", "choice_close"]
    assert tx.limits()["chapter"]["sections"] == 2
    assert not hasattr(P, "needs_extra") and not hasattr(P, "tail_words")          # no padding section, no tail


def test_the_second_section_is_shown_the_whole_first_one():
    req = generate_request()
    first = "Suvi shut the till. " * 400 + "The last line of the first section."
    text = P.writer_prompt(req, P.writer_plan(), 1, first).text
    assert first in text and "The first section of the chapter, as written:" in text
    assert text.index("The first section of the chapter") < text.index("This is section 2 of 2")
    assert "something the passage has not shown yet" in text


def test_the_section_length_is_a_ceiling_and_not_a_target():
    req = generate_request()
    for i in range(2):
        text = P.writer_prompt(req, P.writer_plan(), i, "" if i == 0 else "Some words. ").text
        assert "up to about 1500 words" in text and "ends sooner when the scene has done its work" in text


def test_writer_prompts_end_with_the_reminder_and_hold_the_scene():
    req = generate_request()
    plan = P.writer_plan()
    for i in range(len(plan)):
        p = P.writer_prompt(req, plan, i, "" if i == 0 else "Suvi shut the till. " * 80)
        no_leaks(p.text)
        assert p.stage == "write" and p.version.startswith("writer-")
        assert p.text.rstrip().endswith("Reply with the story text itself, beginning at its first word.")
        assert "Stay in the scene" in p.text.split("\n\n")[-1]
    first = P.writer_prompt(req, plan, 0)
    assert "The first section of the chapter" not in first.text
    assert "The first section of the chapter" in P.writer_prompt(req, plan, 1, "Some words here.").text


def test_the_last_section_ends_the_chapter_and_the_others_do_not():
    req = generate_request()
    plan = P.writer_plan()
    assert "Stop on the ending moment" in P.writer_prompt(req, plan, 1, "x").text
    assert "End this section mid-scene" in P.writer_prompt(req, plan, 0).text


# ---- The planner ----------------------------------------------------------------------------------------------------

def test_planner_prompts_and_beat_schema():
    req = plan_request()
    think = P.planner_think_prompt(req)
    beat = P.planner_beat_prompt(req, "The cellar is dry.")
    for p in (think, beat):
        no_leaks(p.text)
        assert p.version.startswith("planner-")
    assert think.stage == "think" and beat.stage == "beat" and "The cellar is dry." in beat.text
    assert "This is a middle chapter" in think.text
    assert set(beat.schema["properties"]["where"]["enum"]) == {pl["name"] for pl in req["world"]["places"]}


def test_planner_retry_shows_the_problems_and_changes_the_stage():
    req = plan_request()
    req["retry"] = {"thinking": "first thoughts", "beat": {"where": "The Docks", "turn": "Same turn"}, "problems": ["The turn repeats chapter 4's."]}
    p = P.planner_think_prompt(req)
    assert p.stage == "retry" and "The turn repeats chapter 4's." in p.text and "first thoughts" in p.text


def test_beat_schema_follows_the_request():
    req = plan_request()
    schema = S.beat_schema(req)
    assert schema["properties"]["shift"]["enum"] == ["harder", "easier"]
    assert "reveal_rule" in schema["properties"] and "payoff" in schema["properties"]
    assert {"type": "null"} in schema["properties"]["plant"]["anyOf"]      # "no plant" is null, never the word "none"
    req["available_reveals"], req["open_plants"] = [], []
    schema = S.beat_schema(req)
    assert "reveal_rule" not in schema["properties"] and "payoff" not in schema["properties"]
    req["chapter"] = 1
    assert "when_gap" not in S.beat_schema(req)["properties"]


def test_a_good_beat_validates_and_a_wrong_place_does_not():
    req = plan_request()
    schema = S.beat_schema(req)
    places = schema["properties"]["where"].get("enum") or ["x"]
    beat = {k: "words" for k, v in schema["properties"].items() if v.get("type") == "string" and "enum" not in v}
    beat.update({"where": places[0], "shift": "harder", "plant": None})
    if "reveal_rule" in schema["properties"]:
        beat["reveal_rule"] = schema["properties"]["reveal_rule"]["enum"][0]
        beat["reveal_learners"] = []
    if "payoff" in schema["properties"]:
        beat["payoff"] = []
    assert errors(beat, schema) == [], errors(beat, schema)
    if "enum" in schema["properties"]["where"]:
        assert not valid({**beat, "where": "The Moon"}, schema)


# ---- The extractors and the generate reply --------------------------------------------------------------------------

def test_events_prompt_lists_only_what_was_sent():
    req = generate_request()
    p = P.events_prompt(req, "CHAPTER")
    no_leaks(p.text)
    assert p.text.rstrip().endswith("as the reply format asks.") and p.stage == "events"
    for plant in req["open_plants"]:
        assert plant["text"] in p.text
    assert not valid({"happened": "x"}, p.schema)
    reply = {"happened": "Suvi found it.", "changed": "She knows.", "planted": None, "paid_off": [], "reveals_landed": [],
             "behaviors_seen": [], "things_seen": [req["world"]["objects"][0]["name"]], "goal_landed": False}
    assert errors(reply, p.schema) == [], errors(reply, p.schema)
    assert not valid({**reply, "things_seen": ["The Moon"]}, p.schema)


def test_shifts_prompt_never_shows_ids_and_resolves_handles():
    req = generate_request()
    p = P.shifts_prompt(req, "CHAPTER", {"happened": "Suvi found it."})
    no_leaks(p.text)
    handles = p.meta["handles"]
    assert "T1" in handles and p.text.count("T1.") >= 1
    ids = {i for i in all_ids(req["entanglements"]) if i not in handles}
    assert not any(re.search(rf"\b{re.escape(i)}\b", p.text) for i in ids)
    ties = [h for h, info in handles.items() if info["section"] == "ties"]
    out = {"shifts": [{"character": "Suvi", "believes": "Pekka lied."}],
           "changes": [{"section": "ties", "item": ties[0], "field": "edge", "value": "She now doubts him."}], "new_knowledge": [], "shown": [ties[0]]}
    assert errors(out, p.schema) == [], errors(out, p.schema)
    assert not valid({**out, "shown": ["T99"]}, p.schema)          # only handles the request carried
    bad = {**out, "changes": [{"section": "holdings", "item": ties[0], "field": "edge", "value": "x"}]}
    assert not valid(bad, p.schema)
    resolved = P.resolve_changes(out["changes"], handles)
    assert resolved == [{"section": "ties", "item": handles[ties[0]]["id"], "field": "edge", "value": "She now doubts him."}]
    assert P.resolve_changes([{"section": "ties", "item": "T99", "field": "edge", "value": "x"}], handles) == []


def test_assembled_generate_reply_is_what_the_contract_reads():
    req = generate_request()
    ev = P.events_prompt(req, "CHAPTER")
    sh = P.shifts_prompt(req, "CHAPTER")
    ties = [h for h, i in sh.meta["handles"].items() if i["section"] == "ties"]
    events = {"happened": "Suvi found it.", "changed": "", "planted": None, "paid_off": [], "reveals_landed": [], "behaviors_seen": [],
              "things_seen": [], "goal_landed": False}
    shifts = {"shifts": [{"character": "Suvi", "believes": "Pekka lied.", "fears": ""}, {"character": "Aino"}],
              "changes": [{"section": "ties", "item": ties[0], "field": "edge", "value": "x"}], "new_knowledge": []}
    reply = P.assemble_generate_reply("Chapter words.", events, shifts, sh.meta["handles"])
    parsed = contract.parse_reply("generate", reply)
    assert parsed.chapter_text == "Chapter words." and len(parsed.shifts) == 1 and parsed.shifts[0].fears is None
    assert parsed.changes[0].item == sh.meta["handles"][ties[0]]["id"] and parsed.events.changed is None
    assert errors(events, ev.schema) == []


def test_what_the_chapter_showed_and_the_line_someone_joins_come_back_as_ids():
    sh = P.shifts_prompt(generate_request(), "CHAPTER")
    handles = sh.meta["handles"]
    knowledge = [h for h, i in handles.items() if i["section"] == "knowledge"]
    pressure = [h for h, i in handles.items() if i["section"] == "pressures"]
    events = {"happened": "x", "changed": "", "planted": None, "paid_off": [], "reveals_landed": [], "behaviors_seen": [], "things_seen": [], "goal_landed": False}
    out = {"shifts": [], "changes": [], "shown": [pressure[0], pressure[0], "P99"],
           "new_knowledge": [{"person": "Suvi", "status": "knows", "entry": knowledge[0], "belief": None},
                             {"person": "Suvi", "status": "knows", "entry": pressure[0]},     # not a knowledge line: dropped
                             {"person": "Suvi", "status": "suspects", "fact": "A new thing.", "belief": None}]}
    reply = P.assemble_generate_reply("Words.", events, out, handles)
    parsed = contract.parse_reply("generate", reply)
    assert parsed.shown == [handles[pressure[0]]["id"]]
    assert [k.entry for k in parsed.new_knowledge] == [handles[knowledge[0]]["id"], None]


# ---- Fill, judge, style fit, offstage, end of story -----------------------------------------------------------------

def test_fill_prompt_describes_the_card_and_limits_links():
    for name in ("fill_setup", "fill_character"):
        req = golden(name)
        p = P.fill_prompt(req)
        no_leaks(p.text)
        assert p.text.rstrip().endswith("as the reply format asks.") and p.stage is None
        if req.get("note"):
            assert req["note"] in p.text
        assert "id" not in p.schema["properties"]
        assert errors({}, p.schema) == []


def test_fill_links_become_names_in_the_prompt_and_enums_in_the_schema():
    req = {"call": "fill", "schema_version": 1, "language": "en", "card": "entanglements", "note": "Suvi owes Pekka.",
           "related": {"characters": [{"id": "c1", "name": "Suvi"}, {"id": "c2", "name": "Pekka"}],
                       "world": {"places": [{"id": "w1", "name": "The Shop"}]}}}
    schema = S.fill_schema(req)
    assert "Suvi" in json.dumps(schema) and "c1" not in json.dumps(schema)
    ties = schema["properties"]["ties"]["items"]["properties"]
    assert ties["tie_from"]["enum"] == ["Suvi", "Pekka"]


def test_judge_prompts_one_per_rule_with_handles():
    req = golden("judge_world")
    prompts = P.judge_prompts(req)
    assert len(prompts) == len(req["rules"])
    for p in prompts:
        no_leaks(p.text)
        assert p.meta["rule"] in {r["id"] for r in req["rules"]} and p.version.startswith("judge-")
    out = P.assemble_judge_reply(prompts, [{"checks": []}] * len(prompts))
    parsed = contract.parse_reply("judge", out)
    assert [r.rule for r in parsed.results] == [r["id"] for r in req["rules"]]


def _judge_req(rule, fields, values):
    return {"call": "judge", "schema_version": 1, "language": "en", "card": "characters", "instance": "c1",
            "rules": [{"id": rule, "fields": fields}], "related": {}, "values": values}


def test_judge_hits_point_at_ids():
    req = _judge_req("values_positive", ["values"], {"values": [{"id": "v1", "text": "keeps their word"}, {"id": "v2", "text": "never lies"}]})
    p = P.judge_prompts(req)[0]
    assert p.meta["handles"] == {"values.1": "v1", "values.2": "v2"}
    out = P.assemble_judge_reply([p], [{"checks": [{"item": "values.1", "keeps_the_rule": True}, {"item": "values.2", "keeps_the_rule": False}]}])
    assert out["results"][0]["hits"] == [{"field": "values", "item": "v2", "key": None}]


def test_a_set_rule_is_broken_only_when_no_item_keeps_it():
    wants = {"wants": [{"id": "w1", "text": "find a place to stay"}, {"id": "w2", "text": "map the whole valley"}]}
    p = P.judge_prompts(_judge_req("wants_conflict", ["wants"], wants))[0]
    keeps = {"checks": [{"item": "wants.1", "keeps_the_rule": True}, {"item": "wants.2", "keeps_the_rule": False}]}
    assert P.assemble_judge_reply([p], [keeps])["results"][0]["hits"] == []
    none = {"checks": [{"item": "wants.1", "keeps_the_rule": False}, {"item": "wants.2", "keeps_the_rule": False}]}
    assert P.assemble_judge_reply([p], [none])["results"][0]["hits"] == [{"field": "wants", "item": None, "key": None}]
    one = P.judge_prompts(_judge_req("wants_conflict", ["wants"], {"wants": wants["wants"][:1]}))[0]
    assert P.assemble_judge_reply([one], [{"checks": [{"item": "wants.1", "keeps_the_rule": False}]}])["results"][0]["hits"] == []


def test_one_happy_state_satisfies_the_calm_rule():
    values = {"behaviors": [{"id": "b1", "when": "feels happy", "they": "whistle"}]}
    p = P.judge_prompts(_judge_req("behaviors_include_calm", ["behaviors"], values))[0]
    assert P.assemble_judge_reply([p], [{"checks": [{"item": "behaviors.1", "keeps_the_rule": True}]}])["results"][0]["hits"] == []
    assert P.assemble_judge_reply([p], [{"checks": [{"item": "behaviors.1", "keeps_the_rule": False}]}])["results"][0]["hits"] == [{"field": "behaviors", "item": None, "key": None}]


def test_the_judge_schema_asks_for_exactly_one_check_per_item():
    p = P.judge_prompts(_judge_req("values_positive", ["values"], {"values": [{"id": "v1", "text": "a"}, {"id": "v2", "text": "b"}]}))[0]
    ok = {"checks": [{"item": "values.1", "keeps_the_rule": True}, {"item": "values.2", "keeps_the_rule": True}]}
    assert valid(ok, p.schema) and not valid({"checks": ok["checks"][:1]}, p.schema) and not valid({"checks": []}, p.schema)


def test_style_fit_and_offstage_prompts():
    sf = P.style_fit_prompt(golden("style_fit"))
    no_leaks(sf.text)
    assert valid({"fits": True, "message": ""}, sf.schema) and not valid({"fits": "yes"}, sf.schema)
    off = P.offstage_prompt(golden("offstage"))
    no_leaks(off.text)
    assert off.stage == "offstage" and valid({"did": "a", "reach": "b"}, off.schema)
    spot = P.offstage_prompt({**golden("offstage"), "spotlight": {"what": "The board wants the ledger."}})
    assert "The board wants the ledger." in spot.text


def test_end_story_prompts_carry_ids_and_assemble():
    req = [r for r in VECTORS["requests"] if r["name"] == "an end-of-story request"][0]["data"]
    prompts = P.end_story_prompts(req)
    assert len(prompts) == len(req["characters"]) + 1
    first = prompts[0]
    assert req["characters"][0]["id"] in first.text and first.stage == "update"
    out = P.assemble_end_story_reply(prompts, [{"fear": "new"}] * (len(prompts) - 1) + [{}], req)
    parsed = contract.parse_reply("end_story", out)
    assert [c["id"] for c in parsed.characters] == [c["id"] for c in req["characters"]]


def test_every_prompt_is_one_user_turn():
    p = P.style_fit_prompt(golden("style_fit"))
    assert p.messages() == [{"role": "user", "content": p.text}]


# ---- The goal arc ---------------------------------------------------------------------------------------------------

def _needs_goal_request():
    req = json.loads(json.dumps(plan_request()))
    req.update(goal=None, goal_state="needs_goal", story_goal="Relight the oven.", chapter=3, chapter_count=6,
               goal_plan={"state": "needs_goal", "due": "set", "age": 0, "since": 3, "earlier_goals": ["Relight the oven.", "Prove beechwood works."],
                          "last_end": {"kind": "achieved", "goal": "Prove beechwood works."},
                          "directions": [{"kind": "truth", "text": "People believe only applewood works."}]})
    return req


def test_a_needed_goal_is_told_to_the_planner_and_forced_in_the_beat():
    req = _needs_goal_request()
    text = P.planner_beat_prompt(req, "x").text
    assert "Relight the oven." in text and "Prove beechwood works." in text
    assert "starts a new goal" in text and "People believe only applewood works." in text
    schema = P.planner_beat_prompt(req, "x").schema
    assert schema["properties"]["goal_change"]["enum"] == ["redefined"]
    assert {"goal_change", "goal_now"} <= set(schema["required"])
    no_leaks(text)


def test_a_goal_that_is_ended_for_good_offers_no_goal_change():
    req = _needs_goal_request()
    req.update(goal_state="ended", goal_plan={"state": "ended", "due": None, "age": 0, "since": 3, "earlier_goals": [], "last_end": None, "directions": []})
    assert "goal_change" not in P.planner_beat_prompt(req, "x").schema["properties"]
    assert "The story goes on" in P.planner_beat_prompt(req, "x").text


def test_the_writer_is_told_a_new_goal_forms_when_the_story_goes_on():
    from pulpermill.prompts.render import render_setup
    setup = {"protagonist": "Suvi"}
    assert "A new goal forms during this chapter" in render_setup(setup, None, 3, 6, goal_state="needs_goal")
    assert "follow from how it ended" in render_setup(setup, None, 5, 6, goal_state="ended")
    assert "follow from how it ended" in render_setup(setup, None, 5, 6)


def test_the_entanglements_fill_asks_for_three_different_pressures():
    req = {"call": "fill", "schema_version": 1, "language": "en", "card": "entanglements", "related": {}, "values": {}, "note": "Orla and Pim are close."}
    text = P.fill_prompt(req).text
    assert "three pressures" in text
    assert "three pressures" not in P.fill_prompt({**req, "card": "world"}).text


def test_an_either_or_pair_cannot_come_back_both_or_neither():
    schema = S.card_schema("entanglements")
    for field, pair in (("knowledge", ("rule", "fact")), ("pressures", ("source_agent", "source_circumstance"))):
        shape = {"type": "object", "properties": {field: schema["properties"][field]}, "required": [], "additionalProperties": False}
        base = {"knowledge": {"knows": ["Ines"]}, "pressures": {"what": "w"}}[field]
        assert valid({field: [{**base, pair[0]: "a"}]}, shape) and valid({field: [{**base, pair[1]: "b"}]}, shape)
        assert not valid({field: [{**base, pair[0]: "a", pair[1]: "b"}]}, shape)
        assert not valid({field: [base]}, shape)


def test_reveal_payoff_and_plant_are_always_answered():
    schema = S.beat_schema(plan_request())
    for key in ("reveal_rule", "reveal_learners", "payoff", "plant"):
        if key in schema["properties"]:
            assert key in schema["required"], key
    if "reveal_rule" in schema["properties"]:
        assert "" in schema["properties"]["reveal_rule"]["enum"]
    assert valid({**{k: "words" for k in ("when_time", "when_gap", "collision_goal", "collision_block", "choice_a", "choice_b", "turn", "ends_on")},
                  "where": schema["properties"]["where"].get("enum", ["x"])[0], "shift": "harder", "reveal_rule": "", "reveal_learners": [],
                  "payoff": [], "plant": ""}, schema)


def test_a_misled_person_can_be_given_what_they_believe():
    handles = {"K1": {"section": "knowledge", "id": "k1"}}
    schema = S.shifts_schema({"cast": [{"name": "Suvi"}], "world": {"rules": []}}, handles)
    shapes = schema["properties"]["new_knowledge"]["items"]["anyOf"]
    assert len(shapes) == 2 and all("belief" in shape["properties"] for shape in shapes)
    assert any(shape["properties"].get("entry", {}).get("enum") == ["K1"] for shape in shapes)     # join a line that exists, by its handle
    fields = [o["properties"]["field"]["enum"] for o in schema["properties"]["changes"]["items"]["anyOf"]]
    assert ["knows", "suspects", "misled"] in fields and ["belief"] in fields
