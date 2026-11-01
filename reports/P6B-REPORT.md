# P6b report: card-fill eval kit for schema version 3

A one-off report on the branch `p6b-cardfill-eval-kit` (off `main` at da4fc36, after P7). Only `evals/`, `tools/run_cardfill.mjs`, `tests/evals/` and this file were changed. Nothing in `docs/` was changed. Checked on Python 3.12 (the project asks for 3.13) with node 22.

## Read this first

- **P0 was not read.** The Decision Record link is a page that renders in the browser, and neither fetching it nor the artifact reader could open it. So A9, A11 and the deferred list were not consulted. Every decision below rests on the P6b spec's defaults and the schema as it is on `main` (`pulpermill/schema/*.py` and `text/en/*.yaml`). Every default in the spec held against the schema. If P0 says something the schema does not (for example that a false belief should still be representable), the retired items are the place to look: W3, W4, E5, E6, E7, U1, U4.

## Results

| Suite | Before | After |
| --- | --- | --- |
| `python -m pytest tests/evals -q` | 159 passed | 182 passed |
| `python -m pytest tests -q` | 630 passed, 79 skipped | 653 passed, 79 skipped (the 23 new tests are in `tests/evals`) |
| `node --test "tests/web/*.test.mjs"` | 434 passed | 434 passed |
| `node tools/run_cardfill.mjs --dry` | n/a | passes: 65 fixtures, 250 requests, 0 refused |
| `make_fixtures.py` and `make_scoring.py` run twice | | no diff |

## Inventory (task 1; the rows are in `evals/cardfill/CHANGES.md`)

| | Kept | Revised | Retired | New | Live now |
| --- | --- | --- | --- | --- | --- |
| Probes (29 before) | 14 | 8 | 7 | 4 | 26 |
| Cases (12 before) | 6 | 6 | 0 | n/a | 12 |

- **Retired:** W3, W4, E5, E6, E7, U1, U4, as the spec's defaults said.
- **Revised:** W1, E1, E2, E3, E4, U2, U3, U5. U3 now keeps the ending out of `disruption`. E4 stays Tier 1 and is called out as important.
- **New (four of the allowed six):** E8 (a tie that points the wrong way), E9 (ownership written as a tie), U6 (a Setup that restates the character card), U7 (a stated chapter count must be kept). Each has a tempting input and a control, and each is aimed at an error no rule flags.
- **Considered and not kept (six, listed in `CHANGES.md`):** an edge written as a plain feeling (`tie_edge_is_live` flags it, and E3 covers it), a protagonist with no tie (`protagonist_has_tie` fires), a tie to a group World does not hold (that is E2), a wrong holder type (`holding_pair_allowed` blocks it), a self-tie (`tie_not_self` blocks it), a non-character protagonist (that is U5).
- **Cases revised:** 3, 4, 5, 6, 9 and 10. Goal, stakes, knowledge and pressure lines are gone; case 6's six "secrets" are six plain rules, still over the cap; difficulty, genre and characters are unchanged. Cases 1, 2, 7, 8, 11 and 12 needed no change to the input.
- **Tiers:** 13 Tier 1 probes (S3, S4, C1, C4, C8, E1, E2, E4, E8, E9, U3, U6, U7), 13 Tier 2. Recomputed against the current rules. No carried-over probe changed tier: each one's wrong result is still caught (or not) by the same kind of rule. U3 stays Tier 1 because a disruption with an ending in it is still an event.

## What each task found

