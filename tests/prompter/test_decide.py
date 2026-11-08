"""The decider (Plan 1). Step 1: `parse_options` splits a brainstorm reply into options, each with its combination's number. The fixtures are
the brainstorm replies of chapters 1 and 2 of a real run (test 12): chapter 1 is three options; chapter 2 is three `Combination` groups of
three options and was cut off by the token cap in the middle of the seventh. Then the decider call: the shuffle, the prompt, the reply's check, and the pick, which code computes from the best and worst marks.
Everything but the two fixtures is written with neutral placeholder text: the decider says nothing about any one story, and its tests do not either."""
import copy
import json
import random
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


# ---- The decider call ---------------------------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
OPTIONS = [(1, "**Option 1: First (Combination 1)**\nThe protagonist wants one thing. A second person says no."),
           (2, "**Option 2 (Combination 2: A & B)**\nThe protagonist wants another thing. A rule gets in the way."),
           (3, "**Option 3: Combination 3 – A & B**\nThe protagonist wants a third thing. An object is lost.")]
ORDER = [2, 0, 1]                        # shown as A: the third option, B: the first, C: the second
OLD_WORDS = ("pick", "weakest", "loss", "irreversible", "opposed")


def request() -> dict:
    vectors = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
    return copy.deepcopy(next(v["data"] for v in vectors if v["valid"] and v["name"] == "a plan request"))


def first_chapter() -> dict:
    return {**request(), "chapter": 1, "earlier_beats": [], "earlier_events": []}


def reply(best=("A", "A", "B", "A"), worst=("B", "C", "C", "C"), criteria=decide.CRITERIA, n=3) -> dict:
    """A decider reply built by hand: a phrase for every letter, then the best and the worst letter, for each criterion."""
    return {k: {**{decide.LABELS[i]: f"Phrase {k} {decide.LABELS[i]}." for i in range(n)}, "best": b, "worst": w} for k, b, w in zip(criteria, best, worst)}


def test_the_order_is_a_seeded_shuffle_of_every_option_and_does_not_always_start_with_the_first():
    assert decide.order_of(OPTIONS, request()) == decide.order_of(OPTIONS, request())            # the same call shuffles the same way
    assert sorted(decide.order_of(OPTIONS, request())) == [0, 1, 2]
    firsts = {decide.order_of(OPTIONS, {"chapter": n})[0] for n in range(1, 40)}
    assert firsts == {0, 1, 2}, "across chapters every option is shown first at some point"
    many = [(n, f"text {n}") for n in range(1, 13)]
    assert sorted(decide.order_of(many, request())) == list(range(decide.OPTIONS_MAX)) == [0, 1, 2]            # more than three are left out


def test_a_header_loses_the_numbers_that_say_where_the_option_stood_and_keeps_its_other_words():
    assert decide.unnumbered(OPTIONS[0][1]) == "**First**\nThe protagonist wants one thing. A second person says no."
    assert decide.unnumbered(OPTIONS[1][1]) == "**(A & B)**\nThe protagonist wants another thing. A rule gets in the way."
    assert decide.unnumbered(OPTIONS[2][1]) == "**A & B**\nThe protagonist wants a third thing. An object is lost."
    assert decide.unnumbered("**Option 2:** Body of the option.") == "Body of the option."
    assert decide.unnumbered("Option 1: Plain header.\nOption 2 is mentioned in the body.") == "Plain header.\nOption 2 is mentioned in the body."


def test_the_prompt_shows_the_options_under_letters_in_the_shuffled_order_and_never_where_they_stood():
    prompt = decide.build_decide_prompt(request(), OPTIONS, ORDER)
    section = prompt.split("## The options to judge\n")[1].split("## Your task")[0]
    assert section.index("Option A\n") < section.index("Option B\n") < section.index("Option C\n")
    assert section.index("a third thing") < section.index("one thing") < section.index("another thing")      # the third option is shown first
    assert "Option 1" not in section and "Option 2" not in section and "Combination" not in section
    task = prompt.split("## Your task\n")[1]
    w = load_text("plan")
    assert w["decide_task"] in task and "no ending is better than another" in task
    assert prompt.startswith("You are the judge of a story that is written one chapter at a time. Before chapter 2")
    assert "running aim" in prompt and "decide_chain" not in w                                   # chapter 2 carries the chain in the history, not in the task


