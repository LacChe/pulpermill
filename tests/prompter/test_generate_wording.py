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
from pulpermill.prompter.mill import advance, generate as gen, plan as mill_plan  # noqa: E402
from pulpermill.prompter.mill.common import load_text  # noqa: E402
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
    assert prompt.rstrip().endswith("so that it reads whole and ends on a finished beat.")            # the task is said again at the end, with the cap
    assert "a complete chapter of up to 1,200 words, aiming for roughly 900 to 1,200 words" in prompt.splitlines()[-1]
    assert "1,800" not in prompt


RULE = "The cast is fixed, and a name for anyone else would be a new character the reader has to keep track of."


def test_the_rule_about_people_beyond_the_cast_is_stated_once_in_the_plan_block_and_not_in_the_craft_paragraphs():
    prompt = gen.write_prompt(base())
    assert prompt.count(RULE) == 1 and prompt.count("none of them has a name") == 1
    plan_block = prompt.split("## The plan for this chapter")[1].split("## ")[0]
    assert RULE in plan_block and "by what they do or by one telling detail, in the narration and in what people say to them" in plan_block
    assert "only places, events and things do" in plan_block               # only people are limited to the card names
    craft = prompt.split("## How to write it")[1]
    assert "cast is fixed" not in craft and "has a name" not in craft              # no second statement of it in the craft paragraphs
    assert prompt.index(RULE) < prompt.index("## The people on stage")           # near the top, with the plan, not in the closing paragraphs
    for gone in ("Only the people on stage act", "appears by role", "never makes the decisions that carry the story", "stays in the background"):
        assert gone not in prompt, gone


def test_the_writer_craft_has_three_paragraphs_and_a_change_paragraph_and_no_minor_character_paragraph():
    w = load_text("generate")
    assert "craft_people" not in w
    prompt = gen.write_prompt(base())
    craft = prompt.split("## How to write it")[1].split("Write only the text")[0].strip().split("\n\n")
    assert len(craft) == 4 and craft[0].startswith("Make this a chapter") and craft[-1].startswith("By the end of the chapter")


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


SHARED_CRAFT = "must be settled on the page: show how it ends, through what people do and say, and let it cost something that stays spent."


def test_every_chapter_is_told_to_settle_its_collision_on_the_page_with_the_same_force():
    first = {**base(), "chapter": 1, "earlier_events": [], "previous_ending": None,
             "setup": {"protagonist": "c0000001", "normal": "Tides and ledgers.", "disruption": "The ledger is gone.", "chapter_count": 8}}
    for request in (first, base(), {**base(), "chapter": 8}):
        prompt = gen.write_prompt(request)
        assert SHARED_CRAFT in prompt and "cannot be taken back" in prompt and "it is where the collision of this chapter is shown decided" in prompt
    assert "nothing new opened" in gen.write_prompt({**base(), "chapter": 8}) and "nothing new opened" not in gen.write_prompt(base())


def test_the_events_and_shifts_prompts_carry_how_the_collision_ended():
    request = one_tie()
    assert "how the collision of the protagonist's aim and the tie in the spotlight ended" in gen.events_prompt(request, CHAPTER)
    grows = "must grow out of how the collision of the chapter ended"
    assert grows in gen.shifts_prompt(request, Kit(request), CHAPTER)
    assert grows in gen.shifts_prompt(legacy(base()), Kit(base()), CHAPTER)


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
    assert [s.name for s in steps] == ["write", "events", "shifts", "advance_edge", "shifts", "advance_edge"]
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert all(m.ok for m in measures) and len(measures) == 6
    assert steps[0].max_output == gen.WRITE_TOKENS and budget.input_limit(gen.WRITE_TOKENS) > 8000    # the chapter has room to be written


def test_a_chinese_story_states_the_cap_in_characters_at_twice_the_word_figure():
    request = base()
    request["language"] = "zh"
    last = gen.write_prompt(request).splitlines()[-1]
    assert "up to 2,400 Chinese characters" in last and "1,800 to 2,400 Chinese characters" in last and "1,200 words" not in last
    assert last.startswith("Write only the text of the chapter, in Chinese") or "Chinese" in last