1. **Inventory.** Done. The defaults held. The old catalog's tier summary and its "★ theme as goal" and "★ Hidden/Myth" marks went with the retired probes; the only ★ left is an owner inside an object (W1, E1).
2. **Documents.** All five rewritten or updated. The README's P6a note and the "fixtures do not load" known limit are gone, and `fixtures/README.md` now says what "valid" means. The tier rule is unchanged. A test (`test_kit_agrees.py`) fails if any of these words appear in the kit outside `CHANGES.md`: pressure, knowledge, stakes, offstage, plant, reveal, goal, myth, hidden, false_belief, uncommon, rule status.
3. **Cases.** Done as above. Case files remain pasteable, unlabelled input.
4. **Upstream sets.** A, B and C each still serve their probes and are valid under the schema. No card needed adding: A has the ties and the Dock 9 holding for Setup, B has the Lantern Bar for E9 and no Brotherhood for E2, C has the three characters and the Council for E3. Only `upstream/README.md` changed. Set C now serves only E3, since E7 was retired.
5. **Regenerate.** 53 probe fixtures and 12 case fixtures, 159 probe rows and 36 case rows. `test_kit_agrees.py` checks that the catalog, the inputs, the cases, the manifest, the scoring sheets and `CHANGES.md` list the same probes and cases. `test_fixtures_valid.py` covers every fixture by glob, and now pins the count and the eight new fixtures.
6. **Runner.**
   - Runs against `python -m pulpermill.backend --fake` (canned replies) and against the real server with the stub prompter (tested through the test harness with the stub engine, with `Config.prompter = "stub"`).
   - Writes `<out>/<fixture>-run<n>.json`, `summary.csv` and `meta.json`. The rules that fired are in `rules_fired`.
   - The prompter's name and version are not in any HTTP reply, only in the server's run log, so the runner reads them from `--runlog PATH` (the server's `Config.log_path`). Without it they are blank.
   - `--dry` drives the page's own mock engine, builds every fill and judge request, and checks each with `pulpermill.contract.parse_request` through `evals/cardfill/tools/check_requests.py`. It needs no backend and writes nothing.
   - `--judge` asks the `judge` call for the card's model-judged rules after each fill and records which fired and which went unanswered (`judge_missing`). The judge cache is cleared before each call so every run asks again.
   - **Behaviour changed from the old runner:** it used to attach every character note to one character. It now creates one character per character note, in order, so cases 3, 4, 6, 8 and 10 fill all of their characters. A chapter-only case still gets one character.
   - Added `--out DIR` so tests do not write into the kit. `results/` has its own `.gitignore`.
7. **Scoring summary.** `evals/cardfill/tools/summarize_scoring.py`, with `--probes A [B]` and `--cases A [B]`. Per probe, per tier and in total it counts right, wrong-flagged and wrong-silent, and with a second sheet prints the difference. Case sheets are summed by boundary errors (silent and flagged), because a case row has no "right" count.
8. **Trials.** `evals/trials/README.md` has its new first paragraph and nothing else changed.
9. **This report.**

## Things the schema or the protocol made awkward (nothing made a probe impossible)

- **`control-damaged` has no bucket.** The protocol has four results for a probe row (right, wrong-flagged, wrong-silent, control-damaged), and the plan says a damaged control "counts as wrong". It does not say which wrong bucket. The summary shows control-damaged in its own column and in none of the three. I did not change the three buckets. **Decision for you:** keep it separate, or say it counts as wrong-silent (a damaged control is never covered by a rule).
- **E2 can only be silent.** A tie can only end at an existing character or group, so the error it invites is a group written into free text or a dropped tie. Both pass every rule.
- **No rule covers `chapter_count`.** The old plan said 5 to 10; the schema says any whole number ("a budget; forced in code"). The plan now says a whole number, and U7 only tests that a stated count is kept. Whether code should force a range is a schema decision, so I left it.
- **World places and objects have no cap** (`uncapped=True`), so the old "caps of 5" language for places no longer held. The plan now says so for cases 6 and 12 (every place should appear).
- **U6 is Tier 1 with a caveat.** `normal_is_concrete` is judged by a model and might catch the vaguest restatement. The catalog says so. It will only be known when `--judge` runs on a real model.
- **No rule asks for a protagonist's tie to be used,** and `protagonist_has_tie` is advice only, so a Setup that picks a tie-less character is right with a warning.

## Outside my area (for P7.5 or you; I did not edit them)

- `docs/backend-notes.md` line 43 says the runner fills "every fixture in `tests/cardfill/fixtures`". The fixtures are in `evals/cardfill/fixtures`, and the runner now takes `--judge`, `--runlog`, `--out` and `--dry`.
- `pulpermill/prompts/templates/en/fill.yaml` says its scope lines come from `evals/cardfill/00-test-plan.md`. That table was rewritten (Setup no longer invents a goal; Entanglements no longer invents knowledge or pressures). If P7.5 keeps that template, it should be checked against the new table.
- `tools/run_trials.py` and `tests/prompts/trial_set.py` are still on this branch because P7.5 had not landed; the trials README says they are removed, which is true once P7.5 merges.

## What a person still has to do by hand

- **Case 9** has not been read by a native Chinese reader. This was true before and is still true. I edited one line of it (removed "人人都知道").
- **Grade the results.** Nothing here grades. Every Tier 1 probe and every case needs a human read (protocol, "Human sample").
- **Run against a real model.** The stub and the fake backend only prove the mechanics. The `--judge` results with the stub say nothing about quality.
- **Run the judged rules on the upstream sets.** They are hand-checked, not guaranteed warning-free.
- **Decide on the open items above:** where `control-damaged` goes, whether `chapter_count` needs a range rule, and whether to read P0 against the retired list.
- **Check the new probes' tiers once the judge has run** (U6, and E3's flag rate), and re-tier if a rule turns out to catch more or less than the catalog says.
- **Check case 6 and case 12 by hand for places:** the cases give nine and more than five places, and nothing caps them.
