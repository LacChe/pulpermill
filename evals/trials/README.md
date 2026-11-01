# The chapter trials

A kit that plays whole stories through any prompter, chapter by chapter, and lets a person read and compare them. It is for tuning the `plan` and `generate` wording (schema version 3), in the same spirit as the card-fill kit in `evals/cardfill/`. The kit measures. It never writes prompts and it never grades quality by itself: the machine checks flag, a person scores.

## What is in the kit

| Path | What it is |
| --- | --- |
| `stories/*.yaml` | The source of truth: each story written with names, not ids (cards, ties, holdings, setup, what it tests, which chapters to read first) |
| `projects/*.json` | One ready-to-run project file per story: cards filled, schema version 3, ids that are the same on every build, no chapters yet |
| `manifest.json` | What each trial is and what it tests |
| `rubric.md` | The reading rubric (ten lines scored 0 to 2) and what each machine column means |
| `scoring/chapter-scoring.csv` | The blank sheet: one row per trial, run (1 to 3) and chapter |
| `tools/make_projects.py` | Builds `projects/` and `manifest.json` from `stories/` (`--check` compares without writing) |
| `tools/make_scoring.py` | Builds the sheet from the manifest (`--check` as above) |
| `tools/check_requests.py` | The contract check behind `--dry` |
| `results/` | Where the runner writes (not kept in git) |

The tools at the repo root are `tools/run_trials.mjs` (the runner), `tools/trial_checks.mjs` (the machine checks) and `tools/summarize_trials.py` (adds up the sheets).

## The seven trials

| Trial | Story | Lang | Genre | Person / tense | People | Chapters | Protagonist has ties | Ties to groups |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `t1-salt-coast` | The Salt Coast | en | Harbour noir | first / past | 3 | 8 | yes | 1 of 3 |
| `t2-quiet-orchard` | The Orchard Year | en | Quiet domestic fiction | third / past | 2 | 5 | yes | 1 of 3 |
| `t3-star-ferry` | The Ferry That Was Always Late | en | Workplace space comedy | third / present | 5 | 10 | yes | 1 of 6 |
| `t4-hollow-court-zh` | 空庭记 | zh | 宫廷权谋 | third / past | 4 | 6 | yes | 1 of 4 |
| `t5-lantern-road` | The Lamplighter's Road | en | Cozy fantasy | first / present | 3 | 7 | no | 1 of 3 |
| `t6-glass-harbour` | The Glass Harbour Audit | en | Political thriller | third / past | 4 | 9 | yes | 3 of 6 |
| `t7-last-light` | The Last Light on Kestrel Rock | en | Island drama | first / past | 3 | 5 | yes | 1 of 4 |

What each one tests:

- **`t1-salt-coast`**: Noir pressure story, first person past, terse and dry; Three people; the protagonist is at the end of two ties; Groups at the end of ties and holdings (a group tie can be the spotlight); Eight chapters: a full arc with a middle.
- **`t2-quiet-orchard`**: Smallest cast: two people, so every chapter has the same cast; Quiet, lingering, melancholic third person: little plot, so a chapter can easily repeat the last; Five chapters, so chapter 5 is the last chapter and must close the story.
- **`t3-star-ferry`**: Largest cast (five) and longest run (ten chapters); Absurd comedy in third person present: tests tense drift and humour without a list of jokes; Many ties from one protagonist, so the spotlight varies; minor characters must stay roles with no names.
- **`t4-hollow-court-zh`**: Simplified Chinese story: the instructions stay in English, the story is in Chinese; Ornate, melancholic third person past in Chinese; person and tense heuristics are skipped, length counts characters; Four people, ties to a group (the household office).
- **`t5-lantern-road`**: The protagonist is at neither end of any tie: every spotlight is a tie between other people, and the protagonist must be drawn into it; First person present, cozy fantasy; Seven chapters.
- **`t6-glass-harbour`**: Political thriller with two groups; most ties run to a group, so spotlights are often a person against an institution; Terse, clinical, subtext; named minor officials are likely and are flagged; Nine chapters.
- **`t7-last-light`**: Short run of five chapters that has to reach a close (last chapter); First person past, melancholic and lush, with a protagonist who has one tie; Three people on an island: little room for minor characters.

Cast sizes run from 2 to 5, chapter counts from 5 to 10, and the last chapter of every trial is the last chapter of its story, so each trial includes an opening and a close. The manifest's `read` list names the first, a middle and the last chapter of each trial: read those first if there is no time for all of them.

## How to run

