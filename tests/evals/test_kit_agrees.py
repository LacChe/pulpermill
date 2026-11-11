"""The retained card-fill fixtures, manifest, and scoring sheets agree.

The former probe catalog, probe-inputs document, and change log were development
documentation and are no longer part of the evaluation kit. The generated
manifest and scoring sheets now provide the retained machine-readable index."""
import csv
import json
import re
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[2] / "evals" / "cardfill"
MANIFEST = json.loads((KIT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))


def _probe_ids_in_manifest():
    return {e["probe"] for e in MANIFEST if e["kind"] == "probe"}


def _case_numbers():
    return {int(re.search(r"case-(\d+)", p.name).group(1)) for p in KIT.glob("case-*.md")}


def _sheet(name):
    with open(KIT / "scoring" / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_catalog_inputs_and_manifest_list_the_same_probes():
    in_manifest = {e["probe"] for e in MANIFEST if e["kind"] == "probe"}
    assert _probe_ids_in_manifest() == in_manifest
    assert len(in_manifest) == 26


def test_cases_and_manifest_list_the_same_cases():
    in_manifest = {int(e["id"].split("-")[1]) for e in MANIFEST if e["kind"] == "case"}
    assert _case_numbers() == in_manifest == set(range(1, 13))


def test_scoring_sheets_list_the_same_probes_and_cases():
    probes = _sheet("probe-scoring.csv")
    assert {r["probe"] for r in probes} == _probe_ids_in_manifest()
    fixtures = {e["id"] for e in MANIFEST if e["kind"] == "probe"}
    assert {r["fixture"] for r in probes} == fixtures
    assert len(probes) == 3 * len(fixtures)
    cases = _sheet("case-scoring.csv")
    assert {r["case"] for r in cases} == {e["id"] for e in MANIFEST if e["kind"] == "case"}
    assert len(cases) == 3 * 12


def test_every_probe_has_a_tier_and_a_row_for_each_input():
    tiers = {r["probe"]: r["tier"] for r in _sheet("probe-scoring.csv")}
    assert set(tiers.values()) == {"1", "2"}
    assert all(r["tier"] in {"1", "2"} for r in _sheet("probe-scoring.csv"))


def test_scoring_sheets_and_fixtures_have_none_of_the_removed_ideas():
    for path in [*(KIT / "scoring").glob("*.csv"), *(KIT / "fixtures" / "projects").glob("*.json")]:
        text = path.read_text(encoding="utf-8-sig")
        for pattern in (r"pressure", r"knowledge", r"stakes", r"\bmyth\b", r"false_belief"):
            assert not re.search(pattern, text, flags=re.I), f"{path.name}: {pattern}"
