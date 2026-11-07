"""The decider (Plan 1). Step 1: `parse_options` splits a brainstorm reply into options, each with its combination's number. The fixtures are
the brainstorm replies of chapters 1 and 2 of a real run (test 12): chapter 1 is three options; chapter 2 is three `Combination` groups of
three options and was cut off by the token cap in the middle of the seventh. Step 2: the shuffle, the prompt, the reply's check and the pick.
Everything but the two fixtures is written with neutral placeholder text: the decider says nothing about any one story, and its tests do not either."""
import copy
import json
from pathlib import Path

import pytest

from pulpermill.prompter.mill import decide
from pulpermill.prompter.mill.common import load_text

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CHAPTER_1 = (FIXTURES / "brainstorm_chapter1.txt").read_text(encoding="utf-8")
CHAPTER_2 = (FIXTURES / "brainstorm_chapter2.txt").read_text(encoding="utf-8")


def test_chapter_1_is_three_options_numbered_one_to_three_with_their_headers_and_no_lead_in():
    options = decide.parse_options(CHAPTER_1)
    assert [n for n, _ in options] == [1, 2, 3]
    assert options[0][1].startswith("**Option 1: Applewood and Approval") and options[2][1].startswith("**Option 3: Reliable Rise")
    assert all("Here are three options" not in t and "## Chapter" not in t for _, t in options)
    assert options[0][1].endswith("outmaneuver Corbin’s storytelling.") and "**Option 2" not in options[0][1]
    assert options[2][1].endswith("rare grunt of approval.")


def test_chapter_2_keeps_the_six_whole_options_with_their_group_and_drops_the_one_cut_off_mid_sentence():
    assert CHAPTER_2.rstrip().endswith("Losing")                                   # the fixture is what the token cap left
    options = decide.parse_options(CHAPTER_2)
    assert [n for n, _ in options] == [1, 1, 1, 2, 2, 2]                            # the combination of the group, not the option's own number
    assert options[0][1].startswith("**Option 1:** Pim wants to sneak away") and options[3][1].startswith("**Option 1:** Pim wants to share the stone")
    assert options[2][1].endswith("‘seasonal offering’.") and options[5][1].endswith("charmed by her enthusiasm.")
    assert all("**Combination" not in t and "during a lull in baking" not in t for _, t in options)       # group headers and the cut-off option are in no option


def test_a_cut_off_last_option_is_dropped_and_fewer_than_two_options_gives_nothing():
    third = CHAPTER_1.index("**Option 3")
    assert [n for n, _ in decide.parse_options(CHAPTER_1[:third + 200])] == [1, 2]       # option 3 stops mid-sentence
    assert decide.parse_options(CHAPTER_1[:CHAPTER_1.index("**Option 2") + 200]) == []   # one whole option and a cut-off one
    assert [n for n, _ in decide.parse_options(CHAPTER_1[:third] + "**Option 3: Header only**")] == [1, 2]      # a header with no text is cut off too


def test_nothing_to_split_gives_nothing():
    for text in ("", "   \n", "No options here, only a paragraph that ends well.", "**Option 1:** Only one option, and it is whole."):
        assert decide.parse_options(text) == []


def test_the_other_shapes_models_write_are_read_the_same_way():
    parenthesis = ("## Chapter 4 Options:\n\n**Option 1 (Combination 1: A & B)**\nThe protagonist wants a first thing. A refuses.\n\n"
                   "**Option 2 (Combination 2: A & C)**\nThe protagonist wants a second thing. B laughs.\n")
    assert decide.parse_options(parenthesis) == [(1, "**Option 1 (Combination 1: A & B)**\nThe protagonist wants a first thing. A refuses."),
                                                 (2, "**Option 2 (Combination 2: A & C)**\nThe protagonist wants a second thing. B laughs.")]
    overall = ("## Chapter 5 Options:\n\n**Overall Aim:** The protagonist intends to find the third thing.\n\n**Option 1: Combination 1 – A & B.**\nA clash at the first place.\n\n"
               "---\n\n**Option 2: Combination 2 – C & A.**\nA clash at the second place.\n")
    assert decide.parse_options(overall) == [(1, "**Option 1: Combination 1 – A & B.**\nA clash at the first place."),
                                             (2, "**Option 2: Combination 2 – C & A.**\nA clash at the second place.")]
    assert decide.parse_options("Option 1: a refusal. Option 2: a trade.") == []         # the words must start a line: one line is one option or none
    plain = "1. nothing\n\nOption 1: A refusal at the first place.\nOption 2: A trade at the second place.\nOption 3: A lie at the third place."
    assert [n for n, _ in decide.parse_options(plain)] == [1, 2, 3]


