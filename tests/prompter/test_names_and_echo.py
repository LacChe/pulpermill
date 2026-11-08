"""A9: a chapter does not open on the end of the one before, and nobody who is on no card is named in the setup fill. In the plan, the chapter and
the setup fill a name on no card is no longer refused (minor1): it is counted (`plan_names`, `write_names`, `setup_strangers`) and put to the
trace as a soft note, and a name an earlier chapter's record already carries is established, so it is not new. The quoted examples come from
a real run (test-6)."""
import copy
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
from pulpermill.prompter.mill import common, fill, generate as gen, plan  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]


def vector(call, name):
    return copy.deepcopy(next(v["data"] for v in VECTORS if v["valid"] and v["data"]["call"] == call and v["name"] == name))


def generate_request(**over):
    r = vector("generate", "a generate request")
    r.update(over)
    return r


ENDING = ("She deposited the applewood near the Weather Oven, glancing at the half-burned bundle within. "
          "Orla said nothing, and the oven ticked as it cooled. Pim carried the empty basket home through the dusk.")
ECHO = ("She deposited the applewood near the Weather Oven, glancing at the half-burned bundle within. "
        "The next morning Pim woke to a knock at the shutters, and the day had already begun without her.")
FRESH = ("By the next morning the whole street had heard about the bundle. Pim woke to a knock at the shutters, and the day "
         "had already begun without her.")


# ---- the echo ---------------------------------------------------------------------------------------------------------------

def test_a_chapter_that_opens_with_the_last_chapters_final_paragraph_is_refused_and_a_fresh_opening_passes():
    request = generate_request(chapter=2, previous_ending=ENDING)
    line = gen.write_problem(request, ECHO)
    assert line and "repeating the end of the last chapter" in line and "new" in line
    assert gen.write_problem(request, FRESH) is None


def test_case_punctuation_and_spacing_do_not_hide_an_echo():
    request = generate_request(chapter=2, previous_ending=ENDING)
    loud = "SHE DEPOSITED the applewood near the weather oven -- glancing at the half-burned bundle within!  Then it rained."
    assert gen.write_problem(request, loud)


def test_an_ending_cut_mid_sentence_still_counts_when_the_opening_repeats_what_is_left():
    request = generate_request(chapter=2, previous_ending="the oven ticked as it cooled and Orla stood there, saying nothing at all to anyone, until the lamp")
    assert gen.write_problem(request, "Orla stood there, saying nothing at all to anyone, until the lamp went out. Then the street was dark.")


def test_a_short_repeated_phrase_or_a_name_is_not_an_echo():
    request = generate_request(chapter=2, previous_ending="Pim said nothing. Orla nodded. “Come home.”")
    assert gen.write_problem(request, "Pim said nothing. Orla nodded. Morning came slowly over the millpond and the first carts rattled out.") is None


def test_chapter_one_has_no_ending_and_is_never_an_echo():
    request = generate_request(chapter=1)
    request.pop("previous_ending", None)
    assert gen.write_problem(request, ECHO) is None
    assert gen.write_problem({**request, "previous_ending": None}, ECHO) is None


def test_the_ending_lead_asks_for_a_new_first_sentence_in_positive_words():
    request = generate_request(chapter=2, previous_ending=ENDING)
    prompt = gen.write_prompt(request)
    assert "Chapter 1 ended with the passage below" in prompt and "first sentence is a new one" in prompt and "stays true" in prompt
    assert "no recap" not in prompt


# ---- names in the setup fill ------------------------------------------------------------------------------------------------

def setup_request(note="Pim bakes bread in the village.", characters=("Pim", "Orla"), world=None, **over):
    request = {"call": "fill", "schema_version": 4, "language": "en", "card": "setup", "instance": None, "note": note, "example_chapter": None,
               "values": {}, "related": {"characters": [{"name": n} for n in characters],
                                         "world": world or {"name": "Millbrook", "places": [{"name": "The Millpond"}], "powers": [{"name": "The Parish Council"}]}}}
    request.update(over)
    return request


NORMAL = "Pim baked before dawn. Old Man Hemlock bought the first loaf and Bess at the dye works waved from her door."


def fill_check(request):
    flow = fill.FillFlow(request, SimpleNamespace(grammar=SimpleNamespace(fill=lambda: {"type": "object"})))
    return flow, flow._step().check


def test_old_man_hemlock_in_a_setup_reply_is_listed_but_never_refused_when_no_card_names_him(caplog):
    request, reply = setup_request(), {"normal": NORMAL, "disruption": "The oven went cold."}
    strangers = fill.setup_strangers(request, reply)
    assert "Old Man Hemlock" in strangers and "Bess" in strangers
    assert fill.fill_problem(request, reply) is None
    flow, check = fill_check(request)
    with caplog.at_level(logging.WARNING, logger="pulpermill"):
        assert check(reply) is None, "the fill is used on the first attempt"
    assert flow.notes == {"minor_names": len(strangers)}
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("call=fill step=fill soft problem accepted")]
    assert len(lines) == 1 and "Old Man Hemlock" in lines[0] and "Bess" in lines[0] and "by role" in lines[0]


