"""B2, the fill call: what each card's prompt holds in every input mode, the squeeze, the check, the targeted guidance for the Tier 1 probes,
and the whole call through the real server and runner on a scripted fake engine (no model)."""
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
sys.path.insert(0, str(ROOT / "tests" / "backend"))

from pulpermill import contract  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter import load_prompter  # noqa: E402
from pulpermill.prompter.mill import common, fill  # noqa: E402
from pulpermill.prompts import budget, textfiles as tx, tokens  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
FILLS = [v for v in VECTORS if v["valid"] and v["data"]["call"] == "fill"]
CARDS = ["style", "characters", "world", "entanglements", "setup"]
CHAPTER = (ROOT / "evals/cardfill/case-12-long-chapter.md").read_text()

CHARS = [{"id": "c0000001", "name": "Imre", "sex": "male", "wants": [{"id": "w1", "text": "to be taken seriously"}], "fear": "being ordinary"},
         {"id": "c0000002", "name": "Teodora"}]
WORLD = {"name": "Tern Station", "places": [{"id": "p0000001", "name": "Dock 9", "description": "A cold dock.", "effect": "Nobody stays."}],
         "objects": [{"id": "o0000001", "name": "The Lattice", "description": "A drone.", "significance": "Proves debts."}],
         "powers": [{"id": "g0000001", "name": "The Authority", "nature": "Station government", "hold": "Law", "felt": "A tax on the air."}]}
TIES = {"ties": [{"id": "t0000001", "tie_from": "c0000002", "tie_to": "c0000001", "bond": "mentor", "edge": "to keep him safe"}], "holdings": []}
RELATED = {"style": {}, "characters": {}, "world": {"characters": CHARS},
           "entanglements": {"characters": CHARS, "world": WORLD},
           "setup": {"style": {"person": "first", "tense": "past"}, "characters": CHARS, "world": WORLD, "entanglements": TIES}}
VALUES = {"style": {}, "characters": {"id": "c0000009", "name": "Dana"}, "world": {}, "entanglements": {"ties": [], "holdings": []}, "setup": {"protagonist": None}}
NOTE = "Imre is the lead. The Authority posts a notice closing Dock 9. Make it nine chapters."


def req(card="setup", note=NOTE, chapter=None, **over) -> dict:
    r = {"call": "fill", "schema_version": 3, "language": "en", "card": card, "instance": "c0000009" if card == "characters" else None, "note": note,
         "example_chapter": chapter, "values": copy.deepcopy(VALUES[card]), "related": copy.deepcopy(RELATED[card])}
    r.update(over)
    return r


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


def prompt(request, factor=1.0) -> str:
    return fill.build_prompt(request, Kit(request), factor)


def raw_option_pair(text: str) -> str | None:
    """A `field: option` or `field=option` pair for any option field of any card (a structured label reaching the model as such)."""
    for card in CARDS:
        for key, field in tx.schema_text(card)["fields"].items():
            options = field.get("options") or {}
            for option in (options or {}):
                if re.search(rf"\b{re.escape(key)}\s*[:=]\s*\"?{re.escape(option)}\b", text):
                    return f"{key}: {option}"
    return None


MODES = {"note": dict(note=NOTE), "chapter": dict(note=None, chapter="Imre closed the ledger. The Authority had posted its notice on Dock 9."),
         "both": dict(note=NOTE, chapter="Imre closed the ledger. The Authority had posted its notice on Dock 9.")}


# ---- the prompt in every card and mode ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", list(MODES))
@pytest.mark.parametrize("card", CARDS)
def test_every_card_and_input_mode_builds_a_prompt_with_no_ids_and_no_raw_option_keys(card, mode):
    request = req(card, **MODES[mode])
    request["related"]["style"] = {"person": "first", "tense": "past", "humor": "dry", "dialogue": "sparse"} if card == "setup" else request["related"].get("style")
    text = prompt(request)
    for ident in ids_in(request):
        assert ident not in text, ident
    assert raw_option_pair(text) is None, raw_option_pair(text)
    assert "sparse" not in text.split("What each field holds")[0]
    assert text.startswith("You help a writer fill in one card") and "JSON object" in text


def test_the_input_modes_say_what_to_do_with_a_note_a_chapter_or_both():
    note, chapter, both = (prompt(req("world", **MODES[m])) for m in ("note", "chapter", "both"))
    assert "The writer's note:" in note and "The example chapter:" not in note and "Use it exactly as the writer meant it" in note
    assert "The example chapter:" in chapter and "The writer's note:" not in chapter and "work out what this card holds" in chapter
    assert "The writer's note:" in both and "The example chapter:" in both and "The note decides" in both
    assert len({note, chapter, both}) == 3


