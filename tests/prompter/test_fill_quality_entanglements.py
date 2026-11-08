"""Step 3d: the Entanglements fill derives ties and holdings from the cards, not only the note: who wants what is attributed to the right end, an edge is an
aim a chapter can reach, lose or change, and every person gets at least two ties. The first group reads the wording file alone; the second builds the prompt."""
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORDING = yaml.safe_load((ROOT / "pulpermill/prompter/mill/text/en/fill.yaml").read_text(encoding="utf-8"))
SCHEMA = yaml.safe_load((ROOT / "pulpermill/schema/text/en/entanglements.yaml").read_text(encoding="utf-8"))
FIELDS, ITEMS, CARD = WORDING["fields"]["entanglements"], WORDING["item_fields"]["entanglements"], WORDING["cards"]["entanglements"]
CARD_TEXT = " ".join([CARD["intro"], CARD["scope"], *CARD["specific"]])
ALL = " ".join([CARD_TEXT, *FIELDS.values(), *ITEMS["ties"].values(), *ITEMS["holdings"].values()])
LEAVE_OUT = ["nothing to say", "something to say", "is left out", "stays empty", "stay empty", "leave those fields out", "leave it out"]


def test_every_entanglements_field_and_item_field_keeps_a_meaning_sentence():
    assert set(FIELDS) == {"ties", "holdings"}
    assert set(ITEMS["ties"]) == {"tie_from", "tie_to", "bond", "edge"} and set(ITEMS["holdings"]) == {"holdee", "held_by"}
    assert all(len(v) > 20 for v in [*ITEMS["ties"].values(), *ITEMS["holdings"].values(), *FIELDS.values()])


def test_the_card_says_what_it_is_for_and_that_every_field_is_filled():
    assert "one tie per chapter and test the protagonist's aim against it" in CARD_TEXT
    assert "reach, lose or change" in CARD_TEXT and "Every field is filled" in CARD_TEXT
    assert "one tie per chapter" in FIELDS["ties"]


def test_the_card_derives_ties_and_holdings_from_the_cards_and_not_only_the_note():
    assert "Write every tie and holding the note states, then add the ones the cards imply" in CARD_TEXT
    assert "Every person has at least two ties, counting either end" in CARD_TEXT and "at least two ties" in FIELDS["ties"]
    assert "Every group on the World card appears in a tie" in CARD_TEXT and "what the group wants from that person" in CARD_TEXT
    assert "Link only the names listed" in CARD_TEXT


def test_direction_follows_the_note_and_two_wants_make_two_ties():
    assert "A tie points from the person whose driver the edge is" in CARD_TEXT
    assert "the person the note says wants something is the from end of the tie whose edge is that want" in CARD_TEXT
    assert "write two ties, one from each end, each with its own edge" in CARD_TEXT and "The same want is never written twice" in CARD_TEXT
    assert "never written twice from both ends" not in ALL and "The same tie is never written twice" not in ALL
    assert "which is the one the note says wants it" in ITEMS["ties"]["tie_from"]


def test_an_edge_is_an_aim_a_chapter_can_reach_lose_or_change_and_carries_the_stated_stake():
    edge = ITEMS["ties"]["edge"]
    assert edge.startswith("What the from end wants in this tie") and "can reach, lose or change" in edge and "differs from the bond" in edge
    assert "When the note states a stake, what happens if the aim is not met, the edge carries it" in edge
    assert "built from the people's cards" in CARD_TEXT and "want, fear, flaw or vulnerability" in CARD_TEXT
    assert "pull against one another" in CARD_TEXT and "cannot all be had" in CARD_TEXT


def test_a_bond_is_specific_to_the_pair_and_reads_from_the_from_end():
    bond = ITEMS["ties"]["bond"]
    assert "reads from the from end" in bond and "what the from end is to the to end" in bond and "specific to this pair" in bond
    assert "never a general statement about their roles" in bond and "clause of shared past when the note or the cards give one" in bond
    assert "specific to the pair" in CARD_TEXT


def test_holdings_follow_the_cards_and_the_allowed_pairs_stay():
    assert "whenever the cards show one" in CARD_TEXT and "a group whose hold is control of it" in CARD_TEXT
    assert "A thing with no plausible holder gets no holding" in CARD_TEXT
    assert "Things may be held by people, groups or places; places by people or groups" in CARD_TEXT
    assert "whenever the cards show one" in FIELDS["holdings"]


def test_the_pinned_entanglements_sentences_stay():
    for sentence in ("Ownership and control are holdings, never ties", "make no tie or holding for it and do not invent it", "Every tie has a bond and an edge, and they differ",
                     "A tie points from the person whose driver the edge is", "a place or a thing is never an end of a tie, and no bond says that someone owns something",
                     "Create no new person, group, place, thing or rule, in any field and in any free text"):
        assert sentence in CARD_TEXT, sentence


def test_nothing_in_the_entanglements_wording_lets_a_field_stay_out():
    for phrase in LEAVE_OUT:
        assert phrase not in ALL.lower(), phrase


def test_the_entanglements_wording_has_no_sample_value_and_no_story_word():
    text = ALL.lower()
    samples = []
    for field in SCHEMA["fields"].values():
        samples += (field.get("examples") or {}).get("good", []) + (field.get("examples") or {}).get("avoid", [])
        for item in (field.get("item_fields") or {}).values():
            samples += (item.get("examples") or {}).get("good", []) + (item.get("examples") or {}).get("avoid", [])
    assert samples
    for sample in samples:
        assert sample.lower() not in text, sample
    assert not re.search(r"\bmother\b", text)
    for word in "bakery baker bread oven dough applewood apple fog weather pim orla corbin thimble hollow loafcast".split():
        assert not re.search(rf"\b{word}\b", text), word


def _build():
    pytest.importorskip("starlette"); pytest.importorskip("uvicorn"); pytest.importorskip("requests")
    sys.path.insert(0, str(Path(__file__).parent))
    import test_fill_wording as w
    return w


@pytest.mark.parametrize("mode", ["note", "chapter", "both"])
def test_the_entanglements_prompt_carries_the_new_wording_and_the_pinned_sentences(mode):
    w = _build()
    text = w.prompt(w.req("entanglements", **w.MODES[mode]))
    for needed in (FIELDS["ties"], FIELDS["holdings"], ITEMS["ties"]["edge"], ITEMS["ties"]["bond"], w.SCOPE["entanglements"], "The same want is never written twice",
                   "Every person has at least two ties, counting either end", "A tie points from the person whose driver the edge is", "What the from end wants in this tie"):
        assert needed in text, needed[:40]
    assert "mother" not in text and "never written twice from both ends" not in text
    for phrase in LEAVE_OUT:
        assert phrase not in text.lower(), phrase
