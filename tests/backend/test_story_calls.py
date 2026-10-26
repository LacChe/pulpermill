"""generate, plan, offstage and end_story on the fake engine with scripted replies: the order of the passes, the stages, the
section loop, the retry and language rules, too_long before any writing, and the contract on every reply."""
import json
import sys
from pathlib import Path

import pytest

from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.engine.base import CancelFlag
from pulpermill.backend.errors import BackendError, Cancelled
from pulpermill.backend.pipelines import RunContext, story
from pulpermill.prompts import prompts as P, tokens
from pulpermill.schema import contract

VECTORS = {r["name"]: r["data"] for r in json.loads((Path(__file__).parents[2] / "web/tests/contract-vectors.json").read_text())["requests"]
           if r["valid"]}
SENTENCE = ("She walked down to the river and the water was cold against her feet, and she did not look back at the house "
            "that had been her home for all of those years, because there was nothing left in it for her to keep. ")


def section(words: int) -> str:
    out = []
    while len(" ".join(out).split()) < words:
        out.append(SENTENCE.strip())
    return " ".join(out)


def sample(schema):
    """The smallest value that satisfies a schema built from the keywords the prompts use."""
    if "anyOf" in schema:
        return sample(schema["anyOf"][0])
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        return {k: sample(schema["properties"][k]) for k in schema.get("required", [])}
    if kind == "array":
        return [sample(schema.get("items", {})) for _ in range(schema.get("minItems", 0))]
    return {"string": "A short line about it.", "integer": 1, "boolean": False, "null": None}.get(kind)


def vector(name):
    return contract.parse_request(VECTORS[f"the page's {name} request"])


def make(*outputs, **config):
    engine = FakeEngine()
    engine.script(*outputs)
    stages = []
    ctx = RunContext(engine, CancelFlag(), stages.append, Config(**config))
    return ctx, engine, stages


def chapter_outputs(request, sections=4, words=750):
    """Scripted replies for a whole generate call: the sections, then Events and Shifts shaped by the real schemas."""
    req = request.model_dump()
    chapter = "\n\n".join([section(words)] * sections)
    events = sample(P.events_prompt(req, chapter).schema)
    shifts = sample(P.shifts_prompt(req, chapter, events).schema)
    return [section(words)] * sections + [json.dumps(events), json.dumps(shifts)]


def test_generate_writes_four_sections_then_events_then_shifts():
    request = vector("generate")
    ctx, engine, stages = make(*chapter_outputs(request))
    reply = story.generate(request, ctx)
    contract.parse_reply("generate", reply)
    assert engine.calls == 6 and reply["chapter_text"].count("\n\n") == 3
    assert engine.constraints[:4] == [None] * 4 and engine.constraints[4] is not None and engine.constraints[5] is not None
    assert [s for i, s in enumerate(stages) if i == 0 or s != stages[i - 1]] == ["write", "events", "shifts"]
    assert ctx.notes["words_per_section"] == [len(section(750).split())] * 4
    assert ctx.notes["squeeze"] == 1.0 and [p["prompt"] for p in ctx.notes["passes"]] == ["writer"] * 4 + ["events", "shifts"]
    assert isinstance(ctx.notes["flags"], list)


def test_a_section_sees_only_the_tail_of_the_chapter_so_far():
    request = vector("generate")
    ctx, engine, _ = make(*chapter_outputs(request))
    story.generate(request, ctx)
    assert section(750)[:60] not in engine.prompts[0]
    assert "river" in engine.prompts[1]


def test_a_short_chapter_gets_one_extra_section_before_the_close():
    request = vector("generate")
    req = request.model_dump()
    outputs = chapter_outputs(request, sections=5, words=300)
    ctx, engine, _ = make(*outputs)
    story.generate(request, ctx)
    assert engine.calls == 7 and ctx.notes["words_per_section"] == [len(section(300).split())] * 5
    assert len(P.writer_plan(extra=True)) == 5


def test_findings_in_the_chapter_never_fail_the_call():
    request = vector("generate")
    outputs = chapter_outputs(request)
    ctx, _, _ = make(*outputs)
    assert story.generate(request, ctx)["ok"] is True and ctx.notes["flags"]       # the chapter is repetitive: flagged, delivered


def test_a_section_in_the_wrong_language_is_written_again():
    request = vector("generate")
    french = "Elle descendit jusqu'à la rivière et l'eau était froide contre ses pieds, et elle ne regarda pas la maison qui avait été la sienne pendant toutes ces années, parce qu'il n'y avait plus rien dans cette maison pour elle. " * 3
    outputs = chapter_outputs(request)
    ctx, engine, _ = make(french, *outputs)
    story.generate(request, ctx)
    assert engine.calls == 7 and "could not be used" in engine.prompts[1]