@pytest.mark.parametrize("language,name", [("zh-Hans", "Simplified Chinese"), ("zh", "Simplified Chinese"), ("fr", "French"), ("xx", "xx")])
def test_the_story_language_is_named_and_names_are_kept(language, name):
    text = prompt(req("characters", language=language, note="沈青岚，二十八岁，女。"))
    assert f"in {name}" in text and "Keep names exactly as the writer spelled them" in text and "沈青岚，二十八岁，女。" in text


def test_the_current_values_stay_and_an_empty_card_says_so():
    empty = prompt(req("world"))
    assert "The card is still empty." in empty and "leave those fields out" not in empty
    filled = prompt(req("world", values={"name": "Tern Station", "everyday_life": "Air is rationed and taxed."}))
    assert "leave those fields out of your reply" in filled and "Air is rationed and taxed." in filled and "The card is still empty." not in filled
    setup = prompt(req("setup", values={"protagonist": "c0000001", "normal": "He dives at dawn.", "chapter_count": 7}))
    assert "The protagonist is Imre." in setup and "The normal: He dives at dawn." in setup and "The story runs for 7 chapters." in setup


def test_the_cards_a_card_reads_are_shown_as_prose_and_the_link_names_are_listed():
    entanglements = prompt(req("entanglements", note="Teodora mentors Imre; the Authority holds Dock 9."))
    for needed in ("Imre (he/him)", "Dock 9", "The Lattice", "The Authority", "People: Imre, Teodora.", "Groups: The Authority.", "Places: Dock 9.", "Things: The Lattice."):
        assert needed in entanglements, needed
    setup = prompt(req("setup"))
    assert "People: Imre, Teodora." in setup and "Groups:" not in setup and "Teodora toward Imre" in setup
    assert "Link only to these names" not in prompt(req("world"))


def test_every_field_the_grammar_offers_has_a_meaning_sentence_and_nothing_is_orphaned():
    wording = common.load_text("fill")["fields"]
    for card in CARDS:
        offered = list(Kit(req(card)).grammar.fill()["properties"])
        assert set(offered) == set(wording[card]), card
        text = fill.field_guidance(card, offered)
        for key in offered:
            assert f"\n{key}: " in "\n" + text or text.startswith(f"What each field holds:\n\n{key}: "), (card, key)


def test_a_choice_shows_its_answer_words_each_with_its_own_sentence_and_the_examples_are_marked_as_kind_only():
    style = fill.field_guidance("style", list(common.load_text("fill")["fields"]["style"]))
    assert "\"first\": Narrate in the first person" in style and "\"third\": Narrate in the third person" in style
    sex = fill.field_guidance("characters", ["sex"])
    assert "\"female\": the person is a woman" in sex.lower() and "{name}" not in sex
    assert "never reuse their wording" in style
    assert "Text like “a story about debt” is not yet right" in style


# ---- the scope rules and the Tier 1 probes ---------------------------------------------------------------------------------------

SCOPE = {
    "style": "holds no name of any person, place or thing, and no event",
    "characters": "The card names no other person, place or object and no relationship",
    "world": "The card names no character and never says who holds, knows or wants something",
    "entanglements": "Create no new person, group, place, thing or rule, in any field and in any free text",
    "setup": "The protagonist is one of the existing characters; create no new person, place or thing, and write no plan and no ending",
}


@pytest.mark.parametrize("card", CARDS)
def test_the_scope_rule_is_in_the_prompt_of_the_card_it_applies_to(card):
    assert SCOPE[card] in prompt(req(card))
    for other in CARDS:
        if other != card:
            assert SCOPE[other] not in prompt(req(card))


# Each Tier 1 probe and the sentence of the wording that targets its tempting input.
TIER1 = [
    ("S3", "style", "describe the voice itself and leave the name out"),
    ("S4", "style", "Person and tense are rules for every chapter. Read them from the narration of the example chapter"),
    ("C1", "characters", "A want is a broad desire"),
    ("C1", "characters", "so no want names one"),
    ("C4", "characters", "Fear, flaw, vulnerability and values say four different things"),
    ("C8", "characters", "Copy every stated fact exactly"),
    ("E1", "entanglements", "Ownership and control are holdings, never ties"),
    ("E2", "entanglements", "make no tie or holding for it and do not invent it"),
    ("E4", "entanglements", "Every tie has a bond and an edge, and they differ"),
    ("E8", "entanglements", "A tie points from the person whose driver the edge is"),
    ("E9", "entanglements", "a place or a thing is never an end of a tie, and no bond says that someone owns something"),
    ("U3", "setup", "It contains no ending, no outcome and no plan"),
    ("U6", "setup", "Do not restate the character card"),
    ("U7", "setup", "chapter_count is exactly that number"),
]


