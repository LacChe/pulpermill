"""The whole story (tests/e2e's page client) on `Config.prompter = "mill"`, and the run log naming the prompter.
While a call has no module of its own, mill runs the stub's flow, so the stub's fake engine can drive it. These tests pin every call to that
fallback (no module of its own), so they keep their meaning after a call gets real wording; real wording is tested by its own owner."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
for sub in ("backend", "e2e"):
    sys.path.insert(0, str(ROOT / "tests" / sub))

from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.prompter.mill import mill as mill_module  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402
from stub_engine import StubEngine  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@pytest.fixture
def scaffold_only(monkeypatch):
    monkeypatch.setattr(mill_module, "load_module", lambda call: None)


def test_the_whole_story_passes_on_the_mill_prompter(scaffold_only, tmp_path):
    log = tmp_path / "runs.jsonl"
    with running(config=Config(prompter="mill", log_path=str(log)), engine=StubEngine(), run=None) as (base, _):
        done = subprocess.run(["node", str(ROOT / "tools" / "smoke_page.mjs"), base], cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert wait_idle(base)
    assert "the story ran to its end" in done.stdout, done.stdout + done.stderr
    failed = [l for l in done.stdout.splitlines() if l.startswith("FAIL")]
    assert not failed, "\n".join(failed)
    records = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    named = [r["prompter"] for r in records if isinstance(r.get("prompter"), dict)]
    assert named and all(p == {"name": "mill", "version": "mill-0.1"} for p in named)
