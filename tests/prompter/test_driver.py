"""Plan 9, step 2: each brainstorm idea gets its own driver kind, by chapter rotation (driver.py), and the brainstorm prompt shows one line for
each idea. Structural only: code picks the kinds, the lines name them in words and copy no card text. Neutral placeholder text; no model."""
import copy

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

from test_gate_flow import run  # noqa: E402
from test_label_flow import chaptered  # noqa: E402
from test_select import base, choose_request  # noqa: E402

from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter.mill import driver, plan  # noqa: E402
from pulpermill.prompter.mill.common import load_text  # noqa: E402
from pulpermill.prompts import render as r  # noqa: E402

W = load_text("plan")


def with_card(request: dict, **card) -> dict:
    """The request with the protagonist's card replaced field by field."""
    request = copy.deepcopy(request)
    person = next(p for p in request["cast"] if p["id"] == request["protagonist"])
    person.update(card)
    return request


def full(request: dict | None = None, chapter: int = 2) -> dict:
    """A request whose protagonist has every kind: two wants, a fear, a flaw and a value."""
    return {**with_card(request or base(), wants=[{"id": "w1", "text": "To keep the zebra ledger"}, {"id": "w2", "text": "To win the quartz race"}],
                        fear="Being found out", flaw="She hoards what she knows", values=[{"id": "v1", "text": "A promise is a promise"}]), "chapter": chapter}


def bare(request: dict | None = None) -> dict:
    return with_card(request or base(), wants=[], fear="", flaw="", values=[])


def lines_of(prompt: str) -> list[str]:
    return [line for line in prompt.split("\n") if line.startswith("Idea ") and ": the aim is drawn from " in line]


# ---- the kinds ------------------------------------------------------------------------------------------------------------------

def test_a_kind_is_available_when_the_protagonists_card_has_it_and_the_edge_always():
    assert driver.KINDS == ("edge", "want", "fear", "flaw", "value")
    assert driver.available(base()) == ["edge", "want", "fear", "flaw"]              # the sample card has a want, a fear and a flaw, and no values
    assert driver.available(full()) == list(driver.KINDS)
    assert driver.available(bare()) == ["edge"]
    assert driver.available({**base(), "protagonist": "nobody"}) == ["edge"]         # a protagonist outside the cast has no card to draw from
    blank = with_card(base(), wants=[{"id": "w1", "text": "  "}], fear="", flaw="", values=[{"id": "v1", "text": ""}])
    assert driver.available(blank) == ["edge"]                                        # an empty item is no want and no value


def test_rotation_gives_every_kind_a_turn_and_never_gives_two_ideas_the_same_kind_when_three_or_more_exist():
    seen = set()
    for chapter in range(1, 7):
        kinds = driver.assign(full(chapter=chapter))
        assert len(kinds) == 3 and len(set(kinds)) == 3
        seen.update(kinds)
    assert seen == set(driver.KINDS)
    assert driver.assign(full(chapter=1)) == ["edge", "want", "fear"] and driver.assign(full(chapter=2)) == ["want", "fear", "flaw"]
    assert driver.assign(full(chapter=5)) == ["value", "edge", "want"]                # wraps at the end of the fixed order
    assert driver.assign(full(chapter=6)) == driver.assign(full(chapter=1))           # and begins again
    for chapter in range(1, 9):
        assert len(set(driver.assign({**base(), "chapter": chapter}))) == 3            # four kinds: still three different ones


def test_with_fewer_than_three_kinds_they_repeat_in_order_and_with_one_kind_nothing_is_shown():
    two = with_card(base(), wants=[], fear="Being found out", flaw="", values=[])
    assert driver.available(two) == ["edge", "fear"]
    assert driver.assign({**two, "chapter": 1}) == ["edge", "fear", "edge"] and driver.assign({**two, "chapter": 2}) == ["fear", "edge", "fear"]
    assert driver.assign(bare()) == ["edge", "edge", "edge"] and not driver.active(bare()) and driver.text(bare(), W) == ""
    assert driver.active(two) and driver.label({**two, "chapter": 1}) == "edge-fear-edge"


# ---- the prompt -----------------------------------------------------------------------------------------------------------------

def test_the_brainstorm_prompt_has_a_lead_one_line_for_each_idea_and_the_meeting_sentence_after_the_combinations_line():
    for request, combos in ((full(), None), (full(choose_request()), plan_combos())):
        prompt = plan.build_brainstorm_prompt(request, 1.0, combos)
        kinds = driver.assign(request)
        assert prompt.count(W["driver_lead"]) == 1 and prompt.count(W["driver_meets"]) == 1
        assert lines_of(prompt) == [f"Idea {n}: the aim is drawn from {W['driver_kinds'][kind]}." for n, kind in enumerate(kinds, 1)]
        assert prompt.index(W["brainstorm_outcomes"]) < prompt.index(W["driver_lead"]) < prompt.index("Each idea says, in plain sentences")
        if combos:
            assert prompt.index(W["brainstorm_combos"]) < prompt.index(W["driver_lead"])        # after the combinations line, in choose mode
        assert "meets the protagonist on the way, whatever the aim is drawn from" in prompt


