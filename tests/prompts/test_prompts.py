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

def test_writer_plan():
    assert P.writer_plan() == ["open", "press", "choice", "close"]
    assert P.writer_plan(3) == ["open_press", "choice", "close"]
    assert P.writer_plan(4, extra=True) == ["open", "press", "choice", "extra", "close"]


def test_needs_extra_only_before_the_last_section_and_only_when_short():
    assert P.needs_extra(1500, 3) and not P.needs_extra(2200, 3)
    assert not P.needs_extra(100, 2)


def test_tail_words_is_short_and_starts_cleanly():
    text = " ".join(f"Word{n}." for n in range(1000))
    tail = P.tail_words(text)
    assert 200 <= len(tail.split()) <= 300 and tail.endswith("Word999.")
    assert P.tail_words("Short.") == "Short."


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
    assert "The chapter so far" not in first.text
    assert "The chapter so far" in P.writer_prompt(req, plan, 1, "Some words here.").text


def test_the_last_section_ends_the_chapter_and_the_others_do_not():
    req = generate_request()
    plan = P.writer_plan()
    assert "Stop on the ending moment" in P.writer_prompt(req, plan, 3, "x").text
    assert "End this section mid-scene" in P.writer_prompt(req, plan, 1, "x").text


def test_extra_section_has_its_own_job():
    req = generate_request()
    plan = P.writer_plan(extra=True)
    p = P.writer_prompt(req, plan, 3, "x")
    assert p.meta["role"] == "extra" and p.meta["of"] == 5


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
    beat.update({"where": places[0], "shift": "harder"})
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
           "changes": [{"section": "ties", "item": ties[0], "field": "edge", "value": "She now doubts him."}], "new_knowledge": []}
    assert errors(out, p.schema) == [], errors(out, p.schema)
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
        assert valid({"hits": []}, p.schema)
    out = P.assemble_judge_reply(prompts, [{"hits": []}] * len(prompts))
    parsed = contract.parse_reply("judge", out)
    assert [r.rule for r in parsed.results] == [r["id"] for r in req["rules"]]


def test_judge_hits_point_at_ids():
    req = {"call": "judge", "schema_version": 1, "language": "en", "card": "characters", "instance": "c1",
           "rules": [{"id": "wants_conflict", "fields": ["wants"]}], "related": {},
           "values": {"wants": [{"id": "w1", "text": "keep the shop"}, {"id": "w2", "text": "keep the shop open"}]}}
    prompts = P.judge_prompts(req)
    p = prompts[0]
    assert p.meta["handles"] == {"wants.1": "w1", "wants.2": "w2"}
    out = P.assemble_judge_reply(prompts, [{"hits": [{"field": "wants", "item": "wants.2"}]}])
    assert out["results"][0]["hits"][0]["item"] == "w2"


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