```
python -m pulpermill.backend --fake                          # canned replies, to try the mechanics
node tools/run_trials.mjs --dry                              # no backend: builds and checks every request against the contract
node tools/run_trials.mjs http://127.0.0.1:8000 --runs 3 --label writer-0.2 --runlog path/to/run.log [--only t1-salt-coast,t5-lantern-road] [--chapters 3]
python tools/summarize_trials.py evals/trials/scoring/chapter-scoring-writer-0.2.csv --machine evals/trials/results/writer-0.2
python tools/summarize_trials.py --compare sheet-a.csv sheet-b.csv --machine-a results/a --machine-b results/b
```

The runner plays each trial through the page's own client and logic. It starts the story (the start gate, then the five cards are locked), and for each chapter: picks the spotlight tie and the cast the way the page does, adds one more person to the cast in every second chapter (so cast sizes vary within a trial), plans the beat, writes the chapter, and commits the chapter, its events and its shifts together, so the next chapter plans from the new state. It works against the fake backend (`--fake`), against a server whose Config says `prompter: stub`, and against any real prompter. Options: the backend address (and `--token`), `--runs` (default 3), `--chapters N` (play only the first N chapters), `--only`, `--label`, `--out`, `--runlog` and `--dry`.

`--runlog` is the server's run log (`Config.log_path`). Its first line says the prompter's name and version, which go in `summary.csv` and `meta.json`, so two result sets can be told apart. Change the prompter's `version` string whenever its wording changes, then run again under a new `--label`.

A run writes, in `results/<label>/`:
- `<trial>-run<n>.md`: the chapters, each with its beat, its spotlight tie, what happened, what changed, its shifts and its flags. **Read this first.**
- `summary.csv`: one row per trial, run and chapter, with the machine checks.
- `meta.json`: the label, the time, the address, the prompter's name and version, the options and how many chapters failed.
- `<trial>-run<n>.json`: the finished project, for anything the other files do not show.

A chapter whose plan or generate call fails stops that run of that trial; the failure is a row in `summary.csv` and the runner exits 1 at the end.

## How to read the results

1. Read two or three chapters of a run in order, with the beat and the spotlight tie above each. Score them with `rubric.md` in a copy of `scoring/chapter-scoring.csv` (for example `chapter-scoring-writer-0.2.csv`), before you look at the flag columns.
2. Then look at the flags in the `.md` file and `summary.csv`. They say where to look: a length outside 250 to 2500 words, a drift in person or tense, an opening or sentences repeated from an earlier chapter, a spotlight edge that no shift moved, an empty `changed` line, more shifts than the cap of 7, and capitalised names that are on no card. A flag is a lead, not a verdict. Note in `flags_that_were_right` which ones were true.
3. `python tools/summarize_trials.py <sheet> --machine <results dir>` adds up the sheet per trial (the mean share of the possible score, and the mean of each rubric line) and counts the flags. `--compare A B` puts two sheets side by side and marks every line that moved by 0.5 or more.

The Chinese trial (`t4-hollow-court-zh`) needs a native reader for `style_fit` and `minor_roles`. Length there is counted in Han characters, the person check counts 我 against 他/她/它, there is no tense check and no name check.

## Things to know

- **The stub's chapters are constant text**, so a run against the stub flags short chapters and repeated openings in every chapter. That is expected: it proves the kit runs, not that the prompts are good. The same holds for the fake backend.
- **The machine checks are simple.** Person and tense are counted from pronouns and common verb forms outside dialogue; the name check reads capitalised words in the middle of a sentence, so it misses a name that starts a sentence and flags a few ordinary words. The exact rules are in the header of `tools/trial_checks.mjs`.
- **A trial is the same on every run.** The cast and the spotlight are picked from the project and the chapter, so only the model changes between runs. Never edit a story once results exist; add a new trial instead (a new `stories/*.yaml`, then `make_projects.py` and `make_scoring.py`).
- **Chapter regeneration and stale beats** are covered by the end-to-end test (`tests/e2e/`), not here.
- Stories are written to be valid under the schema and to pass the start gate. The model-judged warnings have not been run on them.

## Changing the kit

- **Edit or add a story:** change `stories/<id>.yaml` (every name used in a tie, holding or setup must be a character or an item of the world), then run `python evals/trials/tools/make_projects.py` and `python evals/trials/tools/make_scoring.py`.
- `tests/evals/test_trials_kit.py` checks that the stories, projects, manifest, sheet and this README agree, and that every trial is a valid project. `tests/evals/test_run_trials.py` runs `--dry`, a run against the fake backend and one against the stub prompter, and the summary script. `tests/evals/trial_checks.test.mjs` tests the machine checks.
- The earlier harness (`tools/run_trials.py`, `tests/prompts/trial_set.py`) was removed in P7.5 and exists at the git tag `pre-prompt-design`. This kit replaces it.
