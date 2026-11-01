# Card-fill test kit: plan

Purpose: check whether the pipeline turns free-form text (an example chapter and/or per-card notes) into well-built cards, and use the results to tune the card-fill prompts. There is no answer key. Cards are judged against the schema's own rules plus the checks below. The kit speaks only about the five cards a user fills: Style, Characters, World, Entanglements and Setup, as they are in schema version 3.

The case files contain only pasteable input, with no labels. Everything marked "built in" below is for the evaluator and is never shown to the model.

## Principles

- The user reads and edits every card. The example chapter and notes mainly exist so the user is not faced with empty fields. The failures that matter are the ones that look fine at a glance, because a user who glosses over values might accept them and learn the wrong habit from them.
- Each check is scored in one of three buckets:
  1. **Right.** The fill did the correct thing.
  2. **Wrong but flagged.** The fill erred, and a block rule or warning fired on it (so the user is told).
  3. **Wrong and silent.** The fill erred and nothing fired. This is the only real failure; drive it to zero.
- A control input (the clean version of a probe) that comes back damaged counts as wrong. This catches prompt changes that "fix" a problem by deleting valid content.
- A fill may create freely inside its own card and may only link to what earlier cards already contain.

## Out of scope

- A note that holds another card's material. The user is responsible for putting information in the right note, so nothing needs to be recovered from a wrong note.
- A note that contradicts the example chapter.
- How many character cards a chapter-only fill creates.
- End-of-story updates, and any chapter generation.
- Judge calibration, a plain-prompt baseline, edit-then-fill, and speed or token metrics beyond noting a failed or retried call.

## Fixture conventions

- Character notes leave the character reference unset. The pipeline (the runner, in this kit) creates one character per note, in order, and assigns its id.
- A card with neither a chapter nor a note stays unfilled.
- Each fill reads that card's note (or the example chapter) plus the earlier cards' data, never earlier cards' notes.
- A fixture is a project nobody has finished starting. The card the fill must produce, and any card the kit does not provide, are absent on purpose.

## Files

| File | Input mode |
| --- | --- |
| case-1-noir-chapter.md | Chapter only |
| case-2-domestic-chapter.md | Chapter only (short) |
| case-3-cozy-fantasy-notes.md | Notes only, all five cards, three characters |
| case-4-sf-blurred-notes.md | Notes only, all five cards, three characters |
| case-5-political-chapter-partial-notes.md | Chapter plus notes for Characters (Ilse) and Setup |
| case-6-epic-fantasy-overstuffed-notes.md | Notes only, seven characters |
| case-7-gothic-voice-chapter.md | Chapter only |
| case-8-island-comedy-oneliners.md | Notes only, no Setup note |
| case-9-wuxia-chinese.md | Chapter plus notes for Characters (沈青岚) and World, in Simplified Chinese |
| case-10-messy-notes.md | Notes only, fragmentary and typo-ridden, all five cards, two characters |
| case-11-action-chapter.md | Chapter only, almost all action and dialogue |
| case-12-long-chapter.md | Chapter only, long and fact-rich (about 2,200 words) |

Also in this folder: `01-probe-catalog.md`, `02-probe-inputs.md`, `CHANGES.md`, the `upstream` sets, `fixtures` (every case and probe as a project-shaped file, plus a manifest), `03-scoring-protocol.md` and the `scoring` sheets.

## Scope rule (applies to every case)

| Card | May invent | Must not invent |
| --- | --- | --- |
| Style | Everything in Style | Story-specific names or events |
| Characters | The person itself | Other people, places, objects, relationships |
| World | Places, things, groups, rules, terms | Characters, owners, who holds what, a group's current plans |
| Entanglements | Ties and holdings among existing characters, groups, things and places | New groups, places, objects, rules, characters |
| Setup | Normal, disruption, chapter count | A protagonist who is not a character; new named people, places or objects; a plan or an ending |

An empty list is acceptable when nothing upstream can fill it. It is a failure only if the model invented upstream material to fill it. Ties are expected whenever there are two or more characters.

## Checks

Label each check as code (C), schema judge (J) or human (H). Run each fill through the schema's block rules and warn rules to find out whether an error was flagged. Which rules are model-judged is in the schema (`needs_model`); the runner can ask for them with `--judge`.

### 1. Structure (code)

