# Fixtures

Each file in `projects` is one input, shaped like a project file: `title`, `schema_version`, `output_language`, an optional `example_chapter`, the `card_notes`, and, for Entanglements and Setup probes, the fixed upstream cards (characters, world, and for the Setup probes entanglements). Character notes leave `character` unset: the pipeline creates the character from the note and assigns its id.

`manifest.json` says what each fixture is for: its id, whether it is a probe or a case, the probe it belongs to and its target, its role (tempting, control, or a variant), which cards the fill should produce (`fill`), and which upstream set it uses.

- 62 probe fixtures and 12 case fixtures (74 in all).
- Cases fill the chain in order, each card reading the cards before it. A notes-only case fills only the cards that have a note. A chapter case fills all five. A probe fills one card.
- `output_language` is `en` for everything except case 9 (`zh-Hans`). The field is free text, so change it to whatever the UI language setting actually holds.
- Regenerate everything with `python tools/make_fixtures.py` after editing a case file or `02-probe-inputs.md`.

## Known mismatches with the current schema

Every card and field is required everywhere for now, and that will be relaxed later. Until then, these files describe the intended design, so some of them will not load against `Project` as it is written today:

1. A project with no cards is rejected. `Project` requires every card, and `test_a_project_missing_a_card_is_rejected` pins that. Fixtures hold only the cards a probe needs.
2. A note for the Characters card must name a character. The `note_character_for_characters` rule blocks one that does not, and `note_unique_per_target` would then treat two unlinked character notes as duplicates.