@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
def test_the_output_limit_holds_a_chapter_at_the_cap_with_room_to_spare():
    english = " ".join((" ".join([CHAPTER] * 75)).split()[:1200])      # 1,200 words
    chinese = "她走进内库，听见门外的脚步声，没有回头。" * 142          # 17 Han characters a repeat: 2,414, a little over the cap
    assert len(english.split()) == 1200 and len(re.findall(r"[\u4e00-\u9fff]", chinese)) >= 2400
    for text in (english, chinese):
        assert tokens.count(text) < gen.WRITE_TOKENS, (tokens.count(text), gen.WRITE_TOKENS)
    assert gen.WRITE_TOKENS == 2560 and gen.CAP_WORDS == 1200 and gen.CAP_HAN == 2 * gen.CAP_WORDS


@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
def test_chapter_19_of_20_with_18_earlier_events_fits_and_cuts_the_oldest_history_first():
    request = inflate(one_tie(), cast=6, each=5, ties=6, chapters=18, chars=900)
    request["beat"], request["ties"] = one_tie()["beat"], request["ties"][:2]
    request["previous_ending"] = one_tie()["previous_ending"]
    request["chapter"], request["chapter_count"] = 19, 20
    assert len(request["earlier_events"]) == 18
    flow = gen.build_flow(request, Kit(request))
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert all(m.ok for m in measures) and len(measures) == 6
    full, squeezed = sections(gen.write_prompt(request, 1.0)), sections(gen.write_prompt(request, 0.55))
    history = "The story so far"
    assert squeezed[history] != full[history] and "Chapter 18" in squeezed[history]
    assert "chapter 19 of 20" in gen.write_prompt(request, factor)


# ---- the write step's length check ------------------------------------------------------------------------------------------

def words_of(n: int) -> str:
    return " ".join(["word"] * n)


@pytest.mark.parametrize("n, flagged", [(300, False), (1200, False), (1500, False), (1501, True), (2400, True)])
def test_the_write_check_speaks_only_when_the_chapter_is_far_over_the_cap(n, flagged):
    problem = gen.write_problem(base(), words_of(n))
    assert (problem is not None) == flagged
    if flagged:
        assert problem == "Shorten the chapter to at most 1,200 words by keeping the scenes the plan needs and cutting the rest." and "\n" not in problem


@pytest.mark.parametrize("text", ["", "One line.", words_of(10)])
def test_the_write_check_never_rejects_a_short_chapter(text):
    assert gen.write_problem(base(), text) is None


@pytest.mark.parametrize("n, flagged", [(2400, False), (3000, False), (3001, True)])
def test_the_write_check_counts_han_characters_for_chinese(n, flagged):
    request = base()
    request["language"] = "zh"
    problem = gen.write_problem(request, "她" * n)
    assert (problem is not None) == flagged
    if flagged:
        assert "at most 2,400 Chinese characters" in problem
    assert gen.write_problem(request, "word " * 1600) is None          # Latin words do not count in a Chinese story


def test_the_write_step_carries_the_length_check_and_the_first_attempt_is_kept_when_it_passes():
    request = base()
    step = gen.build_flow(request, Kit(request)).next([])
    assert step.name == "write" and step.max_output == gen.WRITE_TOKENS and step.check(words_of(1500)) is None and step.check(words_of(1600))


# ---- the events step ------------------------------------------------------------------------------------------------------

def test_the_events_prompt_holds_the_chapter_and_asks_for_happened_and_changed():
    prompt = gen.events_prompt(one_tie(), CHAPTER)
    assert CHAPTER in prompt and "happened" in prompt and "changed" in prompt and "one short sentence" in prompt
    assert "at the start its edge was: to bring her daughter home" in prompt


