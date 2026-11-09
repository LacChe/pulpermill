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
from pulpermill.prompter.mill.common import load_text  # noqa: E402
from pulpermill.prompts import budget, tokens  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402
from story_sizes import chapter_text, inflate  # noqa: E402
from stub_engine import StubEngine  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
GENERATES = [v for v in VECTORS if v["valid"] and v["data"]["call"] == "generate"]
EVENTS = {"happened": "Suvi hid the ledger from Marit on the stairs.", "changed": "Suvi kept the ledger. She now goes after Marit's key before dawn. The tie now runs on that key."}
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
    answered = "how the chapter answered what the person at the from end wanted from the other person"
    assert answered in gen.shifts_prompt(request, Kit(request), EVENTS)
    assert answered in gen.shifts_prompt(legacy(base()), Kit(base()), EVENTS)


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
    assert all(m.ok for m in measures) and len(measures) == 3
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
    assert CHAPTER in prompt and "happened" in prompt and "changed" in prompt and "one or two short sentences" in prompt and "the one concrete thing the protagonist goes after next" in prompt
    assert "at the start its edge was: to bring her daughter home" in prompt
    assert "a person, an object or a deadline" in prompt and "is not an aim" in prompt
    assert "not on what they realized, felt or concluded at the end of the chapter" in prompt
    assert "still open" not in prompt and "never hedged" in prompt and "reaching what they were after, losing it, or giving it up" in prompt
    assert "was planned to end" not in prompt          # a beat with no planned outcome is told none


@pytest.mark.parametrize("outcome,phrase,after", [
    ("reached", "reaching what they were after, at a price", "is a new pursuit and not the old aim stated again"),
    ("lost", "losing what they were after.", "is what they turned to, or what the loss now forces"),
    ("gave_up", "giving up what they were after for something else", "is what they turned to, or what the loss now forces"),
])
def test_the_events_prompt_gives_the_planned_outcome_as_a_fact_and_the_next_aim_rule_that_fits_it(outcome, phrase, after):
    request = one_tie()
    request["beat"]["outcome"] = outcome
    prompt = gen.events_prompt(request, CHAPTER)
    given = [p for p in ("reaching what they were after, at a price", "losing what they were after.", "giving up what they were after for something else") if p in prompt]
    assert given == [phrase] and "was planned to end with the protagonist" in prompt and "That is how it ended." in prompt
    assert after in prompt and "still open" not in prompt and "never hedged" in prompt
    assert "ended the way the chapter was planned to end" in prompt and "losing it, or giving it up" not in prompt          # the given outcome is not offered again as a choice
    assert prompt.count("a new pursuit and not the old aim stated again") == (1 if outcome == "reached" else 0)


def test_an_outcome_the_schema_does_not_know_is_left_out_of_the_events_prompt():
    for value in ("partly", None, 2, ["reached"]):
        request = one_tie()
        request["beat"]["outcome"] = value
        assert "was planned to end" not in gen.events_prompt(request, CHAPTER)


def test_the_events_check_refuses_only_an_empty_or_too_short_reply():
    happened = "Suvi hid the ledger and Marit found her."
    assert gen.events_problem({"happened": happened, "changed": "Suvi can no longer hide."}) is None
    assert "plain sentences" in gen.events_problem({"happened": "", "changed": "x"})
    assert "short sentence" in gen.events_problem({"happened": happened, "changed": ""})
    # a changed that runs on is not refused: the flow repairs it
    assert gen.events_problem({"happened": happened, "changed": "Suvi can hide no more. Marit knows everything now."}) is None


