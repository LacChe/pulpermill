"""A4: the trials runner (tools/run_trials.mjs) and the summary script (tools/summarize_trials.py).

* --dry builds every plan and generate request of every trial and checks each against the contract, with no backend.
* A run against the fake backend (canned replies) and against the stub prompter on the real runner writes the chapters, summary.csv and
  meta.json, and finishes. The stub's chapters are constant text, so its machine checks flag things: that is expected.
Node is started the way tests/e2e does it."""
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "backend"))
sys.path.insert(0, str(ROOT / "tests" / "e2e"))

from server_harness import running  # noqa: E402
from stub_engine import StubEngine  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
RUNNER = ROOT / "tools" / "run_trials.mjs"
SUMMARY = ROOT / "tools" / "summarize_trials.py"
CHECKER = ROOT / "evals" / "trials" / "tools" / "check_requests.py"
KIT = ROOT / "evals" / "trials"
MANIFEST = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))


def node(*args, timeout=600):
    return subprocess.run(["node", str(RUNNER), *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def rows_of(out: Path):
    with open(out / "summary.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_dry_run_passes_for_every_trial_and_checks_every_request():
    done = node("--dry")
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"dry run passed: {len(MANIFEST)} trials" in done.stdout and "0 refused" in done.stdout
    requests = int(done.stdout.split("checked ")[1].split(" requests")[0])
    assert requests >= 2 * sum(e["chapters"] for e in MANIFEST)       # at least a plan and a generate per chapter
    assert done.stdout.count("\nok   ") + (1 if done.stdout.startswith("ok   ") else 0) == sum(e["chapters"] for e in MANIFEST)


def test_dry_run_needs_no_backend_and_writes_nothing():
    before = sorted(p.name for p in (KIT / "results").iterdir())
    assert node("--dry", "--only", "t2-quiet-orchard", "--chapters", "2").returncode == 0
    assert sorted(p.name for p in (KIT / "results").iterdir()) == before


def test_dry_run_refuses_an_unknown_trial_and_a_missing_address():
    assert node("--dry", "--only", "no-such-trial").returncode == 2
    assert node().returncode == 2


def test_the_contract_check_refuses_a_broken_request():
    bad = subprocess.run([sys.executable, str(CHECKER)], input=json.dumps([{"label": "broken", "request": {"call": "plan"}}]), capture_output=True, text=True)
    assert bad.returncode == 1 and "BAD broken" in bad.stdout
    assert subprocess.run([sys.executable, str(CHECKER)], input="[]", capture_output=True, text=True).returncode == 0


def test_a_run_against_the_fake_backend_writes_chapters_summary_and_meta(tmp_path):
    out = tmp_path / "fake"
    with running() as (base, _):          # canned replies, like `python -m pulpermill.backend --fake`
        done = node(base, "--runs", "2", "--chapters", "3", "--only", "t1-salt-coast,t4-hollow-court-zh", "--label", "fake", "--out", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    rows = rows_of(out)
    assert len(rows) == 2 * 2 * 3 and all(r["ok"] == "true" for r in rows)
    assert {r["trial"] for r in rows} == {"t1-salt-coast", "t4-hollow-court-zh"} and {r["run"] for r in rows} == {"1", "2"}
    assert {"length", "person_flag", "tense_flag", "opening_repeat", "repeated_sentences", "edge_in_shifts", "changed_empty", "shift_count", "unknown_names"} <= set(rows[0])
    assert {int(r["cast_size"]) for r in rows} <= {2, 3} and len({r["cast_size"] for r in rows}) >= 1
    reading = (out / "t1-salt-coast-run1.md").read_text(encoding="utf-8")
    assert "## Chapter 1" in reading and "## Chapter 3" in reading and "**Flags:**" in reading and "Spotlight:" in reading
    saved = json.loads((out / "t4-hollow-court-zh-run2.json").read_text(encoding="utf-8"))
    assert len(saved["project"]["chapters"]) == 3 and len(saved["project"]["summary_events"]["entries"]) == 3
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["schema_version"] == 3 and meta["runs"] == 2 and meta["chapters"] == 3 and meta["failures"] == 0


def test_a_run_against_the_stub_prompter_completes_whole_trials_and_records_the_prompter(tmp_path):
    out, log = tmp_path / "stub", tmp_path / "run.log"
    with running(config=Config(log_path=str(log), prompter="stub"), engine=StubEngine(write_seconds=0), run=None) as (base, _):
        done = node(base, "--runs", "1", "--only", "t2-quiet-orchard,t7-last-light", "--runlog", str(log), "--label", "stub", "--out", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    rows = rows_of(out)
    assert len(rows) == 5 + 5 and all(r["ok"] == "true" for r in rows), [r for r in rows if r["ok"] != "true"]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["prompter"]["name"] == "stub" and meta["prompter"]["version"]
    assert {r["prompter_name"] for r in rows} == {"stub"} and {r["prompter_version"] for r in rows} == {meta["prompter"]["version"]}
    # Each chapter was planned from the state the last one left: the stub's chapters are constant, so the machine checks flag, and the run still completes.
    assert any(r["length_flag"] == "too_short" for r in rows) and any(r["opening_repeat"] == "true" for r in rows)
    saved = json.loads((out / "t2-quiet-orchard-run1.json").read_text(encoding="utf-8"))
    assert len(saved["project"]["chapters"]) == 5 and len(saved["project"]["outline"]["beats"]) == 5
    assert "(not recorded" not in (out / "t7-last-light-run1.md").read_text(encoding="utf-8")


# ---- the summary script ------------------------------------------------------------------------------------------------
def filled_sheet(path: Path, score: int, trial="t1-salt-coast", chapters=3):
    with open(KIT / "scoring" / "chapter-scoring.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for r in rows:
            if r["trial"] == trial and r["run"] == "1" and int(r["chapter"]) <= chapters:
                for k in ("interesting", "act1_start", "act2_conflict", "act3_turn", "act4_end", "spotlight_moved", "aim_moved", "minor_roles", "style_fit"):
                    r[k] = str(score)
                r["different"] = "" if r["chapter"] == "1" else str(score)
            writer.writerow(r)


def summary(*args):
    return subprocess.run([sys.executable, str(SUMMARY), *args], cwd=ROOT, capture_output=True, text=True)


def test_the_summary_adds_up_a_sheet_and_compares_two(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    filled_sheet(a, 1)
    filled_sheet(b, 2)
    one = summary(str(a))
    assert one.returncode == 0, one.stderr
    assert "t1-salt-coast" in one.stdout and "0.50" in one.stdout        # 1 of a possible 2 on every line, and chapter 1's blank is not counted against it
    both = summary("--compare", str(a), str(b))
    assert both.returncode == 0 and "0.50" in both.stdout and "1.00" in both.stdout and "+1.00" in both.stdout


def test_the_summary_adds_the_machine_flags_and_refuses_a_bad_score(tmp_path):
    out, sheet = tmp_path / "res", tmp_path / "s.csv"
    with running() as (base, _):
        assert node(base, "--runs", "1", "--chapters", "2", "--only", "t1-salt-coast", "--out", str(out)).returncode == 0
    filled_sheet(sheet, 2, chapters=2)
    done = summary(str(sheet), "--machine", str(out))
    assert done.returncode == 0 and "length_flag=2" in done.stdout and "1.00" in done.stdout
    text = sheet.read_text(encoding="utf-8").replace(",2,2,2,2,2,2,2,2,2,", ",2,7,2,2,2,2,2,2,2,", 1)
    sheet.write_text(text, encoding="utf-8")
    assert summary(str(sheet)).returncode != 0