def test_the_prompt_has_each_criterion_once_three_in_chapter_one_and_four_from_chapter_two_and_asks_for_no_pick_or_scores():
    w = load_text("plan")
    second = decide.build_decide_prompt(request(), OPTIONS, ORDER)
    first = decide.build_decide_prompt(first_chapter(), OPTIONS, ORDER)
    for key in ("decide_hook", "decide_resistance", "decide_change", "decide_raise"):
        assert second.count(w[key]) == 1, key
    assert all(first.count(w[key]) == 1 for key in ("decide_hook", "decide_resistance", "decide_change")) and w["decide_raise"] not in first
    assert "hook, resistance, change and raise" in second and "hook, resistance and change" in first and "raise" not in first.split("## Your task")[1].split("Reply with")[1]
    for prompt in (first, second):
        assert not any(word in prompt.lower() for word in OLD_WORDS), [word for word in OLD_WORDS if word in prompt.lower()]
        assert "best and worst" in prompt and "at most 200 characters" in prompt and "in English" in prompt
        assert prompt.count("write the phrases first") == 1
    assert [decide.criteria_for(r) for r in (first_chapter(), request(), {"chapter": None}, {})] == [decide.CRITERIA[:3], decide.CRITERIA, decide.CRITERIA[:3], decide.CRITERIA[:3]]


