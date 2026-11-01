"""A4: the chapter-trials kit (evals/trials).

The stories, the projects built from them, the manifest, the scoring sheet and the README agree; every trial is a valid project under
schema version 3 that the page's start gate accepts; the kit covers what the brief asks (6 to 8 trials, different genres, tones, cast
sizes of 2 to 5, first and last chapters, a protagonist with and without ties, one Simplified Chinese story)."""
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "evals" / "trials"
sys.path.insert(0, str(ROOT))
from pulpermill.schema.project import Project, SCHEMA_VERSION  # noqa: E402
from test_fixtures_valid import unknown_keys  # noqa: E402

MANIFEST = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))
BY_ID = {e["id"]: e for e in MANIFEST}
PROJECTS = sorted((KIT / "projects").glob("*.json"))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---- the pieces agree ------------------------------------------------------------------------------------------------
def test_stories_projects_and_manifest_list_the_same_trials():
    stories = {p.stem for p in (KIT / "stories").glob("*.yaml")}
    assert stories == {p.stem for p in PROJECTS} == set(BY_ID)
    assert len(BY_ID) == len(MANIFEST) and 6 <= len(MANIFEST) <= 8


def test_the_projects_and_the_sheet_are_what_the_stories_and_manifest_give():
    for tool in ("make_projects.py", "make_scoring.py"):
        done = subprocess.run([sys.executable, str(KIT / "tools" / tool), "--check"], capture_output=True, text=True)
        assert done.returncode == 0, f"{tool}: {done.stdout} (run it without --check)"


