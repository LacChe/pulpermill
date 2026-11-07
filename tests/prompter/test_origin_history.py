"""origin history: the Setup's disruption reaches the select, brainstorm and plan prompts of chapters 2+ when the plan request asks for it,
as origin history (on by default) between "The story follows X." and "This is chapter N of M.". Off, chapter 1 and the write prompt are unchanged."""
import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]

from pulpermill import contract  # noqa: E402
from pulpermill.prompter.mill import generate, plan, select  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
DISRUPTION = "A fog rolled in and the town's oven went cold."
NORMAL = "Every dawn the baker lit the Hearthstone oven."


def plan_request(chapter: int = 3, **extra) -> dict:
    request = copy.deepcopy(next(v["data"] for v in VECTORS if v["valid"] and v["name"] == "a plan request"))
    request["chapter"] = chapter
    request["setup"] = {**request["setup"], "normal": NORMAL, "disruption": DISRUPTION}
    request.update(extra)
    return request


def prompts(request: dict) -> dict[str, str]:
    return {"select": select.build_select_prompt({**request, "choose": True}),
            "brainstorm": plan.build_brainstorm_prompt(request),
            "plan": plan.build_prompt(request, brainstorm="An idea.")}


def test_the_flag_is_on_the_plan_request_and_on_by_default():
    assert contract.PlanRequest.model_fields["origin_history"].default is True
    assert contract.PlanRequest.model_validate(plan_request()).origin_history is True
    assert contract.PlanRequest.model_validate(plan_request(origin_history=False)).origin_history is False


@pytest.mark.parametrize("chapter", [2, 4])
def test_a_request_without_the_field_gets_origin_history(chapter):
    request = plan_request(chapter)
    assert "origin_history" not in request
    for step, prompt in prompts(request).items():
        assert prompt == prompts({**request, "origin_history": True})[step] and f"Where the story began: {DISRUPTION}" in prompt, step
    assert plan.build_flow(request, None).notes["origin_history"] is True


@pytest.mark.parametrize("chapter", [2, 3, 6])
def test_on_the_block_sits_between_the_protagonist_line_and_the_chapter_line_in_all_three_prompts(chapter):
    for step, prompt in prompts(plan_request(chapter, origin_history=True)).items():
        began = prompt.index(f"Where the story began: {DISRUPTION}")
        assert prompt.index("The story follows") < began < prompt.index(f"This is chapter {chapter} of"), step
        assert "origin history" in prompt and NORMAL not in prompt, step
        assert prompt.count("Where the story began") == 1, step


@pytest.mark.parametrize("chapter", [2, 3, 6])
def test_off_the_prompts_of_chapters_2_and_later_ignore_the_disruption_entirely(chapter):
    bare = plan_request(chapter)
    bare["setup"] = {**bare["setup"], "disruption": ""}
    for step, prompt in prompts({**plan_request(chapter), "origin_history": False}).items():
        assert prompt == prompts({**bare, "origin_history": False})[step], step
        assert "Where the story began" not in prompt and DISRUPTION not in prompt, step


def test_chapter_one_is_the_same_with_the_flag_on():
    assert prompts(plan_request(1, origin_history=True)) == prompts(plan_request(1, origin_history=False))


def test_a_setup_with_no_disruption_adds_nothing_even_when_on():
    request = plan_request(3, origin_history=True)
    request["setup"]["disruption"] = ""
    assert prompts(request) == prompts({**request, "origin_history": False})


def test_the_write_prompt_is_not_touched_by_the_flag():
    request = copy.deepcopy(next(v["data"] for v in VECTORS if v["valid"] and v["name"] == "a generate request"))
    request["chapter"] = 3
    assert "origin_history" not in contract.GenerateRequest.model_fields
    assert generate.write_prompt({**request, "origin_history": True}) == generate.write_prompt(request)


def test_the_run_notes_log_the_flag_state():
    for flag in (True, False):
        flow = plan.build_flow(plan_request(3, origin_history=flag), None)      # building the flow only reads the request
        assert flow.notes["origin_history"] is flag
