"""Tests for the code checks, the trial set and the trial runner (phase 6). No model, no GPU. Run: python -m pytest tests/prompts"""
import importlib.util
import re
import sys
from pathlib import Path

import prompt_cases as cases
import trial_set
from test_render import generate_request

from pulpermill.prompts import chapter_checks as C
from pulpermill.prompts import prompts as P

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("run_trials", ROOT / "tools" / "run_trials.py")
run_trials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_trials)

GOOD_FIRST = ("I counted the till twice and it still came up short. “You never miss,” Aino said, and I did not answer him. "
              "The lamp hissed. I watched his hands, because hands tell the truth when faces will not. He turned his cap over and over. "
              "Pekka's door stayed shut. I put the brass key back on its nail and left it there, swinging a little, like a thing that knew.")


def ids(flags):
    return {f.id for f in flags}


def req(**beat):
    r = generate_request()
    r["beat"] = {**r["beat"], **beat}
    return r


# ---- The checks -----------------------------------------------------------------------------------------------------

def test_a_good_paragraph_in_the_asked_voice_raises_no_voice_flags():
    style = {"person": "first", "tense": "past"}
    assert not C.check_person_and_tense(GOOD_FIRST, style)
    assert not C.check_format(GOOD_FIRST[:200])


def test_the_wrong_person_is_flagged_both_ways():
    third = "Suvi counted the till twice. She watched Aino's hands. He turned his cap over. " * 10
    assert "person-first" in ids(C.check_person_and_tense(third, {"person": "first", "tense": "past"}))
    assert "person-third" in ids(C.check_person_and_tense(GOOD_FIRST * 6, {"person": "third", "tense": "past"}))
    assert "person-second" in ids(C.check_person_and_tense(third, {"person": "second", "tense": "past"}))


def test_the_words_of_a_speaker_do_not_count_as_the_narration():
    text = "Suvi counted the till. “I think I know what you did to me,” said Aino, “and I am sorry for my part.” " * 12
    assert not C.check_person_and_tense(text, {"person": "third", "tense": "past"})


def test_the_wrong_tense_is_flagged():
    present = "She is at the counter. He says nothing. The lamp is low and the room is cold. She takes the key and holds it. " * 8
    assert "tense" in ids(C.check_person_and_tense(present, {"person": "third", "tense": "past"}))
    assert not C.check_person_and_tense(present, {"person": "third", "tense": "present"})


def test_a_phrase_said_three_times_is_flagged_and_names_do_not_hide_it():
    text = "The water was cold and black. " + "Her hands were shaking again as the door closed behind her. " * 3 + "Then it was quiet."
    assert "repeat-phrase" in ids(C.check_repetition(text))
    assert not C.check_repetition(GOOD_FIRST)


def test_repeated_openers_and_sentence_starts_are_flagged():
    paras = "\n\n".join("Suvi did something small and quiet in the shop today." for _ in range(10))
    assert "repeat-opener" in ids(C.check_repetition(paras))
    run = " ".join(f"She {v} the thing." for v in ("held", "turned", "set", "lifted", "dropped", "found"))
    assert "repeat-sentence-start" in ids(C.check_repetition(run))


def test_leaked_structure_is_flagged():
    for bad in ("## Section 2\nThe door opened.", "Here is the next section:\nThe door opened.", "- the first thing\n- the second thing",
                "She **ran** home.", "Goal: reach the cellar.", "The door opened. <end_of_turn>"):
        assert "format-leak" in ids(C.check_format(bad)), bad
    assert not C.check_format("The door opened and nobody was there.")


def test_a_beat_sentence_copied_into_the_story_is_flagged():
    r = req(collision_goal="Suvi learns the ledger is in the cellar, but Aino now knows she is asking")
    text = "He stared. Suvi learns the ledger is in the cellar, but Aino now knows she is asking, and so on."
    assert "beat-echo" in ids(C.check_echo(text, r["beat"]))
    assert not C.check_echo("She learned where it was, and Aino saw her learn it.", r["beat"])


def test_a_hidden_truth_not_named_by_the_beat_is_flagged():
    r = generate_request()
    r["beat"]["reveal_rule"] = "The dock repairs were paid for by the shopkeepers, not the board."
    leak = "Then Pekka said it plainly: the cellar was sealed to hide the board's old accounts and had never flooded."
    assert "secret-early" in ids(C.check_secrets(leak, r))
    assert not C.check_secrets("The cellar smelled of damp, and the lock was new.", r)
    r["beat"]["reveal_rule"] = "The cellar under the shop floods on the spring tide."
    assert not C.check_secrets(leak, r)                     # the beat names this one: a reader decides