def test_a_running_on_changed_is_repaired_to_its_first_two_sentences_and_the_word_cap():
    fixed = gen.repair_events({"happened": "H", "changed": "Suvi can hide no more. Marit knows everything now. A third sentence."})
    assert fixed == {"happened": "H", "changed": "Suvi can hide no more. Marit knows everything now."}
    kept = gen.repair_events({"happened": "H", "changed": " ".join(["word"] * 90) + "."})
    assert len(kept["changed"].split()) == 90 and kept["changed"].endswith(".")        # a 90-word sentence is kept whole
    long = gen.repair_events({"happened": "H", "changed": " ".join(["word"] * 130) + "."})
    assert gen.CHANGED_WORDS == 100 and len(long["changed"].split()) == 100 and long["changed"].endswith(".")
    assert gen.repair_events({"happened": "H", "changed": "No stop here"})["changed"] == "No stop here"
    assert gen.repair_events({"happened": "H", "changed": "她再也无法隐藏。马里特全都知道了。"})["changed"] == "她再也无法隐藏。 马里特全都知道了。"


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
    prompt = gen.shifts_prompt(request, Kit(request), EVENTS)
    assert "ties.1: Marit toward Suvi: mother. Edge: to bring her daughter home" in prompt
    assert "wants.1" not in prompt and "places." not in prompt and "holdings." not in prompt        # only the ties are shown: nothing else changes in a chapter
    assert "The tie in the spotlight is Marit toward Suvi (ties.1); its edge was: to bring her daughter home" in prompt
    assert "one entry for the ties" in prompt and "only the edge and the bond of a tie" in prompt and "t1000001" not in prompt and "c0000001" not in prompt
    ambiguous = gen.shifts_prompt(legacy(base()), Kit(base()), EVENTS)
    assert "is one of these: ties.1" in ambiguous and "ties.2" in ambiguous
    move = load_text("generate")["shifts_edge_move"]
    assert prompt.count(move) == 1 and ambiguous.count(move) == 1                      # one shared key, in the single-tie and the any-tie version
    bond = load_text("generate")["shifts_bond"]
    assert prompt.count(bond) == 1 and ambiguous.count(bond) == 1                      # one shared key, after the move, in both versions
    assert prompt.index("its edge was:") < prompt.index(move) < prompt.index(bond) < prompt.index("Reply with a JSON object with one key") and "never the old want made stronger" in prompt
    for text in (prompt, ambiguous):
        assert "written the way the old" not in text and "Start from what the last events of the chapter left standing, not from the old edge" in text


def test_the_shifts_check_wants_the_spotlight_edge_replaced_with_something_new():
    request = one_tie()
    kit = Kit(request)
    ok = {"shifts": [entry("ties.1", "to forgive her daughter and let her stay")]}
    assert gen.shifts_problem(request, kit, ok) is None
    for missing in ({"shifts": []},
                    {"shifts": [entry("ties.2", "to hide the ledger for good")]},                  # another tie's edge is not the spotlight's
                    {"shifts": [entry("ties.1", "To bring her daughter home.")]}):                   # the same edge, said again
        problem = gen.shifts_problem(request, kit, missing)
        assert problem and "ties.1" in problem and "Marit toward Suvi" in problem, missing
    people = gen.shifts_problem(request, kit, {"shifts": [{"card": "characters", "target": "Suvi", "patch": {"sketch": "Changed."}}]})
    assert people and "only the edge and the bond of ties" in people                          # a chapter does not change people
    removed = gen.shifts_problem(request, kit, {"shifts": [{"card": "entanglements", "patch": {"ties": [{"op": "remove", "id": "ties.1"}]}}]})
    assert removed and "only the edge and the bond of ties" in removed                        # nor take a tie away


def test_the_shifts_check_lets_a_bond_ride_along_with_a_new_edge_and_never_alone():
    request = one_tie()
    kit = Kit(request)
    tie = lambda values: {"shifts": [{"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": "ties.1", "values": values}]}}]}
    assert gen.shifts_problem(request, kit, tie({"edge": "to forgive her daughter and let her stay", "bond": "two women who share a roof"})) is None
    alone = gen.shifts_problem(request, kit, tie({"bond": "two women who share a roof"}))
    assert alone and "ties.1" in alone and "Marit toward Suvi" in alone                     # a bond without a new edge still fails the edge check
    same = gen.shifts_problem(request, kit, tie({"edge": "To bring her daughter home.", "bond": "two women who share a roof"}))
    assert same and "ties.1" in same                                                         # a bond does not excuse an edge that is the same


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
    assert "+generate:generate-16:" in load_prompter("mill").version


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
    shifts = gen.shifts_prompt(request, Kit(request), EVENTS)
    assert f"The tie in the spotlight is Suvi toward Marit ({handle})" in shifts and "is one of these" not in shifts


