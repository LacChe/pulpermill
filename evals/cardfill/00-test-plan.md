# Card-fill test kit: plan

Purpose: check whether the pipeline turns free-form text (an example chapter and/or per-card notes) into well-built cards, and use the results to tune the card-fill prompts. There is no answer key. Cards are judged against the schema's own rules plus the checks below.

The case files contain only pasteable input, with no labels. Everything marked "planted" below is for the evaluator and is never shown to the model.

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

- Character notes leave the character reference unset. The pipeline creates the character from the note and assigns its id.
- A card with neither a chapter nor a note stays unfilled.
- Each fill reads that card's note (or the example chapter) plus the earlier cards' data, never earlier cards' notes.

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

Also in this folder: `01-probe-catalog.md`, `02-probe-inputs.md`, the `upstream` sets, `fixtures` (every case and probe as a project-shaped file, plus a manifest), `03-scoring-protocol.md` and the `scoring` sheets.

## Scope rule (applies to every case)

| Card | May invent | Must not invent |
| --- | --- | --- |
| Style | Everything in Style | Story-specific names or events |
| Characters | The person itself | Other people, places, objects, relationships |
| World | Places, things, groups, rules, terms | Characters, owners, who knows what, a group's current plans |
| Entanglements | Ties, holdings, knowledge, pressures among existing items (a circumstance pressure is fine) | New groups, places, objects, rules, characters |
| Setup | Normal, disruption, goal, stakes, chapter count | A protagonist who is not a character; new named people, places or objects |

An empty list is acceptable when nothing upstream can fill it. It is a failure only if the model invented upstream material to fill it. Ties are expected whenever there are two or more characters, and at least one pressure is expected.

## Checks

Label each check as code (C), schema judge (J) or human (H). Run each fill through the schema's block rules and warn rules to find out whether an error was flagged.

### 1. Structure (code)

- Required fields present and not blank or stand-ins like "N/A" (C).
- Valid enum values, lists at most 5 items except Ties, `chapter_count` a whole number from 5 to 10 (C).
- Every reference resolves; no self-ties; allowed holder types; `bears_on` only people and groups; exactly one protagonist who is an existing character (C).
- Either/or fields: knowledge has a rule or a fact, never both; a pressure has an agent or a circumstance, never both; a next move only with an agent; a Myth rule has a truth and no other rule does (C).
- A card is filled only when a chapter or a note exists for it (C).
- No ids in prose, no schema help text, no verbatim copies of the schema's example phrases (C).
- Output language matches the input language; enum values stay in schema form (C).
- Style person and tense match the example chapter when one is given (C/H).
- Every name used in Entanglements and Setup resolves to an existing card item (C).
- **Messy input.** Ordinary typos and shorthand are not copied into card text, and stated names are kept exactly as written (C/H).
- **Stated facts preserved.** Every name, age, sex and appearance detail the input states appears on the card exactly as given. Every place, thing, group and rule a note lists appears on its card, up to the cap of 5 (C/H). A dropped or changed fact leaves nothing visible to catch it, so this check is a priority.

### 2. Boundaries (right, wrong but flagged, wrong and silent)

| Pair | Correct | Failure |
| --- | --- | --- |
| Want / edge / goal | Wants abstract; edge a concrete aim between two people; goal the protagonist's story action, narrowing a want | A want that names a person or object; an edge that is a feeling; a goal that is a theme |
| Characters vs Entanglements | No other names or relationships on a character card | "Former partner of X" in a sketch; history naming people |
| Bond / edge | Bond is a standing label; edge is a live aim | The reverse |
| World thing / holding | A thing's text names no owner or place | Ownership in the object description |
| Group felt / pressure | Daily effects in World; current plans in a pressure's next move | A group's present plan inside its World text |
| Rule status / Knowledge | Rules marked Common, Hidden or Myth; Knowledge records who knows, suspects or was misled | Wrong status; beliefs stored as rules; unaware people listed |
| Pressure | States the consequence; next move is situational | "Tension is rising"; a next move that restates general wants |
| Fear / flaw / vulnerability / values | Four distinct things; values phrased positively | Fields repeating each other; values as prohibitions |
| Behaviors | Inner or broad state, tendency not a specific act, one calm state | "When in a bar fight, they punch the wall" |
| Normal / disruption / goal / stakes | Normal is a concrete ordinary day; disruption an event; stakes the cost of quitting; no ending or plan in Setup | Normal as a mood; disruption as a condition; goal containing the ending |
| Style | Era is facts, genre a tradition, lens a habit of attention | "Gloomy age"; genre as plot; lens as topic |

### 3. Craft (human, quick read)

- Story-engine test: from the cards alone, can you say who wants what, who stands in the way, what the clock is, and what it costs?
- Distinctness: characters differ in wants, speech and flaws; items within a list are not near-duplicates.

## Case sheet (planted material; evaluator only)