def test_the_events_check_refuses_only_an_empty_or_too_short_reply():
    happened = "Suvi hid the ledger and Marit found her."
    assert gen.events_problem({"happened": happened, "changed": "Suvi can no longer hide."}) is None
    assert "plain sentences" in gen.events_problem({"happened": "", "changed": "x"})
    assert "short sentence" in gen.events_problem({"happened": happened, "changed": ""})
    # a changed that runs on is not refused: the flow repairs it
    assert gen.events_problem({"happened": happened, "changed": "Suvi can hide no more. Marit knows everything now."}) is None


def test_a_running_on_changed_is_repaired_to_its_first_sentence_and_the_word_cap():
    fixed = gen.repair_events({"happened": "H", "changed": "Suvi can hide no more. Marit knows everything now."})
    assert fixed == {"happened": "H", "changed": "Suvi can hide no more."}
    long = gen.repair_events({"happened": "H", "changed": " ".join(["word"] * 80) + "."})
    assert len(long["changed"].split()) == gen.CHANGED_WORDS and long["changed"].endswith(".")
    assert gen.repair_events({"happened": "H", "changed": "No stop here"})["changed"] == "No stop here"
    assert gen.repair_events({"happened": "H", "changed": "她再也无法隐藏。马里特全都知道了。"})["changed"] == "她再也无法隐藏。"


def test_the_events_fallback_is_plain_code_over_the_chapter():
    chapter = "Suvi hid the ledger. Marit searched the house. They quarrelled at the table. In the end Suvi gave the ledger up."
    got = gen.events_fallback(chapter)
    assert got == {"happened": "Suvi hid the ledger. Marit searched the house.", "changed": "In the end Suvi gave the ledger up."}
    assert gen.events_fallback("A single sentence")["changed"] == "A single sentence"
    assert gen.events_fallback("   ") == {"happened": "", "changed": ""}
    assert len(gen.events_fallback("word " * 500)["happened"].split()) <= gen.HAPPENED_WORDS


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
    assert engine.calls == 4 and "## The plan for this chapter" in engine.prompts[0] and engine.params[0] is not None
    assert [c is None for c in engine.constraints] == [True, False, False, False]                          # prose is free; events and shifts are grammar-bound


def test_a_shifts_reply_that_misses_the_edge_is_asked_for_again_with_the_line_and_then_used():
    request = one_tie()
    kit = Kit(request)
    text, events, shifts, judge = gen.script(request, kit)
    engine = FakeEngine()
    engine.script(text, events, json.dumps({"shifts": []}), shifts, judge)
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        assert post(base_url, request).status_code == 200
        assert wait_idle(base_url)
    assert engine.calls == 5 and "replaces the edge of ties.1" in engine.prompts[3]


def test_the_chapter_is_the_writers_text_and_nothing_else():
    request = one_tie()
    flow = gen.build_flow(request, Kit(request))
    reply = flow.reply(["\n  The chapter.\n", {"happened": "H", "changed": "C"}, {"shifts": []}])
    assert reply == {"chapter_text": "The chapter.", "events": {"happened": "H", "changed": "C"}, "shifts": []}


def test_the_version_follows_the_wording():
    assert "+generate:generate-12:" in load_prompter("mill").version


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


# ---- after the chapter is written: each step on its own, then a last resort (2A) -----------------------------------------------------

def _generate(*texts, **config):
    """The real generate flow on the fake engine, scripted: write, then events and shifts as given. Returns (reply, ctx, engine, good)."""
    from pulpermill.backend import runner
    from pulpermill.backend.engine.base import CancelFlag
    from pulpermill.backend.pipelines import RunContext
    request = base()
    kit = Kit(request)
    good = gen.script(request, kit)
    engine = FakeEngine()
    engine.script(*[good[i] if isinstance(i, int) else i for i in texts], good[3])      # an int stands for the module's own good text number i; the edge judge's good reply comes last (it is unused when no edge was replaced)
    ctx = RunContext(engine, CancelFlag(), [].append, Config(**config))
    ctx.notes["call"] = "generate"
    flow = gen.build_flow(request, kit)
    return flow.reply(runner.run_flow(ctx, flow, "en")), ctx, engine, good


