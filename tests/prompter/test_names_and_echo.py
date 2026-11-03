"""A9: a chapter does not open on the end of the one before, and nobody who is on no card is named in the setup fill, the plan or the chapter.
The quoted examples come from a real run (test-6)."""
import copy
import json
import sys
from pathlib import Path

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
    request = {"call": "fill", "schema_version": 3, "language": "en", "card": "setup", "instance": None, "note": note, "example_chapter": None,
               "values": {}, "related": {"characters": [{"name": n} for n in characters],
                                         "world": world or {"name": "Millbrook", "places": [{"name": "The Millpond"}], "powers": [{"name": "The Parish Council"}]}}}
    request.update(over)
    return request


NORMAL = "Pim baked before dawn. Old Man Hemlock bought the first loaf and Bess at the dye works waved from her door."


def test_old_man_hemlock_in_a_setup_reply_is_refused_when_no_card_names_him():
    line = fill.fill_problem(setup_request(), {"normal": NORMAL, "disruption": "The oven went cold."})
    assert line and "Old Man Hemlock" in line and "Bess" in line and "by role" in line


def test_the_name_passes_when_a_card_or_the_writers_own_text_carries_it():
    assert fill.fill_problem(setup_request(characters=("Pim", "Orla", "Hemlock", "Bess")), {"normal": NORMAL, "disruption": "The oven went cold."}) is None
    assert fill.fill_problem(setup_request(note="Pim bakes. Old Man Hemlock buys the first loaf. Bess at the dye works waves."), {"normal": NORMAL, "disruption": "The oven went cold."}) is None


def test_roles_cards_places_and_sentence_openers_are_not_refused_in_setup():
    normal = "Pim baked before dawn. The woodcutter left a stack by the door, and a neighbour came for the first loaf. Orla opened the shutters at the Millpond. On Tuesday the Parish Council met."
    assert fill.fill_problem(setup_request(), {"normal": normal, "disruption": "Then the oven went cold."}) is None


def test_a_story_in_another_language_is_not_checked():
    request = setup_request(language="zh")
    assert fill.fill_problem(request, {"normal": "皮姆在黎明前烤面包。Hemlock Bess Tiber 来了。", "disruption": "炉子冷了。"}) is None


# ---- names in the plan ------------------------------------------------------------------------------------------------------

def plan_request():
    return vector("plan", "a plan request")


def good_plan(request):
    return json.loads(plan.script(request, __import__("pulpermill.backend.kit", fromlist=["Kit"]).Kit(request))[0])


def test_master_elmsworth_in_a_plan_is_refused_and_a_role_passes():
    request = plan_request()
    beat = good_plan(request)
    assert plan.plan_problem(request, beat) is None
    named = {**beat, "plan": beat["plan"] + " Master Elmsworth, a stern but fair member of the guild, oversees deliveries."}
    line = plan.plan_problem(request, named)
    assert line and "Master Elmsworth" in line and "by role" in line
    by_role = {**beat, "plan": beat["plan"] + " A stern but fair clerk oversees the deliveries."}
    assert plan.plan_problem(request, by_role) is None


def test_names_on_cards_and_places_are_not_refused_in_a_plan():
    request = plan_request()
    beat = good_plan(request)
    cast = [p["name"] for p in request["cast"]]
    place = request["world"]["places"][0]["name"]
    beat["plan"] += f" Later, at {place}, {cast[0]} turns to {cast[-1]}."
    assert plan.plan_problem(request, beat) is None


# ---- names in the chapter ---------------------------------------------------------------------------------------------------

def test_an_invented_named_person_is_refused_in_a_chapter_and_card_names_pass():
    request = generate_request()
    request.pop("previous_ending", None)
    names = [p["name"] for p in request["cast"]]
    clean = f"{names[0]} shut the door. A clerk waited outside, and {names[-1]} nodded to him. Later {names[0]} walked home alone."
    assert gen.write_problem(request, clean) is None
    honorific = clean + " Master Ashworth coughed once."
    line = gen.write_problem(request, honorific)
    assert line and "Master Ashworth" in line and "by role" in line
    repeated = clean + " She saw Silas at the stairs. Then Silas was gone."
    assert "Silas" in gen.write_problem(request, repeated)


def test_a_single_unknown_capitalised_word_in_a_long_chapter_is_let_through():
    request = generate_request()
    request.pop("previous_ending", None)
    assert gen.write_problem(request, "She walked past Tiber's old gate without a word, and went on home.") is None


def test_names_spoken_in_dialogue_are_not_read_as_narration_but_an_honorific_still_counts():
    request = generate_request()
    request.pop("previous_ending", None)
    assert gen.write_problem(request, "“Ask Silas,” she said. “Silas knows.” Then she left.") is None
    assert gen.write_problem(request, "“Ask Mrs Hale,” she said, and left.")


def test_a_chapter_in_chinese_is_not_checked_for_names():
    request = generate_request(language="zh-CN")
    request.pop("previous_ending", None)
    assert gen.write_problem(request, "她关上门。Silas 在楼梯上。Silas 走了。") is None


def test_the_detector_directly():
    known = {"Pim", "Orla"}
    assert common.strange_names("Pim finds Master Elmsworth at the Millpond.", known) == ["Master Elmsworth", "Millpond"]
    assert common.strange_names("Orla spoke. Then Pim spoke.", known) == []
    assert common.detects_names({}) and common.detects_names({"language": "en-GB"}) and not common.detects_names({"language": "zh"})
