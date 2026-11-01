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
from pulpermill.prompter.mill import plan  # noqa: E402
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
    return json.loads(plan.script(request, Kit(request))[0])


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


def test_minor_characters_appear_by_role_and_never_carry_the_plot():
    assert "by role" in plan.build_prompt(base()) and "never carries the plot" in plan.build_prompt(base())


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
    assert [s.name for s in flow.worst_case()] == ["plan"] and flow.worst_case()[0].max_output == plan.MAX_OUTPUT


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


def test_the_step_is_one_json_step_with_the_planner_grammar_and_the_check_on_it():
    request = base()
    kit = Kit(request)
    flow = plan.build_flow(request, kit)
    step = flow.next([])
    assert step.name == "plan" and step.kind == "json" and step.grammar == kit.grammar.plan_beat() and step.sampling == "thinking" and step.language
    assert flow.next([good()]) is None and flow.reply([good()]) == {"beat": good()}
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
    assert engine.calls == 1 and "Act 1" in engine.prompts[0] and engine.params[0] is not None


def test_a_plan_that_fails_the_check_is_asked_for_again_with_the_line_and_then_used():
    request = base()
    engine = FakeEngine()
    engine.script(json.dumps(with_(aim="Feel better about her mother")), plan.script(request, Kit(request))[0])
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        assert post(base_url, request).status_code == 200
        assert wait_idle(base_url)
    assert engine.calls == 2 and "Your previous reply could not be used" in engine.prompts[1] and "state of mind" in engine.prompts[1]
    assert engine.constraints[0] is not None or engine.constraints[1] is not None


def test_the_version_follows_the_wording():
    assert "+plan:plan-1:" in load_prompter("mill").version