def test_the_two_steps_after_the_write_get_more_attempts_and_a_fallback_each():
    steps = gen.build_flow(base(), Kit(base())).worst_case()
    write, events, shifts, judge, *_ = steps
    assert (write.attempts, write.fallback) == (2, None)
    assert (events.attempts, shifts.attempts) == (4, 3) and callable(events.fallback) and callable(shifts.fallback)
    assert shifts.fallback() == {"shifts": []}


def test_an_events_step_that_fails_every_attempt_still_returns_the_chapter_with_a_fallback():
    reply, ctx, engine, good = _generate(0, "no json", "still no", "nope", "again no", 2)
    assert reply["chapter_text"] == good[0].strip() and reply["events"] == gen.events_fallback(good[0].strip())
    assert reply["shifts"] and ctx.notes["flow"] == {"events_fallback": True, "shifts_fallback": False, "edge_move": "complicates", "minor_names": 0, "minor_new": 0, "pressure_on": False}
    events_pass = [p for p in ctx.notes["passes"] if p["step"] == "events"][0]
    assert len(events_pass["attempts"]) == 4 and events_pass["fallback"] is True and engine.calls == 7


def test_a_first_events_attempt_that_fails_does_not_rerun_the_other_steps():
    reply, ctx, engine, good = _generate(0, "no json", 1, 2)
    assert engine.calls == 5 and ctx.notes["flow"] == {"events_fallback": False, "shifts_fallback": False, "edge_move": "complicates", "minor_names": 0, "minor_new": 0, "pressure_on": False}
    assert [(p["step"], len(p["attempts"])) for p in ctx.notes["passes"]] == [("write", 1), ("events", 2), ("shifts", 1), ("advance_edge", 1)]
    assert reply["events"]["happened"] == json.loads(good[1])["happened"]


def test_a_shifts_step_that_fails_every_attempt_gives_an_empty_list_and_keeps_the_events():
    reply, ctx, engine, good = _generate(0, 1, "bad", "worse", "worst")
    assert reply["shifts"] == [] and reply["events"]["changed"] == json.loads(good[1])["changed"]
    assert ctx.notes["flow"] == {"events_fallback": False, "shifts_fallback": True, "minor_names": 0, "minor_new": 0, "pressure_on": False} and engine.calls == 5


def test_the_write_step_keeps_its_own_two_attempts_and_no_fallback():
    from pulpermill.backend.errors import BackendError
    with pytest.raises(BackendError) as e:
        _generate("", "")
    assert e.value.kind == "bad_output"


def test_an_events_reply_that_runs_on_is_repaired_not_retried():
    long = json.dumps({"happened": "The people met and quarrelled over the ledger.", "changed": "Suvi can hide no more. Marit knows everything now."})
    reply, ctx, engine, _ = _generate(0, long, 2)
    assert engine.calls == 4 and reply["events"]["changed"] == "Suvi can hide no more."


def test_every_fallback_is_a_line_in_the_trace(tmp_path):
    path = tmp_path / "trace.jsonl"
    _generate(0, "a", "b", "c", "d", 2, trace_path=str(path))
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    events = [x for x in lines if x["step"] == "events"]
    assert [(x["attempt"], x["used"], x.get("fallback")) for x in events] == [(1, False, None), (2, False, None), (3, False, None), (4, False, None), (5, True, True)]
    assert events[-1]["reply"] == "" and events[-1]["problem"] is None


# ---- the edge judge after the shifts (phase 3, observe-only) -------------------------------------------------------------------------

