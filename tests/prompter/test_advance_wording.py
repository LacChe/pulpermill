"""The advancement judge (2B): the steps build against a request, the grammar accepts only the enums, the verdict helpers are neutral on
what they cannot read, and the labelled cases build into prompts. Nothing here runs a model."""
import copy
import json
from pathlib import Path

import pytest

from pulpermill.prompter.mill import advance

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


def test_the_aim_step_is_a_json_step_with_reason_first_and_the_two_kinds():
    step = advance.aim_step(request(), "Win a stall.")
    assert step.name == "advance_aim" and step.kind == "json" and not step.language
    assert list(step.grammar["properties"]) == ["reason", "kind"] and step.grammar["properties"]["kind"]["enum"] == ["new_kind", "same_kind"]
    assert step.grammar["additionalProperties"] is False


def test_the_edge_step_has_the_five_moves():
    step = advance.edge_step(request(), "a", "b")
    assert step.name == "advance_edge" and list(step.grammar["properties"]) == ["reason", "move"]
    assert step.grammar["properties"]["move"]["enum"] == ["escalates", "reverses", "complicates", "resolves", "rewords"]


def test_the_aim_prompt_shows_names_bond_earlier_aims_by_chapter_and_the_new_aim():
    req = request()
    text = advance.aim_step(req, "Win a stall.").text(1.0)
    for needed in ("Suvi", "Marit toward Suvi", "mother", "Chapter 1: Bake sun loaves.", "Chapter 2: Get wood.", "chapter 3: Win a stall.", "same_kind", "new_kind"):
        assert needed in text, needed
    assert text.index("Chapter 1") < text.index("Chapter 2") and not ids_in(text, req)


def test_the_edge_prompt_shows_the_trail_oldest_first_and_both_edges():
    req = request(spotlight_edges=["first want", "second want"])
    text = advance.edge_step(req, "second want", "a third").text(1.0)
    assert text.index("first want") < text.index("second want") and "before this chapter: second want" in text and "after this chapter: a third" in text
    for word in ("escalates", "reverses", "complicates", "resolves", "rewords"):
        assert word in text
    assert not ids_in(text, req) and "{" not in text


def test_a_request_without_a_trail_or_earlier_aims_still_builds():
    req = request(earlier_beats=[])
    req.pop("spotlight_edges", None)
    assert "earlier chapters" not in advance.aim_step(req, "x").text(1.0)
    assert "oldest first" not in advance.edge_step(req, "a", "b").text(1.0)


def test_a_squeeze_keeps_the_newest_entries():
    req = request(spotlight_edges=["e1", "e2", "e3", "e4"])
    text = advance.edge_step(req, "e4", "n").text(0.5)
    assert "e4" in text and "e1" not in text


def test_the_reason_check_wants_a_reason():
    step = advance.aim_step(request(), "x")
    assert step.check({"reason": "", "kind": "new_kind"}) and step.check({"reason": "It differs.", "kind": "new_kind"}) is None
    assert step.check({"reason": "x " * 300, "kind": "new_kind"})


def test_the_verdicts_are_bad_only_for_the_one_word_each():
    assert advance.aim_ok({"reason": "r", "kind": "new_kind"}) and not advance.aim_ok({"reason": "r", "kind": "same_kind"})
    assert advance.edge_ok({"reason": "r", "move": "escalates"}) and not advance.edge_ok({"reason": "r", "move": "rewords"})
    for odd in (None, {}, "same_kind", {"kind": "nonsense"}, 3):
        assert advance.aim_ok(odd) and advance.edge_ok(odd)


def test_problem_lines_start_from_the_reason_and_tell_the_model_what_to_do():
    assert advance.problem_line("aim", {"reason": "It is still about Orla's approval", "kind": "same_kind"}).startswith("It is still about Orla's approval.")
    assert "different kind" in advance.problem_line("aim", None) and "move" in advance.problem_line("edge", {"reason": "Same want.", "move": "rewords"})
    with pytest.raises(ValueError):
        advance.problem_line("plan", None)


def test_notes_hold_short_words_only():
    assert advance.notes({"reason": "long text", "kind": "same_kind"}, {"reason": "x", "move": "escalates"}) == {"aim_kind": "same_kind", "edge_move": "escalates"}
    assert advance.notes(None, {"move": "bogus"}) == {} and advance.notes() == {}


def test_the_flag_is_off_and_the_version_is_set():
    assert advance.ENFORCE is False and advance.VERSION == "advance-1"


def test_the_labelled_cases_use_only_known_words_and_build_prompts():
    for pair in CASES["edge_pairs"]:
        assert pair["expected"] in advance.EDGE_MOVES
        assert advance.edge_step(request(), pair["old_edge"], pair["new_edge"]).text(1.0)
    assert sum(p["expected"] == "rewords" for p in CASES["edge_pairs"]) >= 3 and sum(p["expected"] != "rewords" for p in CASES["edge_pairs"]) >= 4
    chains = CASES["aim_chains"]
    assert sum(c["expected"] == "same_kind" for c in chains) >= 3 and sum(c["expected"] == "new_kind" for c in chains) >= 4
    for c in chains:
        assert c["expected"] in advance.AIM_KINDS
        beats = [{"chapter": i + 1, "aim": a} for i, a in enumerate(c["earlier_aims"])]
        assert c["new_aim"] in advance.aim_step(request(chapter=len(beats) + 1, earlier_beats=beats), c["new_aim"]).text(1.0)
