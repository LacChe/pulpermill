"""Every model step that writes text for the story names the language the story is in, whatever language the request's content is in."""
import json

import pytest

from tests.prompter.test_coverage_support import flow_for, generate_request, mill_package, plan_request

NAMES = {"en": "English", "zh": "Simplified Chinese"}


def language_steps(call: str, request: dict) -> dict[str, str]:
    """The prompt of every step of the call whose reply is checked for language, keyed by step name."""
    flow, kit = flow_for(call, request)
    replies = mill_package.script(call, request, kit)
    results, out = [], {}
    while (step := flow.next(results)) is not None:
        if step.language:
            out[step.name] = step.text(1.0)
        raw = replies[len(results)]
        results.append(json.loads(raw) if step.kind == "json" else raw)
    return out


@pytest.mark.parametrize("code", ["en", "zh"])
@pytest.mark.parametrize("call,build", [("plan", plan_request), ("generate", generate_request)])
def test_every_checked_step_names_the_story_language(code, call, build):
    request = build(lambda r: r.update(language=code))
    steps = language_steps(call, request)
    assert steps, f"{call} has no step checked for language"
    for name, prompt in steps.items():
        assert NAMES[code] in prompt, f"{call}/{name} does not name {NAMES[code]}"