def test_the_edge_judge_is_a_step_of_its_own_after_the_shifts_with_two_attempts_and_a_neutral_fallback():
    request = base()
    flow = gen.build_flow(request, Kit(request))
    text, events, shifts, judge = gen.script(request, Kit(request))
    step = flow.next([text, json.loads(events), json.loads(shifts)])
    assert step.name == "advance_edge" and step.attempts == 2 and callable(step.fallback)
    assert "to bring her daughter home" in step.text(1.0) and "to settle what this chapter opened" in step.text(1.0)
    assert step.fallback() == {} and advance.edge_ok(step.fallback()) and flow.notes["edge_judge_fallback"] is True


def test_no_edge_judge_runs_when_the_shifts_replaced_no_edge():
    request = base()
    flow = gen.build_flow(request, Kit(request))
    assert flow.next(["a chapter", {"happened": "x", "changed": "y"}, {"shifts": []}]) is None
    assert gen.replaced_edge(request, Kit(request), {"shifts": []}) is None


REWORDS = json.dumps({"reason": "Same want, new words.", "move": "rewords"})


def test_with_the_flag_off_the_verdict_only_goes_to_the_notes_and_the_reply_is_the_same_whatever_it_says(monkeypatch):
    monkeypatch.setattr(advance, "ENFORCE", False)
    reply, ctx, engine, good = _generate(0, 1, 2, REWORDS)
    plain, _, _, _ = _generate(0, 1, 2)
    assert reply == plain and engine.calls == 4 and ctx.notes["flow"] == {"events_fallback": False, "shifts_fallback": False, "edge_move": "rewords", "minor_names": 0, "minor_new": 0, "pressure_on": False}
    assert [s.name for s in gen.build_flow(base(), Kit(base())).worst_case()][-1] == "advance_edge" and len(gen.build_flow(base(), Kit(base())).worst_case()) == 4


def test_a_reworded_edge_sends_only_the_shifts_back_once_with_the_judges_line_and_the_judge_runs_again():
    reply, ctx, engine, good = _generate(0, 1, 2, REWORDS, 2)
    assert engine.calls == 6 and reply["chapter_text"] == good[0].strip()
    assert [(p["step"], len(p["attempts"])) for p in ctx.notes["passes"]] == [("write", 1), ("events", 1), ("shifts", 1), ("advance_edge", 1), ("shifts", 1), ("advance_edge", 1)]
    assert ctx.notes["flow"] == {"events_fallback": False, "shifts_fallback": False, "edge_move": "rewords", "edge_resent": True, "edge_move_after": "complicates", "minor_names": 0, "minor_new": 0, "pressure_on": False}
    assert "Your first list of changes was set aside." not in engine.prompts[2]
    assert "Your first list of changes was set aside. Same want, new words." in engine.prompts[4] and "Let the edge move" in engine.prompts[4]
    assert engine.prompts[4].rindex("Let the edge move") < engine.prompts[4].rindex("Reply with a JSON object with one key")                # the line sits ahead of the format rule
    assert "Your first list" not in engine.prompts[0]                                                      # the write was never asked again


def test_a_second_reworded_verdict_is_accepted_and_noted_and_nothing_runs_a_third_time():
    reply, ctx, engine, good = _generate(0, 1, 2, REWORDS, 2, REWORDS)
    assert engine.calls == 6 and reply["shifts"]
    assert ctx.notes["flow"]["edge_resent"] is True and ctx.notes["flow"]["edge_move_after"] == "rewords" and ctx.notes["flow"]["edge_accepted"] is True


def test_a_good_verdict_sends_nothing_back():
    reply, ctx, engine, good = _generate(0, 1, 2)
    assert engine.calls == 4 and "edge_resent" not in ctx.notes["flow"]


def test_shifts_that_cannot_be_redone_keep_the_first_ones_and_the_call_still_succeeds():
    reply, ctx, engine, good = _generate(0, 1, 2, REWORDS, "a", "b", "c")
    assert engine.calls == 7 and reply["shifts"] == json.loads(good[2])["shifts"]                 # three refused attempts, then the first shifts stand
    assert ctx.notes["flow"]["edge_resend_fallback"] is True and ctx.notes["flow"]["edge_accepted"] is True


