# Card-fill test kit

This kit tests how well the Pulpermill pipeline turns free-form text into cards. The text is an example chapter, per-card notes, or both. The cards are Style, Characters, World, Entanglements and Setup (schema version 3). The results are used to tune the card-fill prompts.

There is no answer key. A fill is judged against the schema's own rules and a short set of checks, and the checks that matter most are the ones a user who glosses over the values would not notice. The kit works with any prompter (the stub or a real one): it measures, it does not write prompts and it does not judge quality.

## The idea in brief

- The user reads and edits every card. The example chapter and notes mainly exist so the user is not faced with empty fields. A flat or ugly card gets fixed by the user. A card that looks fine but is wrong (an owner written into an object, a tie that points the wrong way, a Setup that repeats the character card) can slip through and teach the wrong habit.
- Each result is scored in one of three buckets: **right**, **wrong but flagged** (a rule or warning fired and covers the problem), or **wrong and silent** (nothing fired). The aim is zero silent errors.
- There are two kinds of test input. **Cases** are realistic whole inputs that test everything at once. **Probes** are tiny inputs that isolate one field or boundary, so you can tune a prompt against one failure at a time.

## What is in the folder

| Path | What it is |
| --- | --- |
| `00-test-plan.md` | The plan: principles, what is out of scope, the checks, the scope rule, what is built into each case, which probes each case overlaps, and how to run |
| `01-probe-catalog.md` | The 26 probes: target field, tempting input, clean control, what "right" looks like, which rule should flag a wrong result, and tier |
| `02-probe-inputs.md` | The actual pasteable text for every probe (53 inputs) |
| `03-scoring-protocol.md` | How to run a fixture and grade the result |
| `CHANGES.md` | What changed from the earlier kit: every probe and case as kept, revised, retired or new, with the reason |
| `case-1` to `case-12` (`.md`) | The 12 cases. Each file has only pasteable input, with no labels |
| `upstream/` | Three fixed, hand-written sets of cards (A, B, C) that give the Entanglements and Setup probes a stable foundation |
| `fixtures/` | Every case and probe as a project-shaped file (`projects/`), plus `manifest.json` saying what each one is for |
| `scoring/` | `probe-scoring.csv` (159 rows) and `case-scoring.csv` (36 rows), blank templates to fill in |
| `tools/` | `make_fixtures.py` and `make_scoring.py` (regenerate the fixtures and the sheets), `summarize_scoring.py` (adds up filled sheets), `check_requests.py` (the contract check behind `--dry`) |
| `results/` | Where the runner writes (not kept in git) |

The runner is `tools/run_cardfill.mjs` at the repo root.

## How the pieces fit

1. **Inputs** are written in the case files and `02-probe-inputs.md`. These are the source of truth.
2. **`make_fixtures.py`** turns them into fixtures: one JSON file per input, shaped like a project file (`title`, `schema_version`, `output_language`, an optional `example_chapter`, `card_notes`, and for some probes the upstream cards). The manifest records, for each fixture, whether it is a probe or a case, which cards the fill should produce, and which upstream set it uses.
3. **The runner** fills each fixture three times through the page's own client and logic, and writes what came out and which code rules fired (and with `--judge`, which model-judged rules fired).
4. **You grade** each result using the scoring protocol and record it in the sheets. **`make_scoring.py`** builds the blank sheets from the manifest and the catalog.
5. **`summarize_scoring.py`** counts right, wrong-flagged and wrong-silent per probe, per tier and in total, and compares two filled sheets.
6. **You tune** the prompts, bump the prompter's `version`, rerun the affected probes and overlapping cases, and compare.

## Cases and probes

