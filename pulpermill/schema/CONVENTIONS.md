# Pulpermill schema: running conventions

Decided while writing cards, in chain order. Anything marked TEST is not yet exercised and may change when a later card needs it.

## Package contents
`pulpermill/schema/` (structure and declared rules, including `project.py`, the save-and-load file), `pulpermill/schema/text/en/` (all wording) and this file, plus `tests/schema/` at the repo root. The throwaway pipeline draft is not included; wherever this file mentions it, the pipeline is built from scratch.
- `tests/schema/test_lint.py` checks structure and text for every card and every language folder under `text/` (a new language is linted automatically). It holds no design decisions.
- `tests/schema/test_project.py` checks the project file: every card has a home, a full save/load round trip keeps ids, and its integrity rules are well formed.
- `tests/schema/test_decisions.py` pins the decisions made so far (the 5-item cap and its exceptions, the pairing table, plants, the card chain) plus sample cards. Update it on purpose when a decision changes.
- `tests/schema/helpers.py` holds shared helpers and two policy lists (`UNCAPPED`, `BLOCK_CHECKS`).
Run from the project root: `python -m pytest tests`.

## Translation
Translation is deferred until the English text is final, so wording changes are made once. To add a language: copy `text/en/` to `text/<lang>/` with identical keys, translate every value (labels and help for the human, and expansions, lead-ins, item templates and judge prompts for the model), leave every `{token}` unchanged, and run the tests: the lint and the parity test (same keys, same tokens in every template) already cover every folder under `text/`. The output language of the story is the same setting as the UI language, passed to the writer; it is never stored on a card. DECIDED (data-flow review): the writer is told the target language in English and model-facing text (expansions, lead-ins, item templates, judge prompts) is not translated; only the human-facing text (labels, help, rule messages and fixes) is. Code checks the output language and retries once if it drifted. When the second language is written, the parity test should cover the human-facing keys only; the procedure above is then reduced to those keys.

## Separation
The schema is data: `schema/` (structure and declared rules) and `text/` (all wording). Anything that runs, renders or checks lives outside `schema/` (the throwaway `pipeline_draft/` is not in this repo; the real pipeline and the UI are built from scratch). The UI is not wired yet.

## Files (per card)
- `pulpermill/schema/<card>.py`: structure only (Pydantic). Types, required, options, input type, group, render kind.
- `pulpermill/schema/text/<lang>/<card>.yaml`: all words. Labels, help, option expansions, lead-ins. One file per language, same keys.
- `pulpermill/schema/__init__.py`: registry of cards in chain order. `tests/schema/test_lint.py` runs the same lint over every registered card.
- `tests/schema/`: schema and text lint only. Imports nothing from the pipeline.
- `pipeline_draft/` (not in this repo): throwaway code that proved the schema works (prose rendering, rule checking). Not part of the schema, and the schema never imports it.

## Established by Style
1. **Everything is human editable, and everything is required by default** (the human will loosen this after review). A field is optional only if declared `required=False`. There is no read-only input type.
2. **Field render kinds** (how a field reaches the model):
   - `rule`: chosen option becomes a fixed rule sentence (person, tense).
   - `axis`: chosen option becomes descriptive prose via its expansion text.
   - `note`: free text passed through exactly as written.
   - `free`: free text passed through after a lead-in sentence containing `{value}`.
3. **One choice per axis, or none.** An empty axis means the model decides.
4. **Human-only vs model text.** `label`, `help`, `summary` never reach the model. Only `expand` and `lead_in` do. A test checks the rendered prose for leaks.
5. **Expansions use positive phrasing:** what to do, never what to avoid.
6. **Groups** have an id, a `collapsed` flag for the UI, and a label and help in the text file.
7. **Prose assembly order is declared in the structure** (`RENDER_ORDER`), not inferred from the form order. Style renders as two paragraphs, with Genre first.
8. **Group notes are ordinary `note` fields** named `<group>_note`.
9. **Internal keys avoid names that clash with the library** (e.g. the Register field is keyed `formality`; its label is still "Register").
10. **Lint tests required for every card:** each field has label and help; each option has label and expansion; no orphan text keys; groups and render order cover every field; required set is as expected.
11. **Translations** are a separate file per language with identical keys. A parity test is added when the second language is written (not yet).