@pytest.mark.parametrize("probe,card,sentence", TIER1, ids=[f"{p}-{s[:24]}" for p, _, s in TIER1])
def test_each_tier_1_probe_has_a_sentence_in_the_prompt_that_targets_its_tempting_input(probe, card, sentence):
    assert sentence in prompt(req(card))


def test_the_object_has_no_owner_rule_is_in_the_world_prompt():
    text = prompt(req("world"))
    assert "keep the barge and leave the owner and the location out" in text and "they are written later as holdings" in text
    assert "what the group is planning or about to do" in text and "naming no individual" in text


def test_the_probe_texts_themselves_are_not_in_the_wording():
    wording = json.dumps(common.load_text("fill"))
    for probe_text in ("Dana Whitlock", "Teodora owns the Lattice", "Walt owns the Lantern Bar", "Ines was hired by Walt", "King Aldric", "Mira Solenne",
                       "pass Mr. Hale", "Dockhands' Brotherhood", "life was dull and lonely", "things are getting tense", "Make it nine chapters"):
        assert probe_text not in wording, probe_text


# ---- the squeeze ---------------------------------------------------------------------------------------------------------------

def big() -> dict:
    related = copy.deepcopy(RELATED["setup"])
    related["world"]["places"] = [{"id": f"p{n:07d}", "name": f"Place {n}", "description": "A long description. " * 60, "effect": "An effect. " * 60} for n in range(1, 10)]
    related["characters"] = [{"id": f"c{n:07d}", "name": f"Person {n}", "fear": "A fear. " * 40, "flaw": "A flaw. " * 40} for n in range(1, 8)]
    return req("setup", chapter=CHAPTER, related=related)


def test_every_squeeze_factor_keeps_the_note_the_guidance_and_the_fields_and_only_shrinks():
    request = big()
    texts = {f: prompt(request, f) for f in budget.SQUEEZES}
    sizes = [len(texts[f]) for f in budget.SQUEEZES]
    assert sizes == sorted(sizes, reverse=True) and sizes[0] > sizes[-1]
    for f, text in texts.items():
        assert NOTE in text and "The disruption is one event" in text and "What each field holds:" in text and "JSON object" in text
        assert "Opening of the chapter" in CHAPTER or CHAPTER.split()[0] in text           # the chapter's opening stays
        assert CHAPTER.split()[-1] in text                                                  # and so does its end, where late facts sit


@pytest.mark.skipif(not tokens.available(), reason="the tokenizer files are not installed")
@pytest.mark.parametrize("card", CARDS)
def test_a_long_chapter_with_large_related_cards_fits_the_context_at_some_squeeze(card):
    request = big()
    request.update(card=card, instance="c0000009" if card == "characters" else None, values=copy.deepcopy(VALUES[card]))
    kit = Kit(request)
    flow = fill.build_flow(request, kit)
    made, factor, measures = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in flow.worst_case()])
    assert all(m.ok for m in measures) and flow.worst_case()[0].max_output == fill.MAX_OUTPUT


# ---- the check -------------------------------------------------------------------------------------------------------------------

def good(card, request=None) -> dict:
    request = request or req(card)
    return json.loads(fill.script(request, Kit(request))[0])


@pytest.mark.parametrize("card", CARDS)
def test_the_check_accepts_the_scripted_reply_for_every_card(card):
    request = req(card)
    assert fill.fill_problem(request, good(card, request)) is None


def problem(card, value, **over):
    return fill.fill_problem(req(card, **over), value)


def test_the_check_refuses_what_the_grammar_cannot_see():
    assert "JSON object" in problem("world", ["x"])
    assert "stand-in" in problem("world", {"name": "TBD"})
    assert "stand-in" in problem("characters", {"sketch": "N/A"})
    assert problem("style", {"humor": "none", "edge": "clean"}) is None                       # an answer word such as none is a choice
    assert "Fill in the card" in problem("world", {})
    assert problem("entanglements", {}) is None                                                # nothing upstream can fill ties: empty is fine
    assert problem("world", {}, values={"name": "Tern Station"}) is None                       # already filled: nothing to add
    assert "world card must name no character" in problem("world", {"history": "Imre left the station in a famine."})
    assert "at least two wants" in problem("characters", {"wants": [{"text": "to be left alone"}]})
    assert problem("characters", {"wants": [{"text": "to be left alone"}]}, values={"id": "c0000009", "wants": [{"text": "to win"}]}) is None


