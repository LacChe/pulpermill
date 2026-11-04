"""The one chapter contract across the three prompting steps (plan, write, events and shifts): every chapter, first and middle and last, is told to settle the
collision of the protagonist's aim and the spotlight tie for good and to leave both in a new state that grows out of the outcome. Only the last chapter's
state is final. Each step's own wording is pinned in its own test file; this file checks that the steps agree and that no chapter is told less than another."""
import re

import pytest

from test_coverage_support import PLAN, generate_request, plan_request, prompts
from pulpermill.prompter.mill.common import load_text

COUNT = 20
MIDDLE = (2, 14, 19)          # 14 and 19 sat in the old "late" tier (from ceil(20 * 2 / 3)); 2 sat before it
LAST = COUNT

SHARED_CRAFT_SENTENCE = ("By the end of the chapter the collision between the protagonist's aim and the tie in the spotlight must be settled on the page: "
                         "show how it ends, through what people do and say, and let it cost something that stays spent.")


def plan_prompts(chapter: int) -> dict[str, str]:
    def mutate(q):
        q.update(chapter=chapter, chapter_count=COUNT, setup={**PLAN["setup"], "chapter_count": COUNT})
    return prompts("plan", plan_request(mutate))


def write_prompts(chapter: int) -> dict[str, str]:
    return prompts("generate", generate_request(lambda q: q.update(chapter=chapter, chapter_count=COUNT)))


def ended(text: str) -> bool:
    return re.search(r"how the collision\b[^.]*\bended", text) is not None


def test_late_chapter_is_gone_from_the_planner_wording():
    assert "late_chapter" not in load_text("plan")


@pytest.mark.parametrize("chapter", [*MIDDLE, LAST])
def test_every_chapter_is_told_to_settle_its_collision_in_the_brainstorm_and_the_plan(chapter):
    p = plan_prompts(chapter)
    assert "cannot be undone" in p["plan"] or chapter == LAST          # the last chapter has its own closing words, checked below
    assert "collision" in p["brainstorm"] and "decided for good" in p["brainstorm"] and "decided for good" in p["plan"]
    assert "how the clash is decided for good" in p["brainstorm"]
    assert "Act 3" in p["plan"] and "Act 4" in p["plan"] and "collision of the chapter is decided for good" in p["plan"]


@pytest.mark.parametrize("chapter", MIDDLE)
def test_middle_chapters_are_told_as_firmly_as_the_last_chapter_is(chapter):
    w = load_text("plan")
    p = plan_prompts(chapter)
    for step in ("brainstorm", "plan"):
        assert w["middle_chapter"] in p[step], step
        assert "cannot be undone" in p[step] and "Leave nothing of that collision hanging" in p[step], step
    last = plan_prompts(LAST)
    assert "settle the collision" in last["plan"] and "settles the collision" in last["brainstorm"]            # the same verb, in the same two prompts


def test_chapters_2_14_and_19_get_the_same_chapter_note_in_every_planner_prompt():
    w = load_text("plan")
    for chapter in MIDDLE:
        p = plan_prompts(chapter)
        assert w["middle_chapter"] in p["plan"] and w["middle_chapter"] in p["brainstorm"]
        assert "tighten the pressure" not in p["plan"] and "tighten the pressure" not in p["brainstorm"]


@pytest.mark.parametrize("chapter", [*MIDDLE, LAST])
def test_every_chapter_is_asked_to_show_its_collision_settled_on_the_page(chapter):
    p = write_prompts(chapter)
    assert SHARED_CRAFT_SENTENCE in p["write"]                                      # word for word the same in the middle and the last chapter
    assert "cannot be taken back" in p["write"]
    assert ended(p["events"]) and ended(p["shifts"]), (p["events"][-600:], p["shifts"][-600:])


@pytest.mark.parametrize("chapter", MIDDLE)
def test_a_middle_chapter_seeds_the_next_and_is_not_final(chapter):
    p = plan_prompts(chapter)
    w = write_prompts(chapter)
    assert "distinctly new state" in p["plan"] and "what the protagonist wants now" in p["plan"]
    assert "makes the next chapter matter" in w["write"]
    for text in (*p.values(), *w.values()):
        assert "open nothing new" not in text and "final state" not in text and "nothing new opened" not in text


def test_only_the_last_chapter_is_final_and_opens_nothing_new():
    p, w = plan_prompts(LAST), write_prompts(LAST)
    assert "open nothing new" in p["plan"] and "final state" in p["plan"] and "distinctly new state" not in p["plan"]       # movement_last, beside last_chapter
    assert "final state" in p["brainstorm"] and "nothing new opened" in p["brainstorm"]
    assert "final state" in w["write"] and "nothing new opened" in w["write"] and "makes the next chapter matter" not in w["write"]
    assert "settles what it set in motion" in w["write"]


def test_the_last_chapter_plan_prompt_does_not_ask_for_a_new_want_beside_a_final_state():
    plan = plan_prompts(LAST)["plan"]
    assert "what the protagonist wants now" not in plan and "turned into a new one" not in plan
