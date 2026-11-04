"""B1, the plan call: what the prompt holds, how it squeezes, what the check accepts and refuses, and the whole call through the real
server and runner on a scripted fake engine (no model)."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
for sub in ("backend", "prompts"):
    sys.path.insert(0, str(ROOT / "tests" / sub))

from pulpermill import contract  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter import load_prompter  # noqa: E402
from pulpermill.prompter.mill import advance, plan  # noqa: E402
from pulpermill.prompter.mill.common import load_text  # noqa: E402
from pulpermill.prompts import budget, tokens  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402
from story_sizes import inflate  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
PLANS = [v for v in VECTORS if v["valid"] and v["data"]["call"] == "plan"]


def base() -> dict:
    return copy.deepcopy(next(v["data"] for v in PLANS if v["name"] == "a plan request"))


def ids_in(node, out=None):
    out = set() if out is None else out
    if isinstance(node, dict):
        if isinstance(node.get("id"), str):
            out.add(node["id"])
        for v in node.values():
            ids_in(v, out)
    elif isinstance(node, list):
        for v in node:
            ids_in(v, out)
    return out


def good(request=None) -> dict:
    request = request or base()
    beat = json.loads(plan.script(request, Kit(request))[1])
    beat.pop(plan.IDEA_USE, None)          # the reply never carries it
    return beat


def plain(text: str) -> dict:
    """A scripted plan reply as the call's reply carries it: without `idea_use`, which stays in the trace."""
    beat = json.loads(text)
    beat.pop(plan.IDEA_USE, None)
    return beat


def brain(request=None) -> str:
    """The scripted brainstorm text, the first reply of a plan call."""
    request = request or base()
    return plan.script(request, Kit(request))[0]