def test_without_the_id_the_mill_reads_the_tie_from_the_plan_as_before():
    one, same = one_tie(), legacy(one_tie())
    assert mill_plan.spotlight_of(same) is None
    kit = Kit(one)
    assert gen.write_prompt(same) == gen.write_prompt(one) and gen.events_prompt(same, CHAPTER) == gen.events_prompt(one, CHAPTER)
    assert gen.shifts_prompt(same, kit, EVENTS) == gen.shifts_prompt(one, kit, EVENTS)
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
    assert gen.shifts_prompt(request, kit, EVENTS) == gen.shifts_prompt(legacy(one_tie()), kit, EVENTS)
    assert gen.shifts_problem(request, kit, {"shifts": [entry("ties.1", "to forgive her daughter")]}) is None
    assert gen.script(request, kit)
    for attached in (gen.write_prompt(request), gen.shifts_prompt(request, kit, EVENTS)):
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
    texts = [gen.write_prompt(request), gen.events_prompt(request, CHAPTER), gen.shifts_prompt(request, kit, EVENTS)]
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
    engine.script(*[good[i] if isinstance(i, int) else i for i in texts])      # an int stands for the module's own good text number i
    ctx = RunContext(engine, CancelFlag(), [].append, Config(**config))
    ctx.notes["call"] = "generate"
    flow = gen.build_flow(request, kit)
    return flow.reply(runner.run_flow(ctx, flow, "en")), ctx, engine, good


def test_the_two_steps_after_the_write_get_more_attempts_and_a_fallback_each():
    steps = gen.build_flow(base(), Kit(base())).worst_case()
    write, events, shifts = steps
    assert (write.attempts, write.fallback) == (2, None)
    assert (events.attempts, shifts.attempts) == (4, 3) and callable(events.fallback) and callable(shifts.fallback)
    assert shifts.fallback() == {"shifts": []}


def test_an_events_step_that_fails_every_attempt_still_returns_the_chapter_with_a_fallback():
    reply, ctx, engine, good = _generate(0, "no json", "still no", "nope", "again no", 2)
    assert reply["chapter_text"] == good[0].strip() and reply["events"] == gen.events_fallback(good[0].strip())
    assert reply["shifts"] and ctx.notes["flow"] == {"events_fallback": True, "shifts_fallback": False, "minor_names": 0, "minor_new": 0, "pressure_on": False}
    events_pass = [p for p in ctx.notes["passes"] if p["step"] == "events"][0]
    assert len(events_pass["attempts"]) == 4 and events_pass["fallback"] is True and engine.calls == 6


def test_a_first_events_attempt_that_fails_does_not_rerun_the_other_steps():
    reply, ctx, engine, good = _generate(0, "no json", 1, 2)
    assert engine.calls == 4 and ctx.notes["flow"] == {"events_fallback": False, "shifts_fallback": False, "minor_names": 0, "minor_new": 0, "pressure_on": False}
    assert [(p["step"], len(p["attempts"])) for p in ctx.notes["passes"]] == [("write", 1), ("events", 2), ("shifts", 1)]
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
    assert engine.calls == 3 and reply["events"]["changed"] == "Suvi can hide no more. Marit knows everything now."


def test_every_fallback_is_a_line_in_the_trace(tmp_path):
    path = tmp_path / "trace.jsonl"
    _generate(0, "a", "b", "c", "d", 2, trace_path=str(path))
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    events = [x for x in lines if x["step"] == "events"]
    assert [(x["attempt"], x["used"], x.get("fallback")) for x in events] == [(1, False, None), (2, False, None), (3, False, None), (4, False, None), (5, True, True)]
    assert events[-1]["reply"] == "" and events[-1]["problem"] is None


# ---- after the shifts: nothing --------------------------------------------------------------------------------------------------