def test_the_sheet_has_one_row_per_trial_run_and_chapter():
    with open(KIT / "scoring" / "chapter-scoring.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    expected = {(e["id"], str(r), str(c)) for e in MANIFEST for r in (1, 2, 3) for c in range(1, e["chapters"] + 1)}
    assert {(r["trial"], r["run"], r["chapter"]) for r in rows} == expected and len(rows) == len(expected)
    rubric = (KIT / "rubric.md").read_text(encoding="utf-8")
    for column in ("interesting", "act1_start", "act2_conflict", "act3_turn", "act4_end", "spotlight_moved", "aim_moved", "minor_roles", "style_fit", "different"):
        assert column in rows[0] and f"`{column}`" in rubric


def test_the_readme_names_every_trial_and_every_file():
    readme = (KIT / "README.md").read_text(encoding="utf-8")
    for e in MANIFEST:
        assert e["id"] in readme, e["id"]
    for name in ("rubric.md", "manifest.json", "make_projects.py", "make_scoring.py", "run_trials.mjs", "summarize_trials.py", "trial_checks.mjs"):
        assert name in readme, name
    assert not re.search(r"\bgoal\b|\bstakes\b", readme)


# ---- every trial is a valid project ----------------------------------------------------------------------------------
@pytest.mark.parametrize("path", PROJECTS, ids=lambda p: p.stem)
def test_trial_is_a_valid_project_under_schema_version_3(path):
    data = load(path)
    assert unknown_keys(Project, data) == []
    Project.model_validate(data)
    assert data["schema_version"] == SCHEMA_VERSION == 3
    assert data["chapters"] == [] and data["outline"]["beats"] == [] and data["summary_events"]["entries"] == [] and data["shifts"]["entries"] == []
    assert 5 <= data["setup"]["chapter_count"] <= 10
    assert data["output_language"] in ("en", "zh")


@pytest.mark.parametrize("path", PROJECTS, ids=lambda p: p.stem)
def test_trial_links_resolve_and_the_story_is_playable(path):
    data = load(path)
    people = {c["id"]: c for c in data["characters"]}
    world = data["world"]
    powers = {x["id"] for x in world["powers"]}
    holdable = {x["id"] for k in ("objects", "places") for x in world[k]}
    assert data["setup"]["protagonist"] in people and 2 <= len(people) <= 5
    for t in data["entanglements"]["ties"]:
        assert {t["tie_from"], t["tie_to"]} <= set(people) | powers and t["tie_from"] != t["tie_to"]
        assert t["bond"].strip() and t["edge"].strip()
    for h in data["entanglements"]["holdings"]:
        assert h["holdee"] in holdable and h["held_by"] in set(people) | powers | {x["id"] for x in world["places"]}
    # The page's spotlight pick needs at least one tie between people; the cast needs the protagonist and both ends to fit in 5.
    between = [t for t in data["entanglements"]["ties"] if t["tie_from"] in people and t["tie_to"] in people]
    assert between or any(t["tie_from"] in people or t["tie_to"] in people for t in data["entanglements"]["ties"])
    ids = [x["id"] for x in [*people.values(), *data["entanglements"]["ties"], *data["entanglements"]["holdings"], *world["places"], *world["objects"], *world["powers"]]]
    assert len(ids) == len(set(ids)), "an id appears twice"
    assert all(re.fullmatch(r"[0-9a-f]{8}", i) for i in ids)


def test_the_manifest_says_what_each_trial_is():
    for e in MANIFEST:
        project = load(KIT / "projects" / f"{e['id']}.json")
        assert e["chapters"] == project["setup"]["chapter_count"] and e["characters"] == len(project["characters"])
        assert e["language"] == project["output_language"] and e["person"] == project["style"]["person"] and e["tense"] == project["style"]["tense"]
        assert e["tests"] and all(isinstance(x, str) and x.strip() for x in e["tests"])
        assert e["read"] and all(1 <= n <= e["chapters"] for n in e["read"]) and 1 in e["read"] and e["chapters"] in e["read"]


def test_the_kit_covers_what_it_is_meant_to_cover():
    assert sorted({e["language"] for e in MANIFEST}) == ["en", "zh"] and sum(e["language"] == "zh" for e in MANIFEST) == 1
    assert {e["characters"] for e in MANIFEST} >= {2, 3, 5}
    assert len({e["genre"] for e in MANIFEST}) == len(MANIFEST)
    assert {e["person"] for e in MANIFEST} == {"first", "third"} and {e["tense"] for e in MANIFEST} == {"past", "present"}
    assert any(e["protagonist_has_ties"] for e in MANIFEST) and any(not e["protagonist_has_ties"] for e in MANIFEST)
    assert any(e["ties_to_groups"] for e in MANIFEST)
    assert min(e["chapters"] for e in MANIFEST) == 5 and max(e["chapters"] for e in MANIFEST) == 10


def test_the_chinese_story_is_in_chinese():
    zh = next(e for e in MANIFEST if e["language"] == "zh")
    data = load(KIT / "projects" / f"{zh['id']}.json")
    def values(node):
        if isinstance(node, dict):
            return [v for k, x in node.items() if k != "id" for v in values(x)]
        return [v for x in node for v in values(x)] if isinstance(node, list) else [str(node)]
    text = " ".join(values([data["setup"], data["characters"], data["world"], data["entanglements"]]))
    text = re.sub(r"\b(first|third|past|present|female|male|other)\b", "", text)          # option values are not prose
    han = len(re.findall(r"[一-鿿]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    assert han > 10 * latin


def test_the_stories_do_not_speak_of_removed_ideas():
    for p in (KIT / "stories").glob("*.yaml"):
        story = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert set(story["setup"]) == {"protagonist", "normal", "disruption", "chapter_count"}, p.name


def test_results_stay_out_of_git():
    assert (KIT / "results" / ".gitignore").read_text(encoding="utf-8").split() == ["*", "!.gitignore"]


# ---- the machine checks (a node test, run here so the suite covers it) --------------------------------------------------
@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_machine_checks_pass_their_own_node_tests():
    done = subprocess.run(["node", "--test", str(ROOT / "tests" / "evals" / "trial_checks.test.mjs")], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
