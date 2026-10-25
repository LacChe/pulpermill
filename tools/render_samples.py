"""Writes the material the renderers make for the sample story, so it can be read. Run from the repository root:
python tools/render_samples.py   (writes docs/prompts/samples/*.txt). Phase 5 turns these into golden prompts."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pulpermill.prompts import Report, assemble, planner_blocks, writer_blocks      # noqa: E402
from tests.prompts import test_render as sample                                       # noqa: E402

OUT = ROOT / "docs" / "prompts" / "samples"
OUT.mkdir(parents=True, exist_ok=True)

for name, blocks in (("writer-material", writer_blocks), ("planner-material", planner_blocks)):
    request = sample.generate_request() if name.startswith("writer") else sample.plan_request()
    report = Report()
    text = assemble(blocks(request, report))
    (OUT / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
    print(f"{name}: {len(text)} characters, {len(text.split())} words, {len(report.clips)} clipped")
