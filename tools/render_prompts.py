"""Writes every complete prompt for the sample story, so it can be read. Run from the repository root:
python tools/render_prompts.py   (writes docs/prompts/samples/prompts/*.txt). Phase 5 turns these into golden prompts."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pulpermill.prompts import prompts as P                                           # noqa: E402
from tests.prompts import test_render as sample                                       # noqa: E402

OUT = ROOT / "docs" / "prompts" / "samples" / "prompts"
OUT.mkdir(parents=True, exist_ok=True)
vectors = {r["name"]: r["data"] for r in json.loads((ROOT / "web/tests/contract-vectors.json").read_text(encoding="utf-8"))["requests"]}

gen, plan = sample.generate_request(), sample.plan_request()
roles = P.writer_plan()
earlier = " ".join(["[the chapter so far would be here]"] * 3)
files = {
    "writer-1-open": P.writer_prompt(gen, roles, 0),
    "writer-4-close": P.writer_prompt(gen, roles, 3, earlier),
    "planner-1-think": P.planner_think_prompt(plan),
    "planner-2-beat": P.planner_beat_prompt(plan, "[the planner's thinking would be here]"),
    "events": P.events_prompt(gen, "[the chapter would be here]"),
    "shifts": P.shifts_prompt(gen, "[the chapter would be here]", {"happened": "[what the Events pass found]"}),
    "fill-character": P.fill_prompt(vectors["the page's fill_character request"]),
    "judge-world": P.judge_prompts(vectors["the page's judge_world request"])[0],
    "style-fit": P.style_fit_prompt(vectors["the page's style_fit request"]),
    "offstage": P.offstage_prompt(vectors["an offstage request"]),
    "end-story-character": P.end_story_prompts(vectors["an end-of-story request"])[0],
}
for name, prompt in files.items():
    schema = json.dumps(prompt.schema, indent=1) if prompt.schema else "(free text)"
    (OUT / f"{name}.txt").write_text(f"[{prompt.name} {prompt.version}, stage: {prompt.stage}]\n\n{prompt.text}\n\n---- reply shape ----\n{schema}\n", encoding="utf-8")
    print(f"{name}: {len(prompt.text.split())} words")
