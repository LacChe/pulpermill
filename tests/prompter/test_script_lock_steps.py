"""In a Chinese story every step that writes free text into the story is limited by its grammar to the story's script: the events record, the
shifts of a chapter and of the end, and the planner's beat. A story in another language gets the grammars as they were."""
import copy
import json
import re
from pathlib import Path

import pytest

from pulpermill.backend import grammar
from pulpermill.backend.kit import Kit
from tests.prompter.test_coverage_support import flow_for, generate_request, mill_package, plan_request

ROOT = Path(__file__).resolve().parents[2]
FINISH = next(v["data"] for v in json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
              if v["valid"] and v["data"]["call"] == "finish" and v["name"] == "a finish request carries the summaries and the base characters")

ENGLISH = "The collision of her aim and the tie ended with her losing what she was after."
CHINESE = "沈青岚失去了主动权，她必须在三天内找到新的线索。"


def strings(node, path=""):
    """(path, schema) of every string node in the schema that is not a fixed word."""
    if isinstance(node, dict):
        if node.get("type") == "string" and "enum" not in node and "const" not in node:
            yield path, node
        for k, v in node.items():
            yield from strings(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from strings(v, f"{path}/{i}")


def zh(request: dict) -> dict:
    return {**copy.deepcopy(request), "language": "zh"}


def finish_request(language: str) -> dict:
    return {**copy.deepcopy(FINISH), "language": language}


def assert_locked(schema: dict) -> None:
    free = list(strings(schema))
    assert free, "the grammar has no free text to check"
    for path, node in free:
        assert "pattern" in node, f"{path} is free text with no script limit"
        assert re.fullmatch(node["pattern"], CHINESE), path
        assert not re.fullmatch(node["pattern"], ENGLISH), path


def assert_untouched(schema: dict) -> None:
    assert "pattern" not in json.dumps(schema)


def test_the_events_of_a_chinese_chapter_are_chinese_in_both_fields():
    request = zh(generate_request())
    g = Kit(request).grammar.events("沈青岚在临江客栈醒来。")
    assert set(g["properties"]) == {"happened", "changed"} and g["required"] == ["happened", "changed"]
    assert_locked(g)
    assert len(list(strings(g))) == 2


def test_a_latin_name_in_the_chapter_may_be_spelled_in_the_events():
    request = zh(generate_request())
    plain = Kit(request).grammar.events("沈青岚在客栈醒来。")["properties"]["happened"]["pattern"]
    named = Kit(request).grammar.events("沈青岚在客栈遇见了 Pim。")["properties"]["happened"]["pattern"]
    assert not re.fullmatch(plain, "Pim 来了。") and re.fullmatch(named, "Pim 来了。")
    assert not re.fullmatch(named, "Pim arrived at the inn.")


def test_the_chapters_shifts_are_chinese():
    request = zh(generate_request())
    kit = Kit(request)
    g = kit.grammar.shifts()
    if g.get("maxItems") == 0:
        pytest.skip("this request sent no tie to shift")
    assert_locked(g)


def test_the_end_of_story_shifts_are_chinese():
    request = finish_request("zh")
    g = Kit(request).grammar.finish()
    assert_locked(g)


def steps_of(call: str, request: dict):
    """Every step of the call, run on the script's replies, by name."""
    flow, kit = flow_for(call, request)
    replies = mill_package.script(call, request, kit)
    results, out = [], {}
    while (step := flow.next(results)) is not None:
        out.setdefault(step.name, step)
        raw = replies[len(results)]
        results.append(json.loads(raw) if step.kind == "json" else raw)
    return out


def test_the_planners_beat_and_its_idea_note_are_chinese():
    request = zh(plan_request())
    assert_locked(Kit(request).grammar.plan_beat())
    plan = steps_of("plan", request)["plan"]
    assert plan.grammar is not None and "idea_use" in plan.grammar["properties"], "the plan step should carry the idea note"
    assert_locked(plan.grammar)


def test_the_events_and_shifts_steps_of_a_chinese_generate_are_locked_as_the_flow_builds_them():
    steps = steps_of("generate", zh(generate_request()))
    assert_locked(steps["events"].grammar)
    if list(strings(steps["shifts"].grammar)):
        assert_locked(steps["shifts"].grammar)


@pytest.mark.parametrize("language", ["en", "fr", None])
def test_other_languages_are_left_alone(language):
    gen = {**generate_request(), "language": language}
    kit = Kit(gen)
    assert_untouched(kit.grammar.events("Dusk came early."))
    assert_untouched(kit.grammar.shifts())
    assert_untouched(Kit({**plan_request(), "language": language}).grammar.plan_beat())
    assert_untouched(Kit(finish_request(language or "en")).grammar.finish())
    assert kit.grammar.in_script({"type": "string"}) == {"type": "string"}
