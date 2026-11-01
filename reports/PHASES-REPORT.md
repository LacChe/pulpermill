# Phases report (P7 integration gate)

A one-off report on the branch `p7-integration-gate` (P1 to P6a merged). Nothing in `docs/` was changed. Checked on Python 3.12 (CI uses 3.13) and node 22, in a clean virtualenv holding only the packages the CI file installs.

## Results

| Suite | Before P7 | After P7 |
| --- | --- | --- |
| `python -m pytest tests -q` | 616 passed, 79 skipped, 1 failed | 630 passed, 79 skipped, 0 failed (the 13 new tests are the end-to-end story) |
| `node --test "tests/web/*.test.mjs"` | 405 passed, 29 failed | 434 passed, 0 failed |

### Task 1: failures and where they belonged

- **Python: `tests/backend/test_conformance.py`, the cancel test (P4).** A test defect. The test cancelled as soon as the server said "busy", but the runner fits the prompt before the first token, so the stop often landed before any engine call and no cancelled call was counted. The test now waits until the engine is running. Cancelling itself behaves correctly. Fixed three runs in a row.
- **Page: 29 failures, all in `tests/web/logic.test.mjs` (P5a).** Stale tests. They still asserted ideas P1 removed or the old schema shape (reveals and payoffs, pacing, rule truth and status, knowledge, goal changes, either-or and `required_if` fields on cards, the old beat's option lists). None was a defect in the page code.
  - Where the page still does the thing, the test was moved to the new schema (for example the item titles and link labels now use `ties`).
  - The page still honours the generic either-or and `visible_if` mechanisms, but no card uses them any more, so those tests now run on a small field list of their own.
  - Where the test was only about a removed idea (the pacing test, the reveal test, the rule truth test, the `required_if` rules test) it was replaced by a short test that the idea is gone from the schema. **This is the nearest thing to deleting tests in this phase; please look at it.** None of them was a parked test.
  - Also removed from the allow-list in `tests/web/text.test.mjs`: two stale diagnostics (offstage, knowledge entries).

### Task 2: leftover search

Searched the repo outside `docs/` for the listed terms.

Removed or reworded in live code:
- the `counted` flag, from the `schema/common.py` docstring and the `FLAGS` list in `tools/build_schema.py` (the schema regenerates with no diff);
- one comment in `schema/world.py` that used "pressure" as an ordinary word;
- the stale names used as stand-in field names in `tests/web/logic.test.mjs`.

Explained, not removed:
- `pulpermill/prompts/` (`render.py`, `prompts.py`, `schemas.py`, `blocks.py`, `chapter_checks.py`, the yaml and templates, `parked/`): parked story prompt code, per P4's `PARKED.md`. Prompt design rewrites it. `render.py` still has renderers for removed fields; the generic card renderer in it is what stays.
- `pulpermill/schema/CONVENTIONS.md`: a repo doc, deferred with the other repo docs.
- Tests that assert the removal (`tests/schema/*`, `tests/backend/test_seam.py` checking that an `offstage` flow is refused, the new "is gone" tests in `logic.test.mjs`).
- `tools/run_trials.py` (the `T1-pressure` trial) and `evals/trials`: the old trial harness, parked with the story prompts.
- Ordinary English ("counted", "knowledge", "plant", "reveal" in prose) and the tokenizer vocabulary file.
- **Not checked one by one:** the hits under `evals/` (fixtures and scoring files); I classed them with the parked eval kit without opening each.

### Task 3: the end-to-end story

`tests/e2e/test_e2e.py` starts the real server code (runner and stub prompter) on a scripted fake engine (`tests/e2e/stub_engine.py`, which feeds the stub prompter's own valid scripts back as the model's output), and plays the story with the page's own client in `tools/smoke_page.mjs` (`runStory`, also usable from the command line against `python -m pulpermill.backend --fake`). The story: ready project, start (five cards locked), chapters 1 to 3, regenerate chapter 2, chapter 4 with a Stop in the middle of writing, finish, export and import. All checks pass, and the test passes on repeated runs. Each fact is an assertion:

- the spotlight tie exists and the cast holds everyone it requires, before every plan;
- each chapter commits chapter, Events and shifts together, and an undo restores the project exactly (also for a regeneration);
- before chapter 3 the effective cards equal the base cards plus the shifts of chapters 1 and 2, folded by hand in the test rather than by the page's own function; the base cards are untouched;
- after regenerating chapter 2 the old shifts of chapter 2 and later are gone, chapter 1's remain, the later beats are stale and the later chapter text stays;
- planning the same chapter twice gives the same picks and the same request, also on separate copies of the project;
- a Stop in the middle of a generate gives a `stopped` failure, reaches the engine, and leaves the project unchanged;
- the end copy of Characters, World and Entanglements equals the fold of all shifts, and the originals are untouched;
- exporting and re-importing gives the same project.

### Task 4: contract agreement

Already covered and passing, not duplicated: the golden request test in `tests/web/logic.test.mjs` (the page builds exactly every golden vector), the reply-reading test over every reply vector, and `tests/backend/test_conformance.py` (the backend accepts the vectors and the stub's replies). The end-to-end story adds the page reading real stub replies for `plan`, `generate` and `style_fit`. **Not covered end to end:** the page reading real stub `fill` and `judge` replies; those are only covered by the vectors on both sides.

### Task 5: CI

`.github/workflows/pages.yml` now installs `pytest pyyaml pydantic starlette uvicorn requests`. Before, the install line lacked `starlette`, `uvicorn` and `requests`, so the backend tests would have failed to import in CI. `python -m pytest tests` now includes `tests/e2e`, which needs node (already set up in the job); the web test command is unchanged; deploy still `needs: test`.

## Parked tests

79 skipped in total:

- **73 `PARKED(prompt-design)`**, all from earlier phases, none added in P7: `tests/prompts/test_render.py` (blocks.py is parked story prompt code; the standing record was replaced by shifts; the old beat was reshaped; reveals, plants and the offstage move were removed; rule status and truth were removed; pressures and knowledge were removed from Entanglements; code numbers for plants, reveals and legal shifts were removed) and `tests/prompts/test_budget.py` (the golden prompts are the old story prompts and read the old request shapes; old text is capped by the parked renderers). The first group is individually marked with the reasons above.
- **6 skipped without the marker**, `tests/schema/test_lint.py`: "UI wording not written yet". These wait on UI wording, not prompt design, so I did not re-label them. Decision needed: leave as they are, or park them under a marker.

## Open questions from P0: defaults used

All three were answered in P0, and the code follows the answers:
1. The end copy includes Entanglements (checked by the end-of-story assertions).
2. Regenerating chapter N drops the shifts of N and later; later chapters keep their text and events and get stale beats (checked).
3. The shift cap is one entry per card that appeared in the chapter, at most 7 (`MAX_SHIFTS_PER_CHAPTER = 7`; not separately tested in P7).

## Deviations from the phase specs

- P5a's tests were edited in P7 (see Task 1); P4's cancel test was edited.
- The story's project is the mock-filled `readyProject()` used by the other page tests, not a migrated eval fixture, and has four chapters.
- Chapter 3 is not forced to regenerate after chapter 2. See the finding below: the story accepts either a rewrite or a `beat_blocked` refusal.
- `tools/smoke_page.mjs` was rewritten into the story driver; its earlier checks (status, style fit, plan, generate, end of story) are all still in it.

## For prompt design

- After chapter 2 is rewritten, chapter 3's beat is stale and may point at a tie that only the old chapter 2's shifts created. Regenerating chapter 3 is then refused with `beat_blocked` ("A beat points to something that no longer exists"), and the beat has to be planned again. That is by design, but the planner will be asked for this often, and the stub's shifts do it about half the time.
- The `aim_not_repeated` rule blocks a plan whose aim is too close to an earlier aim or to an earlier Events `changed` line. The stub's constant text would always be blocked, so the test engine gives each chapter a different aim. A real planner needs its retry to carry that rule's words.
- The canned pipeline (`--fake`) never produces shifts. Only the stub through the real runner does (three entries per chapter), so shift handling is exercised only through the e2e test.
- Every call spends about a second fitting the prompt before the first token. A Stop in that stretch is correct but never reaches the engine.
- The mock gives every project a random id, so the seeded picks differ between runs but are fixed within one project.
- `render.py` still renders the removed ideas; only the generic card renderer should survive.