## To exercise in later cards (TEST)
- Use counts on World list items (Characters' Behaviors are flagged `counted`).
- `ref_select` fields fed by other cards, and broken-link flags (Entanglements, Setup, Outline).
- Live and append-only cards, and who fills a field first (planner, extractor, code).
- Rules that read other cards (Style's name check gets its name lists from the project; see Rules).
- Fields rendered from several items (not a single value).

## Rules (warnings and rejections)
Three severities, one meaning each:
- **reject**: the value cannot be stored (not an allowed option, wrong type, more than 5 items in a list). Built in for every field from its Pydantic type, so cards never declare these.
- **block**: a draft can be saved, but generation cannot start (a required field is empty). Built in for every required field.
- **warn**: advice only; the human may ignore it. Cards declare these as `Rule` objects in `RULES`.

A `Rule` has: `id`, `severity`, `fields`, `when` (plain-English description), `check` (name of a code check), `context` (outside data the check needs, e.g. character and place names, supplied by the project), and `needs_model` (judgment call answered by a model pass instead of code).
- All wording lives in the text file: built-in messages in `text/<lang>/common.yaml`; card rules under `rules:` in the card's text file (`message`, `fix`, and `judge_prompt` for model checks).
- A warning may propose a fix but never applies one.
- The checker (the earlier draft is not in this repo) returns issues, the pending model checks, and `can_generate`.

## Input types
Real HTML only: `text` (<input type=text>), `textarea`, `number` (<input type=number>), `select`, `select-multiple` (<select multiple>). Lists, paired lists and options fed by another card are not single HTML controls; they get separate attributes when Characters first needs them.

## Limits
No text field has a maximum length: limits depend on model context with everything considered, so they are decided in the pipeline. The exception is **repeating lists, capped at 5 items** (`MAX_ITEMS` in `schema/common.py`). Stories run 5 to 10 chapters, so a cap of 5 lets list types rotate between chapters and lets an item recur for more depth. Going over the cap is a reject. Exceptions are declared one at a time with `uncapped=True` and listed in the lint test; so far only Entanglements' Ties (a cast has many). How items rotate is a pipeline matter, not decided here.

## Established by Characters
12. **Repeating lists.** A list field has `repeat=True` and `input=None`; its item model declares the real HTML inputs. Every item is an object with a system-made `id` (never typed), so use counts kept in project state survive edits. Single-box lists use `TextItem`; multi-box items (Behaviors) get their own item model.
13. **Two more render kinds.** `items` (single-box list joined into `{items}` in a lead-in) and `pairs` (multi-box list, each item rendered by an `item_template`, joined with `item_join`).
14. **Template tokens.** Text templates may use `{value}`, `{items}`, `{name}` (the card's own name field), and for item templates the item's field names. Lint rejects unknown tokens.
15. **Field flags.** `fixed=True`: a fact the story must never change, always sent in full (name, age, sex, appearance). `counted=True`: list items carry use counts in project state (Behaviors). Counts themselves are never stored on cards.
16. **Cards other cards link to** (Characters, World) carry an `id` like list items (`class Characters(Item)`), so links are ids. Characters is marked `many_per_project`.
17. **Rule params.** A code check can take `params` (e.g. `item_count` with a min). The only hard item limit is the cap of 5 on every list; the source docs' softer guidance (wants 2 to 4, behaviors up to 5) is replaced by that cap plus a warning for fewer than 2 wants.
18. **Rules that read other cards** use `context` (names of other characters and world things); the project supplies it.
19. **Source-doc "optional" markers** are kept as comments next to fields that are required by default for now, so they can be loosened later.

## Established by World
20. **Items with several boxes** are item models (Place, Thing, Power, WorldRule, Term), all rendered with an `item_template` (kind `pairs`; the name now covers any multi-box item).
21. **A choice inside an item** (a rule's status) is a normal `select` with options in the text file, under the item field. In an item template it renders as the option's `expand` text, which may use sibling item fields (a false rule's expansion carries `{truth}`).
22. **Conditionally required fields** are `required=False` plus a `block` rule using the `required_if` check (a rule widely believed but false must state the truth). `block` rules are allowed only for this.
23. **Rules that guard what drives the story** (friction, cost, pressure) are marked `# drives story` in the schema, so they can be reviewed together: everyday friction, place effects, object stakes, group presence, rule cost.
24. **Counted lists:** Places and Objects (the doc's priority for rotation). Groups, Rules and Terms are not counted.

## Established by Entanglements
25. **Links are ids, shown as names.** A field that points at another card has `ref=[...]` and is a `select` (or `select-multiple`). Each source is a card id (`characters`) or `<card>.<list field>` (`world.places`). Values are item ids; in templates a link token renders as the target's name. Linked selects have no `options` in the text file, because the choices come from the other card. Lint checks every source exists.
26. **Filtered choices.** A field can be filtered by another field in the same item (`ref_filter_by`). The pairing data is a table in the card file (`HOLDING_PAIRS`: what may hold what).
27. **Live fields.** `changes=True` marks fields that move during a story; unflagged fields are fixed once set. Only a `mutable` card may have them. How changes are proposed and applied is pipeline.
28. **Either/or and conditional fields** are `required=False` plus a `block` rule: `exactly_one` (a fact is a world rule or free text; a pressure has an agent or a circumstance), `required_if` (`when` a field has a value, or `when_present` another field is filled).
29. **Block rules are for structure the pipeline cannot work around:** `fields_differ`, `holding_pairs_allowed`, `ref_exists` (a link whose target was removed, flagged until fixed), `includes_value` (the cast has the protagonist), `tie_ends_in_cast` (the characters at both ends of the spotlight tie are in the cast), and for the hidden records `unique_across_items`, `at_least_one`, `max_per_group`. Lint keeps this list closed (`BLOCK_CHECKS` in `tests/schema/helpers.py`).
30. **Pressure rotation, spotlight and agent moves** are pipeline. The schema only holds the fields, the `changes` flags and a warning above three active pressures.

## Established by Setup
31. **Launch cards** (`type: launch`) are static, one per story, and read the cards before them. Setup needed no new field structure: a ref select (protagonist), free-text fields, and a number.
32. **Rule context** on a model-judged rule (`context=[...]`) names the project data the judge needs (the protagonist's wants, pressures, ties). The project supplies it; the schema only names it.
33. **Chapter count** has model wording like every other field, but the planner sees it as 'chapter n of N' and the writer is told when it is the last chapter (code forces the count either way).
34. **Setup holds no ending and no plan.** Its rules guard that the goal is an action, checkable, and connected to the other cards, and that the disruption is an event.

## Established by Outline
35. **Growing cards** (`between_chapters: "append"`) hold a list that gains one item per chapter. A beat is frozen while a chapter points at it; a beat nobody has written yet may be replaced (for example a stale one). The list is uncapped (it is bounded by the chapter count), declared like Ties.
36. **Who fills a field first.** Beat fields carry `filled_by="planner"|"code"|"human"` (the cast is picked by the human before Plan). Everything stays human editable (including the code-picked Spotlight); this only records who writes the first value.
37. **Code-limited choices.** `limited_by="code"` marks a select whose options the code may disable (Shift).
38. **Filtered link sources.** `ref_where={...}` limits which entries of a linked list may be picked (Reveal: only rules marked uncommon or false).
39. **Multi-select caps.** `max_selected=N` caps a multi-select (Cast, 5, a value I chose: the source doc only said "capped").
40. **Checkbox** is a real HTML type, used once for the frozen flag (`written`).
41. **More block checks,** all from the source doc's "checks with a retry": `includes_value` (cast has the protagonist), `unique_across_items` (a rule is revealed once), `all_or_none` (offstage change gives both parts), `legal_shift`, plus `required_if` with `unless` (the gap is needed after chapter 1).
42. **What stays pipeline:** choosing the spotlight, deciding legal shifts, spotlight rotation, offstage moves, and planning from state. The schema holds only the fields and the checks they must pass.

## Established by the summary records
43. **Records** (`type: record`, `hidden: True`) are pipeline-only (`between_chapters: "per_chapter"`): one entry per chapter, never edited by hand, and replaced as a whole when that chapter is regenerated. `sent_to_model` says whether they reach the writer (Events and Shifts do).
44. **Per-chapter versions.** Once the story starts, every card except the Outline is locked (a lock is a UI restriction only; P0 A12). Between chapters only the next beat can be edited. There is no history snapshot: what changes during the story is recorded as shifts (see 82), and the effective card going into any chapter is the base card plus the shifts of earlier chapters, computed by the page and never stored. The end-of-story Style, Characters, World and Entanglements (originals kept) live in the project file (`schema/project.py`, see below).
45. **Snapshot and patch kinds.** A field of kind `snapshot` holds a whole copy of another card (`snapshot_of`); a field of kind `patch` (shifts only) holds a partial copy of one. Neither has an input and neither is rendered.
46. **Resolutions go in the later entry.** Facts that resolve something earlier are recorded in the later entry. A plant is identified by the entry that planted it, and `paid_off` lists those entries. A replaced entry keeps its id, so links from later entries do not dangle (those later entries are stale until their chapters are redone).
47. **Plants:** at most one planted thing per chapter (a single field, not a list), at most two open plants (a block rule), and at most two payoffs per chapter.
48. **Counts are tallied, not stored.** Use counts for behaviors (`behaviors_seen`), things (`things_seen`), places (Outline `where`) and characters (Outline `cast`) are computed from the entries, so a resumed story cannot lose them. Counts are always recounted by id, never kept. A character's "last appeared" chapter is likewise derived, from the cast lists of the earlier Outline beats.
49. **Flat lists with a beat link** (Shifts: one entry per card per chapter) keep every list item the same shape, and the 7-entries-per-chapter limit is a `max_per_group` rule grouped by beat.
50. **`filled_by`** may also be `"extractor"` (the post-chapter step), alongside `"planner"` and `"code"`.

## Established by the project file (`schema/project.py`)
51. **The project is the save-and-load file, not a card.** It holds every card as it stands now, the three records, the written chapters, the optional end-of-story copy, and what the user gave the model to fill cards from (example chapter, per-card notes) plus the field locks (see the data-flow review below). It is written and read as JSON, with every id preserved, so a user or the pipeline can stop mid-story and resume from the file alone. `CARD_FIELDS` maps every registered card to its project field and a test fails if a new card is not added.
52. **Cards are embedded, not referenced.** The portable root cards (Style, Characters, World) are copied into the project, so a file is self-contained. A project holds any number of characters (an uncapped list, a deliberate exception like Ties).
53. **Chapter text** is its own list (`Chapter`: beat link and text). Regenerating a chapter replaces its text and its records (events and shifts), reuses its beat, and marks every later beat stale.
54. **Chapters are committed whole.** The backend is stateless: the page sends everything a call needs and commits what comes back as one unit (chapter text, events and shifts). A chapter is complete or does not exist, so there is no resume point and no interrupted chapter; a failed or stopped call changes nothing and is redone by pressing generate again.
55. **End-of-story copy** (`after_story`): updated copies of the portable root cards (Style, Characters, World). The originals stay untouched in the project, so a new story can start fresh or from the copy, and the user can download it. It may exist only when every chapter up to Setup's chapter count is written, and it keeps the originals' ids.
56. **Project rules** are block-only integrity checks with no user wording (a failure means a damaged or half-saved file). They are declared in `PROJECT_RULES` like card rules.
57. **Kind `card`** marks a project field that holds a whole card (`card_of` says which). `schema_version` lets older files be recognised and migrated.
58. **Rule status labels** (World): Common knowledge, Hidden, Myth. The stored keys (`common`, `uncommon`, `false_belief`) and the model wording did not change. Rule types were removed from World.

## Established by the data-flow review
59. **The user's workflow** (the flow diagram) is: open the page and connect the backend; optional setup (import a project, import individual cards, paste an example chapter); a card loop (optional free-form notes, optional model fill, then the required human fill or adjust); a chapter loop (generate, optionally regenerate after adjusting cards); export (cards, story, project file; only the story export is required). Outline is part of the card loop (chapter 1's beat is generated or typed). Beats are made by a separate Plan button (chapter 1 included): the user picks the cast, presses Plan, assesses the beat, replans if wanted, then generates. Events and shifts are made inside generate chapter. Generating or regenerating uses the values on screen plus whatever summaries the chapter needs; regenerating marks later beats stale (see 66).
60. **Example chapter and card notes** live on the project, not on cards, so cards stay portable. Both are optional. The model may fill a card only when there is an example chapter or a note for that card. A note names its card, and for Characters also the character it is about; there is one note per target. There is no "revise a card" generation: notes are inputs to the first fill.
61. **Locks** are project-level entries (`Lock`) that read outside in: card, character (for Characters), field, list item id, box inside the item. An empty level means the lock covers everything under it, so a card alone locks the whole card. A lock means no one can edit the value, the human included; removing the lock is how it is edited again. When a model output (a card fill or an extractor's proposal) would change a locked value, the page asks the user to confirm that it will be unlocked and overwritten before committing; declining drops that change. Locks carry no story information.
62. **`bears_on`** links people and groups only (characters and groups); ties are not a target.
63. **Open obligations** are dropped. Shift legality is set in code from the chapter number, the chapter count and the earlier shifts.
64. **Counts and cast.** Place use is tallied from Outline beats' `where` and character use from beats' `cast` (the plan, by design); thing and behavior use come from the Events entries. A project may hold more characters than a chapter's cast of 5.
65. **Style fit** (does the protagonist's personality allow the story to be told in the chosen person, tense and voice) is checked before the story is created. It is a pipeline check, so no field holds it.
66. **Chapter number lives only on the beat** (`Beat.chapter`, filled by code). `Chapter`, events entries and shifts each carry a `beat` link instead (a beat link renders as its chapter number in templates). "Later than chapter N" means the beat's number is greater than N. Staleness is one flag, `Beat.stale`, set by code on every beat after a regenerated chapter; the chapter and the records linked to that beat read as stale through it, and the flag is cleared when that chapter is generated again. `Beat.written` is dropped: a beat is written when a chapter points at it.
67. **Not yet decided, set later in the build:** chapter length target (hardcoded in the pipeline), model and generation settings, and prompt and template versions.

## Established by the pipeline review
68. **Planned is not done.** A reveal, plant, payoff or goal change counts only once the extractor has confirmed it landed in the chapter text. The extractor reads the beat's planned items beside the chapter. A planned item that did not land stays available (a reveal can be tried again, a plant is not open, a payoff stays open, a goal change stays pending). `reveal_not_repeated` therefore counts landed reveals (`not_already_landed`). Who actually learned a reveal is proposed by the Shifts and Entanglements extractor and applied by code; code warns when a reveal landed but nobody's knowledge changed.
69. **Plants are planned on the beat.** `Beat.plant` (optional text) and `Beat.payoff` (optional, up to two, picked from open plants). A plant's status is computed, never stored: planned (on a beat), open (its chapter's Events `planted` is filled and no later `paid_off` points at it), resolved. The two-open-plants limit counts landed plants only.
70. **The goal.** Setup's goal never changes. The current goal is derived in code by walking the beats in order and applying each landed `redefined` change. A landed `achieved` or `abandoned` ends the goal and the remaining chapters wind down, with no next goal. `Events.goal_landed` records whether a beat's change happened. A change that did not land stays pending and is tried again; forcing goals to land is deferred. `goal_now` carries the same warnings as Setup's goal.
71. **Offstage pass.** A separate model call inside Plan, run only occasionally, when code says a change is due. The spotlight pressure always involves someone in the cast, so the offstage change is never about it: it is a background group acting or a place changing, written as free text. It reads the groups, places and ties involved and this chapter's Events, and writes `offstage_did` and `offstage_reach`. The writer, extractors and planner never see an unchosen character.
72. **One-sided links.** For the writer, a tie is shown when the on-stage person is `tie_from`, labeled offstage and not present, name only; it is skipped when the offstage person is `tie_from`. Holdings and knowledge follow the same rule.
73. **Precedence.** Shifts and Events win over the cards where they disagree. The writer sees the cards first, then Entanglements, then a block of the latest value per field per character, marked as overriding. A human edit made after a chapter counts as newer than that chapter's shift.
74. **What goes where.** Characters hold abstract content only: nothing concrete and nothing about other people. A tie's `edge` is a concrete aim between two people; Shifts `wants` are abstract. Knowledge is measured against canon, which cannot be wrong; Shifts `believes` is a personal conviction that can be proven wrong, and a belief about a canon fact goes in Knowledge. `Shifts.hides` is dropped (hiding is an edge plus Knowledge).
75. **Cast and plan state.** The human picks the cast (up to 5, protagonist included) before pressing Plan, and code suggests the least-used characters (`Beat.cast` is `filled_by="human"`). `Beat.planned_from` holds a fingerprint of the live Entanglements the beat was planned from; a mismatch marks the plan as made from older state and highlights Plan. It never replans on its own.
76. **Normal and disruption** are used only for chapter 1. Later chapters carry them forward through the Events summaries.
77. **Channels.** Cards reach a model as prose (names, never ids), as pick-lists (the model picks names, code maps them to ids; used for detection by the extractors and for creative fit in the planner), or as code-derived values (counts, rotation picks, spotlight, current goal, available reveals) fed as prose. Rotation items are chosen by code; the planner chooses only among a code-made shortlist.
78. **Canon and secrets.** The writer sees all of World, including Hidden and Myth rules and their truths. They are hidden only from characters, through Knowledge, and a hidden truth reaches the page only through the beat's reveal.
79. **Events summaries.** `happened` is one sentence per event, usually 4 to 8 sentences, where an event changes who knows what, who holds what or where people stand. The end-of-story update always reads the Events and Shifts summaries, never the full chapters, so it needs no length threshold.
80. **Retries and stale plans.** A beat gets two attempts in total, the first failure's message going into the second; if a block rule still fails, the user sees its message and fix and Generate stays disabled. Warnings never block. Generate warns about a plan made from older state but does not block.
81. **Counts are a deliberate exception.** Place and character use counts come from planned beats (the beat chose them for the chapter); behavior and thing counts come from landed Events entries.
82. **Shifts** (`schema/shifts.py`) record what changed for one card in one chapter as a sparse copy of that card: an entry is `{beat, card, target, patch}`, with `card` one of characters, world or entanglements and `target` the character id for Characters only. A patch holds only non-fixed fields in the card's own keys; a scalar holds its new value, a list holds `add` / `replace` / `remove` operations on items by id, and links are ids. Fixed fields and an item's identity fields (`identity=True`: a tie's two ends, a holding's holdee) never appear in a `replace`. Everything is derived from the card schemas (`shiftable_fields`, `validate_patch`), so a field added to a card later is shiftable with no other change. One entry per beat, card and target; at most `MAX_SHIFTS_PER_CHAPTER` (7) per beat; a patch is never empty. Python only validates: the overlay (base plus shifts of earlier chapters) is written once, in the page, and defined by `tests/shared/overlay-vectors.json`.