def test_a_generate_call_runs_exactly_write_events_and_shifts():
    request = base()
    flow = gen.build_flow(request, Kit(request))
    text, events, shifts = gen.script(request, Kit(request))
    results = [text, json.loads(events), json.loads(shifts)]
    assert flow.next(results) is None and flow.next([]).name == "write" and flow.next(results[:1]).name == "events" and flow.next(results[:2]).name == "shifts"
    assert [s.name for s in flow.worst_case()] == ["write", "events", "shifts"]
    reply, ctx, engine, good = _generate(0, 1, 2)
    assert engine.calls == 3 and [p["step"] for p in ctx.notes["passes"]] == ["write", "events", "shifts"]
    assert ctx.notes["flow"] == {"events_fallback": False, "shifts_fallback": False, "minor_names": 0, "minor_new": 0, "pressure_on": False}


def test_shifts_that_replace_the_spotlight_edge_are_accepted_as_they_are_and_returned():
    request = one_tie()
    kit = Kit(request)
    tie = lambda values: json.dumps({"shifts": [{"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": "ties.1", "values": values}]}}]})
    for shifts in (tie({"edge": "to bring her daughter home, and soon"}), tie({"edge": "a feeling", "bond": "Two women, bound by it"}), tie({"edge": "to forgive her daughter and let her stay"})):
        assert gen.shifts_problem(request, kit, json.loads(shifts)) is None
        reply, ctx, engine, _ = _generate(0, 1, shifts)
        assert engine.calls == 3 and reply["shifts"] == json.loads(shifts)["shifts"]            # no model reads the new edge or bond, and nothing sends the shifts back
        assert [p["step"] for p in ctx.notes["passes"]] == ["write", "events", "shifts"]
        assert not any(k.startswith("edge_") for k in ctx.notes["flow"])


def test_the_shifts_prompt_gets_the_summary_facts_and_never_the_prose():
    request = one_tie()
    prompt = gen.shifts_prompt(request, Kit(request), EVENTS)
    assert EVENTS["happened"] in prompt and "What happened in the chapter, as its summary records it:" in prompt
    assert "What the chapter changed, as its summary records it:" in prompt and "The chapter:" not in prompt
    assert load_text("generate")["shifts_form"] in prompt and prompt.count(load_text("generate")["shifts_form"]) == 1
    assert "a concrete person, thing, place or deadline" in prompt and "not a mood, a manner or a trend" in prompt and "it does not describe a feeling" in prompt
    assert CHAPTER not in prompt and CHAPTER not in gen.shifts_prompt(request, Kit(request), EVENTS, 1.0)
    no_changed = gen.shifts_prompt(request, Kit(request), {"happened": "Only this."})
    assert "Only this." in no_changed and "What the chapter changed" not in no_changed
    reply, ctx, engine, good = _generate(0, 1, 2)
    assert good[0].strip() not in engine.prompts[2] and json.loads(good[1])["happened"] in engine.prompts[2]


# ---- the pressure (world-pressure-2): the writer's line, the judge, the notes -----------------------------------------------------------

SENTENCE = "a part of the collision, whether or not it has anything to do with the aim or the tie to begin with"


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


def test_with_a_pressure_in_the_request_the_flow_runs_no_pressure_step_and_the_notes_still_say_pressure_on():
    request = pressed()
    good = gen.script(request, Kit(request))
    assert len(good) == 3 and len(gen.script(base(), Kit(base()))) == 3       # no reply for a pressure judge, with or without a pressure
    reply, ctx, engine = _generate_pressed(request, *good)
    assert engine.calls == 3 and [p["step"] for p in ctx.notes["passes"]] == ["write", "events", "shifts"]
    assert ctx.notes["flow"]["pressure_on"] is True and not any(k.startswith("pressure_") and k != "pressure_on" for k in ctx.notes["flow"])
    assert not any("advance_pressure" in p["step"] for p in ctx.notes["passes"]) and reply["shifts"]
    flow = gen.build_flow(request, Kit(request))
    assert flow.notes["pressure_on"] is True and "advance_pressure" not in [s.name for s in flow.worst_case()]
    plain = gen.build_flow(base(), Kit(base()))
    assert plain.notes["pressure_on"] is False and "advance_pressure" not in [s.name for s in plain.worst_case()]