def test_the_name_passes_when_a_card_or_the_writers_own_text_carries_it(caplog):
    for request in (setup_request(characters=("Pim", "Orla", "Hemlock", "Bess")),
                    setup_request(note="Pim bakes. Old Man Hemlock buys the first loaf. Bess at the dye works waves.")):
        reply = {"normal": NORMAL, "disruption": "The oven went cold."}
        assert fill.fill_problem(request, reply) is None and fill.setup_strangers(request, reply) == []
        flow, check = fill_check(request)
        with caplog.at_level(logging.WARNING, logger="pulpermill"):
            assert check(reply) is None
        assert flow.notes == {"minor_names": 0}
    assert not [r for r in caplog.records if "soft problem" in r.getMessage()]


def test_roles_cards_places_and_sentence_openers_are_not_listed_in_setup():
    normal = "Pim baked before dawn. The woodcutter left a stack by the door, and a neighbour came for the first loaf. Orla opened the shutters at the Millpond. On Tuesday the Parish Council met."
    reply = {"normal": normal, "disruption": "Then the oven went cold."}
    assert fill.fill_problem(setup_request(), reply) is None and fill.setup_strangers(setup_request(), reply) == []


def test_a_story_in_another_language_is_not_checked():
    request = setup_request(language="zh")
    reply = {"normal": "皮姆在黎明前烤面包。Hemlock Bess Tiber 来了。", "disruption": "炉子冷了。"}
    assert fill.fill_problem(request, reply) is None and fill.setup_strangers(request, reply) == []


def test_a_hard_problem_still_refuses_a_setup_fill_that_also_names_a_stranger(caplog):
    flow, check = fill_check(setup_request())
    with caplog.at_level(logging.WARNING, logger="pulpermill"):
        line = check({"normal": NORMAL, "disruption": ""})
    assert line and "disruption" in line and "minor_names" not in flow.notes
    assert not [r for r in caplog.records if "soft problem" in r.getMessage()]


def test_only_a_setup_fill_is_checked_for_names():
    request = {**setup_request(), "card": "world"}
    assert fill.setup_strangers(request, {"normal": NORMAL, "disruption": "The oven went cold."}) == []


# ---- names in the plan ------------------------------------------------------------------------------------------------------

def plan_request():
    return vector("plan", "a plan request")


def good_plan(request):
    return json.loads(plan.script(request, __import__("pulpermill.backend.kit", fromlist=["Kit"]).Kit(request))[1])


def test_master_elmsworth_in_a_plan_is_counted_not_refused_and_a_role_counts_nothing():
    request = plan_request()
    beat = good_plan(request)
    assert plan.plan_problem(request, beat) is None and plan.plan_names(request, beat) == (0, [])
    named = {**beat, "plan": beat["plan"] + " Master Elmsworth, a stern but fair member of the guild, oversees deliveries."}
    assert plan.plan_problem(request, named) is None                 # no problem line, so nothing is sent back and nothing is thrown away
    assert plan.plan_names(request, named) == (1, ["Master Elmsworth"])
    by_role = {**beat, "plan": beat["plan"] + " A stern but fair clerk oversees the deliveries."}
    assert plan.plan_problem(request, by_role) is None and plan.plan_names(request, by_role) == (0, [])


def test_names_on_cards_and_places_are_not_refused_in_a_plan():
    request = plan_request()
    beat = good_plan(request)
    cast = [p["name"] for p in request["cast"]]
    place = request["world"]["places"][0]["name"]
    beat["plan"] += f" Later, at {place}, {cast[0]} turns to {cast[-1]}."
    assert plan.plan_problem(request, beat) is None and plan.plan_names(request, beat) == (0, [])


# ---- names in the chapter ---------------------------------------------------------------------------------------------------

def test_an_invented_named_person_is_counted_not_refused_in_a_chapter_and_card_names_count_nothing():
    request = generate_request()
    request.pop("previous_ending", None)
    names = [p["name"] for p in request["cast"]]
    clean = f"{names[0]} shut the door. A clerk waited outside, and {names[-1]} nodded to him. Later {names[0]} walked home alone."
    assert gen.write_problem(request, clean) is None and gen.write_names(request, clean) == (0, [])
    honorific = clean + " Master Ashworth coughed once."
    assert gen.write_problem(request, honorific) is None            # the chapter is used on the first attempt
    assert gen.write_names(request, honorific) == (1, ["Master Ashworth"])
    repeated = clean + " She saw Silas at the stairs. Then Silas was gone."
    assert gen.write_problem(request, repeated) is None and gen.write_names(request, repeated) == (1, ["Silas"])


def test_a_single_unknown_capitalised_word_in_a_long_chapter_is_not_counted():
    request = generate_request()
    request.pop("previous_ending", None)
    text = "She walked past Tiber's old gate without a word, and went on home."
    assert gen.write_problem(request, text) is None and gen.write_names(request, text) == (0, [])          # a plain name counts only when it comes back


