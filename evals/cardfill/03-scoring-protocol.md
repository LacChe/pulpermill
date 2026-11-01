# Scoring protocol

How to run the fixtures and record what happened. Results go in `scoring/probe-scoring.csv` (one row per probe fixture per run) and `scoring/case-scoring.csv` (one row per case per run). Both open in any spreadsheet. Each has three rows per fixture, one for each run.

## What to record on every row

- `prompt_version` and `model_and_settings`: free text, filled the same way on every row of a run, so results from different prompt versions can be compared. `prompt_version` is the prompter's `name` and `version` as the runner recorded them (`meta.json`, or the prompter columns of `summary.csv`).
- `calls_failed_or_retried`: how many calls failed, hit a shape retry, or were retried for language drift. A card that only comes out on the second attempt is a finding, even when the final card is good.
- `graded_by`: your initials, or "auto" for results from code checks.
- `notes`: anything surprising.

## The loop for one fixture

1. Run the fixture with `node tools/run_cardfill.mjs` (it fills the cards the manifest lists under `fill`; cases run the chain in order, each card reading the pipeline's own earlier cards; probes fill one card, from the upstream cards in the fixture). Results are in `results/<label>/<fixture>-run<n>.json`.
2. Run the structure checks from the plan on the output (code).
3. Take the schema's block and warn rules that fired from `summary.csv` (`rules_fired`, the code rules; `judge_fired`, the model-judged ones when the run used `--judge`) and write down which fired and on what field or item. A rule in `judge_missing` was not answered, which is not the same as passed.
4. **Grade first, then look at the flags.** Read the target in the output and decide whether it is right before you look at which rules fired. This keeps the flags from shaping your reading.
5. Record the result.

## Grading a probe

Use the `right_looks_like` column. Record exactly one result:

| Result | Meaning |
| --- | --- |
| right | The target is correct. |
| wrong-flagged | The target is wrong, and a rule or warning that covers that problem fired on the same field or item. |
| wrong-silent | The target is wrong and nothing covering it fired. This is the failure to drive to zero. |
| control-damaged | (Controls only.) The clean input came back changed for the worse: valid content was removed, or a problem was added. Counted as wrong-silent in the totals, because a damaged control is still a valid card and no rule covers it. |

Rules for deciding:
- **A flag counts only if it covers the problem.** A warning on an unrelated field, or about a different issue on the same field, does not make a wrong result "flagged." Write the rule ids that fired in `flags_that_fired`, and compare them to `expected_flag`.
- **A block rule that would have rejected the output counts as flagged.** Record the retry in `calls_failed_or_retried`.
- **Deleted is not translated.** If the fill removes the tempting content and leaves a required field blank, that is a structure failure. If it replaces it with correct material (for example turns "pass Mr. Hale's exam" into an abstract want), that is right.
- **Only the target is graded.** Anything else the fill invented is ignored, except that the same mistake showing up somewhere else on the card goes in `also_seen_elsewhere`.
- **Variants (C1 a and b, S4 excerpts, C8) are graded against their own expected value**, since each has its own control or is the other's control. S4: excerpt 1 is first person past, excerpt 2 is third person present.

## Grading a case

Fill one row per run:
- `structure_failures`: how many structure checks failed, and which.
- `stated_facts_dropped_or_changed`: any name, age, sex or appearance detail, or any listed place, thing, group or rule, that is missing or altered.
- `scope_invented_upstream`: any group, place, object, rule or character created by Entanglements or Setup that no earlier card holds.
- `boundary_wrong_silent` and `boundary_wrong_flagged`: how many boundary errors you found of each kind, with the details in `boundary_details`. Use `probes_to_look_for` to know where to look.
- `story_engine_0_to_2` and `distinctness_0_to_2`: a quick human read. 0 means you could not answer the question, 2 means it was clear.

## Runs and thresholds

- Run each fixture three times.
- **Solid:** tempting right in 3 of 3 runs and its control right in 3 of 3.
- **Flagged failure:** wrong in at least one run, but every wrong result was flagged.
- **Silent failure:** any wrong-silent result in any run. Fix these first.
- **Unstable:** a mix of right and wrong across runs.
- Target for Tier 1 probes: no silent failures. Tier 2 probes may show flagged failures, but a flag that fired on a result you judged right is a false alarm and worth noting.

## Human sample

- Grade every Tier 1 probe and every case by hand.
- For Tier 2 probes, hand-grade at least one run in three per fixture, chosen at random, and compare it with what the rules said. A disagreement means a rule is missing something or flagging something correct.

## Reporting and tuning

After each batch:
1. Count results per bucket per card (`python evals/cardfill/tools/summarize_scoring.py scoring/probe-scoring.csv scoring/case-scoring.csv`; give a second filled pair to see the difference).
2. List the silent failures by probe id, most important first (Tier 1, then the one you named: an owner in an object).
3. Make one prompt change at a time, bump the prompter's `version`, and rerun only the probes for that card plus the cases that overlap them (see `probes_to_look_for`).
4. Check that the change did not turn any solid probe into an unstable or damaged one.
5. Do not tune a prompt only to trigger or avoid a flag. The aim is fewer silent errors.