| # | Planted | Main focus |
| --- | --- | --- |
| 1 | Named relationship (Dov Haskell, late husband's brother); watch changes hands; the Mutual's present plan (take Walt's lease on Friday); a secret few know (dues are passed upstairs); an unnamed group mentioned once (Customs House); a Friday deadline; a place that silences people when a grey coat enters | Boundaries across Entanglements; scope (does Entanglements invent the Customs House as a group?); Setup goal and chapter count invented from nothing; Style match (first person, past) |
| 2 | Two people, one kitchen, the car keys, an unspoken tension; a neighbour mentioned (Mrs. Aalto); no group, no secret | Completeness from thin input; no padding; ties and a circumstance pressure only |
| 3 | Clean notes, each card nearly correct; a Myth rule (applewood) with a stated truth; a one-sided suspicion (Pim) | Baseline run. Distinct characters, behaviors with a calm state, Knowledge recording Pim's suspicion; stated facts preserved |
| 4 | Brother relationship inside a character note; wants phrased as concrete aims; a want to get promoted; object ownership and a group's plan inside World; a Hidden rule; a theme as the goal; a condition as the disruption; story-specific names in Style; plot as the genre | Nearly every boundary pair. Pass means the brother, the ownership and the group's plan are kept out of the wrong cards; the goal becomes an action and the disruption an event |
| 5 | Notes cover Ilse and Setup only; the chapter holds Matthias, Speaker Voss, the Millers' League, the Corn Exchange (mentioned once), a sealed envelope, a four o'clock vote, and a whispered Hidden rule (the Speaker's casting vote is sold) | Partial-notes coverage; notes honored only on their own cards; scope (Corn Exchange belongs to World only) |
| 6 | Eight wants for Vessa; nine places; seven characters; four groups; six hidden truths; relationship talk in character and World notes; five pressures | Caps of 5; seven distinct cards; survivors match the input's emphasis; at most 3 active pressures; no near-duplicates |
| 7 | Dense specific names and events; a first-person gothic voice; a lens of hands; a buried object under the pecan tree | Style only: lens as habit, genre as tradition, nothing story-specific. Check the other cards lightly |
| 8 | One-liners; no Setup note; no chapter | Role-only sketches deepened (real wants that pull against each other, fear, flaw); Setup left unfilled; no invented plot-carrying entities |
| 9 | Name variants (沈青岚 / 沈姑娘 / 青岚; 钱三 / 钱掌柜 / 掌柜); a group mentioned in the chapter that the World note also names (盐帮); a second group (威远镖局); a jade pendant; a three-day deadline | Language; variants resolve to one character each; same checks as case 1 |
| 10 | Lowercase fragments, typos, "w/" and "b4", question marks where the writer is unsure ("3rd person, past i think, maybe present idk"); ages and sex in shorthand ("36 f"); a rule everyone knows and a secret only the well-keepers know; "6 chaps" | Stated facts preserved from shorthand (36, female; 61, male); typos not copied; Style must pick one person and tense; chapter count 6 |
| 11 | Almost all action and dialogue. Names Kit and Ras only; a satchel, a rope, men in green coats; no ages, appearance, setting or backstory | Completeness from almost no facts; names exact; nothing in the cards contradicts the chapter; Style from action prose |
| 12 | About 2,200 words. Five named people with stated ages (Suvi 33, Okoye 61, Pell 26, Lio 24, Hesper Quill 55); more than five places; a Common rule (no open flame), a Hidden one (the original Charter differs from the public copy) and a Myth with its truth (the Tide Bell rings by itself); a key and a box that change hands | Size handling (record a failed or retried call); facts from the end of the chapter reach the cards; ages and names exact; caps of 5 respected with sensible survivors |

## Where each case overlaps the probes

A case exercises several things at once. When a case result is wrong, find the probe that isolates the same detail and tune against that. Probe IDs are in `01-probe-catalog.md`.

| Case | Overlapping probes |
| --- | --- |
| 1 | S4 (first person, past); C2 (Dov); W1 and E1 (the watch changes hands); W2 and E5 (the Mutual's plan, the Friday deadline); W3 and E6 (the dues secret); E2 (the Customs House mentioned once); U1 to U4 (goal, normal, disruption and stakes invented from the chapter) |
| 2 | E3 and E4 (the tie between two people); E5 (a circumstance pressure); U1 and U2 (goal and disruption invented from thin material) |
| 3 | C4, C5, C6, C7 (character fields); W2 (the Parish Council's daily effect); W3 and W4 (the applewood myth and its truth); E3 and E7 (Pim suspects the truth); U1 to U4 (clean Setup note) |
| 4 | S1, S2, S3 (topic lens, plot genre, names in Style); C1 and C2 (concrete aims, the brother); W1 and E1 (owner in the object); W2 (the Authority's plan); W3 (the Line); U1 and U2 (theme goal, condition disruption); U4 (stakes) |
| 5 | S4 (third person, past); C2; W3 and E6 (the Speaker's casting vote); E2 (the Corn Exchange mentioned once); E5 (the vote deadline); U1 (a clean goal in the note) |
| 6 | C1 and C7 (the want cap); W2; W3 and W4 (six secrets); E5 (five pressures, at most 3 active); E6 and E7 (who knows what) |
| 7 | S1, S2, S3, S4 (Style probes on a full chapter) |
| 8 | C3 and C7 (one-liners deepened, wants that conflict); S1 and S2 (light) |
| 9 | S4 (third person, past, in Chinese); C8 (names and name variants); E2 (the salt guild is named in both World note and chapter, so Entanglements should link to it); E5 and U1 (invented from the chapter) |
| 10 | C8 (stated facts in shorthand); W3 (the well-keepers' secret, the no-trains rule); W2 (the Water Board); U2 and U4 (concrete normal, an event as disruption, stakes) |
| 11 | S4 (third person, past); C8 (names only); U1 and U2 (invented from almost nothing) |
| 12 | C8 (ages); W3 and W4 (the Hidden Charter, the Tide Bell Myth and its truth); W1 and E1 (the key and the box); E6 (who knows about the Charter and the bell); E2 (the Chandlers' Guild mentioned in passing) |

## Running the tests

1. Run each case at least three times. Report counts in each bucket, and treat structure as expected-stable.
2. Cases run chained, each card reading the pipeline's own earlier cards. The probes already run Entanglements and Setup from the fixed upstream sets, so a failure on a later card in a case can be checked against the matching probe instead of needing a separate hand-written upstream for every case.
3. Have a human grade a sample, so the judges' flags are checked against a person's reading.
4. The goal is fewer silent errors, not just more warnings. Do not tune the fill prompts only to trigger or avoid a flag.