# ---- Step 2: the decider call --------------------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
OPTIONS = [(1, "**Option 1: First (Combination 1)**\nThe protagonist wants one thing. A second person says no."),
           (2, "**Option 2 (Combination 2: A & B)**\nThe protagonist wants another thing. A rule gets in the way."),
           (3, "**Option 3: Combination 3 – A & B**\nThe protagonist wants a third thing. An object is lost.")]


def request() -> dict:
    vectors = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
    return copy.deepcopy(next(v["data"] for v in vectors if v["valid"] and v["name"] == "a plan request"))


def reply(pick: str, n: int = 3, **over) -> dict:
    entry = {"weakest": "It is thin in the middle.", "loss": 2, "irreversible": True, "opposed": False}
    return {"options": [{"label": decide.LABELS[i], **{**entry, **over}} for i in range(n)], "pick": pick}


def test_the_order_is_a_seeded_shuffle_of_every_option_and_does_not_always_start_with_the_first():
    assert decide.order_of(OPTIONS, request()) == decide.order_of(OPTIONS, request())            # the same call shuffles the same way
    assert sorted(decide.order_of(OPTIONS, request())) == [0, 1, 2]
    firsts = {decide.order_of(OPTIONS, {"chapter": n})[0] for n in range(1, 40)}
    assert firsts == {0, 1, 2}, "across chapters every option is shown first at some point"
    many = [(n, f"text {n}") for n in range(1, 13)]
    assert sorted(decide.order_of(many, request())) == list(range(decide.OPTIONS_MAX))            # more than the most are left out


def test_a_header_loses_the_numbers_that_say_where_the_option_stood_and_keeps_its_other_words():
    assert decide.unnumbered(OPTIONS[0][1]) == "**First**\nThe protagonist wants one thing. A second person says no."
    assert decide.unnumbered(OPTIONS[1][1]) == "**(A & B)**\nThe protagonist wants another thing. A rule gets in the way."
    assert decide.unnumbered(OPTIONS[2][1]) == "**A & B**\nThe protagonist wants a third thing. An object is lost."
    assert decide.unnumbered("**Option 2:** Body of the option.") == "Body of the option."
    assert decide.unnumbered("Option 1: Plain header.\nOption 2 is mentioned in the body.") == "Plain header.\nOption 2 is mentioned in the body."


def test_the_prompt_shows_the_options_under_letters_in_the_shuffled_order_and_never_where_they_stood():
    order = [2, 0, 1]
    prompt = decide.build_decide_prompt(request(), OPTIONS, order)
    section = prompt.split("## The options to judge\n")[1].split("## Your task")[0]
    assert section.index("Option A\n") < section.index("Option B\n") < section.index("Option C\n")
    assert section.index("a third thing") < section.index("one thing") < section.index("another thing")      # the third option is shown first
    assert "Option 1" not in section and "Option 2" not in section and "Combination" not in section
    task = prompt.split("## Your task\n")[1]
    assert load_text("plan")["decide_task"] in task and load_text("plan")["decide_output"] in task
    assert "weakest point first" in task and "stands to lose" in task and "irreversible" in task and "actively works against" in task
    assert prompt.startswith("You are the judge of a story that is written one chapter at a time. Before chapter 2")
    assert "running aim" in prompt                                              # chapter 2 carries the chain: the prompt says to weigh it
    first = {**request(), "chapter": 1, "earlier_beats": [], "earlier_events": []}
    assert load_text("plan")["decide_chain"] not in decide.build_decide_prompt(first, OPTIONS, order)


def test_the_grammar_asks_for_one_entry_per_option_weak_point_first_then_the_pick():
    g = decide.grammar(3)
    entry = g["properties"]["options"]["items"]
    assert list(entry["properties"]) == ["label", "weakest", "loss", "irreversible", "opposed"] and entry["required"] == list(entry["properties"])
    assert g["properties"]["options"]["minItems"] == g["properties"]["options"]["maxItems"] == 3 and g["properties"]["pick"]["enum"] == ["A", "B", "C"]
    assert list(g["properties"]) == ["options", "pick"] and g["additionalProperties"] is False and entry["additionalProperties"] is False


def test_the_check_wants_every_letter_once_and_a_weak_point_of_one_sentence_and_nothing_else():
    p = load_text("plan")["problems"]
    assert decide.decide_problem(reply("B"), 3) is None
    assert decide.decide_problem(reply("B", n=2), 3) == p["decide_labels"]                                  # a letter missing
    dup = reply("A")
    dup["options"][1]["label"] = "A"
    assert decide.decide_problem(dup, 3) == p["decide_labels"] and decide.decide_problem({}, 3) == p["decide_labels"]
    assert decide.decide_problem(reply("A", weakest=" "), 3) == p["decide_weakest"]
    assert decide.decide_problem(reply("A", weakest="x" * (decide.WEAKEST_MAX + 1)), 3) == p["decide_weakest"]
    assert decide.decide_problem(reply("A", weakest="x" * decide.WEAKEST_MAX), 3) is None


