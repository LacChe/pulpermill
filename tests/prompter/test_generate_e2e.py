"""The whole story (tools/smoke_page.mjs, the page's own client) on `Config.prompter = "mill"` with the real plan and generate wording.
The fake engine answers a plan or generate call with the module's own `script(request, kit)` (queued when the flow is built) and leaves
the other calls to the stub's scripts, so the page's rules, the runner's checks (the planner check, the edge check) and the contract
are all exercised end to end with no model."""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
for sub in ("backend", "e2e"):
    sys.path.insert(0, str(ROOT / "tests" / sub))

from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.errors import Cancelled  # noqa: E402
from pulpermill.prompter.mill import generate as gen, plan  # noqa: E402
from server_harness import running, wait_idle  # noqa: E402
from stub_engine import StubEngine  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


class MillEngine(StubEngine):
    """The stub engine for the calls still on the stub's flow; scripted texts for the calls with their own wording."""

    def generate(self, prompt, max_tokens, *, constraint=None, on_token=None, cancel=None, params=None):
        if prompt.startswith("Stub prompt for"):
            return super().generate(prompt, max_tokens, constraint=constraint, on_token=on_token, cancel=cancel, params=params)
        if constraint is None and max_tokens == gen.WRITE_TOKENS and cancel:         # a slow stretch a Stop can land in
            with self._lock:
                self.calls += 1
                self.active = True
            try:
                for _ in range(int(self.write_seconds / 0.02)):
                    cancel.raise_if_cancelled()
                    time.sleep(0.02)
            except Cancelled:
                with self._lock:
                    self.cancelled_calls += 1
                raise
            finally:
                with self._lock:
                    self.active = False
                    self.finished += 1
        return super(StubEngine, self).generate(prompt, max_tokens, constraint=constraint, on_token=on_token, cancel=cancel, params=params)


@pytest.fixture
def engine_with_scripts(monkeypatch):
    engine = MillEngine()
    for module in (plan, gen):
        original = module.build_flow

        def build(request, kit, _original=original, _module=module):
            with engine._lock:
                engine._outputs.clear()            # a Stop in the middle of a call leaves its unused texts behind; each call starts afresh
            engine.script(*_module.script(request, kit))
            return _original(request, kit)
        monkeypatch.setattr(module, "build_flow", build)
    return engine


def test_the_whole_story_passes_on_the_mill_prompter_with_real_plan_and_generate_wording(engine_with_scripts, tmp_path):
    log = tmp_path / "runs.jsonl"
    with running(config=Config(prompter="mill", log_path=str(log)), engine=engine_with_scripts, run=None) as (base, _):
        done = subprocess.run(["node", str(ROOT / "tools" / "smoke_page.mjs"), base], cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert wait_idle(base)
    assert "the story ran to its end" in done.stdout, done.stdout + done.stderr
    failed = [line for line in done.stdout.splitlines() if line.startswith("FAIL")]
    assert not failed, "\n".join(failed)
    prompts = engine_with_scripts.prompts
    assert any("## Your task" in p for p in prompts) and any("## The plan for this chapter" in p for p in prompts)
    versions = {r for r in log.read_text().split('"version": "') if r.startswith("mill-0.1")}
    assert versions and all("+plan:plan-1:" in v and "+generate:generate-1:" in v for v in versions)