- **The 12 cases** cover different genres, input modes (chapter only, notes only, both) and difficulty. Cases 1 to 9 are the main set. Case 4 has deliberately blurred notes, case 6 is overstuffed, case 8 is one-liners, and case 9 is in Simplified Chinese. Cases 10 to 12 are messy inputs: fragmentary notes with typos, a chapter that is almost all action, and a long fact-rich chapter.
- **The 26 probes** are grouped by card: Style (S1 to S4), Characters (C1 to C8), World (W1, W2, W5), Entanglements (E1 to E4, E8, E9) and Setup (U2, U3, U5, U6, U7). The gaps in the numbering are retired probes; ids are never reused. Most come as a **tempting** input that invites a mistake and a **control** that is the clean version. Comparing them shows whether a prompt change fixes the mistake or just deletes valid content.
- Probes marked **Tier 1** are ones where no rule would flag a wrong fill, so a wrong result can only be silent. Start tuning there. **Tier 2** probes have a rule or warning that should flag a wrong result. The one you named is marked ★: an owner inside an object (W1, E1).
- The plan's case-overlap table says which probes each case also exercises. When a case result is wrong, find the matching probe and tune against that.

## The scope rule

A fill may create freely inside its own card and may only link to what earlier cards already hold. World can invent groups, but Entanglements may only create ties and holdings among items that already exist. Setup must pick an existing character as the protagonist. Each fill reads its own note (or the example chapter) and the earlier cards' data, never earlier cards' notes. A note that holds another card's material is the user's responsibility, so the test only checks that the material stays out of the wrong card.

## The upstream sets

Entanglements and Setup are filled from the earlier cards, so a bad World fill would make a later failure look like Entanglements' fault. The probes avoid this by starting from fixed, hand-written, schema-valid cards. See `upstream/README.md` for what each set holds and which probes use it.

The cases do not use these. They run chained, with each card reading the pipeline's own earlier cards.

## Running a test

```
python -m pulpermill.backend --fake          # canned replies, to try the mechanics
node tools/run_cardfill.mjs --dry            # no backend: builds every request and checks it against the contract
node tools/run_cardfill.mjs http://127.0.0.1:8000 --runs 3 --label stub-v1 --runlog path/to/run.log [--judge] [--only s1-tempting,case-1]
```

1. Pick the fixtures (all, or `--only` some by id from `fixtures/manifest.json`).
2. The runner fills the cards listed under `fill`. A character note leaves `character` unset, and the runner creates one character per note and assigns its id.
3. It records, per fixture, run and card: whether the call worked, what was filled, and the rules that fired. `meta.json` and `summary.csv` carry the prompter's name and version (from `--runlog`), so two result sets can be compared.
4. Grade the result before looking at the flags, then record it. Full detail is in `03-scoring-protocol.md`.

## Changing things

- **Edit a case or a probe input:** change `case-N.md` or `02-probe-inputs.md`, then run `python evals/cardfill/tools/make_fixtures.py` and `python evals/cardfill/tools/make_scoring.py`.
- **Add a probe:** add a row to `01-probe-catalog.md` and a section to `02-probe-inputs.md` (a heading `### X9 · target`, then a label line and a fenced block for each input). Use a new id, never a retired one. If it needs upstream cards, add it to the `UPSTREAM` table in `make_fixtures.py`. Keep it only if a wrong result would not be flagged by a rule. Then rerun both scripts.
- **Change an upstream set:** the sets are built from `upstream/*.json`. Edit the JSON, then rerun `make_fixtures.py` so the fixtures pick it up.
- `tests/evals/` checks that the manifest, the catalog, the inputs, the cases and the scoring sheets list the same probes and cases, that every fixture is a valid project, and that none of the removed ideas appear in the kit.

## Known limits

- **The model-judged warnings have not been run** on the upstream cards or the fixtures. The upstream cards are hand-checked, not guaranteed warning-free.
- **Case 9 has not been checked by a native Chinese reader.** Do that before trusting any language-related result.
- **Case 12 is about 2,200 words.** Whether that stresses the fill depends on your context size, so extend it if you want a real limit test.
- **`output_language` is `en` or `zh-Hans`.** The field is free text, so change it to whatever your UI setting actually holds.
- **The runner fills every character a case has a note for,** and one character for a chapter-only case. A chapter that names several people gets only one character card from the runner; fill the rest by hand in the page if you want them.
- **Out of scope:** notes that contradict the chapter, how many characters a chapter-only fill creates, end-of-story updates, chapter generation, judge calibration, a plain-prompt baseline, and speed and token metrics beyond noting failed or retried calls.
