"""B1, the generate call: the writer prompt, the events and shifts steps, the squeeze order, the edge check, and the whole call through the
real server and runner on a scripted fake engine (no model)."""
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
from pulpermill.prompter.mill import generate as gen  # noqa: E402
from pulpermill.prompts import budget, tokens  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402
from story_sizes import chapter_text, inflate  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
GENERATES = [v for v in VECTORS if v["valid"] and v["data"]["call"] == "generate"]
CHAPTER = "Suvi shut the ledger and listened to Marit on the stairs, counting each step as it came."


def base() -> dict:
    return copy.deepcopy(next(v["data"] for v in GENERATES if v["name"] == "a generate request"))


def one_tie() -> dict:
    """The beat names only Suvi and Marit, so the spotlight tie is identified (the request itself does not carry it)."""
    request = base()
    request["beat"]["aim"] = "Suvi wants the ledger out before dawn."
    return request


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


def sections(prompt: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", prompt, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


# ---- the writer prompt ----------------------------------------------------------------------------------------------------

def test_the_writer_prompt_holds_the_plan_the_voice_the_cast_the_ending_and_the_story_so_far():
    prompt = gen.write_prompt(base())
    for needed in ("Suvi hides the ledger in the quay stores", "Dusk, the second day", "The people on stage are Suvi and Marit", "Narrate in the first person",
                   "Person and tense are rules", "The character's name is Marit", "She closed the door on the quay and did not look back.",
                   "Chapter 1 ended with the passage below", "Suvi learned the board has the ledger", "chapter 2 of 8", "in English",
                   "The Board [offstage]", "wants of their own", "subtext", "did not see coming", "no labels, no headings"):
        assert needed in prompt, needed
    assert prompt.index("## The plan for this chapter") < prompt.index("## The people on stage")      # the plan is the spine, read first
    assert prompt.rstrip().endswith("about 1,800 words.")                                              # the task is said again at the end


def test_minor_characters_appear_by_role_and_only_the_cast_act():
    prompt = gen.write_prompt(base())
    assert "appears by role" in prompt and "never makes the decisions that carry the story" in prompt and "Only the people on stage act" in prompt


def test_the_prompt_holds_no_ids_and_no_raw_option_keys():
    request = base()
    request["style"] = {"person": "first", "tense": "past", "humor": "dry", "dialogue": "sparse", "rhythm": "terse"}
    for text in (gen.write_prompt(request), gen.events_prompt(request, CHAPTER)):
        for ident in ids_in(request):
            assert ident not in text, ident
        assert "sparse" not in text and "female" not in text
        assert not re.search(r"\b(humor|dialogue|rhythm|person|tense|sex)\s*[:=]\s*\w+", text)
    assert "dialogue: sparse" not in gen.write_prompt(request)


def test_the_spotlight_tie_is_shown_when_the_plan_names_it():
    prompt = gen.write_prompt(one_tie())
    assert "## The tie in the spotlight" in prompt and "What drives Marit in this tie: to bring her daughter home" in prompt
    assert "The tie in the spotlight is Marit toward Suvi" in prompt
    ambiguous = gen.write_prompt(base())                          # both ties are named in this plan, so none is singled out
    assert "## The tie in the spotlight" not in ambiguous


@pytest.mark.parametrize("language,name", [("zh", "Simplified Chinese"), ("de", "German")])
def test_the_story_language_is_named_in_every_step(language, name):
    request = {**base(), "language": language}
    kit = Kit(request)
    assert f"in {name}" in gen.write_prompt(request) and f"in {name}" in gen.events_prompt(request, CHAPTER)
    assert gen.build_flow(request, kit).next([]).language is True


def test_the_first_and_the_last_chapter_are_written_differently():
    first = {**base(), "chapter": 1, "earlier_events": [], "previous_ending": None,
             "setup": {"protagonist": "c0000001", "normal": "Tides and ledgers.", "disruption": "The ledger is gone.", "chapter_count": 8}}
    last = {**base(), "chapter": 8}
    p_first, p_last, p_mid = (gen.write_prompt(x) for x in (first, last, base()))
    assert "Open the story where ordinary life was: Tides and ledgers." in p_first and "What just broke it: The ledger is gone." in p_first
    assert "## How the last chapter ended" not in p_first and "## The story so far" not in p_first
    assert "This is the last chapter" in p_last and "settles what it set in motion" in p_last
    assert "makes the next chapter matter" in p_mid and "makes the next chapter matter" not in p_last
    assert "Open the story" not in p_mid and "This is the last chapter" not in p_mid
    assert len({p_first, p_last, p_mid}) == 3


# ---- the squeeze ----------------------------------------------------------------------------------------------------------

def big() -> dict:
    request = inflate(one_tie(), cast=6, each=5, ties=6, chapters=9, chars=900)
    request["beat"] = one_tie()["beat"]
    request["ties"] = request["ties"][:2]            # the clones repeat the ends of these, which would make the spotlight ambiguous
    request["previous_ending"] = one_tie()["previous_ending"]
    return request


def test_the_squeeze_cuts_oldest_history_then_world_then_cast_and_never_the_plan_the_spotlight_or_the_style():
    request = big()
    prompts = {f: gen.write_prompt(request, f) for f in budget.SQUEEZES}
    sizes = [len(prompts[f]) for f in budget.SQUEEZES]
    assert sizes == sorted(sizes, reverse=True) and sizes[0] > sizes[-1]
    full, a, b, c = (sections(prompts[f]) for f in (1.0, 0.85, 0.7, 0.55))
    h, w, k = "The story so far", "The world", "The people on stage"
    assert a[h] != full[h] and a[w] == full[w] and a[k] == full[k]
    assert b[w] != a[w] and b[k] == a[k]
    assert c[k] != b[k]
    for f in budget.SQUEEZES:
        s = sections(prompts[f])
        for never in ("The plan for this chapter", "The voice of the story", "The tie in the spotlight", "How the last chapter ended", "How to write it"):
            assert s[never] == full[never], (f, never)
    assert f"Chapter {request['chapter'] - 1}" in sections(prompts[0.3])[h]       # the newest history is the last to go


@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
@pytest.mark.parametrize("size", ["small", "large"])
def test_every_step_at_its_heaviest_fits_the_context_at_some_squeeze(size):
    request = big() if size == "large" else base()
    flow = gen.build_flow(request, Kit(request))
    steps = flow.worst_case()
    assert [s.name for s in steps] == ["write", "events", "shifts"]
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert all(m.ok for m in measures) and len(measures) == 3
    assert steps[0].max_output == gen.WRITE_TOKENS and budget.input_limit(gen.WRITE_TOKENS) > 8000    # the chapter has room to be written


# ---- the events step ------------------------------------------------------------------------------------------------------

def test_the_events_prompt_holds_the_chapter_and_asks_for_happened_and_changed():
    prompt = gen.events_prompt(one_tie(), CHAPTER)
    assert CHAPTER in prompt and "happened" in prompt and "changed" in prompt and "one short sentence" in prompt
    assert "at the start its edge was: to bring her daughter home" in prompt


def test_the_events_check_wants_what_happened_and_one_short_changed_sentence():
    assert gen.events_problem({"happened": "Suvi hid the ledger and Marit found her.", "changed": "Suvi can no longer hide."}) is None
    assert "plain sentences" in gen.events_problem({"happened": "", "changed": "x"})
    assert "short sentence" in gen.events_problem({"happened": "Suvi hid the ledger and Marit found her.", "changed": ""})
    assert "one short sentence" in gen.events_problem({"happened": "Suvi hid the ledger and Marit found her.", "changed": "Suvi can hide no more. Marit knows everything now."})


# ---- the shifts step ------------------------------------------------------------------------------------------------------

def entry(handle: str, edge: str) -> dict:
    return {"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": handle, "values": {"edge": edge}}]}}