def test_the_check_refuses_ties_and_holdings_that_break_the_scope_or_the_split_between_them():
    tie = lambda **kw: {"ties": [{"tie_from": "Teodora", "tie_to": "Imre", "bond": "mentor since the fire", "edge": "to keep him safe", **kw}]}
    assert problem("entanglements", tie()) is None
    assert "not one of the names" in problem("entanglements", tie(tie_to="The Brotherhood"))
    assert "two different" in problem("entanglements", tie(tie_to="Teodora"))
    assert "different things" in problem("entanglements", tie(bond="to keep him safe."))
    assert "Ownership is a holding" in problem("entanglements", tie(bond="owner of his debt"))
    assert "Ownership is a holding" in problem("entanglements", tie(bond="belongs to her"))
    assert problem("entanglements", {"holdings": [{"holdee": "The Lattice", "held_by": "Teodora"}]}) is None
    assert problem("entanglements", {"holdings": [{"holdee": "The Lattice", "held_by": "Dock 9"}]}) is None          # a thing may be held by a place
    assert "not one of the names" in problem("entanglements", {"holdings": [{"holdee": "The Lantern Bar", "held_by": "Teodora"}]})
    assert "cannot be held by" in problem("entanglements", {"holdings": [{"holdee": "Dock 9", "held_by": "Dock 9"}]})


def test_the_check_keeps_a_stated_chapter_count_and_links_the_protagonist_to_a_character():
    assert problem("setup", {"chapter_count": 9, "protagonist": "Imre"}) is None
    assert "nine" not in (problem("setup", {"chapter_count": 6}) or "") and "chapter_count is 9" in problem("setup", {"chapter_count": 6})
    assert "Set chapter_count to 9" in problem("setup", {"normal": "He dives at dawn."})
    assert problem("setup", {"normal": "He dives at dawn."}, note="Imre is the lead.") is None
    assert "not one of the names" in problem("setup", {"protagonist": "Maren Holt"})


@pytest.mark.parametrize("note,count", [("Make it nine chapters", 9), ("6 chaps", 6), ("a 12 chapter saga", 12), ("六章", None), ("共6章", 6), ("Make it Seven Chapters.", 7),
                                        ("The chapter opens at dusk", None), ("", None)])
def test_a_stated_chapter_count_is_found(note, count):
    assert fill.stated_chapter_count(note) == count


def test_the_step_is_one_json_step_with_the_fill_grammar_and_the_check_on_it():
    request = req("world")
    kit = Kit(request)
    flow = fill.build_flow(request, kit)
    step = flow.next([])
    assert step.name == "fill" and step.kind == "json" and step.grammar == kit.grammar.fill() and step.sampling == "structured" and step.language
    assert flow.next([{}]) is None and flow.reply([{"name": "X"}]) == {"values": {"name": "X"}}
    assert step.check({"name": "TBD"}) and step.check({"name": "Tern Station"}) is None
    assert budget.input_limit(step.max_output) > 10000


# ---- the whole call -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("vector", FILLS, ids=lambda v: v["name"])
def test_every_fill_vector_is_answered_through_the_real_server_on_the_mill_prompter(vector):
    request = vector["data"]
    engine = FakeEngine()
    engine.script(*fill.script(request, Kit(request)))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        response = post(base_url, request)
        body = response.json()
        assert response.status_code == 200 and body["ok"] is True, body
        assert contract.parse_reply("fill", body).values
        assert wait_idle(base_url)
    assert engine.calls == 1 and engine.prompts[0].startswith("You help a writer fill in one card")


def test_a_reply_that_fails_the_check_is_asked_for_again_with_the_line_and_then_used():
    request = req("setup")
    kit = Kit(request)
    engine = FakeEngine()
    engine.script(json.dumps({"normal": "TBD", "chapter_count": 9}), fill.script(request, kit)[0])
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        assert post(base_url, request).status_code == 200
        assert wait_idle(base_url)
    assert engine.calls == 2 and "stand-in" in engine.prompts[1] and "Your previous reply could not be used" in engine.prompts[1]


def test_the_version_follows_the_wording():
    assert "+fill:fill-1:" in load_prompter("mill").version
