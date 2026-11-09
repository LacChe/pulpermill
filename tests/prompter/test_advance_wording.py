"""The advancement judge (2B): the steps build against a request, the grammar accepts only the enums, the verdict helpers are neutral on
what they cannot read, and the labelled cases build into prompts. Nothing here runs a model."""
import copy
import json
from pathlib import Path

import pytest

from pulpermill.prompter.mill import advance, common

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
CASES = json.loads((ROOT / "evals/advance/cases.json").read_text())


def request(**changes) -> dict:
    data = copy.deepcopy(next(v["data"] for v in VECTORS if v["valid"] and v["name"] == "a plan request"))
    data.update(chapter=3, earlier_beats=[{"chapter": 1, "aim": "Bake sun loaves.", "plan": "p"}, {"chapter": 2, "aim": "Get wood.", "plan": "p"}])
    data.update(changes)
    return data


def ids_in(text: str, req: dict) -> list[str]:
    found = []
    def walk(n):
        if isinstance(n, dict):
            if isinstance(n.get("id"), str):
                found.append(n["id"])
            [walk(v) for v in n.values()]
        elif isinstance(n, list):
            [walk(v) for v in n]
    walk(req)
    return [i for i in found if i in text]


def test_the_aim_step_is_a_json_step_with_reason_first_then_link_and_new_obstacle():
    step = advance.aim_step(request(), "Win a stall.")
    assert step.name == "advance_aim" and step.kind == "json" and not step.language
    assert list(step.grammar["properties"]) == ["reason", "link", "new_obstacle"] and step.grammar["required"] == ["reason", "link", "new_obstacle"]
    assert step.grammar["properties"]["link"]["enum"] == ["continues", "drifts"] and step.grammar["properties"]["new_obstacle"]["enum"] == ["yes", "no"]
    assert step.grammar["additionalProperties"] is False


def test_the_edge_step_has_the_five_moves_and_same_is_the_one_that_is_sent_back():
    step = advance.edge_step(request(), "a", "b")
    assert step.name == "advance_edge" and list(step.grammar["properties"]) == ["old_object", "new_object", "reason", "move"] and step.grammar["required"] == list(step.grammar["properties"])
    assert step.grammar["properties"]["move"]["enum"] == ["reverses", "complicates", "resolves", "redirects", "same"] == list(advance.EDGE_MOVES)


def test_the_aim_prompt_shows_the_chain_with_the_latest_marked_the_last_ending_and_the_new_aim():
    req = request(earlier_events=[{"chapter": 1, "happened": "h", "changed": "Ending one."}, {"chapter": 2, "happened": "h", "changed": "Ending two."}])
    text = advance.aim_step(req, "Win a stall.").text(1.0)
    for needed in ("Suvi", "Marit toward Suvi", "mother", "Chapter 1: aim: Bake sun loaves. It ended: Ending one.", "Chapter 2 (the latest): aim: Get wood.",
                   "Where the aim stands now, at the end of chapter 2: Ending two.", "chapter 3: Win a stall.", "continues", "drifts", "new_obstacle"):
        assert needed in text, needed
    assert text.index("Chapter 1") < text.index("Chapter 2") < text.index("Win a stall.") and not ids_in(text, req)
    assert "same_kind" not in text and "new_kind" not in text and "different kind" not in text


def test_the_edge_prompt_shows_the_trail_oldest_first_and_both_edges():
    req = request(spotlight_edges=["first want", "second want"])
    text = advance.edge_step(req, "second want", "a third").text(1.0)
    assert text.index("first want") < text.index("second want") and "before this chapter: second want" in text and "after this chapter: a third" in text
    for word in ("reverses", "complicates", "resolves", "redirects", "same"):
        assert word in text
    assert "escalates" not in text and "rewords" not in text
    assert not ids_in(text, req) and "{" not in text


def test_a_request_without_a_trail_or_earlier_aims_still_builds():
    req = request(earlier_beats=[])
    req.pop("spotlight_edges", None)
    assert "running aim, chapter by chapter" not in advance.aim_step(req, "x").text(1.0)
    assert "oldest first" not in advance.edge_step(req, "a", "b").text(1.0)


def test_a_squeeze_keeps_the_newest_entries():
    req = request(spotlight_edges=["e1", "e2", "e3", "e4"])
    text = advance.edge_step(req, "e4", "n").text(0.5)
    assert "e4" in text and "e1" not in text


def test_the_reason_check_wants_a_reason():
    step = advance.aim_step(request(), "x")
    ok = {"link": "continues", "new_obstacle": "yes"}
    assert step.check({"reason": "", **ok}) and step.check({"reason": "It goes on.", **ok}) is None
    assert step.check({"reason": "x " * 300, **ok})


def test_the_verdicts_are_bad_only_for_the_one_word_each():
    assert not advance.edge_ok({"reason": "r", "move": "same"})
    for word in ("reverses", "complicates", "resolves", "redirects"):
        assert advance.edge_ok({"reason": "r", "move": word})
    for odd in (None, {}, "same", {"move": "nonsense"}, {"move": "escalates"}, {"move": "rewords"}, 3):         # unreadable or no longer a word: a failed judge costs nothing
        assert advance.edge_ok(odd)
    assert not hasattr(advance, "aim_ok")          # the aim judge only observes: nothing acts on its verdict


def test_problem_lines_start_from_the_reason_and_tell_the_model_what_to_do():
    assert advance.problem_line("edge", {"reason": "Same want.", "move": "same"}).startswith("Same want.") and "move" in advance.problem_line("edge", None)
    assert "stronger" in advance.problem_line("edge", None) and "not the old want made stronger" in advance.problem_line("edge", None)           # it names the bad case and never offers it
    for kind in ("aim", "plan"):
        with pytest.raises(ValueError):
            advance.problem_line(kind, None)


