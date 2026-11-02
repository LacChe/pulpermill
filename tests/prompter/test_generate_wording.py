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
for sub in ("backend", "prompts", "e2e"):
    sys.path.insert(0, str(ROOT / "tests" / sub))

from pulpermill import contract  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter import load_prompter  # noqa: E402
from pulpermill.prompter.mill import generate as gen, plan as mill_plan  # noqa: E402
from pulpermill.prompts import budget, tokens  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402
from story_sizes import chapter_text, inflate  # noqa: E402
from stub_engine import StubEngine  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
GENERATES = [v for v in VECTORS if v["valid"] and v["data"]["call"] == "generate"]
CHAPTER = "Suvi shut the ledger and listened to Marit on the stairs, counting each step as it came."


def base() -> dict:
    return copy.deepcopy(next(v["data"] for v in GENERATES if v["name"] == "a generate request"))


def one_tie() -> dict:
    """The beat names the spotlight tie by id (`beat.spotlight`), and its plan names only Suvi and Marit, so name-matching would find it too."""
    request = base()
    request["beat"]["aim"] = "Suvi wants the ledger out before dawn."
    return request


def legacy(request: dict) -> dict:
    """The same request as an older page sent it: the beat carries no spotlight, so the mill has to read the tie from the names in the plan."""
    out = copy.deepcopy(request)
    out["beat"].pop("spotlight", None)
    return out


def two_ties() -> dict:
    """Two ties between Suvi and Marit, and the plan names both people: name-matching finds both ties. The beat says it is the second."""
    return copy.deepcopy(next(v["data"] for v in GENERATES if v["name"] == "a generate request whose cast has two ties between the same people"))


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
    ambiguous = gen.write_prompt(legacy(base()))                  # an older page sent no id, and both ties are named in this plan, so none is singled out
    assert "## The tie in the spotlight" not in ambiguous
    assert "The tie in the spotlight is Marit toward Suvi" in gen.write_prompt(base())      # with the id the tie is known even though both are named


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
    ambiguous = gen.shifts_prompt(legacy(base()), Kit(base()), CHAPTER)
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
    request = legacy(base())
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
        assert edges and edges[0].id == request["beat"]["spotlight"]                                # handles came back as the id the page sent, the spotlight's
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
    assert "+generate:generate-2:" in load_prompter("mill").version


# ---- A5: the spotlight tie is named by id -------------------------------------------------------------------------------

def entry_for(request: dict, tie_id: str, edge: str) -> dict:
    handle = Kit(request).handles.of_card("entanglements")[0].of("ties", tie_id)
    return entry(handle, edge)


def test_every_valid_generate_vector_names_one_of_its_ties_as_the_spotlight():
    assert len(GENERATES) >= 3
    for vector in GENERATES:
        request = vector["data"]
        assert request["beat"]["spotlight"] in {t["id"] for t in request["ties"]}, vector["name"]
        assert mill_plan.spotlight_of(request)["id"] == request["beat"]["spotlight"]


def test_the_mill_picks_the_tie_by_id_where_name_matching_would_find_two():
    request = two_ties()
    names = mill_plan.names_of(request)
    guessed = {t["id"] for t in mill_plan.spotlight_candidates(request, names)}
    assert {"t1000001", "t1000003"} <= guessed and len(guessed) > 1                                              # the old guess: several ties
    assert mill_plan.spotlight_of(request)["id"] == "t1000003"
    candidates, identified = gen._spot(request, names)
    assert identified and [t["id"] for t in candidates] == ["t1000003"]
    prompt = gen.write_prompt(request)
    assert "The tie in the spotlight is Suvi toward Marit: friend" in prompt
    assert "What drives Suvi in this tie: to keep Marit from learning where the ledger is" in prompt and "What drives Marit in this tie" not in prompt
    assert "to keep Marit from learning where the ledger is" in gen.events_prompt(request, CHAPTER)
    handle = Kit(request).handles.of_card("entanglements")[0].of("ties", "t1000003")
    shifts = gen.shifts_prompt(request, Kit(request), CHAPTER)
    assert f"The tie in the spotlight is Suvi toward Marit ({handle})" in shifts and "is one of these" not in shifts


def test_without_the_id_the_mill_reads_the_tie_from_the_plan_as_before():
    one, same = one_tie(), legacy(one_tie())
    assert mill_plan.spotlight_of(same) is None
    kit = Kit(one)
    assert gen.write_prompt(same) == gen.write_prompt(one) and gen.events_prompt(same, CHAPTER) == gen.events_prompt(one, CHAPTER)
    assert gen.shifts_prompt(same, kit, CHAPTER) == gen.shifts_prompt(one, kit, CHAPTER)
    ambiguous = legacy(two_ties())
    candidates, _ = gen._spot(ambiguous, mill_plan.names_of(ambiguous))
    assert len(candidates) > 1                                                                                  # several named: none is singled out
    assert "## The tie in the spotlight" not in gen.write_prompt(ambiguous)