def test_the_shifts_prompt_shows_handles_and_names_the_edge_to_replace():
    request = one_tie()
    prompt = gen.shifts_prompt(request, Kit(request), CHAPTER)
    assert "ties.1: Marit toward Suvi: mother. Edge: to bring her daughter home" in prompt and "wants.1: To be left alone with the records" in prompt
    assert "The tie in the spotlight is Marit toward Suvi (ties.1); its edge was: to bring her daughter home" in prompt
    assert "at most seven entries" in prompt and "t1000001" not in prompt and "c0000001" not in prompt
    ambiguous = gen.shifts_prompt(base(), Kit(base()), CHAPTER)
    assert "is one of these: ties.1" in ambiguous and "ties.2" in ambiguous


def test_the_shifts_check_wants_the_spotlight_edge_replaced_with_something_new():
    request = one_tie()
    kit = Kit(request)
    ok = {"shifts": [entry("ties.1", "to forgive her daughter and let her stay")]}
    assert gen.shifts_problem(request, kit, ok) is None
    for missing in ({"shifts": []},
                    {"shifts": [{"card": "characters", "target": "Suvi", "patch": {"sketch": "Changed."}}]},
                    {"shifts": [entry("ties.2", "to hide the ledger for good")]},                  # another tie's edge is not the spotlight's
                    {"shifts": [entry("ties.1", "To bring her daughter home.")]},                    # the same edge, said again
                    {"shifts": [{"card": "entanglements", "patch": {"ties": [{"op": "remove", "id": "ties.1"}]}}]}):
        problem = gen.shifts_problem(request, kit, missing)
        assert problem and "ties.1" in problem and "Marit toward Suvi" in problem, missing