def test_notes_hold_short_words_only():
    assert advance.notes({"reason": "long text", "link": "drifts", "new_obstacle": "yes"}, {"reason": "x", "move": "redirects"}) == {"aim_link": "drifts", "aim_new": "yes", "edge_move": "redirects"}
    assert advance.notes({"link": "continues"}) == {"aim_link": "continues"} and advance.notes({"link": "sideways", "new_obstacle": "maybe"}) == {}
    assert advance.notes(None, {"move": "bogus"}) == {} and advance.notes() == {}


def test_the_flag_is_on_and_the_version_is_set():
    assert advance.ENFORCE is True and advance.VERSION == "advance-6"


def test_a_resend_line_exists_for_the_edge_only_and_says_the_first_reply_was_set_aside():
    edge = {"reason": "Same want.", "move": "same"}
    assert advance.resend_line("edge", edge).startswith("Your first list of changes was set aside. Same want.")
    assert "aim" not in common.load_text("advance")["resend"] and "aim" not in common.load_text("advance")["problems"]
    for kind in ("aim", "plan"):
        with pytest.raises((ValueError, KeyError)):
            advance.resend_line(kind, None)


def test_the_labelled_cases_use_only_known_words_and_build_prompts():
    for pair in CASES["edge_pairs"]:
        assert pair["expected"] in advance.EDGE_MOVES
        assert advance.edge_step(request(), pair["old_edge"], pair["new_edge"]).text(1.0)
    assert sum(p["expected"] == "same" for p in CASES["edge_pairs"]) >= 3 and sum(p["expected"] != "same" for p in CASES["edge_pairs"]) >= 4
    assert sum(p["expected"] == "redirects" for p in CASES["edge_pairs"]) >= 1
    chains = CASES["aim_chains"]
    assert sum(c["expected_link"] == "drifts" for c in chains) >= 3 and sum(c["expected_link"] == "continues" for c in chains) >= 3
    assert {c["expected_new_obstacle"] for c in chains} == {"yes", "no"} and all(c["earlier"] for c in chains)
    for c in chains:
        assert c["expected_link"] in advance.AIM_LINKS and c["expected_new_obstacle"] in advance.YES_NO
        beats = [{"chapter": i + 1, "aim": e["aim"]} for i, e in enumerate(c["earlier"])]
        events = [{"chapter": i + 1, "happened": "h", "changed": e["changed"]} for i, e in enumerate(c["earlier"])]
        text = advance.aim_step(request(chapter=len(beats) + 1, earlier_beats=beats, earlier_events=events), c["new_aim"]).text(1.0)
        assert c["new_aim"] in text and c["earlier"][-1]["aim"] in text and "Where the aim stands now" in text and c["earlier"][-1]["changed"] in text


# ---- the pressure judge (world-pressure-2, observe-only) ----------------------------------------------------------------------------

def pressure_request(case: dict) -> dict:
    """A request that holds a labelled case's pressure, protagonist and tie, in the shape the judge reads."""
    req = request()
    req["cast"] = [{"id": "c1", "name": case["protagonist"]}, {"id": "c2", "name": case["tie"]["tie_to"]}]
    req["protagonist"] = "c1"
    req["ties"] = [{"id": "t1", "tie_from": "c1", "tie_to": "c2", "bond": case["tie"]["bond"], "edge": "to win"}]
    req["spotlight"] = "t1"
    req["pressure"] = case["pressure"]
    return req


def test_the_pressure_cases_are_labelled_for_both_kinds_and_both_texts():
    cases = CASES["pressure_cases"]
    assert len(cases) >= 8 and {c["expected"] for c in cases} == {"acts", "decor"}
    for expected in ("acts", "decor"):
        mine = [c for c in cases if c["expected"] == expected]
        assert len(mine) >= 4 and {c["source"] for c in mine} == {"plan", "happened"} and {c["pressure"]["kind"] for c in mine} == {"rule", "object"}
    assert len({c["protagonist"] for c in cases}) == len(cases) and all(c["note"] and c["text"] and c["aim"] for c in cases)


def test_the_pressure_prompt_shows_the_element_the_aim_and_the_text_in_words_and_asks_for_one_word():
    for case in CASES["pressure_cases"]:
        req = pressure_request(case)
        prompt = advance.pressure_prompt(req, case["text"], case["source"], case["aim"])
        element = case["pressure"].get("statement") or case["pressure"].get("description")
        assert element in prompt and case["aim"] in prompt and case["text"] in prompt and case["tie"]["tie_to"] in prompt
        assert ("What happened in the chapter:" if case["source"] == "happened" else "The plan for the chapter:") in prompt
        assert "effect: acts, decor or unclear" in prompt and not ids_in(prompt, req)
        step = advance.pressure_step(req, case["text"], case["source"], case["aim"])
        assert step.name == "advance_pressure" and step.grammar["properties"]["effect"]["enum"] == ["acts", "decor", "unclear"]


def test_the_pressure_verdict_word_is_unclear_when_it_cannot_be_read_and_the_notes_carry_it():
    assert advance.pressure_effect({"effect": "acts"}) == "acts" and advance.pressure_effect({"effect": "decor"}) == "decor"
    for odd in (None, {}, {"effect": "loud"}, "acts", {"effect": 3}):
        assert advance.pressure_effect(odd) == "unclear"
    assert advance.notes(pressure_value={"effect": "decor"}) == {"pressure_effect": "decor"} and advance.notes() == {}
    assert advance.notes(aim_value={"link": "drifts"}, pressure_value={}) == {"aim_link": "drifts", "pressure_effect": "unclear"}
