# P7.5 cleanup report

One-off report, branch `p7.5-cleanup` (off `main` at P7, `da4fc36`). Nothing in `docs/` or `evals/` was changed.

## Tag
`pre-prompt-design` is on the remote and points at `da4fc36` (the P7 commit). It existed before this phase started (checked with `git ls-remote --tags origin`). Deleting began only after that.

## Results
| Suite | Before | After |
| --- | --- | --- |
| `python -m pytest tests -q` | 630 passed, 79 skipped | **646 passed, 6 skipped** |
| `node --test "tests/web/*.test.mjs"` | 434 passed | 434 passed, 0 skipped |
| `python -m pytest tests/e2e` three times | | 22 passed each time |

The 6 skips are the `PENDING(ui-wording)` lint tests. No tokenizer or engine skip occurred. No test carries `PARKED(prompt-design)` (the only file in the repo that still contains the string is `reports/PHASES-REPORT.md`, P7's report, and `docs/`). `python -m pulpermill.backend --fake` starts; the backend imports only `budget` and `tokens` from `pulpermill/prompts/`. `.github/workflows/pages.yml` needed no change.

## Files deleted
- Story prompt code: `pulpermill/prompts/prompts.py`, `blocks.py`, `schemas.py`, `chapter_checks.py`
- Wording and parked copies: `templates/en/*` (all ten), `parked/` (three `.txt`), `PARKED.md`
- Tools: `tools/run_trials.py`, `render_prompts.py`, `render_samples.py`, and `budget_report.py` (it needed `prompt_cases` and the old story prompts to measure; it cannot work without them)
- Tests: `tests/prompts/test_prompts.py`, `test_judge_direction.py`, `test_trials.py`, `trial_set.py`, `schema_lite.py`
- `textfiles.template()` (read only the deleted templates)

## Files restored from deletion
- `pulpermill/prompts/limits.yaml`, **trimmed**: `textfiles.limits()` still reads it for `characters.max_behaviors`, `setup.goal`, `setup.stakes` and the two `events.full_chapters_*` counts, which the kept renderers use. Dropped from it: `pressure_what`, `next_move`, `fact`, `rule_truth`, `beat`, `code`, `offstage`, `standing`, `chapter`.
- `text/en/frames.yaml` and `text/en/style_directives.yaml` were never deleted (the kept renderers read them); `frames.yaml` is pruned of keys no kept renderer reads (code numbers, knowledge, scene, standing, titles, planner offstage/tone, previous ending, rules note).
- Nothing in `templates/` was needed.

## Renderers in `render.py`
- **Kept:** `render_style`, `render_person`, `render_cast`, `render_world`, `groups_in_play`, `render_entanglements`, `render_setup`, `render_story_so_far`, `render_earlier_beats`, `render_person_brief`, `names_by_id`, `in_words`, and the helpers (`Report`, `s`, `clip`, `soften`, `join_names`, `sentence`, `tidy`, `fill`, `lead`, `fill_lead`, `_items_block`, `_uses`, `_list_items`, `_first_sentence`).
- **Removed:** `render_standing`, `render_scene`, `render_code_numbers`, `_goal_lines`, `knowledge_line`, `render_handles`, `render_shifts_history`.
- **Branches removed inside kept renderers:** the pressures and knowledge blocks of `render_entanglements`; pressures in `groups_in_play`; rule status ordering and truth in `render_world`.
- **One output change to flag:** `render_earlier_beats` no longer prints `({shift})` on each line or the "closed on this moment" line from `ends_on`. Both read beat fields that no longer exist (the old line ended in an empty `()`). Everything else renders byte for byte as before (the kept tests pass unchanged).

`pulpermill/prompts/__init__.py` now exports: `Report, render_style, render_cast, render_world, render_entanglements, render_setup, render_story_so_far, render_earlier_beats, groups_in_play`. New `pulpermill/prompts/README.md`.

## Tests removed (counted by `def test_`)
| File | Removed |
| --- | --- |
| `test_prompts.py` | 34 (file) |
| `test_judge_direction.py` | 4 (file) |
| `test_trials.py` | 22 (file) |
| `test_render.py` | 13 (36 to 23) |
| `test_budget.py` | 2 (the golden-prompt test and the standing/code-numbers cap test; 19 to 17) |

Helper files removed with them: `trial_set.py`, `schema_lite.py`. `prompt_cases.py` was renamed to `story_sizes.py`, with its parked prompt builders cut, because the kept budget tests use its story-size helpers. `PARKED(prompt-design)` markers: all 73 removed with the tests.

## Tests added
- `tests/schema/test_shift_cap.py` (9 cases): one entry per card accepted for 1, 3 and 5 people (up to 7); exactly 7 accepted; an eighth refused; a sixth person pushing past 7 refused with "at most 7"; two entries for the same card (world, and a character) refused; a character target outside the beat's cast, or none, refused. These run through `backend/assemble.shifts`, the code that enforces the cap. **No code was changed to make them pass.**
- `tests/e2e/fill_judge_page.mjs` plus 10 tests in `tests/e2e/test_e2e.py`: the page's `fillCard` and `judgeCard` read real stub `fill` and `judge` replies through the real runner, and the page's rules accept them (all model rules asked are answered, no unresolved fill values).

## PENDING(ui-wording)
Six skipped tests in `tests/schema/test_lint.py`, kept: three test functions at lines 253, 316 and 332, each parametrized over two languages or cards (2 + 2 + 2).

## For review (P7's replaced tests, kept)
In `tests/web/logic.test.mjs`:
- "World: a rule is how the world works: a statement, its cost and what happens when it is broken, with no status or truth" (was: a rule's truth shows only for a false belief)
- "no rule asks for a field to be required only under a condition any more" (was: `required_if`: when, when_present and unless)
- "the outline has no beat shift and no pacing rule any more" (was: pacing: at most 2 harder in a row, at most 1 easier)
- "the outline has no reveal, plant or payoff fields or rules any more" (was: a reveal may not repeat, and a payoff must be an earlier, still-open plant)

Also changed in P7 for the removed ideas: "either-or: only the chosen field is shown, and a conditional field needs its sibling", "a beat with an aim and a plan has no missing-field problem", "a fill reply keeps a list's items".
In `tests/web/text.test.mjs`: two allow-list lines removed (the offstage move messages; the knowledge-entry messages).

## Leftover search
Outside `docs/` and `evals/`, words: P7's list plus `offstage_did`, `offstage_reach`, `standing`, `code numbers`. Remaining hits, by category:
- **Tests asserting a removal:** `tests/schema/test_decisions.py` (11), `test_contract.py` (2), `tests/web/logic.test.mjs` (8), `tests/web/panels.test.mjs` (2), `tests/backend/test_seam.py` (1, an `offstage` flow is refused).
- **`pulpermill/schema/CONVENTIONS.md`:** 24 hits, a repo doc, deferred.
- **Live things that share the word:** `pacing` (a Style axis: `schema/style.py`, style text, `render.py`, `style_directives.yaml`, `test_render.py`, `test_lint.py`; about 14 hits); `offstage` as the marker for a person not in the cast (`render.py` 3, `frames.yaml` 2, `test_render.py` 5); `required_if` as a project-level lock rule (`schema/project.py` 3, `test_lint.py`, `test_project.py`, `logic.test.mjs` 1).
- **Ordinary English:** "counted", "standing" ("standing trait", "forty years' standing"), "spotlight" in CSS and similar (`web/*.js`, `web/style.css`, schema text, `tests/prompts/fixtures`, `budgets.yaml`, `story_sizes.py`).
- **Tokenizer vocabulary:** `tokenizer.json`, excluded.
- **Unexplained:** none.

## Stale references I did not touch (outside my files)
- `docs/prompts/samples/**` (golden prompts and `budget-report.md`): stale; `docs/` is off limits.
- `notebooks/pulpermill_backend.ipynb` imports `tools.run_trials` (the cell is commented) and `pulpermill/backend/complete.py` names `tools/run_trials.py` in its docstring. `complete.py` itself is generic; both are outside this phase's files, so left as they are.
- `tests/shared/contract-vectors.json` has a note mentioning `PARKED(P5a)`; `tests/shared/` is not changed here.
- `evals/trials/README.md` points at the deleted `tests/prompts/trial_set.py`. `evals/` belongs to P6b.
- Root `README.md` names no deleted file; unchanged.

## For prompt design
- `render.py` is now only what the current cards support. New renderers (a scene, a spotlight tie, shifts history) have to be written; the old ones are under the tag.
- `textfiles.limits()` still builds caps from the schema plus `limits.yaml`. A prompter that wants its own wording files should keep them under `pulpermill/prompter/<name>/`.
- The pre-existing `reports/PHASES-REPORT.md` points at `PARKED.md`, which is gone.
