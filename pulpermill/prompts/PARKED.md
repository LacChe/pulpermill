# Parked story prompt code (P4)

The backend no longer uses the code below. Prompt design decides what to reuse; nothing is deleted. Nothing outside `tests/prompts/` may
import the story-specific parts, and `pulpermill/backend/` imports only the generic `budget`, `tokens` and `textfiles`.

| Parked | What it is |
| --- | --- |
| `prompts.py`, `blocks.py` | the old story prompt builders (writer, planner, events, shifts, fill, judge, style_fit, offstage, end of story) and reply assemblers; they read the old request shapes |
| `schemas.py` | the old story reply shapes, left exactly as it was. The generic parts (card grammar, `one_of`, `obj`, link names, the shifts patch grammar) were remade in `pulpermill/backend/grammar.py`; nothing imports this copy |
| `chapter_checks.py`, `templates/`, `text/` | the old chapter checks and the old wording files |
| `limits.yaml` | what is left of the length limits: counts, text a model wrote, caps of removed fields. The per-field caps are now `cap` on the schema fields |
| `parked/pipelines_*.py.txt` | the old orchestration (`pipelines/story.py`, `simple.py`, `structured.py`): the two-section writer loop, the planner's think and beat, offstage, end of story, the old two-attempt call. Kept as text, not importable. Their replacement is `pulpermill/backend/runner.py` |

`render.py` is generic and unchanged. Some of its functions still render removed ideas (standing, code numbers, scene, knowledge, pressures);
their tests are marked `PARKED(prompt-design)`.

Tests of parked code carry `PARKED(prompt-design)` with a reason: all of `tests/prompts/test_prompts.py`, `test_judge_direction.py` and
`test_trials.py`, and the individual tests listed in the P4 report.