def sections(prompt: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", prompt, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


# ---- the prompt -----------------------------------------------------------------------------------------------------------

def test_the_prompt_names_the_collision_the_four_points_and_the_spotlight():
    prompt = plan.build_prompt(base())
    for needed in ("collision", "Act 1", "Act 2", "Act 3", "Act 4", "Marit toward Suvi", "What drives Marit in this tie", "distinctly new state",
                   "chapter 2 of 8", "Chapter 1: Suvi wants to learn who took the ledger.", "Suvi now knows the board is hunting her", "in English"):
        assert needed in prompt, needed
    assert "Get the guild clerk to sign the permit before the auditor arrives" in prompt     # the outline text's own good example
    assert "Feel better about her father" in prompt and "is not yet an aim" in prompt         # and its avoid example, said positively


RULE = "The cast is fixed, so the plan names only people from the cards: a new name is a new character to keep track of."
BRAINSTORM_RULE = "The cast is fixed, so your options name only people from the cards: a new name is a new character to track."
OLD_WORDING = ("by role", "with no name", "Only the people on stage act", "such as a guard or a clerk", "stays in the background")


def test_the_rule_about_people_beyond_the_cast_is_stated_once_in_the_plan_prompt_with_or_without_a_brainstorm():
    for prompt in (plan.build_prompt(base()), plan.build_prompt(base(), brainstorm="1. An idea. 2. Another idea. 3. A third idea.")):
        assert prompt.count(RULE) == 1 and BRAINSTORM_RULE not in prompt
        assert "Anyone else appears by what they do or one telling detail" in prompt and "never carries the plot" in prompt
        assert "Places, events and things may have proper names; no other person does." in prompt          # only people are limited to the card names
        for gone in OLD_WORDING:
            assert gone not in prompt, gone


def test_the_brainstorm_prompt_states_the_same_rule_once_in_its_own_words():
    prompt = plan.build_brainstorm_prompt(base())
    assert prompt.count(BRAINSTORM_RULE) == 1 and RULE not in prompt
    assert "by what they do or one telling detail and never carries the plot" in prompt and "no other person does" in prompt
    for gone in OLD_WORDING:
        assert gone not in prompt, gone


def test_the_planner_rule_names_no_story_and_no_one_setting_and_is_prose():
    w = load_text("plan")
    for key in ("people_rule", "brainstorm_people"):
        text = w[key]
        assert "\n" not in text and not re.search(r"(^|\s)(-|\*|\d+\.)\s", text), key        # prose, no list
        assert "supporting" in text and "never carries the plot" in text, key
    assert w["people_rule"].count("(") == 1           # two short example phrases, in one parenthesis
    examples = w["people_rule"].split("(")[1].split(")")[0]
    assert "tech who logs the samples" in examples and "stallholder with cracked scales" in examples          # unrelated settings: a lab and a market


def test_people_outside_the_spotlight_tie_are_told_they_are_supporting():
    prompt = plan.build_prompt(base())
    assert "outside the spotlight tie are supporting" in prompt and "the chapter stays about the tie" in prompt


def test_the_prompt_holds_no_ids_and_no_raw_option_keys():
    request = base()
    request["style"] = {"person": "first", "tense": "past", "humor": "dry", "pacing": "brisk", "genre": "harbour noir", "lens": "an exact clerk's eye"}
    prompt = plan.build_prompt(request)
    for ident in ids_in(request):
        assert ident not in prompt, ident
    assert not re.search(r"\b(humor|pacing|dialogue|person|tense|sex)\s*[:=]\s*\w+", prompt)
    assert "female" not in prompt and "sparse" not in prompt and "t1000001" not in prompt


@pytest.mark.parametrize("language,name", [("zh", "Simplified Chinese"), ("fr", "French"), ("xx", "xx")])
def test_the_story_language_is_named(language, name):
    request = {**base(), "language": language}
    assert f"in {name}" in plan.build_prompt(request)


def test_the_first_and_the_last_chapter_are_told_differently():
    first = {**base(), "chapter": 1, "earlier_beats": [], "earlier_events": [],
             "setup": {**base()["setup"], "normal": "Tides and ledgers.", "disruption": "The ledger is gone."}}
    last = {**base(), "chapter": 8}
    middle = base()
    p_first, p_last, p_mid = (plan.build_prompt(x) for x in (first, last, middle))
    assert "This is the first chapter" in p_first and "Tides and ledgers." in p_first and "The ledger is gone." in p_first
    assert "This is the last chapter" in p_last and "closes it" in p_last and "first chapter" not in p_last
    assert "Build on what the earlier chapters changed" in p_mid and "first chapter" not in p_mid and "last chapter" not in p_mid
    assert len({p_first, p_last, p_mid}) == 3
    assert "tighten the pressure" in plan.build_prompt({**base(), "chapter": 7}) and "tighten the pressure" not in p_mid


def test_a_retry_carries_its_problems_and_the_refused_attempt_into_the_prompt():
    retry = next(v["data"] for v in PLANS if v["name"] == "a plan retry carries the first attempt and the rules' words")
    prompt = plan.build_prompt(retry)
    assert "The aim is too like chapter 1's aim." in prompt and "Nothing changes." in prompt and "fixes every one of these problems" in prompt
    assert "refused" not in plan.build_prompt(base())


# ---- the squeeze ----------------------------------------------------------------------------------------------------------

def with_idea_use(grammar: dict) -> dict:
    """The planner grammar as the plan step carries it when there is a brainstorm: `idea_use` first."""
    grammar = copy.deepcopy(grammar)
    grammar["properties"] = {"idea_use": {"type": "string"}, **grammar["properties"]}
    grammar["required"] = ["idea_use", *grammar["required"]]
    return grammar


def big() -> dict:
    request = inflate(base(), cast=6, each=5, ties=6, chapters=9, chars=900)
    request["earlier_beats"] = [{"chapter": n, "where": "The Quay", "when": "Morning", "aim": f"Chase number {n} across the harbour", "plan": "x"} for n in range(1, 10)]
    return request


def test_every_squeeze_factor_still_holds_the_essentials_and_only_shrinks_in_order():
    request = big()
    prompts = {f: plan.build_prompt(request, f) for f in budget.SQUEEZES}
    sizes = [len(prompts[f]) for f in budget.SQUEEZES]
    assert sizes == sorted(sizes, reverse=True) and sizes[0] > sizes[-1]
    for f, text in prompts.items():
        assert "collision" in text and "Act 4" in text and "Marit toward Suvi" in text and "What drives Marit in this tie" in text
    full, a, b, c = (sections(prompts[f]) for f in (1.0, 0.85, 0.7, 0.55))
    heads = sections(prompts[1.0]).keys()
    h, w, k = "The story so far", "The world", "The people"
    assert a[h] != full[h] and a[w] == full[w] and a[k] == full[k]          # first the oldest history goes
    assert b[w] != a[w] and b[k] == a[k]                                      # then world detail
    assert c[k] != b[k]                                                       # then cast texture
    for f in budget.SQUEEZES:                                                 # never the spotlight, the task or the tone of the story
        s = sections(prompts[f])
        assert s["The tie in the spotlight"].split("\n")[0] == full["The tie in the spotlight"].split("\n")[0]
        assert s["Your task"] == full["Your task"] and set(s) == set(heads)
    assert "Chase number 9" in prompts[0.3] or "Chapter 9" in prompts[0.3]    # the newest history is the last thing cut


@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
def test_the_planner_fits_the_context_at_some_squeeze_for_a_large_story():
    flow = plan.build_flow(big(), Kit(big()))
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert all(m.ok for m in measures) and factor <= 1.0
    assert [s.name for s in flow.worst_case()] == ["brainstorm", "plan", "advance_aim", "plan", "advance_aim"]
    assert flow.worst_case()[0].max_output == plan.BRAINSTORM_OUTPUT and flow.worst_case()[1].max_output == plan.MAX_OUTPUT


# ---- the check ------------------------------------------------------------------------------------------------------------

def test_the_check_accepts_a_good_plan():
    assert plan.plan_problem(base(), good()) is None


def with_(**changes) -> dict:
    return {**good(), **changes}


GOOD_PLAN = good()["plan"]
DEFECTS = {
    "no where": ({"where": ""}, "place"),
    "no aim": ({"aim": "  "}, "aim"),
    "abstract aim (a state of mind)": ({"aim": "Feel better about her mother"}, "state of mind"),
    "abstract aim (wants to)": ({"aim": "Suvi wants to come to terms with the past."}, "state of mind"),
    "too short an aim": ({"aim": "Win"}, "state of mind"),
    "no Act 3": ({"plan": re.sub(r"Act 3:.*?(?=Act 4)", "", GOOD_PLAN)}, "Act 3"),
    "no labels": ({"plan": "Suvi and Marit argue on the quay and then make peace for good, which changes both of them."}, "Act 1"),
    "an empty point": ({"plan": "Act 1: Suvi and Marit meet. Act 2: Act 3: A costly choice turns it. Act 4: A new state for both."}, "Act 2"),
    "points out of order": ({"plan": "Act 2: The conflict. Suvi and Marit clash. Act 1: Suvi and Marit meet at dawn. Act 3: A costly choice turns it. Act 4: A new state for both."}, "order"),
    "the tie's people not named": ({"plan": GOOD_PLAN.replace("Marit", "the mother")}, "Marit"),
    "the same aim as an earlier chapter": ({"aim": "Suvi wants to learn who took the ledger."}, "chapter 1"),
}


@pytest.mark.parametrize("name", list(DEFECTS))
def test_the_check_refuses_each_defect_with_one_plain_line(name):
    changes, said = DEFECTS[name]
    problem = plan.plan_problem(base(), with_(**changes))
    assert problem and "\n" not in problem and said in problem, problem


def test_the_check_refuses_the_aim_of_the_refused_attempt_on_a_retry():
    retry = next(v["data"] for v in PLANS if v["name"] == "a plan retry carries the first attempt and the rules' words")
    problem = plan.plan_problem(retry, with_(aim=retry["retry"]["beat"]["aim"]))
    assert problem and "refused attempt" in problem


@pytest.mark.parametrize("aim", ["Get the guild clerk to sign the permit before the auditor arrives", "Suvi needs to reach the cellar before the clerk does",
                                 "Suvi wants to learn who took the ledger from the cellar"])
def test_concrete_aims_pass(aim):
    request = {**base(), "earlier_beats": []}
    assert plan.plan_problem(request, with_(aim=aim)) is None


def test_the_plan_step_is_a_json_step_with_the_planner_grammar_and_the_check_on_it():
    request = base()
    kit = Kit(request)
    flow = plan.build_flow(request, kit)
    assert flow.next([]).name == "brainstorm"
    step = flow.next([brain()])
    assert step.name == "plan" and step.kind == "json" and step.grammar == with_idea_use(kit.grammar.plan_beat()) and step.sampling == "thinking" and step.language
    assert flow.reply([brain(), good()]) == {"beat": good()} and flow.next([brain(), good()]).name == "advance_aim"      # the earlier aims are there to be judged against
    assert step.check({**good(), "where": ""}) and step.check(good()) is None
    assert budget.input_limit(step.max_output) > 10000                     # the context keeps room for the prompt


# ---- the whole call -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("vector", PLANS, ids=lambda v: v["name"])
def test_every_plan_vector_is_answered_through_the_real_server_on_the_mill_prompter(vector):
    request = vector["data"]
    engine = FakeEngine()
    engine.script(*plan.script(request, Kit(request)))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        response = post(base_url, request)
        body = response.json()
        assert response.status_code == 200 and body["ok"] is True, body
        assert contract.parse_reply("plan", body).beat["where"]
        assert wait_idle(base_url)
    assert engine.calls == 2 + bool(advance.earlier_aims(request)) and "Act 1" in engine.prompts[1] and engine.params[0] is not None


def test_a_plan_that_fails_the_check_is_asked_for_again_with_the_line_and_then_used():
    request = base()
    engine = FakeEngine()
    texts = plan.script(request, Kit(request))
    engine.script(texts[0], json.dumps(with_(aim="Feel better about her mother")), *texts[1:])
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        assert post(base_url, request).status_code == 200
        assert wait_idle(base_url)
    assert engine.calls == 4 and "Your previous reply could not be used" in engine.prompts[2] and "state of mind" in engine.prompts[2]
    assert engine.constraints[1] is not None or engine.constraints[2] is not None


def test_the_version_follows_the_wording():
    assert f"+plan:{plan.VERSION}:" in load_prompter("mill").version


# ---- the aim judge after the plan (phase 3, observe-only) ---------------------------------------------------------------------------

def run_plan(request, *texts, **config):
    """The real plan flow on the fake engine, scripted with `texts`. Returns (reply, ctx, engine)."""
    from pulpermill.backend import runner
    from pulpermill.backend.engine.base import CancelFlag
    from pulpermill.backend.pipelines import RunContext
    kit = Kit(request)
    engine = FakeEngine()
    engine.script(*texts)
    ctx = RunContext(engine, CancelFlag(), [].append, Config(**config))
    ctx.notes["call"] = "plan"
    flow = plan.build_flow(request, kit)
    return flow.reply(runner.run_flow(ctx, flow, "en")), ctx, engine


def test_the_aim_judge_is_a_step_of_its_own_after_the_plan_with_two_attempts_and_a_neutral_fallback():
    request = base()
    flow = plan.build_flow(request, Kit(request))
    step = flow.next([brain(), good()])
    assert step.name == "advance_aim" and step.attempts == 2 and callable(step.fallback) and good()["aim"] in step.text(1.0)
    assert step.fallback() == {} and advance.aim_ok(step.fallback()) and flow.notes["aim_judge_fallback"] is True


def test_no_aim_judge_runs_in_the_first_chapter():
    request = base()
    request.update(chapter=1, earlier_beats=[], earlier_events=[])
    flow = plan.build_flow(request, Kit(request))
    assert flow.next([brain(request), good(request)]) is None and [s.name for s in flow.worst_case()] == ["brainstorm", "plan"]
    reply, ctx, engine = run_plan(request, *plan.script(request, Kit(request)))
    assert engine.calls == 2 and ctx.notes["flow"] == {"minor_names": 0, "minor_new": 0, "pressure_on": False} and [p["step"] for p in ctx.notes["passes"]] == ["brainstorm", "plan"]


SAME = json.dumps({"reason": "It is another errand to impress Orla.", "kind": "same_kind"})
NEW = json.dumps({"reason": "It is a different kind of aim.", "kind": "new_kind"})
SECOND = {**good(), "aim": "Carry the spare lantern across the harbour before the tide turns"}
SECOND_TEXT = json.dumps({plan.IDEA_USE: "Idea 3, the misunderstanding at the door.", **SECOND})        # the second plan as the engine says it: with `idea_use`, the brainstorm being there


def test_with_the_flag_off_the_verdict_only_goes_to_the_notes_and_the_reply_is_the_same_whatever_it_says(monkeypatch):
    monkeypatch.setattr(advance, "ENFORCE", False)
    request = base()
    texts = plan.script(request, Kit(request))
    bad_reply, bad_ctx, bad_engine = run_plan(request, texts[0], texts[1], SAME)
    good_reply, good_ctx, _ = run_plan(request, texts[0], texts[1], NEW)
    assert bad_reply == good_reply == {"beat": plain(texts[1])} and bad_engine.calls == 3
    assert bad_ctx.notes["flow"] == {"aim_kind": "same_kind", "minor_names": 0, "minor_new": 0, "pressure_on": False} and good_ctx.notes["flow"] == {"aim_kind": "new_kind", "minor_names": 0, "minor_new": 0, "pressure_on": False}
    assert [p["step"] for p in bad_ctx.notes["passes"]] == ["brainstorm", "plan", "advance_aim"]
    assert [s.name for s in plan.build_flow(request, Kit(request)).worst_case()] == ["brainstorm", "plan", "advance_aim"]


def test_a_same_kind_aim_sends_the_plan_back_once_with_the_judges_line_and_the_judge_runs_again():
    request = base()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_plan(request, texts[0], texts[1], SAME, SECOND_TEXT, NEW)
    assert reply == {"beat": SECOND} and engine.calls == 5
    assert [p["step"] for p in ctx.notes["passes"]] == ["brainstorm", "plan", "advance_aim", "plan", "advance_aim"]
    assert ctx.notes["flow"] == {"aim_kind": "same_kind", "aim_resent": True, "aim_kind_after": "new_kind", "minor_names": 0, "minor_new": 0, "pressure_on": False}
    assert "Your first plan was set aside." not in engine.prompts[1]
    assert "Your first plan was set aside. It is another errand to impress Orla." in engine.prompts[3] and "different kind" in engine.prompts[3]
    assert engine.prompts[3].rindex("different kind") < engine.prompts[3].index("Reply with a JSON object with four keys")           # the line sits in the task, ahead of the output rule


def test_a_second_same_kind_verdict_is_accepted_and_noted_and_nothing_runs_a_third_time():
    request = base()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_plan(request, texts[0], texts[1], SAME, SECOND_TEXT, SAME)
    assert reply == {"beat": SECOND} and engine.calls == 5
    assert ctx.notes["flow"] == {"aim_kind": "same_kind", "aim_resent": True, "aim_kind_after": "same_kind", "aim_accepted": True, "minor_names": 0, "minor_new": 0, "pressure_on": False}


def test_a_good_verdict_sends_nothing_back():
    request = base()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_plan(request, *texts)
    assert reply == {"beat": plain(texts[1])} and engine.calls == 3 and "aim_resent" not in ctx.notes["flow"]


def test_a_plan_that_cannot_be_redone_keeps_the_first_one_and_the_call_still_succeeds():
    request = base()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_plan(request, texts[0], texts[1], SAME, "no json", "still none")
    assert reply == {"beat": plain(texts[1])} and engine.calls == 5                         # no second judge: the plan that stands was judged
    assert ctx.notes["flow"] == {"aim_kind": "same_kind", "aim_resent": True, "aim_resend_fallback": True, "aim_accepted": True, "minor_names": 0, "minor_new": 0, "pressure_on": False}


def test_a_judge_that_fails_every_attempt_never_fails_the_call_and_leaves_the_reply_alone():
    request = base()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_plan(request, texts[0], texts[1], "no json", "still none")
    assert reply == {"beat": plain(texts[1])} and engine.calls == 4
    assert ctx.notes["flow"] == {"aim_judge_fallback": True, "minor_names": 0, "minor_new": 0, "pressure_on": False}                                   # no verdict: nothing is sent back
    judge_pass = [p for p in ctx.notes["passes"] if p["step"] == "advance_aim"][0]
    assert len(judge_pass["attempts"]) == 2 and judge_pass["fallback"] is True


def test_the_resent_plan_step_is_the_plan_step_with_the_line_and_the_first_plan_as_its_last_resort():
    request = base()
    flow = plan.build_flow(request, Kit(request))
    first = good()
    flow.next([brain()])
    step = flow.next([brain(), first, {"reason": "Same errand.", "kind": "same_kind"}])
    assert step.name == "plan" and step.attempts == 2 and step.fallback() == first
    assert "Your first plan was set aside. Same errand." in step.text(1.0) and "Same errand." not in plan.build_prompt(request)


# ---- the brainstorm before the plan (phase 5) ----------------------------------------------------------------------------------------

def test_the_brainstorm_is_a_free_text_step_first_with_thinking_sampling_and_no_brainstorm_as_its_last_resort():
    request = base()
    flow = plan.build_flow(request, Kit(request))
    step = flow.next([])
    assert step.name == "brainstorm" and step.kind == "text" and step.grammar is None and step.sampling == "thinking" and step.language is False
    assert step.max_output == plan.BRAINSTORM_OUTPUT == 400 and step.attempts == 2
    assert step.check("Too short.") and step.check(brain()) is None
    assert step.fallback() == "" and flow.notes["brainstorm_fallback"] is True


def test_the_brainstorm_prompt_asks_for_three_chapters_of_different_kinds_with_the_four_things_for_each():
    prompt = plan.build_brainstorm_prompt(base())
    for needed in ("three chapters that differ in kind", "a refusal, a trade, a secret kept or told, or a misunderstanding",
                   "what the protagonist is after", "what Marit wants from this chapter", "the line or moment where the two of them clash", "what it costs",
                   "Marit toward Suvi", "chapter 2 of 8", "in English"):
        assert needed in prompt, needed
    assert "Act 1" not in prompt and "JSON" not in prompt and "four points" not in prompt        # no plan shape is asked for here
    assert "supporting" in prompt and "by what they do or one telling detail" in prompt


def test_the_brainstorm_prompt_shows_the_earlier_aims_as_the_kinds_already_used_and_the_plan_prompt_does_not():
    request = base()
    brainstorm, planned = plan.build_brainstorm_prompt(request), plan.build_prompt(request)
    assert "The kinds of aim the story has already used" in brainstorm and "Chapter 1: Suvi wants to learn who took the ledger." in brainstorm
    assert "differs in kind from all of them" in brainstorm
    assert "The kinds of aim the story has already used" not in planned and "What the protagonist was after in the earlier chapters" in planned
    first = {**request, "chapter": 1, "earlier_beats": [], "earlier_events": []}
    assert "already used" not in plan.build_brainstorm_prompt(first) and "This is the first chapter" in plan.build_brainstorm_prompt(first)


def test_the_brainstorm_prompt_is_told_the_chapters_place_and_carries_a_retry():
    last = plan.build_brainstorm_prompt({**base(), "chapter": 8})
    assert "This is the last chapter" in last and "chapter 8 of 8" in last
    assert "tighten the pressure" in plan.build_brainstorm_prompt({**base(), "chapter": 7})
    retry = next(v["data"] for v in PLANS if v["name"] == "a plan retry carries the first attempt and the rules' words")
    prompt = plan.build_brainstorm_prompt(retry)
    assert "An earlier plan for this chapter was refused" in prompt and "The aim is too like chapter 1's aim." in prompt
    assert "refused" not in plan.build_brainstorm_prompt(base())


def test_the_brainstorm_prompt_holds_no_ids_and_names_the_story_language():
    request = {**base(), "language": "zh"}
    prompt = plan.build_brainstorm_prompt(request)
    for ident in ids_in(request):
        assert ident not in prompt, ident
    assert "in Simplified Chinese" in prompt


def test_the_other_person_is_the_end_of_the_tie_that_is_not_the_protagonist():
    request = base()
    names = plan.names_of(request)
    assert plan.protagonist_name(request, names) == "Suvi" and plan.other_end(request, names) == "Marit"
    flipped = {**request, "protagonist": next(t for t in request["ties"] if t["id"] == request["spotlight"])["tie_from"]}
    assert plan.other_end(flipped, names) == "Suvi"
    assert "what Suvi wants from this chapter" in plan.build_brainstorm_prompt(flipped)


def test_the_plan_prompt_carries_the_brainstorm_under_its_heading_and_is_told_to_choose():
    request = base()
    text = brain()
    prompt = plan.build_prompt(request, 1.0, "", text)
    s = sections(prompt)
    assert s["Three ideas for this chapter"] == text and "Choose one of them, or combine two" in s["Your task"]
    assert list(s).index("Three ideas for this chapter") == list(s).index("Your task") - 1          # right before the task
    assert "Three ideas" not in plan.build_prompt(request) and "Choose one of them" not in plan.build_prompt(request)
    assert "Three ideas" not in plan.build_prompt(request, 1.0, "", "   ")                         # a blank brainstorm is no brainstorm


def test_act_two_must_say_what_the_other_person_wants_and_does_with_or_without_a_brainstorm():
    for prompt in (plan.build_prompt(base()), plan.build_prompt(base(), 1.0, "", brain())):
        assert "Act 2 says what Marit wants from this chapter and what Marit does about it" in prompt


def test_the_plan_json_shape_did_not_change():
    request = base()
    assert plan.build_flow(request, Kit(request)).next([brain()]).grammar == with_idea_use(Kit(request).grammar.plan_beat())
    assert set(good()) == {"where", "when_time", "aim", "plan"}


def test_the_brainstorm_text_reaches_the_plan_prompt_through_the_runner_and_the_resent_plan_too():
    request = base()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_plan(request, texts[0], texts[1], SAME, SECOND_TEXT, NEW)
    assert "Three ideas for this chapter" not in engine.prompts[0] and "Option 1: a refusal." in engine.prompts[1]
    assert texts[0] in engine.prompts[1] and texts[0] in engine.prompts[3]                         # the same text, on the first pass and on the resent one
    assert "Three ideas" not in engine.prompts[2] and ctx.notes["flow"].get("brainstorm_fallback") is None


def test_the_flow_runs_brainstorm_then_plan_then_judge_and_the_reply_is_the_plan():
    request = base()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_plan(request, *texts)
    assert [p["step"] for p in ctx.notes["passes"]] == ["brainstorm", "plan", "advance_aim"] and reply == {"beat": plain(texts[1])}
    assert engine.params[0] == engine.params[1] != engine.params[2]                               # the brainstorm and the plan think; the judge is structured
    assert engine.constraints[0] is None                                                          # free text: no grammar on the brainstorm


def test_a_cut_off_brainstorm_is_trimmed_to_its_last_full_sentence():
    flow = plan.build_flow(base(), Kit(base()))
    full = "Option 1: a refusal. Marit says no. Option 2: a trade. Marit wants a price. Option 3: a lie. Marit tells one. It costs trust."
    flow.next([full + " Suvi then"])
    assert flow.brainstorm == full
    flow = plan.build_flow(base(), Kit(base()))
    flow.next(["One long opening with no stop in it at all that runs on and on"])
    assert flow.brainstorm.startswith("One long opening")                                          # nothing to cut back to: kept as it is


def test_a_brainstorm_that_fails_every_attempt_never_fails_the_call_and_the_plan_runs_without_it():
    request = base()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_plan(request, "no", "still no", json.dumps(plain(texts[1])), texts[2])        # no brainstorm: the plan grammar has no `idea_use`
    assert reply == {"beat": plain(texts[1])} and engine.calls == 4
    assert ctx.notes["flow"] == {"brainstorm_fallback": True, "aim_kind": "new_kind", "minor_names": 0, "minor_new": 0, "pressure_on": False}
    assert "Three ideas for this chapter" not in engine.prompts[2] and "Choose one of them" not in engine.prompts[2]
    brainstorm_pass = [p for p in ctx.notes["passes"] if p["step"] == "brainstorm"][0]
    assert len(brainstorm_pass["attempts"]) == 2 and brainstorm_pass["fallback"] is True
    assert "Propose three different chapters" in engine.prompts[1]                                  # the retry line said what to fix


def test_one_refused_brainstorm_is_asked_for_again_and_then_used():
    request = base()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_plan(request, "short", *texts)
    assert engine.calls == 4 and texts[0] in engine.prompts[2] and "brainstorm_fallback" not in ctx.notes.get("flow", {})


def test_the_worst_case_counts_the_brainstorm_and_the_plan_carries_one_of_the_longest_size():
    request = base()
    steps = plan.build_flow(request, Kit(request)).worst_case()
    assert [s.name for s in steps] == ["brainstorm", "plan", "advance_aim", "plan", "advance_aim"]
    stand_in = plan.BRAINSTORM_STAND_IN.strip()
    assert stand_in in steps[1].text(1.0) and stand_in in steps[3].text(1.0)
    assert len(steps[1].text(1.0)) > len(plan.build_prompt(request)) + len(stand_in)


@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
def test_the_whole_plan_flow_fits_the_context_at_a_full_cast_of_five_without_any_squeeze():
    request = inflate(base(), cast=5, each=5, ties=6, chapters=9, chars=900)
    request["earlier_beats"] = [{"chapter": n, "where": "The Quay", "when": "Morning", "aim": f"Chase number {n} across the harbour", "plan": "x"} for n in range(1, 10)]
    assert len(request["cast"]) == 5
    flow = plan.build_flow(request, Kit(request))
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert factor == 1.0 and all(m.ok for m in measures) and len(measures) == 5
    brainstorm = flow.worst_case()[0]
    assert tokens.count(brainstorm.text(1.0)) < tokens.count(flow.worst_case()[1].text(1.0))      # the brainstorm prompt is the lighter of the two


def test_the_prompter_version_changes_with_the_plan_wording():
    version = load_prompter("mill").version
    assert f"+plan:{plan.VERSION}:" in version and plan.VERSION == "plan-9"


# ---- what the planner did with the brainstorm (for the trace only) ----------------------------------------------------------------

def test_the_plan_prompt_asks_for_idea_use_only_when_it_carries_a_brainstorm():
    request = base()
    assert "idea_use" in plan.build_prompt(request, brainstorm=brain(request)) and "idea_use" not in plan.build_prompt(request)
    flow = plan.build_flow(request, Kit(request))
    plain = Kit(request).grammar.plan_beat()
    assert flow.next([brain(request)]).grammar["required"][0] == "idea_use" and list(flow.next([brain(request)]).grammar["properties"])[0] == "idea_use"
    flow.brainstorm = ""                                                     # a brainstorm that fell back: the plan is asked for as before
    assert flow._step().grammar == plain


def test_idea_use_is_left_out_of_the_reply_but_does_not_make_the_check_refuse_a_plan():
    request = base()
    flow = plan.build_flow(request, Kit(request))
    used = {"idea_use": "Idea 2, for the trade at the door.", **good(request)}
    step = flow.next([brain(request)])
    assert step.check(used) is None and step.check(good(request)) is None     # the key is optional to the check
    assert flow.reply([brain(request), used]) == {"beat": good(request)}
    assert flow.reply([brain(request), good(request)]) == {"beat": good(request)}


def test_idea_use_reaches_the_trace_and_not_the_reply(tmp_path):
    request = base()
    used = {"idea_use": "Idea 1: the refusal, for the clash at the door.", **good(request)}
    trace = tmp_path / "trace.jsonl"
    reply, ctx, engine = run_plan(request, brain(request), json.dumps(used), json.dumps({"reason": "A new kind of errand.", "kind": "new_kind"}), trace_path=str(trace))
    assert "idea_use" not in reply["beat"]
    lines = [json.loads(x) for x in trace.read_text(encoding="utf-8").splitlines()]
    assert any(l["step"] == "plan" and "Idea 1: the refusal" in l["reply"] for l in lines)
    assert any(l["step"] == "brainstorm" and l["reply"] for l in lines)


# ---- the pressure (world-pressure-2): the line, the judge, the notes ----------------------------------------------------------------

SENTENCE = "act on the aim or the tie"
ACTS = json.dumps({"reason": "The rule costs her something.", "effect": "acts"})
DECOR = json.dumps({"reason": "The rule is only mentioned.", "effect": "decor"})


def with_pressure(request=None, kind="rule") -> dict:
    """A plan request that carries a pressure in words (the page's W1 shape), taken from the world the request already holds (W2)."""
    request = request or base()
    world = request["world"]
    if kind == "rule":
        rule = world["rules"][0]
        request["pressure"] = {"kind": "rule", "statement": rule["statement"], "cost": rule["cost"], "when_broken": rule["when_broken"]}
    else:
        thing = world["objects"][0]
        request["pressure"] = {"kind": "object", "name": thing["name"], "description": thing["description"], "significance": thing["significance"]}
    return request


def element_of(request: dict) -> str:
    """A phrase that only the pressure's element carries in the prompt (the rule's statement, the object's description)."""
    pressure = request["pressure"]
    return pressure["statement"] if pressure["kind"] == "rule" else pressure["description"]


@pytest.mark.parametrize("kind", ["rule", "object"])
@pytest.mark.parametrize("build", [plan.build_prompt, plan.build_brainstorm_prompt])
def test_a_pressure_adds_one_sentence_and_the_element_once_inside_the_spotlight_section_and_no_new_section(build, kind):
    plain, pressed = base(), with_pressure(kind=kind)
    a, b = build(plain), build(pressed)
    secs_a, secs_b = sections(a), sections(b)
    assert list(secs_a) == list(secs_b)                                          # no new section
    assert a.count(SENTENCE) == 0 and b.count(SENTENCE) == 1
    phrase = element_of(pressed)
    assert a.count(phrase) == 1 and b.count(phrase) == 1                         # the element moves out of its world list and into the line
    assert SENTENCE in secs_b["The tie in the spotlight"] and phrase in secs_b["The tie in the spotlight"]
    assert phrase not in secs_b["The world"] and phrase in secs_a["The world"]
    assert not ids_in(pressed["pressure"]) and not (ids_in(pressed) & set(re.findall(r"\b[a-z]\d{7}\b", b)))      # words, never ids


@pytest.mark.parametrize("build", [plan.build_prompt, plan.build_brainstorm_prompt])
def test_with_no_pressure_the_prompts_are_what_they_were_and_a_squeeze_drops_the_sentence_first(build):
    plain = base()
    assert build(dict(plain, pressure=None)) == build(plain) and SENTENCE not in build(plain)
    for kind in ("rule", "object"):
        pressed = with_pressure(base(), kind)
        assert build(pressed, 0.99) == build(plain, 0.99)                         # the sentence goes at the first squeeze, and the element is back in its list
        assert build(pressed, 0.7) == build(plain, 0.7)


def test_the_pressure_adds_about_sixty_words_at_most_to_a_planner_prompt():
    request = with_pressure()
    request["pressure"].update(statement="Nobody may cross the river after dark, whatever the business, whoever the patron, and every crossing is logged. " * 3,
                               cost="Anyone who does is struck from the registry of the guild and loses every protection it ever gave them. " * 3)
    plain = base()
    for build in (plan.build_prompt, plan.build_brainstorm_prompt):
        assert len(build(request).split()) - len(build(plain).split()) <= 70        # the longest element, at its cap, and the one sentence


def run_pressed(request, *texts):
    return run_plan(request, *texts)


def test_the_pressure_judge_runs_once_after_the_plan_and_the_aim_judge_and_reads_the_plan_text():
    request = with_pressure()
    texts = plan.script(request, Kit(request))
    assert len(texts) == 4 and json.loads(texts[3])["effect"] == "acts"
    reply, ctx, engine = run_pressed(request, *texts)
    assert reply == {"beat": plain(texts[1])} and engine.calls == 4
    assert [p["step"] for p in ctx.notes["passes"]] == ["brainstorm", "plan", "advance_aim", "advance_pressure"]
    assert ctx.notes["flow"] == {"pressure_on": True, "aim_kind": "new_kind", "pressure_effect": "acts", "minor_names": 0, "minor_new": 0}
    judged = engine.prompts[3]
    assert plain(texts[1])["plan"] in judged and element_of(request) in judged and "Act 1" in judged
    assert "effect: acts, decor or unclear" in judged and not (set(re.findall(r"\b[a-z]\d{7}\b", judged)))


def test_a_decor_verdict_changes_nothing_sends_nothing_back_and_adds_no_problem_line():
    request = with_pressure()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_pressed(request, texts[0], texts[1], texts[2], DECOR)
    assert reply == {"beat": plain(texts[1])} and engine.calls == 4
    assert ctx.notes["flow"]["pressure_effect"] == "decor" and "aim_resent" not in ctx.notes["flow"]
    assert [p["step"] for p in ctx.notes["passes"]].count("plan") == 1               # no second plan: the verdict is only recorded
    assert not any("pressure" in p for p in ctx.notes["passes"][1:3])


def test_the_pressure_judge_runs_in_the_first_chapter_too():
    request = with_pressure()
    request.update(chapter=1, earlier_beats=[], earlier_events=[])
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_pressed(request, *texts)
    assert len(texts) == 3 and engine.calls == 3 and [p["step"] for p in ctx.notes["passes"]] == ["brainstorm", "plan", "advance_pressure"]
    assert reply == {"beat": plain(texts[1])} and ctx.notes["flow"]["pressure_effect"] == "acts"


def test_the_pressure_judge_reads_the_plan_that_stands_after_the_plan_was_sent_back():
    request = with_pressure()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_pressed(request, texts[0], texts[1], SAME, SECOND_TEXT, NEW, DECOR)
    assert reply == {"beat": SECOND} and engine.calls == 6                           # the reply is the second plan, not the verdict that follows it
    assert [p["step"] for p in ctx.notes["passes"]] == ["brainstorm", "plan", "advance_aim", "plan", "advance_aim", "advance_pressure"]
    assert SECOND["aim"] in engine.prompts[5] and good()["aim"] not in engine.prompts[5]
    assert ctx.notes["flow"]["pressure_effect"] == "decor" and ctx.notes["flow"]["aim_resent"] is True


def test_a_pressure_judge_that_fails_every_attempt_is_unclear_and_never_fails_the_call():
    request = with_pressure()
    texts = plan.script(request, Kit(request))
    reply, ctx, engine = run_pressed(request, texts[0], texts[1], texts[2], "no", "still no")
    assert reply == {"beat": plain(texts[1])} and engine.calls == 5
    assert ctx.notes["flow"]["pressure_effect"] == "unclear" and ctx.notes["flow"]["pressure_judge_fallback"] is True
    step = plan.build_flow(request, Kit(request)).next([brain(request), good(request), json.loads(texts[2])])
    assert step.name == "advance_pressure" and step.attempts == 2 and step.fallback() == {"effect": "unclear"}


def test_no_pressure_means_no_pressure_judge_and_pressure_off_in_the_notes():
    request = base()
    flow = plan.build_flow(request, Kit(request))
    assert flow.notes["pressure_on"] is False and [s.name for s in flow.worst_case()] == ["brainstorm", "plan", "advance_aim", "plan", "advance_aim"]
    assert plan.build_flow(with_pressure(), Kit(request)).worst_case()[-1].name == "advance_pressure"
    texts = plan.script(request, Kit(request))
    assert len(texts) == 3


@pytest.mark.parametrize("vector", PLANS, ids=lambda v: v["name"])
def test_every_plan_vector_with_a_pressure_is_answered_through_the_real_server(vector):
    request = with_pressure(copy.deepcopy(vector["data"]))
    engine = FakeEngine()
    engine.script(*plan.script(request, Kit(request)))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        response = post(base_url, request)
        body = response.json()
        assert response.status_code == 200 and body["ok"] is True, body
        assert contract.parse_reply("plan", body).beat["where"]
        assert wait_idle(base_url)
    assert engine.calls == 3 + bool(advance.earlier_aims(request)) and SENTENCE in engine.prompts[1]