- Required fields present and not blank or stand-ins like "N/A" (C).
- Valid enum values, lists at most 5 items except Ties and Holdings (and World's places and objects), `chapter_count` a whole number (C). The 5 to 10 chapter range is a prompt-level rule for the planner, not a schema check (see `pulpermill/prompter/DECISIONS.md`).
- Every reference resolves; no self-ties; allowed holder types; exactly one protagonist who is an existing character (C).
- A card is filled only when a chapter or a note exists for it (C).
- No ids in prose, no schema help text, no verbatim copies of the schema's example phrases (C).
- Output language matches the input language; enum values stay in schema form (C).
- Style person and tense match the example chapter when one is given (C/H).
- Every name used in Entanglements and Setup resolves to an existing card item (C).
- **Messy input.** Ordinary typos and shorthand are not copied into card text, and stated names are kept exactly as written (C/H).
- **Stated facts preserved.** Every name, age, sex and appearance detail the input states appears on the card exactly as given. Every place, thing, group and rule a note lists appears on its card (groups and rules up to the cap of 5; places and things have no cap, so none may be dropped) (C/H). A dropped or changed fact leaves nothing visible to catch it, so this check is a priority.

### 2. Boundaries (right, wrong but flagged, wrong and silent)

| Pair | Correct | Failure |
| --- | --- | --- |
| Want / edge | Wants abstract; an edge is the "from" person's driver in a tie | A want that names a person or object; an edge that is a feeling |
| Characters vs Entanglements | No other names or relationships on a character card | "Former partner of X" in a sketch; history naming people |
| Bond / edge | Bond is what the tie is; edge is what it makes the "from" person want | The reverse, or one restating the other |
| Tie direction | The edge belongs to the "from" end | The edge describes the "to" person |
| World thing / holding | A thing's text names no owner or place | Ownership in the object description |
| Holding / tie | Ownership of a thing or place is a holding | Ownership written as a tie's bond |
| Group felt / plan | Daily effects in World; a group's present plan stays out of World | A group's present plan inside its World text |
| Fear / flaw / vulnerability / values | Four distinct things; values phrased positively | Fields repeating each other; values as prohibitions |
| Behaviors | Inner or broad state, tendency not a specific act, one calm state | "When in a bar fight, they punch the wall" |
| Normal / disruption | Normal is a concrete ordinary day and what it gave the protagonist; disruption is an event; no ending or plan in Setup | Normal as a mood; disruption as a condition; an ending inside the disruption; Setup repeating the character card |
| Style | Era is facts, genre a tradition, lens a habit of attention | "Gloomy age"; genre as plot; lens as topic |

### 3. Craft (human, quick read)

- Story-engine test: from the cards alone, can you say who wants what, who stands in the way, and what has just broken the normal?
- Distinctness: characters differ in wants, speech and flaws; items within a list are not near-duplicates.

## Case sheet (built in; evaluator only)

| # | Built in | Main focus |
| --- | --- | --- |
| 1 | Named relationship (Dov Haskell, late husband's brother); a watch changes hands; the Mutual's present plan (take Walt's lease on Friday); dues passed upstairs; an unnamed group mentioned once (Customs House); a Friday deadline; a place that silences people when a grey coat enters | Boundaries across Entanglements; scope (does Entanglements invent the Customs House as a group?); Setup normal and disruption from the chapter alone; chapter count invented from nothing; Style match (first person, past) |
| 2 | Two people, one kitchen, the car keys, an unspoken tension; a neighbour mentioned (Mrs. Aalto); no group | Completeness from thin input; no padding; ties only |
| 3 | Clean notes, each card nearly correct; an applewood rule for the Weather Oven; a council leaning on Orla | Baseline run. Distinct characters, behaviors with a calm state, ties with bond and edge apart; stated facts preserved |
| 4 | Brother relationship inside a character note; wants phrased as concrete aims; a want to get promoted; object ownership and a group's plan inside World; a theme-like Style note; plot as the genre; a condition as the disruption | Nearly every boundary pair. Pass means the brother, the ownership and the group's plan are kept out of the wrong cards; the disruption becomes an event |
| 5 | Notes cover Ilse and Setup only; the chapter holds Matthias, Speaker Voss, the Millers' League, the Corn Exchange (mentioned once), a sealed envelope, a four o'clock vote | Partial-notes coverage; notes honored only on their own cards; scope (Corn Exchange belongs to World only) |
| 6 | Eight wants for Vessa; nine places; seven characters; four groups; six rules; relationship talk in character and World notes; many ties and three holdings | Caps of 5 where they apply (wants, groups, rules); places and things have no cap, so all nine places should appear; seven distinct cards; survivors match the input's emphasis; no near-duplicates |
| 7 | Dense specific names and events; a first-person gothic voice; a lens of hands; a buried object under the pecan tree | Style only: lens as habit, genre as tradition, nothing story-specific. Check the other cards lightly |
| 8 | One-liners; no Setup note; no chapter | Role-only sketches deepened (real wants that pull against each other, fear, flaw); Setup left unfilled; no invented plot-carrying entities |
| 9 | Name variants (沈青岚 / 沈姑娘 / 青岚; 钱三 / 钱掌柜 / 掌柜); a group in the chapter that the World note also names (盐帮); a second group (威远镖局); a jade pendant; a three-day deadline | Language; variants resolve to one character each; same checks as case 1 |
| 10 | Lowercase fragments, typos, "w/" and "b4", question marks where the writer is unsure ("3rd person, past i think, maybe present idk"); ages and sex in shorthand ("36 f"); two rules; "6 chaps" | Stated facts preserved from shorthand (36, female; 61, male); typos not copied; Style must pick one person and tense; chapter count 6 |
| 11 | Almost all action and dialogue. Names Kit and Ras only; a satchel, a rope, men in green coats; no ages, appearance, setting or backstory | Completeness from almost no facts; names exact; nothing in the cards contradicts the chapter; Style from action prose |
| 12 | About 2,200 words. Five named people with stated ages (Suvi 33, Okoye 61, Pell 26, Lio 24, Hesper Quill 55); more than five places; three rules (no open flame, the original Charter differs from the public copy, the Tide Bell rings by itself); a key and a box that change hands | Size handling (record a failed or retried call); facts from the end of the chapter reach the cards; ages and names exact; caps of 5 respected where they apply, with sensible survivors; every place appears (places have no cap) |

## Where each case overlaps the probes

A case exercises several things at once. When a case result is wrong, find the probe that isolates the same detail and tune against that. Probe IDs are in `01-probe-catalog.md`.

| Case | Overlapping probes |
| --- | --- |
| 1 | S4 (first person, past); C2 (Dov); W1 and E1 (the watch changes hands); W2 (the Mutual's plan); E2 (the Customs House mentioned once); U2 and U3 (normal and disruption invented from the chapter) |
| 2 | E3 and E4 (the tie between two people); U2 (normal and disruption from thin material) |
| 3 | C4, C5, C6, C7 (character fields); W2 (the Parish Council's daily effect); E3 and E4 (Pim and Orla, Corbin and Pim); E9 (Orla keeps the oven key); U2 (clean Setup note) |
| 4 | S1, S2, S3 (topic lens, plot genre, names in Style); C1 and C2 (concrete aims, the brother); W1 and E1 (owner in the object); W2 (the Authority's plan); E8 (Imre looks up to Teodora; she covers for him); U2 (condition as disruption) |
| 5 | S4 (third person, past); C2; E2 (the Corn Exchange mentioned once); U2 (a clean note) |
| 6 | C1 and C7 (the want cap); W2; E3, E4 and E8 (many ties, some written from the other end); E9 (holdings); U2 |
| 7 | S1, S2, S3, S4 (Style probes on a full chapter) |
| 8 | C3 and C7 (one-liners deepened, wants that conflict); S1 and S2 (light) |
| 9 | S4 (third person, past, in Chinese); C8 (names and name variants); E2 (the salt guild is named in both World note and chapter, so Entanglements should link to it); U2 (invented from the chapter) |
| 10 | C8 (stated facts in shorthand); W2 (the Water Board); E9 (Osric keeps the boiler key); U2 (concrete normal, an event as disruption); U7 ("6 chaps") |
| 11 | S4 (third person, past); C8 (names only); U2 and U6 (invented from almost nothing) |
| 12 | C8 (ages); W1 and E1 (the key and the box); E2 (the Chandlers' Guild mentioned in passing) |

## Running the tests

1. Run each case at least three times. Report counts in each bucket, and treat structure as expected-stable.
2. Cases run chained, each card reading the pipeline's own earlier cards. The probes already run Entanglements and Setup from the fixed upstream sets, so a failure on a later card in a case can be checked against the matching probe instead of needing a separate hand-written upstream for every case.
3. Have a human grade a sample, so the judges' flags are checked against a person's reading.
4. The aim is fewer silent errors, not just more warnings. Do not tune the fill prompts only to trigger or avoid a flag.
5. `node tools/run_cardfill.mjs` does the running and records the code rules (and, with `--judge`, the model-judged ones); a person does the grading, and `tools/summarize_scoring.py` adds up the sheets.
