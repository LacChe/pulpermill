"""The card-fill kit (tools/run_cardfill.mjs, the page's own client and logic) against the real server on `Config.prompter = "mill"`, with the
real fill and judge wording and a scripted fake engine (no model): every fixture of the kit is filled, chained, and judged, and every call must
come back valid. This proves the kit works with the mill calls; the quality of the cards is the real model's, tuned in step D."""
import csv
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
sys.path.insert(0, str(ROOT / "tests" / "backend"))

from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.prompter.mill import fill, judge, style_fit  # noqa: E402
from server_harness import running, wait_idle  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@pytest.fixture
def engine_with_scripts(monkeypatch):
    engine = FakeEngine()
    for module in (fill, judge, style_fit):
        original = module.build_flow

        def build(request, kit, _original=original, _module=module):
            with engine._lock:
                engine._outputs.clear()
            engine.script(*_module.script(request, kit))
            return _original(request, kit)
        monkeypatch.setattr(module, "build_flow", build)
    return engine


def test_every_fixture_of_the_kit_is_filled_and_judged_on_the_mill_prompter(engine_with_scripts, tmp_path):
    out, log = tmp_path / "results", tmp_path / "runs.jsonl"
    with running(config=Config(prompter="mill", log_path=str(log)), engine=engine_with_scripts, run=None) as (base, _):
        done = subprocess.run(["node", str(ROOT / "tools" / "run_cardfill.mjs"), base, "--runs", "1", "--judge", "--label", "mill-test", "--runlog", str(log),
                               "--out", str(out)], cwd=ROOT, capture_output=True, text=True, timeout=600)
        assert wait_idle(base)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    rows = list(csv.DictReader((out / "summary.csv").open()))
    assert len(rows) >= 60
    failed = [row for row in rows if row.get("ok") not in (None, "", "true", "True", "1", "yes")]
    assert not failed, failed[:3]
    meta = json.loads((out / "meta.json").read_text())
    assert "mill-0.1" in json.dumps(meta) and "fill:fill-1" in json.dumps(meta)
    assert any("## " not in p and p.startswith("You help a writer fill in one card") for p in engine_with_scripts.prompts)