def test_a_judge_that_fails_every_attempt_never_fails_the_call_and_leaves_the_reply_alone():
    reply, ctx, engine, good = _generate(0, 1, 2)
    engine_bad = FakeEngine()
    from pulpermill.backend import runner
    from pulpermill.backend.engine.base import CancelFlag
    from pulpermill.backend.pipelines import RunContext
    request = base()
    kit = Kit(request)
    engine_bad.script(good[0], good[1], good[2], "no json", "still none")
    ctx2 = RunContext(engine_bad, CancelFlag(), [].append, Config())
    ctx2.notes["call"] = "generate"
    flow = gen.build_flow(request, kit)
    again = flow.reply(runner.run_flow(ctx2, flow, "en"))
    assert again == reply and ctx2.notes["flow"]["edge_judge_fallback"] is True and "edge_move" not in ctx2.notes["flow"]
    judge_pass = [p for p in ctx2.notes["passes"] if p["step"] == "advance_edge"][0]
    assert len(judge_pass["attempts"]) == 2 and judge_pass["fallback"] is True


def test_the_prompter_version_changes_with_the_judge_wording(monkeypatch, tmp_path):
    import shutil
    from pulpermill.prompter.mill import common
    first = load_prompter("mill").version
    assert f"+advance:{advance.VERSION}:" in first
    shutil.copytree(common.TEXT, tmp_path / "text")
    monkeypatch.setattr(common, "TEXT", tmp_path / "text")
    assert load_prompter("mill").version == first                           # a copy of the same wording: the same version
    with open(tmp_path / "text" / "en" / "advance.yaml", "a", encoding="utf-8") as handle:
        handle.write("# one more word\n")
    changed = load_prompter("mill").version
    assert changed != first and changed.split("+advance:")[0] == first.split("+advance:")[0]


# ---- the pressure (world-pressure-2): the writer's line, the judge, the notes -----------------------------------------------------------

SENTENCE = "a part of the collision, whether or not it has anything to do with the aim or the tie to begin with"
ACTS = json.dumps({"reason": "The rule costs her something.", "effect": "acts"})
DECOR = json.dumps({"reason": "The rule is only mentioned.", "effect": "decor"})


def pressed(kind="rule") -> dict:
    """A generate request with a pressure in words (the page's W1 shape) and its id on the beat, as the page sends both."""
    request = base()
    world = request["world"]
    if kind == "rule":
        rule = world["rules"][0]
        request["pressure"] = {"kind": "rule", "statement": rule["statement"], "cost": rule["cost"], "when_broken": rule["when_broken"]}
        request["beat"]["pressure"] = rule["id"]
    else:
        thing = world["objects"][0]
        request["pressure"] = {"kind": "object", "name": thing["name"], "description": thing["description"], "significance": thing["significance"]}
        request["beat"]["pressure"] = thing["id"]
    return request


def _generate_pressed(request, *texts):
    from pulpermill.backend import runner
    from pulpermill.backend.engine.base import CancelFlag
    from pulpermill.backend.pipelines import RunContext
    kit = Kit(request)
    engine = FakeEngine()
    engine.script(*texts)
    ctx = RunContext(engine, CancelFlag(), [].append, Config())
    ctx.notes["call"] = "generate"
    flow = gen.build_flow(request, kit)
    return flow.reply(runner.run_flow(ctx, flow, "en")), ctx, engine


@pytest.mark.parametrize("kind", ["rule", "object"])
def test_the_writer_gets_the_pressure_line_and_the_element_once_in_the_scene_block_and_no_new_section(kind):
    plain, request = base(), pressed(kind)
    a, b = gen.write_prompt(plain), gen.write_prompt(request)
    assert list(sections(a)) == list(sections(b)) and a.count(SENTENCE) == 0 and b.count(SENTENCE) == 1
    phrase = request["pressure"]["statement"] if kind == "rule" else request["pressure"]["description"]
    assert a.count(phrase) == 1 and b.count(phrase) == 1
    scene = [body for body in sections(b).values() if SENTENCE in body][0]
    assert phrase in scene and "Suvi hides the ledger" in scene                               # next to the plan, in the same block
    assert request["beat"]["pressure"] not in b                                              # the id never reaches the prompt


