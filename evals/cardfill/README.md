> **Note (P6a):** the case text, `01-probe-catalog.md` and `02-probe-inputs.md` predate the redesign and may still mention removed fields (pressures, knowledge, goal and stakes, rule status and truth). They are to be revised in P6b. Only the upstream sets and fixtures have been migrated to the new schema.

# Card-fill test kit

This kit tests how well the Pulpermill pipeline turns free-form text into cards. The text is an example chapter, per-card notes, or both. The cards are Style, Characters, World, Entanglements and Setup. The results are used to tune the card-fill prompts.

There is no answer key. A fill is judged against the schema's own rules and a short set of checks, and the checks that matter most are the ones a user who glosses over the values would not notice.

## The idea in brief

- The user reads and edits every card. The example chapter and notes mainly exist so the user is not faced with empty fields. A flat or ugly card gets fixed by the user. A card that looks fine but is wrong (an owner written into an object, a theme written as a goal, a wrong Hidden/Myth choice) can slip through and teach the wrong habit.
- Each result is scored in one of three buckets: **right**, **wrong but flagged** (a rule or warning fired and covers the problem), or **wrong and silent** (nothing fired). The aim is zero silent errors.
- There are two kinds of test input. **Cases** are realistic whole inputs that test everything at once. **Probes** are tiny inputs that isolate one field or boundary, so you can tune a prompt against one failure at a time.

## What is in the folder

| Path | What it is |
| --- | --- |
| `00-test-plan.md` | The plan: principles, what is out of scope, the checks, the scope rule, a table of what is planted in each case, which probes each case overlaps, and how to run |
| `01-probe-catalog.md` | The 29 probes: target field, tempting input, clean control, what "right" looks like, which rule should flag a wrong result, and tier |
| `02-probe-inputs.md` | The actual pasteable text for every probe (62 inputs) |
| `03-scoring-protocol.md` | How to run a fixture and grade the result |
| `case-1` to `case-12` (`.md`) | The 12 cases. Each file has only pasteable input, with no labels |
| `upstream/` | Three fixed, hand-written sets of cards (A, B, C) that give the Entanglements and Setup probes a stable foundation |
| `fixtures/` | Every case and probe as a project-shaped file (`projects/`), plus `manifest.json` saying what each one is for |
| `scoring/` | `probe-scoring.csv` (186 rows) and `case-scoring.csv` (36 rows), blank templates to fill in |
| `tools/` | `make_fixtures.py` and `make_scoring.py`, which regenerate the fixtures and the sheets from the source files |

## How the pieces fit

1. **Inputs** are written in the case files and `02-probe-inputs.md`. These are the source of truth.
2. **`make_fixtures.py`** turns them into fixtures: one JSON file per input, shaped like a project file (`title`, `schema_version`, `output_language`, an optional `example_chapter`, `card_notes`, and for some probes the upstream cards). The manifest records, for each fixture, whether it is a probe or a case, which cards the fill should produce, and which upstream set it uses.
3. **You run the pipeline** on each fixture, three times.
4. **You grade** each result using the scoring protocol and record it in the sheets. **`make_scoring.py`** builds the blank sheets from the manifest and the catalog.
5. **You tune** the prompts, bump `prompt_version`, rerun the affected probes and overlapping cases, and compare.

## Cases and probes