def test_the_prompt_holds_no_ids():
    ids = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("id"), str):
                ids.add(node["id"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(request())
    prompt = decide.build_decide_prompt(request(), OPTIONS, ORDER)
    assert ids and all(i not in prompt for i in ids)


def test_the_grammar_asks_for_a_phrase_per_letter_then_best_and_worst_for_each_criterion_and_no_pick():
    g = decide.grammar(3, decide.CRITERIA)
    assert list(g["properties"]) == list(decide.CRITERIA) and g["required"] == list(decide.CRITERIA) and g["additionalProperties"] is False
    entry = g["properties"]["hook"]
    assert list(entry["properties"]) == ["A", "B", "C", "best", "worst"] and entry["required"] == list(entry["properties"]) and entry["additionalProperties"] is False
    assert entry["properties"]["best"]["enum"] == entry["properties"]["worst"]["enum"] == ["A", "B", "C"] and entry["properties"]["A"] == {"type": "string"}
    assert "pick" not in g["properties"] and list(decide.grammar(3, decide.CRITERIA[:3])["properties"]) == ["hook", "resistance", "change"]


def test_the_check_wants_every_criterion_a_short_phrase_for_every_letter_and_a_different_best_and_worst():
    p = load_text("plan")["problems"]
    assert decide.decide_problem(reply(), 3, decide.CRITERIA) is None and decide.decide_problem(reply(criteria=decide.CRITERIA[:3]), 3, decide.CRITERIA[:3]) is None
    assert decide.decide_problem(reply(criteria=decide.CRITERIA[:3]), 3, decide.CRITERIA) == p["decide_shape"]          # a criterion missing
    missing = reply()
    del missing["change"]["B"]
    assert decide.decide_problem(missing, 3, decide.CRITERIA) == p["decide_shape"] and decide.decide_problem({}, 3, decide.CRITERIA) == p["decide_shape"]
    assert decide.decide_problem(None, 3, decide.CRITERIA) == p["decide_shape"] and decide.decide_problem({**reply(), "hook": "text"}, 3, decide.CRITERIA) == p["decide_shape"]
    for bad in (" ", "x" * (decide.PHRASE_MAX + 1), 3):
        phrase = reply()
        phrase["hook"]["C"] = bad
        assert decide.decide_problem(phrase, 3, decide.CRITERIA) == p["decide_phrase"]
    ok = reply()
    ok["hook"]["C"] = "x" * decide.PHRASE_MAX
    assert decide.decide_problem(ok, 3, decide.CRITERIA) is None
    for best, worst in (("A", "A"), ("A", "Z"), ("Z", "A"), (None, "A")):
        same = reply()
        same["resistance"].update(best=best, worst=worst)
        assert decide.decide_problem(same, 3, decide.CRITERIA) == p["decide_best_worst"], (best, worst)


def test_the_scores_are_plus_one_for_each_best_and_minus_one_for_each_worst():
    assert decide.scores(reply(), 3, decide.CRITERIA) == [3, 0, -3]
    assert decide.scores(reply(criteria=decide.CRITERIA[:3]), 3, decide.CRITERIA[:3]) == [2, 0, -2] and decide.scores({}, 3) == [0, 0, 0]


def test_the_pick_is_the_option_with_the_highest_total_whatever_letter_it_stood_under():
    for wanted, letter in ((3, "A"), (1, "B"), (2, "C")):             # shown as A: the third option, B: the first, C: the second
        other = "B" if letter == "A" else "A"
        got = decide.decide(OPTIONS, ORDER, reply(best=(letter,) * 4, worst=(other,) * 4), decide.CRITERIA)
        assert (got.position, got.combo, got.fell_back, got.order, got.tied) == (wanted, wanted, False, (3, 1, 2), 1)


def test_a_tie_picks_one_of_the_tied_options_at_random():
    tie = reply(best=("A", "B", "A", "B"), worst=("C", "C", "B", "A"))        # totals: A 1, B 1, C -2
    seen = set()
    for seed in range(40):
        random.seed(seed)
        got = decide.decide(OPTIONS, ORDER, tie, decide.CRITERIA)
        assert got.tied == 2 and got.scores == (1, -2, 1) and not got.fell_back
        seen.add(got.position)
    assert seen == {1, 3}                                                     # A is the third option, B the first: both win sometimes, C never


def test_a_result_that_cannot_be_used_picks_a_random_option_and_says_it_fell_back():
    for value in ({}, None, {"pick": "Z"}, {"hook": {}}, reply(best=("A", "A", "A", "A"), worst=("A", "A", "A", "A"))):
        got = decide.decide(OPTIONS, ORDER, value, decide.CRITERIA)
        assert got.fell_back and got.position in (1, 2, 3) and got.scores == (0, 0, 0) and got.marks == {} and got.combo == got.position
    seen = set()
    for seed in range(60):
        random.seed(seed)
        seen.add(decide.decide(OPTIONS, ORDER, {}, decide.CRITERIA).position)
    assert seen == {1, 2, 3}, "a fallback is not always the first option"


def test_the_notes_carry_the_totals_and_every_mark_as_short_plain_words():
    random.seed(1)
    got = decide.decide(OPTIONS, ORDER, reply(), decide.CRITERIA)                  # A (place 3) wins with 3; B (place 1) has 0; C (place 2) has -3
    assert got.notes() == {"decide": "on", "decide_options": 3, "decide_order": "3-1-2", "decide_pick": 3, "decide_combo": 3, "decide_sampling": "structured",
                           "decide_s1": 0, "decide_s2": -3, "decide_s3": 3, "decide_tied": 1, "decide_invented": 0,
                           "decide_hook_best": "A3", "decide_hook_worst": "B1", "decide_resistance_best": "A3", "decide_resistance_worst": "C2",
                           "decide_change_best": "B1", "decide_change_worst": "C2", "decide_raise_best": "A3", "decide_raise_worst": "C2"}
    three = decide.decide(OPTIONS, ORDER, reply(criteria=decide.CRITERIA[:3]), decide.CRITERIA[:3]).notes()
    assert not any("raise" in k for k in three) and "decide_change_best" in three
    fell = decide.decide(OPTIONS, ORDER, {}, decide.CRITERIA).notes()
    assert fell["decide"] == "fallback" and fell["decide_s1"] == fell["decide_s2"] == fell["decide_s3"] == 0 and fell["decide_tied"] == 3 and "decide_hook_best" not in fell


def test_the_notes_are_only_what_the_run_log_may_keep():
    pytest.importorskip("starlette")
    import re
    from pulpermill.backend import runlog
    notes = decide.decide(OPTIONS, ORDER, reply(), decide.CRITERIA).notes()
    assert runlog._plain_notes(notes) == notes and all(len(k) <= 32 for k in notes)
    assert all(isinstance(v, (bool, int)) or re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", v) for v in notes.values())


def test_the_step_is_a_small_low_temperature_json_call_with_two_attempts_and_a_fallback_that_makes_no_call():
    flags = []
    step = decide.step(request(), OPTIONS, ORDER, lambda: flags.append("fell back"), decide.criteria_for(request()))
    assert (step.name, step.kind, step.sampling, step.attempts, step.language) == ("decide", "json", "structured", 2, False)
    assert step.max_output == decide.MAX_OUTPUT < 1200 and step.grammar == decide.grammar(3, decide.CRITERIA)
    assert step.text(1.0) == decide.build_decide_prompt(request(), OPTIONS, ORDER)
    assert step.check(reply()) is None and step.check({}) == load_text("plan")["problems"]["decide_shape"]
    assert step.fallback() == {} and flags == ["fell back"]
    assert decide.step(first_chapter(), OPTIONS, ORDER, lambda: None).grammar == decide.grammar(3, decide.CRITERIA[:3])


def test_the_step_runs_on_the_fake_engine_and_a_reply_that_cannot_be_used_twice_falls_back():
    pytest.importorskip("starlette")
    from pulpermill.backend import runner
    from pulpermill.backend.config import Config
    from pulpermill.backend.engine import FakeEngine
    from pulpermill.backend.engine.base import CancelFlag
    from pulpermill.backend.pipelines import RunContext
    flags = []
    step = decide.step(request(), OPTIONS, ORDER, lambda: flags.append(1))
    good = FakeEngine()
    good.script(json.dumps(reply()))
    result = runner.run_step(RunContext(good, CancelFlag(), [].append, Config()), step, 1.0, "en")
    assert result.value == reply() and not result.fallback and good.calls == 1 and good.prompts[0] == step.text(1.0)
    bad = FakeEngine()
    bad.script(json.dumps(reply(best=("A",) * 4, worst=("A",) * 4)), "not json")
    ctx = RunContext(bad, CancelFlag(), [].append, Config())
    result = runner.run_step(ctx, step, 1.0, "en")
    assert result.value == {} and result.fallback and bad.calls == 2 and flags == [1] and decide.decide(OPTIONS, ORDER, result.value, decide.CRITERIA).fell_back
    assert ctx.notes["passes"][0]["step"] == "decide" and ctx.notes["passes"][0]["fallback"] is True
    assert load_text("plan")["problems"]["decide_best_worst"] in bad.prompts[1]          # the retry says what to fix


def test_the_worst_case_stand_in_is_three_options_each_as_long_as_the_brainstorm_allows():
    stand = decide.stand_in(1200)
    assert len(stand) == decide.OPTIONS_MAX == 3 and sum(len(t.split()) for _, t in stand) <= 1200 and [n for n, _ in stand] == [1, 2, 3]


# ---- Each option shown with the combination it is built on (choose mode) -------------------------------------------------------

def choose_combos():
    """Three different combinations as the select step makes them, from the choose request of the select tests (its reasons name the combination
    by number, as a model may: the decider must not show it)."""
    pytest.importorskip("starlette")
    from test_select import choose_request
    from pulpermill.prompter.mill import select
    req = choose_request()
    picks = [{"reason": f"The tie and the rule or object of combination {n} pull against what the protagonist wants. Option {n} is the way in.", "tie": t, "pressure": p}
             for n, (t, p) in enumerate(((1, 1), (2, 2), (3, 1)), 1)]
    combos = select.combos(req, {"picks": picks})
    assert combos is not None and len({c["tie_words"] for c in combos}) == 3
    return select.without_pair(req), combos


def item_of(prompt: str, letter: str) -> str:
    """The lettered option's block of the prompt: from its header to the next option or the end of the section."""
    section = prompt.split("## The options to judge\n")[1].split("## Your task")[0]
    return section.split(f"Option {letter}\n")[1].split("\n\nOption ")[0]


def test_in_choose_mode_each_option_is_shown_with_its_own_tie_edge_rule_or_object_and_reason_and_never_its_number():
    req, combos = choose_combos()
    prompt = decide.build_decide_prompt(req, OPTIONS, ORDER, 1.0, None, combos)
    for letter, place in zip("ABC", ORDER):                         # A shows the third option, B the first, C the second
        item, mine = item_of(prompt, letter), combos[place]
        assert OPTIONS[place][1].split("\n")[1] in item                               # the option's own text
        assert "It is built on:" in item and f"The tie: {mine['tie_words']}" in item and mine["tie_words"].count("edge:") == 1 and "(edge:" in item
        assert mine["pressure_words"] in item and "How they may collide:" in item
        others = [c for k, c in enumerate(combos) if k != place]
        assert all(c["tie_words"] not in item for c in others)
    section = prompt.split("## The options to judge\n")[1].split("## Your task")[0]
    assert "combination" not in section.lower() and "Option 1" not in section and not any(f"Option {n}" in section for n in (1, 2, 3))      # the selector's reason named it: replaced
    assert "this one" in section and prompt.count(load_text("plan")["decide_combos"]) == 1


def test_with_another_shuffle_the_same_option_keeps_its_own_combination_lines():
    req, combos = choose_combos()
    first = decide.build_decide_prompt(req, OPTIONS, [2, 0, 1], 1.0, None, combos)
    second = decide.build_decide_prompt(req, OPTIONS, [1, 2, 0], 1.0, None, combos)
    assert "a third thing" in item_of(first, "A") and combos[2]["tie_words"] in item_of(first, "A")
    assert "a third thing" in item_of(second, "B") and combos[2]["tie_words"] in item_of(second, "B")
    assert "one thing" in item_of(second, "C") and combos[0]["tie_words"] in item_of(second, "C")


def test_a_combination_without_a_rule_or_object_shows_the_tie_and_the_reason_only():
    req, combos = choose_combos()
    bare = [{**c, "pressure": None, "pressure_words": ""} for c in combos]
    item = item_of(decide.build_decide_prompt(req, OPTIONS, ORDER, 1.0, None, bare), "A")
    assert "The tie:" in item and "How they may collide:" in item and "The rule" not in item and "The object" not in item


def test_plain_mode_adds_no_combination_lines_and_does_not_say_the_options_carry_them():
    prompt = decide.build_decide_prompt(request(), OPTIONS, ORDER)
    for text in ("It is built on:", "How they may collide:", "The tie:", load_text("plan")["decide_combos"]):
        assert text not in item_of(prompt, "A") and text not in prompt.split("## Your task")[1], text


def test_the_step_and_the_worst_case_prompt_carry_the_combinations():
    req, combos = choose_combos()
    step = decide.step(req, OPTIONS, ORDER, lambda: None, None, combos)
    assert step.text(1.0) == decide.build_decide_prompt(req, OPTIONS, ORDER, 1.0, None, combos) and "It is built on:" in step.text(1.0)
    assert "It is built on:" not in decide.step(req, OPTIONS, ORDER, lambda: None).text(1.0)


# ---- Invented names -------------------------------------------------------------------------------------------------------------

INVENTED = "The protagonist asks Zorbax Quillfeather to open the gate."
PLAIN = "The protagonist asks the guard to open the gate."


def named(text: str, n: int = 1) -> tuple[int, str]:
    return (n, f"**Option {n}: A Title**\n{text}")


def test_an_option_that_names_a_person_on_no_card_is_flagged_and_a_header_title_is_not_a_name():
    options = [named(INVENTED, 1), named(PLAIN, 2), (3, f"**Option 3:** {INVENTED}")]
    assert decide.invented(request(), options) == [True, False, True]


def test_a_name_on_a_card_or_in_an_earlier_chapters_record_is_not_flagged():
    req = request()
    assert decide.invented(req, [named(INVENTED)]) == [True]
    on_card = {**req, "setup": f"{req.get('setup') or ''} Zorbax Quillfeather keeps the gate."}
    assert decide.invented(on_card, [named(INVENTED)]) == [False]
    earlier = {**req, "earlier_events": [*req["earlier_events"], {"chapter": 1, "happened": "Zorbax Quillfeather locked the gate.", "changed": ""}]}
    assert decide.invented(earlier, [named(INVENTED)]) == [False]
    earlier_plan = {**req, "earlier_beats": [*req["earlier_beats"], {"chapter": 1, "plan": "Zorbax Quillfeather locked the gate."}]}
    assert decide.invented(earlier_plan, [named(INVENTED)]) == [False]


def test_a_story_in_a_language_the_detector_does_not_read_gets_no_penalty():
    assert decide.invented({**request(), "language": "de"}, [named(INVENTED)]) == [False]


def test_an_option_that_invents_a_name_loses_one_point_to_an_otherwise_equal_option():
    flagged = [False, False, False]
    flagged[2] = True                                  # the third option (shown as A) names a stranger
    tie = reply(best=("A", "B", "A", "B"), worst=("C", "C", "B", "A"))               # totals by letter: A 1, B 1, C -2
    seen = set()
    for seed in range(40):
        random.seed(seed)
        got = decide.decide(OPTIONS, ORDER, tie, decide.CRITERIA, flagged)
        assert got.scores == (1, -2, 0) and got.tied == 1 and got.position == 1 and got.invented == 1 and not got.fell_back
        seen.add(got.position)
    assert seen == {1}                                 # without the penalty the third option wins half the time (see the tie test)


def test_a_penalty_is_not_an_elimination():
    got = decide.decide(OPTIONS, ORDER, reply(), decide.CRITERIA, [False, False, True])        # A (place 3) leads with 3 and loses one point: still wins with 2
    assert (got.position, got.scores, got.invented) == (3, (0, -3, 2), 1)


def test_nothing_is_penalized_when_nothing_was_compared_but_the_count_is_noted():
    got = decide.decide(OPTIONS, ORDER, {}, decide.CRITERIA, [True, False, True])
    assert got.fell_back and got.scores == (0, 0, 0) and got.invented == 2


def test_the_notes_carry_how_many_options_were_flagged_as_a_number():
    got = decide.decide(OPTIONS, ORDER, reply(), decide.CRITERIA, [True, False, True])
    assert got.notes()["decide_invented"] == 2 and isinstance(got.notes()["decide_invented"], int)
    assert decide.decide(OPTIONS, ORDER, reply(), decide.CRITERIA).notes()["decide_invented"] == 0
