"""Writes every complete prompt for the sample story, so it can be read. Run from the repository root:
python tools/render_prompts.py   (writes docs/prompts/samples/prompts/*.txt). These files are the golden prompts: the test in
tests/prompts/test_golden.py fails when a prompt changes without these being written again."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "prompts"))

import prompt_cases as cases                                                                         # noqa: E402

OUT = ROOT / "docs" / "prompts" / "samples" / "prompts"
OUT.mkdir(parents=True, exist_ok=True)
for name, prompt in cases.golden().items():
    (OUT / f"{name}.txt").write_text(cases.golden_file(prompt), encoding="utf-8")
    print(f"{name}: {len(prompt.text.split())} words")