@pytest.mark.parametrize("wrong", ["t9999999", "", "Marit", 7, None, ["t1000001"]])
def test_an_id_that_is_not_one_of_the_ties_falls_back_and_does_not_raise(wrong):
    request = one_tie()
    request["beat"]["spotlight"] = wrong
    assert mill_plan.spotlight_of(request) is None
    kit = Kit(request)
    assert gen.write_prompt(request) == gen.write_prompt(legacy(one_tie()))
    assert gen.events_prompt(request, CHAPTER) == gen.events_prompt(legacy(one_tie()), CHAPTER)
    assert gen.shifts_prompt(request, kit, CHAPTER) == gen.shifts_prompt(legacy(one_tie()), kit, CHAPTER)
    assert gen.shifts_problem(request, kit, {"shifts": [entry("ties.1", "to forgive her daughter")]}) is None
    assert gen.script(request, kit)
    for attached in (gen.write_prompt(request), gen.shifts_prompt(request, kit, CHAPTER)):
        assert str(wrong) not in attached or wrong in ("", None) or str(wrong) in "Marit Suvi"             # a bad id is not shown either
    beat_less = {k: v for k, v in request.items() if k != "beat"}
    assert mill_plan.spotlight_of(beat_less) is None and mill_plan.spotlight_of({**request, "beat": "text"}) is None


def test_the_shifts_check_wants_the_edge_of_that_exact_tie_replaced_with_a_new_value():
    request = two_ties()
    kit = Kit(request)
    right = entry_for(request, "t1000003", "to tell Marit everything")
    assert gen.shifts_problem(request, kit, {"shifts": [right]}) is None
    other = entry_for(request, "t1000001", "to be let into her daughter's secret")                          # the other tie between the same people
    problem = gen.shifts_problem(request, kit, {"shifts": [other]})
    assert problem and "Suvi toward Marit" in problem and "to keep Marit from learning where the ledger is" in problem
    both = {"card": "entanglements", "patch": {"ties": other["patch"]["ties"] + right["patch"]["ties"]}}
    assert gen.shifts_problem(request, kit, {"shifts": [both]}) is None                                      # both replaced in one entry: the spotlight's is
    same = entry_for(request, "t1000003", "To keep Marit from learning where the ledger is.")                # the same edge, said again
    assert gen.shifts_problem(request, kit, {"shifts": [same]})
    assert gen.shifts_problem(request, kit, {"shifts": []})
    assert gen.shifts_problem(legacy(request), kit, {"shifts": [other]}) is None                               # the fallback keeps the weaker check


def test_the_script_replaces_the_edge_of_the_spotlight_tie():
    request = two_ties()
    kit = Kit(request)
    shifts = json.loads(gen.script(request, kit)[2])
    assert gen.shifts_problem(request, kit, shifts) is None
    handle = Kit(request).handles.of_card("entanglements")[0].of("ties", "t1000003")
    assert [op["id"] for s in shifts["shifts"] if s["card"] == "entanglements" for op in s["patch"]["ties"]] == [handle]


@pytest.mark.parametrize("vector", GENERATES, ids=lambda v: v["name"])
def test_no_prompt_shows_the_tie_id_or_the_raw_key(vector):
    request = vector["data"]
    kit = Kit(request)
    texts = [gen.write_prompt(request), gen.events_prompt(request, CHAPTER), gen.shifts_prompt(request, kit, CHAPTER)]
    for text in texts:
        for ident in ids_in(request) | {request["beat"]["spotlight"]}:
            assert ident not in text, ident
        assert not re.search(r'(^|\n)\s*spotlight\s*[:=]|"spotlight"|\bspotlight=', text)           # the key is never printed (the word, in prose, is fine)
    for factor in budget.SQUEEZES:
        assert request["beat"]["spotlight"] not in gen.write_prompt(request, factor)
    step = gen.build_flow(request, kit).next([])
    assert request["beat"]["spotlight"] not in step.text(1.0)


def test_a_beat_without_a_known_tie_never_prints_its_id_as_the_spotlight():
    request = one_tie()
    request["beat"]["spotlight"] = "t9999999"
    request["beat"]["aim"] = "Suvi wants the ledger out before dawn, and Marit wants to hear about the board."       # names Suvi, Marit
    assert "t9999999" not in gen.write_prompt(request)
    assert "The tie in the spotlight is t9999999" not in gen.write_prompt(request)


@pytest.mark.parametrize("vector", GENERATES, ids=lambda v: v["name"])
def test_every_generate_vector_is_answered_through_the_real_server_on_the_stub_prompter(vector):
    """The stub ignores the beat keys it does not know: it only puts the request in its prompt. The runner accepts what the stub answers."""
    request = vector["data"]
    with running(config=Config(prompter="stub"), engine=StubEngine(write_seconds=0), run=None) as (base_url, _):
        response = post(base_url, request)
        body = response.json()
        assert response.status_code == 200 and body["ok"] is True, body
        reply = contract.parse_reply("generate", body)
        assert reply.chapter_text and reply.events.happened
        assert wait_idle(base_url)