def test_the_pick_is_the_original_combination_of_the_option_behind_the_letter():
    order = [2, 0, 1]                        # shown as A: the third option, B: the first, C: the second
    for letter, combo, place in (("A", 3, 3), ("B", 1, 1), ("C", 2, 2)):
        got = decide.decide(OPTIONS, order, reply(letter))
        assert (got.combo, got.position, got.fell_back, got.order) == (combo, place, False, (3, 1, 2))
    grouped = [(1, "a."), (1, "b."), (2, "c."), (2, "d.")]                  # several options for one combination: the combination is the answer
    assert decide.decide(grouped, [3, 2, 1, 0], reply("B", n=4)).combo == 2 and decide.decide(grouped, [3, 2, 1, 0], reply("D", n=4)).position == 1


def test_a_result_that_cannot_be_used_picks_the_first_option_and_says_it_fell_back():
    for value in ({}, None, {"pick": "Z"}, {"pick": 2}, {"options": []}):
        got = decide.decide(OPTIONS, [1, 2, 0], value)
        assert (got.combo, got.position, got.fell_back) == (1, 1, True)
    assert decide.decide(OPTIONS, [1, 2, 0], {}).notes() == {"decide": "fallback", "decide_options": 3, "decide_order": "2-3-1", "decide_pick": 1, "decide_combo": 1}
    assert decide.decide(OPTIONS, [1, 2, 0], reply("C")).notes() == {"decide": "on", "decide_options": 3, "decide_order": "2-3-1", "decide_pick": 1, "decide_combo": 1}


def test_the_notes_are_only_what_the_run_log_may_keep():
    pytest.importorskip("starlette")
    from pulpermill.backend import runlog
    notes = decide.decide(OPTIONS, [1, 2, 0], reply("A")).notes()
    assert runlog._plain_notes(notes) == notes
    nine = decide.decide([(n, "x.") for n in range(1, 10)], list(range(9)), reply("I", n=9)).notes()
    assert runlog._plain_notes(nine) == nine


def test_the_step_is_a_small_low_temperature_json_call_with_two_attempts_and_a_fallback_that_makes_no_call():
    flags = []
    step = decide.step(request(), OPTIONS, [2, 0, 1], lambda: flags.append("fell back"))
    assert (step.name, step.kind, step.sampling, step.attempts, step.language) == ("decide", "json", "structured", 2, False)
    assert step.max_output == decide.MAX_OUTPUT < 1200 and step.grammar == decide.grammar(3)
    assert step.text(1.0) == decide.build_decide_prompt(request(), OPTIONS, [2, 0, 1])
    assert step.check(reply("A")) is None and step.check({}) == load_text("plan")["problems"]["decide_labels"]
    assert step.fallback() == {} and flags == ["fell back"]


def test_the_step_runs_on_the_fake_engine_and_a_reply_that_cannot_be_used_twice_falls_back():
    pytest.importorskip("starlette")
    from pulpermill.backend import runner
    from pulpermill.backend.config import Config
    from pulpermill.backend.engine import FakeEngine
    from pulpermill.backend.engine.base import CancelFlag
    from pulpermill.backend.pipelines import RunContext
    flags = []
    step = decide.step(request(), OPTIONS, [2, 0, 1], lambda: flags.append(1))
    good, engine = FakeEngine(), None
    good.script(json.dumps(reply("B")))
    result = runner.run_step(RunContext(good, CancelFlag(), [].append, Config()), step, 1.0, "en")
    assert result.value == reply("B") and not result.fallback and good.calls == 1 and good.prompts[0] == step.text(1.0)
    bad = FakeEngine()
    bad.script("not json", json.dumps(reply("B", n=2)))
    ctx = RunContext(bad, CancelFlag(), [].append, Config())
    result = runner.run_step(ctx, step, 1.0, "en")
    assert result.value == {} and result.fallback and bad.calls == 2 and flags == [1] and decide.decide(OPTIONS, [2, 0, 1], result.value).fell_back
    assert ctx.notes["passes"][0]["step"] == "decide" and ctx.notes["passes"][0]["fallback"] is True


def test_the_worst_case_stand_in_is_the_most_options_each_as_long_as_the_brainstorm_allows():
    stand = decide.stand_in(1200)
    assert len(stand) == decide.OPTIONS_MAX and sum(len(t.split()) for _, t in stand) <= 1200 and [n for n, _ in stand] == list(range(1, 10))