def plan_combos() -> list[dict]:
    return [{"tie_id": f"t{i}", "tie_words": f"Tie words {i}", "pressure_id": None, "pressure": None, "pressure_words": "", "reason": f"Reason {i}"} for i in (1, 2, 3)]


def test_chapter_one_shows_the_lines_too_and_a_squeeze_drops_them_with_the_used_table():
    first = {**full(), "chapter": 1, "earlier_beats": [], "earlier_events": []}
    assert lines_of(plan.build_brainstorm_prompt(first)) == ["Idea 1: the aim is drawn from " + W["driver_kinds"]["edge"] + ".",
                                                            "Idea 2: the aim is drawn from " + W["driver_kinds"]["want"] + ".",
                                                            "Idea 3: the aim is drawn from " + W["driver_kinds"]["fear"] + "."]
    for factor in (0.9, 0.5):
        squeezed = plan.build_brainstorm_prompt(full(), factor)
        assert W["driver_lead"] not in squeezed and W["driver_meets"] not in squeezed and not lines_of(squeezed)
    assert lines_of(plan.build_brainstorm_prompt(full(), 1.0))


def test_a_protagonist_with_no_card_gets_no_lines_no_note_and_no_driver_wording():
    request = bare()
    prompt = plan.build_brainstorm_prompt(request)
    assert not lines_of(prompt) and W["driver_lead"] not in prompt and W["driver_meets"] not in prompt
    assert all(phrase not in prompt for phrase in W["driver_kinds"].values())
    assert "driver_kinds" not in plan.build_flow(request, Kit(request)).notes
    assert prompt.count(W["brainstorm_outcomes"]) == 1 and prompt.index(W["brainstorm_outcomes"]) < prompt.index("Each idea says, in plain sentences")


def test_the_driver_lines_are_not_in_the_plan_prompt():
    request = full()
    prompt = plan.build_prompt(request, 1.0, "Option 1: x\n\nOption 2: y\n\nOption 3: z")
    assert W["driver_lead"] not in prompt and not lines_of(prompt)


def test_different_chapters_show_different_lines_in_the_brainstorm_prompts_of_a_fake_engine_run():
    lines = {}
    for chapter in (3, 4):
        request = chaptered(base(), last=chapter)
        flow, reply, ctx, engine, texts = run(request, (0, 0, 0))
        brainstorms = [p for p in engine.prompts if W["driver_lead"] in p]
        assert len(brainstorms) == 1
        lines[chapter] = lines_of(brainstorms[0])
        assert ctx.notes["flow"]["driver_kinds"] == driver.label(request)
        assert not any(W["driver_lead"] in p for p in engine.prompts if p is not brainstorms[0])      # nothing after the brainstorm carries them
    assert len(lines[3]) == len(lines[4]) == 3 and lines[3] != lines[4]


def test_the_picked_want_is_the_one_the_prompt_shows_and_the_line_names_the_kind_without_copying_card_text():
    request = full(chapter=2)                                          # chapter 2 rotates to want, fear, flaw: the want line is there
    prompt = plan.build_brainstorm_prompt(request)
    person = next(p for p in request["cast"] if p["id"] == request["protagonist"])
    shown = r.render_person(person, scope="planner", pick=str(request["chapter"]))
    picked = "zebra" if "zebra" in shown else "quartz"
    other = "quartz" if picked == "zebra" else "zebra"
    assert picked in prompt and other not in prompt                    # one want is shown, the one the card renderer picked for this chapter
    assert W["driver_kinds"]["want"] in prompt and not any(word in "\n".join(lines_of(prompt)) for word in ("zebra", "quartz", "ledger", "promise", "hoards"))


def test_when_the_gate_drops_an_idea_the_survivors_keep_their_own_driver_lines_and_nothing_is_renumbered():
    request = chaptered(full(), last=5)
    flow, reply, ctx, engine, texts = run(request, (5, 0, 0))             # the first idea repeats five labels and is dropped
    brainstorm = next(p for p in engine.prompts if W["driver_lead"] in p)
    kinds = driver.assign(request)
    assert lines_of(brainstorm) == [f"Idea {n}: the aim is drawn from {W['driver_kinds'][k]}." for n, k in enumerate(kinds, 1)]
    assert ctx.notes["flow"]["repeat_dropped"] == 1 and flow._alive == [1, 2]
    assert ctx.notes["flow"]["driver_kinds"] == "-".join(kinds)            # still the three kinds of the places 1, 2, 3
    assert [kinds[i] for i in flow._alive] == kinds[1:]                    # the survivors, places 2 and 3, keep the kinds they had
    assert sum(W["driver_lead"] in p for p in engine.prompts) == 1


def test_choose_mode_builds_idea_n_on_combination_n_and_drives_it_by_driver_n_both_by_number():
    request = full(chaptered(choose_request(), last=3), chapter=3)
    prompt = plan.build_brainstorm_prompt(request, 1.0, plan_combos())
    assert "idea 1 is built on combination 1, idea 2 on combination 2 and idea 3 on combination 3" in prompt
    assert [line.split(":")[0] for line in lines_of(prompt)] == ["Idea 1", "Idea 2", "Idea 3"]
    assert prompt.count("idea 1 ends with") == 1                          # the outcome by number is unchanged
