"""Keeps the page's rule checks and the shared test vectors in step with the schema.
Reads web/logic.js and tests/shared/rule-vectors.json as text, so no JavaScript has to run here."""
import json, re
import pytest
from helpers import REPO, CARD_IDS as ALL_CARD_IDS, card

# The page only draws and checks the cards the writer sees. The hidden record cards are the backend's.
CARD_IDS = [cid for cid in ALL_CARD_IDS if not card(cid)[4].get("hidden")]

LOGIC = (REPO / "web" / "logic.js").read_text(encoding="utf-8")
VECTORS = json.loads((REPO / "tests" / "shared" / "rule-vectors.json").read_text(encoding="utf-8"))["cases"]


def code_rules(cid):
    return [r for r in card(cid)[3] if not r.needs_model]


def written_checks():
    return set(re.findall(r"^CHECKS\.(\w+) = ", LOGIC, re.M))


def pending_checks():
    body = re.search(r"export const PENDING_CHECKS = \[(.*?)\];", LOGIC, re.S).group(1)
    return set(re.findall(r'"(\w+)"', body))


def named_checks():
    return {r.check for cid in CARD_IDS for r in code_rules(cid)}


def test_every_named_check_is_written_or_listed_as_pending():
    missing = named_checks() - written_checks() - pending_checks()
    assert not missing, f"checks named in the schema but neither written in web/logic.js nor pending: {sorted(missing)}"


def test_the_page_has_no_check_the_schema_never_names():
    assert not written_checks() - named_checks(), sorted(written_checks() - named_checks())


@pytest.mark.parametrize("cid", CARD_IDS)
def test_vectors_point_at_real_rules_and_cover_every_code_rule(cid):
    ids = {r.id for r in card(cid)[3]}
    mine = [c for c in VECTORS if c["card"] == cid]
    assert all(c["rule"] in ids for c in mine), [c["name"] for c in mine if c["rule"] not in ids]
    for rule in code_rules(cid):
        cases = [c for c in mine if c["rule"] == rule.id]
        assert any(c["broken"] for c in cases), f"{cid}/{rule.id}: no case where it is broken"
        assert any(not c["broken"] for c in cases), f"{cid}/{rule.id}: no case where it passes"


def test_vector_names_are_unique_per_rule():
    seen = [(c["card"], c["rule"], c["name"]) for c in VECTORS]
    assert len(seen) == len(set(seen))