def test_cast_missing_and_offstage_are_flagged():
    r = generate_request()
    assert "cast-missing" in ids(C.check_cast("Suvi and Aino argued.", r))
    text = "Suvi, Aino and Pekka stood there. " + "Hale came. " * 5
    r["cast"].append({"name": "Hale"})
    assert "cast-offstage" in ids(C.check_cast(text, r))


def test_an_ending_that_misses_the_target_or_stops_mid_sentence_is_flagged():
    beat = {"ends_on": "Suvi finds her own initials in the ledger's last entry"}
    assert not C.check_ending("... She turned the page and there, in the last entry, were her own initials.", beat)
    assert "ending-target" in ids(C.check_ending("... They drank their tea and talked about the weather.", beat))
    assert "ending-cut" in ids(C.check_ending("She turned the page and there were her own", beat))


def test_dialogue_share_and_mixed_quotes():
    assert "dialogue-none" in ids(C.check_dialogue("She walked and walked and thought about the tide. " * 20))
    assert "quotes-mixed" in ids(C.check_dialogue('"One," she said. “Two,” he said. "Three." “Four.” "Five." “Six.” "Seven." “Eight.” "Nine."'))


def test_language_drift_is_flagged():
    assert "language-drift" in ids(C.check_language("She said 你好 and left."))
    assert not C.check_language("She said hello and left.")


def test_length_flags():
    assert "length-short" in ids(C.check_length("word " * 1000)) and "length-long" in ids(C.check_length("word " * 5000))
    assert not C.check_length("word " * 3000)


# ---- The trial set --------------------------------------------------------------------------------------------------

def test_four_trials_each_a_different_kind_of_chapter():
    all_ = trial_set.all_trials()
    assert list(all_) == list(trial_set.TRIALS) and len(all_) == 4
    assert [r["chapter"] for r in all_.values()] == [5, 6, 7, 1]
    assert len({(r["style"]["person"], r["style"]["tense"], r["style"]["pacing"]) for r in all_.values()}) == 4


def test_every_trial_renders_all_its_prompts_without_leaks():
    for name, r in trial_set.all_trials().items():
        for i in range(2):
            text = P.writer_prompt(r, P.writer_plan(), i, "" if i == 0 else "Suvi shut the till. " * 40).text
            assert not re.search(r"\{[a-z_]+\}", text) and "None" not in text, (name, i)
        assert r["beat"]["ends_on"] in P.writer_prompt(r, P.writer_plan(), 1, "x " * 50).text, name


def test_the_opening_trial_has_no_history_and_the_others_do():
    t = trial_set.all_trials()
    assert not t["T4-opening"]["earlier_events"] and not t["T4-opening"]["previous_ending"]
    assert "chapter 1 of" in P.writer_prompt(t["T4-opening"], P.writer_plan(), 0).text
    for name in ("T1-pressure", "T2-quiet", "T3-fast"):
        assert t[name]["earlier_events"] and t[name]["previous_ending"], name


def test_a_trial_changes_the_style_the_prompt_asks_for():
    a = P.writer_prompt(trial_set.trial("T1-pressure"), P.writer_plan(), 0).text
    b = P.writer_prompt(trial_set.trial("T2-quiet"), P.writer_plan(), 0).text
    assert "first person, past tense" in a and "third person, present tense" in b


def test_the_trials_are_made_the_same_way_every_time():
    assert trial_set.all_trials() == trial_set.all_trials()


# ---- The runner -----------------------------------------------------------------------------------------------------

def test_the_chapter_loop_writes_two_sections_and_the_second_sees_the_whole_first():
    seen = []

    def complete(text):
        seen.append(text)
        return cases.chapter_text(800)
    chapter, sections = run_trials.run_chapter(trial_set.trial("T1-pressure"), complete)
    assert len(sections) == 2 and len(seen) == 2
    assert "The first section of the chapter" not in seen[0] and sections[0] in seen[1]
    assert chapter.count("\n\n") >= 1


def test_a_short_chapter_is_left_short_and_a_cut_section_ends_on_a_sentence():
    outputs = iter([cases.chapter_text(300), cases.chapter_text(300) + " She was about to say that it wasn"])
    _, sections = run_trials.run_chapter(trial_set.trial("T1-pressure"), lambda text: next(outputs))
    assert len(sections) == 2 and sections[1].endswith(".") and not sections[1].endswith("wasn")


def test_a_result_file_has_the_chapter_first_and_the_flags_after(tmp_path=None):
    import tempfile
    out = Path(tempfile.mkdtemp())
    r = trial_set.trial("T1-pressure")
    row = run_trials.write_result(out, "T1-pressure", 1, r, cases.chapter_text(3000), "writer-0.1", "stub")
    text = (out / "T1-pressure-run1.md").read_text(encoding="utf-8")
    assert text.index("Read the chapter") < text.index("The harbour board") < text.index("Code flags")
    assert row["words"] > 2900 and row["prompt_version"] == "writer-0.1"
