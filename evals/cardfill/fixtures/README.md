# Fixtures

Each file in `projects` is one input, shaped like a project file: `title`, `schema_version`, `output_language`, an optional `example_chapter`, the `card_notes`, and, for Entanglements and Setup probes, the fixed upstream cards (characters, world, and for the Setup probes entanglements). Character notes leave `character` unset: the pipeline creates the character from the note and assigns its id.

`manifest.json` says what each fixture is for: its id, whether it is a probe or a case, the probe it belongs to and its target, its role (tempting, control, or a variant), which cards the fill should produce (`fill`), and which upstream set it uses.

- 53 probe fixtures and 12 case fixtures (65 in all).
- Cases fill the chain in order, each card reading the cards before it. A notes-only case fills only the cards that have a note. A chapter case fills all five. A probe fills one card.
- `output_language` is `en` for everything except case 9 (`zh-Hans`). The field is free text, so change it to whatever the UI language setting actually holds.
- Regenerate everything with `python evals/cardfill/tools/make_fixtures.py` after editing a case file or `02-probe-inputs.md`. A second run changes nothing.

## What "valid" means here

`tests/evals/test_fixtures_valid.py` loads every fixture as a `Project` under schema version 3 and rejects any key the schema no longer has. A fixture is a project nobody has finished starting, so the card the fill must produce (and Style and Setup, which the kit never provides) are absent on purpose; nothing else may be missing or broken, and every tie, holding and note must point at something the fixture holds.

One thing is deliberate: a note for the Characters card leaves `character` unset, because the character does not exist yet. The runner (`tools/run_cardfill.mjs`) creates one character per such note, in order, and attaches the note to it before the fill.