def test_generate_that_cannot_fit_is_too_long_before_any_writing():
    sys.path.insert(0, str(Path(__file__).parents[1] / "prompts"))
    import prompt_cases as cases                       # the prompts work's own way of making a very large story
    from test_render import generate_request
    if not tokens.available():
        pytest.skip("the Gemma tokenizer files are not installed")
    big = cases.inflate(generate_request(), **cases.TIERS["large"][0])      # eight full people: documented as not fitting
    ctx, engine, _ = make()
    with pytest.raises(BackendError) as e:
        story.generate(contract.parse_request(big), ctx)
    assert e.value.kind == "too_long" and engine.calls == 0


def test_stop_during_the_chapter_ends_the_call_and_no_extractor_runs():
    request = vector("generate")
    ctx, engine, _ = make(*chapter_outputs(request))
    engine.fail_next(Cancelled())
    with pytest.raises(Cancelled):
        story.generate(request, ctx)
    assert engine.calls == 1


def test_a_broken_extractor_is_bad_output_and_gives_no_chapter():
    request = vector("generate")
    outputs = chapter_outputs(request)
    outputs[4:] = ["nope", "still nope"]
    ctx, _, _ = make(*outputs)
    with pytest.raises(BackendError) as e:
        story.generate(request, ctx)
    assert e.value.kind == "bad_output"


# ---- plan -----------------------------------------------------------------------------------------------------------

def test_plan_thinks_freely_then_fills_the_beat_constrained():
    request = vector("plan")
    req = request.model_dump()
    thinking = "I would put the confrontation by the river, because that is where it started. " * 5
    beat = sample(P.planner_beat_prompt(req, thinking).schema)
    ctx, engine, stages = make(thinking, json.dumps(beat))
    reply = story.plan(request, ctx)
    contract.parse_reply("plan", reply)
    assert reply["thinking"] == thinking.strip() and reply["beat"] == beat
    assert engine.constraints[0] is None and engine.constraints[1] is not None
    assert stages == ["think", "beat"] and thinking.strip() in engine.prompts[1]


def test_a_plan_after_a_refused_beat_says_retry():
    request = contract.parse_request(VECTORS["a plan retry carries the first attempt and the rules' words"])
    req = request.model_dump()
    beat = sample(P.planner_beat_prompt(req, "x").schema)
    ctx, _, stages = make("Thinking again about it.", json.dumps(beat))
    story.plan(request, ctx)
    assert stages[0] == "retry" and stages[-1] == "beat"


def test_an_empty_thought_is_asked_for_again():
    request = vector("plan")
    beat = sample(P.planner_beat_prompt(request.model_dump(), "x").schema)
    ctx, engine, _ = make("  ", "Now I have a thought about it.", json.dumps(beat))
    assert story.plan(request, ctx)["ok"] and engine.calls == 3


# ---- offstage -------------------------------------------------------------------------------------------------------

def test_offstage_needs_both_parts():
    request = vector("offstage")
    ctx, engine, stages = make(json.dumps({"did": "The guild closed the gate.", "reach": ""}),
                               json.dumps({"did": " The guild closed the gate. ", "reach": "A porter tells her by morning."}))
    reply = story.offstage(request, ctx)
    contract.parse_reply("offstage", reply)
    assert reply == {"ok": True, "did": "The guild closed the gate.", "reach": "A porter tells her by morning."}
    assert engine.calls == 2 and stages[0] == "offstage"


# ---- end_story ------------------------------------------------------------------------------------------------------

def test_end_story_updates_every_character_then_the_world_and_keeps_their_ids():
    request = contract.parse_request(VECTORS["an end-of-story request"])
    req = request.model_dump()
    prompts = P.end_story_prompts(req)
    outputs = [json.dumps(sample(p.schema)) for p in prompts]
    ctx, engine, stages = make(*outputs)
    reply = story.end_story(request, ctx)
    contract.parse_reply("end_story", reply)
    assert engine.calls == len(prompts) and [c["id"] for c in reply["characters"]] == [c["id"] for c in req["characters"]]
    assert set(stages) == {"update"}


def test_chinese_is_written_with_its_own_sampling_and_other_languages_with_the_prose_set():
    zh = "她走到河边，水很冷，她没有回头看那座房子。" * 40
    request = vector("generate").model_dump()
    ctx, engine, _ = make(*[zh] * 6)
    story._write(ctx, request, "zh", 3000)
    assert engine.params and all(p is ctx.config.prose_zh for p in engine.params)
    assert (ctx.config.prose_zh.temperature, ctx.config.prose_zh.top_p, ctx.config.prose_zh.top_k, ctx.config.prose_zh.repeat_penalty) == (0.8, 0.9, 40, 1.0)
    ctx, engine, _ = make(*chapter_outputs(vector("generate"))[:4])
    story._write(ctx, request, "en", 3000)
    assert all(p is ctx.config.prose for p in engine.params)
    assert ctx.config.prose_for("fr") is ctx.config.prose and ctx.config.prose_for(None) is ctx.config.prose
