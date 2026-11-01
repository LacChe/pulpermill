"""P6b: the kit's runner (tools/run_cardfill.mjs).

* --dry builds every request the kit would send (fills and judges) and checks each against the contract, with no backend.
* A run against the fake backend (canned replies) and against the stub prompter on the real runner writes results, summary.csv and meta.json.
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
RUNNER = ROOT / "tools" / "run_cardfill.mjs"
CHECKER = ROOT / "evals" / "cardfill" / "tools" / "check_requests.py"


def node(*args, timeout=300):
    return subprocess.run(["node", str(RUNNER), *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def test_dry_run_on_two_fixtures_builds_and_checks_every_request():
    done = node("--dry", "--only", "s1-tempting,case-3")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "dry run passed: 2 fixtures" in done.stdout
    # s1: one fill and one judge; case-3: style, three characters, world, entanglements, setup, each filled and judged
    assert "0 refused" in done.stdout
    requests = int(done.stdout.split("checked ")[1].split(" requests")[0])
    assert requests >= 2 + 2 * 7


def test_dry_run_needs_no_backend_and_writes_nothing():
    before = sorted(p.name for p in (ROOT / "evals" / "cardfill" / "results").iterdir())
    done = node("--dry", "--only", "u3-tempting,e8-tempting")
    assert done.returncode == 0, done.stdout + done.stderr
    assert sorted(p.name for p in (ROOT / "evals" / "cardfill" / "results").iterdir()) == before


def test_dry_run_refuses_an_unknown_fixture():
    assert node("--dry", "--only", "no-such-fixture").returncode == 2


def test_the_contract_check_refuses_a_broken_request():
    bad = subprocess.run([sys.executable, str(CHECKER)], input=json.dumps([{"label": "broken", "request": {"call": "fill"}}]),
                         capture_output=True, text=True)
    assert bad.returncode == 1 and "BAD broken" in bad.stdout
    empty = subprocess.run([sys.executable, str(CHECKER)], input="[]", capture_output=True, text=True)
    assert empty.returncode == 0


def _read(out: Path):
    with open(out / "summary.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_a_run_against_the_fake_backend_writes_results_and_summary(tmp_path):
    out = tmp_path / "fake"
    with running() as (base, _):          # canned replies, like `python -m pulpermill.backend --fake`
        done = node(base, "--runs", "2", "--only", "s1-tempting,case-3", "--label", "fake", "--out", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    rows = _read(out)
    assert {r["fixture"] for r in rows} == {"s1-tempting", "case-3"}
    assert {r["run"] for r in rows} == {"1", "2"}
    assert all(r["ok"] == "true" for r in rows)
    assert {r["card"] for r in rows if r["fixture"] == "case-3"} == {"style", "characters#1", "characters#2", "characters#3", "world", "entanglements", "setup"}
    assert {"rules_fired", "judge_fired", "prompter_name", "prompter_version"} <= set(rows[0])
    for n in (1, 2):
        saved = json.loads((out / f"case-3-run{n}.json").read_text(encoding="utf-8"))
        assert len(saved["project"]["characters"]) == 3
        assert all(note["character"] for note in saved["project"]["card_notes"] if note["card"] == "characters")
    assert json.loads((out / "meta.json").read_text())["schema_version"] == 3


def test_a_run_against_the_stub_prompter_records_the_rules_the_judge_and_the_prompter(tmp_path):
    out, log = tmp_path / "stub", tmp_path / "run.log"
    with running(config=Config(log_path=str(log), prompter="stub"), engine=StubEngine(), run=None) as (base, _):
        done = node(base, "--runs", "1", "--only", "s1-tempting,c8-input,e1-tempting,u3-tempting", "--judge", "--runlog", str(log), "--label", "stub", "--out", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    rows = _read(out)
    assert len(rows) == 4 and all(r["ok"] == "true" for r in rows), rows
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["prompter"]["name"] == "stub" and meta["prompter"]["version"] and meta["judge"] is True
    assert {r["prompter_name"] for r in rows} == {"stub"} and {r["prompter_version"] for r in rows} == {meta["prompter"]["version"]}
    saved = json.loads((out / "e1-tempting-run1.json").read_text(encoding="utf-8"))
    assert saved["steps"][0]["judge"]["ok"] is True
    assert saved["steps"][0]["judge"]["answered"], "the judge ran for the card's model-judged rules"
    assert isinstance(saved["steps"][0]["rules"], list)