def test_names_spoken_in_dialogue_are_not_read_as_narration_but_an_honorific_still_counts():
    request = generate_request()
    request.pop("previous_ending", None)
    assert gen.write_names(request, "“Ask Silas,” she said. “Silas knows.” Then she left.") == (0, [])
    assert gen.write_names(request, "“Ask Mrs Hale,” she said, and left.") == (1, ["Mrs Hale"])


def test_a_chapter_in_chinese_is_not_checked_for_names():
    request = generate_request(language="zh-CN")
    request.pop("previous_ending", None)
    text = "她关上门。Silas 在楼梯上。Silas 走了。"
    assert gen.write_problem(request, text) is None and gen.write_names(request, text) == (0, [])


# ---- names the story already used are established ---------------------------------------------------------------------------

EARLIER = [{"chapter": 1, "happened": "Silas sold Pim a sack of flour at the stairs.", "changed": "Pim now owes Silas, and Master Ashworth knows it."}]


def test_a_name_in_an_earlier_chapters_events_is_counted_but_not_new_in_a_chapter():
    request = generate_request(earlier_events=EARLIER)
    request.pop("previous_ending", None)
    body = "Pim shut the door. She saw Silas at the stairs. Then Silas was gone, and Master Ashworth with him."
    assert gen.write_problem(request, body) is None
    assert gen.write_names(request, body) == (2, [])               # both walk-ons are in the history: counted by the old rule, not new
    fresh = body + " Later she met Zorblax at the gate and told Zorblax to wait."
    assert gen.write_names(request, fresh) == (3, ["Zorblax"])


def test_a_name_is_established_by_the_events_of_any_earlier_chapter_but_not_by_a_later_record_of_another_kind():
    request = generate_request(earlier_events=[{"chapter": 1, "happened": "Nothing.", "changed": "Nothing."}, *EARLIER[:1]])
    request.pop("previous_ending", None)
    assert gen.write_names(request, "Pim saw Silas at the stairs. Then Silas was gone.") == (1, [])
    assert gen.write_names(generate_request(earlier_events=[]), "Pim saw Silas at the stairs. Then Silas was gone.") == (1, ["Silas"])


def test_a_name_in_an_earlier_beats_plan_or_events_is_not_new_in_a_plan():
    request = plan_request()
    beat = good_plan(request)
    named = {**beat, "plan": beat["plan"] + " Master Elmsworth, a stern clerk, oversees deliveries."}
    assert plan.plan_names({**request, "earlier_beats": [], "earlier_events": []}, named) == (1, ["Master Elmsworth"])
    from_beat = {**request, "earlier_beats": [{"chapter": 1, "where": "x", "aim": "y", "plan": "Act 1: Master Elmsworth waits at the gate."}], "earlier_events": []}
    assert plan.plan_names(from_beat, named) == (1, [])
    from_events = {**request, "earlier_beats": [], "earlier_events": [{"chapter": 1, "happened": "Master Elmsworth came.", "changed": "Nothing else."}]}
    assert plan.plan_names(from_events, named) == (1, [])
    only_changed = {**request, "earlier_beats": [], "earlier_events": [{"chapter": 1, "happened": "Nothing.", "changed": "Master Elmsworth stayed."}]}
    assert plan.plan_names(only_changed, named) == (1, [])


def test_only_the_history_the_model_is_shown_establishes_a_name():
    request = {"earlier_events": [{"chapter": 1, "happened": "Silas came.", "changed": "Tiber left.", "id": "Zorblax"}],
               "earlier_beats": [{"chapter": 1, "where": "Zorblax's yard", "aim": "Find Zorblax", "plan": "Act 1: Hemlock waits."}]}
    assert common.earlier_records(request) == ["Silas came.", "Tiber left."]
    assert common.earlier_records(request, beats=True) == ["Silas came.", "Tiber left.", "Act 1: Hemlock waits."]
    assert common.earlier_records({}) == [] and common.earlier_records({"earlier_events": [None, "x"]}, beats=True) == []


def test_the_counts_directly_and_a_language_the_detector_does_not_read():
    request, known = {"language": "en"}, [{"cast": ["Pim", "Orla"]}]
    earlier = ["Hemlock came by."]
    text = "Pim met Hemlock at the gate. Then Hemlock left, and Bess waved. Later Pim told Bess to wait."
    assert common.minor_people(request, [text], known, earlier, min_count=2) == (2, ["Bess"])
    assert common.minor_people(request, [text], known, [], min_count=2) == (2, ["Hemlock", "Bess"])
    assert common.minor_people({"language": "zh"}, [text], known, earlier) == (0, [])
    assert common.minor_people(request, ["Orla spoke. Then Pim spoke."], known, earlier) == (0, [])


def test_the_detector_directly():
    known = {"Pim", "Orla"}
    assert common.strange_names("Pim finds Master Elmsworth at the Millpond.", known) == ["Master Elmsworth", "Millpond"]
    assert common.strange_names("Orla spoke. Then Pim spoke.", known) == []
    assert common.detects_names({}) and common.detects_names({"language": "en-GB"}) and not common.detects_names({"language": "zh"})
