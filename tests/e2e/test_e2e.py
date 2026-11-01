"""P7: the whole story, end to end. The real server code (the runner and the stub prompter) runs on a scripted fake engine, and the page's own
client (tools/smoke_page.mjs) plays the story against it: create, start, chapters 1 to 3, chapter 2 again, chapter 4, finish.
Every check the story makes is one assertion here."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server_harness import running  # noqa: E402
from stub_engine import StubEngine  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _story(base: str) -> list[tuple[bool, str]]:
    done = subprocess.run(["node", str(ROOT / "tools" / "smoke_page.mjs"), base], cwd=ROOT, capture_output=True, text=True, timeout=300)
    lines = [(l.startswith("ok"), l[5:]) for l in done.stdout.splitlines() if l.startswith(("ok", "FAIL"))]
    if done.returncode not in (0, 1) or not lines or "the story ran to its end" not in done.stdout:
        pytest.fail(f"the story did not run to its end (exit {done.returncode})\n{done.stdout}\n{done.stderr}")
    return lines


@pytest.fixture(scope="module")
def story():
    engine = StubEngine()
    with running(engine=engine, run=None) as (base, _):
        yield _story(base), engine


def test_every_step_of_the_story_passes(story):
    lines, _ = story
    failed = [text for ok, text in lines if not ok]
    assert not failed, "\n".join(failed)


@pytest.mark.parametrize("fact", [
    "the spotlight tie exists and the cast holds everyone it requires",
    "the chapter, its Events and its shifts commit together",
    "undo restores the project exactly",
    "before chapter 3 the effective cards are the base cards plus the shifts of chapters 1 and 2",
    "regenerating chapter 2 drops the shifts of chapter 2 and later and keeps chapter 1's",
    "planning the same chapter again builds the same request",
    "a stop in the middle of a generate leaves the project unchanged",
    "the end copy of Characters, World and Entanglements is the fold of all shifts",
    "the original Characters, World and Entanglements are untouched",
    "exporting and importing a project gives the same project",
    "the story produced shifts to fold (so the fold checks are not empty)",
])
def test_the_story_checked(story, fact):
    lines, _ = story
    assert any(fact in text and ok for ok, text in lines), f"never saw a passing check: {fact}"


def test_the_stop_reached_the_engine(story):
    _, engine = story
    assert engine.cancelled_calls >= 1
    assert not engine.active