def test_the_shifts_check_accepts_any_named_tie_when_the_spotlight_is_not_singled_out():
    request = base()
    kit = Kit(request)
    assert gen.shifts_problem(request, kit, {"shifts": [entry("ties.2", "to burn the ledger")]}) is None
    assert gen.shifts_problem(request, kit, {"shifts": [entry("ties.1", "to keep her daughter near")]}) is None
    assert "edge of the tie the chapter was about" in gen.shifts_problem(request, kit, {"shifts": []})


def test_the_shifts_check_passes_the_kits_own_problem_through():
    request = one_tie()
    problem = gen.shifts_problem(request, Kit(request), {"shifts": [entry("ties.9", "to flee")]})
    assert problem and "ties.9" in problem


def test_the_shifts_step_carries_the_check_and_the_grammar():
    request = one_tie()
    kit = Kit(request)
    step = gen.build_flow(request, kit).next(["a chapter", {"happened": "x", "changed": "y"}])
    assert step.name == "shifts" and step.kind == "json" and step.check({"shifts": []}) and step.check({"shifts": [entry("ties.1", "to move on")]}) is None


# ---- the whole call -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("vector", GENERATES, ids=lambda v: v["name"])
def test_every_generate_vector_is_answered_through_the_real_server_on_the_mill_prompter(vector):
    request = vector["data"]
    engine = FakeEngine()
    engine.script(*gen.script(request, Kit(request)))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        response = post(base_url, request)
        body = response.json()
        assert response.status_code == 200 and body["ok"] is True, body
        reply = contract.parse_reply("generate", body)
        assert reply.chapter_text and reply.events.happened
        edges = [op for s in reply.shifts if s.card == "entanglements" for op in s.patch.get("ties", []) if op.op == "replace"]
        assert edges and edges[0].id in {"t1000001", "t1000002"}                                    # handles came back as the ids the page sent
        assert wait_idle(base_url)
    assert engine.calls == 3 and "## The plan for this chapter" in engine.prompts[0] and engine.params[0] is not None
    assert [c is None for c in engine.constraints] == [True, False, False]                          # prose is free; events and shifts are grammar-bound


def test_a_shifts_reply_that_misses_the_edge_is_asked_for_again_with_the_line_and_then_used():
    request = one_tie()
    kit = Kit(request)
    text, events, shifts = gen.script(request, kit)
    engine = FakeEngine()
    engine.script(text, events, json.dumps({"shifts": []}), shifts)
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        assert post(base_url, request).status_code == 200
        assert wait_idle(base_url)
    assert engine.calls == 4 and "replaces the edge of ties.1" in engine.prompts[3]


def test_the_chapter_is_the_writers_text_and_nothing_else():
    request = one_tie()
    flow = gen.build_flow(request, Kit(request))
    reply = flow.reply(["\n  The chapter.\n", {"happened": "H", "changed": "C"}, {"shifts": []}])
    assert reply == {"chapter_text": "The chapter.", "events": {"happened": "H", "changed": "C"}, "shifts": []}


def test_the_version_follows_the_wording():
    assert "+generate:generate-1:" in load_prompter("mill").version