def test_with_no_pressure_the_writer_prompt_is_what_it_was_and_a_squeeze_drops_the_sentence_first():
    plain = base()
    assert gen.write_prompt(dict(plain, pressure=None)) == gen.write_prompt(plain) and SENTENCE not in gen.write_prompt(plain)
    for kind in ("rule", "object"):
        assert gen.write_prompt(pressed(kind), 0.99) == gen.write_prompt(plain, 0.99)
        assert gen.write_prompt(pressed(kind), 0.7) == gen.write_prompt(plain, 0.7)


def test_the_pressure_judge_runs_last_reads_what_happened_and_not_the_chapter_and_records_a_word():
    request = pressed()
    kit = Kit(request)
    good = gen.script(request, kit)
    assert len(good) == 5 and json.loads(good[4])["effect"] == "acts"
    reply, ctx, engine = _generate_pressed(request, *good)
    assert engine.calls == 5 and [p["step"] for p in ctx.notes["passes"]] == ["write", "events", "shifts", "advance_edge", "advance_pressure"]
    judged = engine.prompts[4]
    assert json.loads(good[1])["happened"] in judged and good[0].strip() not in judged and request["pressure"]["statement"] in judged
    assert request["beat"]["pressure"] not in judged and request["beat"]["aim"] in judged
    assert ctx.notes["flow"]["pressure_on"] is True and ctx.notes["flow"]["pressure_effect"] == "acts"
    assert reply["events"]["happened"] == json.loads(good[1])["happened"] and reply["shifts"]


def test_a_decor_verdict_or_a_failing_judge_changes_nothing_in_the_reply():
    request = pressed()
    good = gen.script(request, Kit(request))
    reply_acts, _, _ = _generate_pressed(request, *good)
    reply_decor, ctx, engine = _generate_pressed(request, *good[:4], DECOR)
    assert reply_decor == reply_acts and engine.calls == 5 and ctx.notes["flow"]["pressure_effect"] == "decor"
    reply_bad, ctx, engine = _generate_pressed(request, *good[:4], "no", "still no")
    assert reply_bad == reply_acts and engine.calls == 6
    assert ctx.notes["flow"]["pressure_effect"] == "unclear" and ctx.notes["flow"]["pressure_judge_fallback"] is True


def test_the_reply_keeps_the_resent_shifts_when_a_pressure_judge_follows_them():
    request = pressed()
    good = gen.script(request, Kit(request))
    reply, ctx, engine = _generate_pressed(request, good[0], good[1], good[2], REWORDS, good[2], good[3], ACTS)
    assert engine.calls == 7 and [p["step"] for p in ctx.notes["passes"]][-3:] == ["shifts", "advance_edge", "advance_pressure"]
    assert reply["shifts"] == json.loads(good[2])["shifts"] and ctx.notes["flow"]["pressure_effect"] == "acts"
    assert ctx.notes["flow"]["edge_resent"] is True


def test_the_pressure_judge_runs_when_no_edge_was_replaced_and_not_without_a_pressure():
    request = pressed()
    flow = gen.build_flow(request, Kit(request))
    step = flow.next(["a chapter", {"happened": "The rule cost her.", "changed": "y"}, {"shifts": []}])
    assert step.name == "advance_pressure" and "The rule cost her." in step.text(1.0)
    assert flow.notes["pressure_on"] is True and [s.name for s in flow.worst_case()][-1] == "advance_pressure"
    plain = gen.build_flow(base(), Kit(base()))
    assert plain.notes["pressure_on"] is False and "advance_pressure" not in [s.name for s in plain.worst_case()] and len(gen.script(base(), Kit(base()))) == 4
