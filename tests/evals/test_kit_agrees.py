"""P6b: the kit's pieces list exactly the same probes and cases, and none of the removed ideas are in it.

Sources of truth: the probe catalog (01), the probe inputs (02), the case files, the manifest, the scoring sheets and CHANGES.md
must all name the same probes and cases. The kit's documents, cases and probes must not speak of ideas the schema no longer has
(CHANGES.md is the one place retired items are named)."""
import csv
import json
import re
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[2] / "evals" / "cardfill"
MANIFEST = json.loads((KIT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))


def _probe_ids_in_catalog():
    return {m.group(1) for m in re.finditer(r"^\| ([SCWEU]\d+)(?: ★)? \|", (KIT / "01-probe-catalog.md").read_text(encoding="utf-8"), re.M)}


def _probe_ids_in_inputs():
    return {m.group(1) for m in re.finditer(r"^### ([SCWEU]\d+) ·", (KIT / "02-probe-inputs.md").read_text(encoding="utf-8"), re.M)}


def _case_numbers():
    return {int(re.search(r"case-(\d+)", p.name).group(1)) for p in KIT.glob("case-*.md")}


def _sheet(name):
    with open(KIT / "scoring" / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_catalog_inputs_and_manifest_list_the_same_probes():
    in_manifest = {e["probe"] for e in MANIFEST if e["kind"] == "probe"}
    assert _probe_ids_in_catalog() == _probe_ids_in_inputs() == in_manifest
    assert len(in_manifest) == 26


def test_cases_and_manifest_list_the_same_cases():
    in_manifest = {int(e["id"].split("-")[1]) for e in MANIFEST if e["kind"] == "case"}
    assert _case_numbers() == in_manifest == set(range(1, 13))


def test_scoring_sheets_list_the_same_probes_and_cases():
    probes = _sheet("probe-scoring.csv")
    assert {r["probe"] for r in probes} == _probe_ids_in_catalog()
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


def test_changes_names_every_probe_and_case_once():
    text = (KIT / "CHANGES.md").read_text(encoding="utf-8")
    rows = [l for l in text.splitlines() if l.startswith("|")]
    status = {}
    for line in rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if re.fullmatch(r"([SCWEU]\d+|case-\d+)", cells[0]):
            assert cells[0] not in status, f"{cells[0]} appears twice in CHANGES.md"
            status[cells[0]] = cells[1].lower()
            assert cells[1].lower() in {"kept", "revised", "retired", "new"}, line
            assert cells[2], f"no reason for {cells[0]}"
    live = _probe_ids_in_catalog() | {f"case-{n}" for n in _case_numbers()}
    retired = {k for k, v in status.items() if v == "retired"}
    assert live == set(status) - retired, "CHANGES.md and the live probes and cases disagree"
    assert len(retired) == 7 and not retired & live
    assert sum(v == "new" for v in status.values()) <= 6


def test_no_new_probe_reuses_a_retired_id():
    assert not {"W3", "W4", "E5", "E6", "E7", "U1", "U4"} & _probe_ids_in_catalog()


# The ideas the schema no longer has. Words only: the kit's prose must not use them (CHANGES.md may, to name what was retired).
REMOVED = [r"pressure", r"knowledge", r"stakes", r"offstage", r"\bplants?\b", r"\breveals?\b", r"\bgoals?\b", r"\bmyth\b",
           r"\bhidden\b", r"false_belief", r"uncommon", r"rule status"]
KIT_TEXT = [p for p in sorted(KIT.glob("*.md")) + sorted((KIT / "upstream").glob("*.md")) + sorted((KIT / "fixtures").glob("*.md"))
            if p.name != "CHANGES.md"]


@pytest.mark.parametrize("path", KIT_TEXT, ids=lambda p: p.name)
def test_documents_cases_and_probes_have_none_of_the_removed_ideas(path):
    text = path.read_text(encoding="utf-8")
    if path.name.startswith("case-") and "chapter" in path.name:
        text = text.split("## Card notes")[1] if "## Card notes" in text else ""      # chapters are story prose, not kit vocabulary
    for pattern in REMOVED:
        found = re.findall(pattern, text, flags=re.I)
        assert not found, f"{path.name} mentions a removed idea: {found[:3]}"


def test_scoring_sheets_and_fixtures_have_none_of_the_removed_ideas():
    for path in [*(KIT / "scoring").glob("*.csv"), *(KIT / "fixtures" / "projects").glob("*.json")]:
        text = path.read_text(encoding="utf-8-sig")
        for pattern in (r"pressure", r"knowledge", r"stakes", r"\bmyth\b", r"false_belief"):
            assert not re.search(pattern, text, flags=re.I), f"{path.name}: {pattern}"