- **The 12 cases** cover different genres, input modes (chapter only, notes only, both) and difficulty. Cases 1 to 9 are the main set. Case 4 has deliberately blurred notes, case 6 is overstuffed, case 8 is one-liners, and case 9 is in Simplified Chinese. Cases 10 to 12 are messy inputs: fragmentary notes with typos, a chapter that is almost all action, and a long fact-rich chapter.
- **The 29 probes** are grouped by card: Style (S1 to S4), Characters (C1 to C8), World (W1 to W5), Entanglements (E1 to E7) and Setup (U1 to U5). Most come as a **tempting** input that invites a mistake and a **control** that is the clean version. Comparing them shows whether a prompt change fixes the mistake or just deletes valid content.
- Probes marked **Tier 1** are ones where no rule would flag a wrong fill, so a wrong result can only be silent. Start tuning there. **Tier 2** probes have a rule or warning that should flag a wrong result. The ones you named are marked ★: an owner inside an object (W1, E1), a theme written as a goal (U1), and a wrong Hidden/Myth/Common choice (W3).
- The plan's case-overlap table says which probes each case also exercises. When a case result is wrong, find the matching probe and tune against that.

## The scope rule

A fill may create freely inside its own card and may only link to what earlier cards already hold. World can invent groups, but Entanglements may only create ties, holdings, knowledge and pressures among items that already exist. Setup must pick an existing character as the protagonist. Each fill reads its own note (or the example chapter) and the earlier cards' data, never earlier cards' notes. A note that holds another card's material is the user's responsibility, so the test only checks that the material stays out of the wrong card.

## The upstream sets

Entanglements and Setup are filled from the earlier cards, so a bad World fill would make a later failure look like Entanglements' fault. The probes avoid this by starting from fixed, hand-written, schema-valid cards:

- **A (Tern Station):** used by E1 and the Setup probes (U1 to U5). The Lattice is unowned, there is a Hidden rule, and for the Setup probes there are ties and a pressure.
- **B (Quay Street):** used by E2, E4, E5 and E6. It has a Hidden rule and a Myth rule, and no Dockhands' Brotherhood, so E2's tempting input names a group that does not exist.
- **C (Thimble Hollow):** used by E3 and E7. It has the applewood Myth.

The cases do not use these. They run chained, with each card reading the pipeline's own earlier cards.

## Running a test

1. Pick a fixture from `fixtures/manifest.json`.
2. Run the fill for the cards listed under `fill`. A character note leaves `character` unset, and the pipeline creates the character and assigns its id.
3. Run the structure checks and the schema's block and warn rules, and write down which rules fired on which field.
4. Grade the result before looking at the flags, then record it.
5. Repeat three times. Full detail is in `03-scoring-protocol.md`.

## Changing things

- **Edit a case or a probe input:** change `case-N.md` or `02-probe-inputs.md`, then run `python tools/make_fixtures.py` and `python tools/make_scoring.py`.
- **Add a probe:** add a row to `01-probe-catalog.md` and a section to `02-probe-inputs.md` (a heading `### X9 · target`, then a label line and a fenced block for each input). If it needs upstream cards, add it to the `UPSTREAM` table in `make_fixtures.py`. Then rerun both scripts.
- **Change an upstream set:** the sets are built from `upstream/*.json`. Edit the JSON, then rerun `make_fixtures.py` so the fixtures pick it up.

## Known limits

- **The model-judged warnings were never run** on the upstream cards or the fixtures. The package was checked with a script covering the structural rules (shape, links, allowed holder types, truth on exactly the Myth rules, no names where there should be none), and the tempting and control inputs were hand-checked against the judge prompts. The upstream cards are hand-checked, not guaranteed warning-free.
- **The fixtures do not load against `Project` as written today.** Every card is required, and a Characters note must name a character. Both are expected for now. The fixtures follow the intended design, which is that a project can be saved with missing cards, and that a character note creates its character.
- **Case 9 has not been checked by a native Chinese reader.** Do that before trusting any language-related result.
- **Case 12 is about 2,200 words.** Whether that stresses the fill depends on your context size, so extend it if you want a real limit test.
- **`output_language` is `en` or `zh-Hans`.** The field is free text, so change it to whatever your UI setting actually holds.
- **Out of scope:** notes that contradict the chapter, how many characters a chapter-only fill creates, end-of-story updates, chapter generation, judge calibration, a plain-prompt baseline, and speed and token metrics beyond noting failed or retried calls.
