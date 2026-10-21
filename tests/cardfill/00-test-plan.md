# Card-fill test kit

Purpose: check whether the pipeline turns free-form text (an example chapter and/or per-card notes) into well-built cards. These inputs are what you use to tune the card-fill prompts. There is no answer key. Cards are judged against the schema's own rules plus the checks below.

The case files contain only pasteable input, with no labels. Everything marked "planted" below is for the evaluator and was never shown to the model.

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

## Scope rule (applies to every case)

A fill may create freely inside its own card and may only link to what earlier cards already contain.

| Card | May invent | Must not invent |
| --- | --- | --- |
| Style | Everything in Style | Story-specific names or events |
| Characters | The person itself | Other people, places, objects, relationships |
| World | Places, things, groups, rules, terms | Characters, owners, who knows what, a group's current plans |
| Entanglements | Ties, holdings, knowledge, pressures among existing items (a circumstance pressure is fine) | New groups, places, objects, rules, characters |
| Setup | Normal, disruption, goal, stakes, chapter count | A protagonist who is not a character; new named people, places or objects |

An empty list is acceptable when nothing upstream can fill it. It is a failure only if the model invented upstream material to fill it. Ties are expected whenever there are two or more characters, and at least one pressure is expected.

## Checks

Label each result as code (C), schema judge (J) or human (H).

### 1. Structure (hard fail)

- Required fields present and not blank or stand-ins like "N/A" (C).
- Valid enum values, lists at most 5 items except Ties, `chapter_count` a whole number from 5 to 10 (C).
- Every reference resolves; no self-ties; allowed holder types; `bears_on` only people and groups; exactly one protagonist who is an existing character (C).
- Either/or fields: knowledge has a rule or a fact, never both; a pressure has an agent or a circumstance, never both; a next move only with an agent; a Myth rule has a truth and no other rule does (C).
- A card is filled only when a chapter or a note exists for it (C).
- No ids in prose, no schema help text, no verbatim copies of the schema's example phrases (C).
- Output language matches the input language; enum values stay in schema form (C).
- Style person and tense match the example chapter when one is given (C/H).
- Every name used in Entanglements and Setup resolves to an existing card item (C).

### 2. Boundaries (rate per probe; test both wrong-place and deleted-instead-of-moved)

| Pair | Correct | Failure |
| --- | --- | --- |
| Want / edge / goal | Wants abstract; edge a concrete aim between two people; goal the protagonist's story action, narrowing a want | A want that names a person or object; an edge that is a feeling; a goal that is a theme |
| Characters vs Entanglements | No other names or relationships on a character card | "Former partner of X" in a sketch; history naming people |
| Bond / edge | Bond is a standing label; edge is a live aim | The reverse |
| World thing / holding | A thing's text names no owner or place | Ownership in the object description |
| Group felt / pressure | Daily effects in World; current plans in a pressure's next move | A group's present plan inside its World text |
| Rule status / Knowledge | Rules marked Common, Hidden or Myth; Knowledge records who knows, suspects or was misled | Beliefs stored as rules; unaware people listed |
| Pressure | States the consequence; next move is situational | "Tension is rising"; a next move that restates general wants |
| Fear / flaw / vulnerability / values | Four distinct things; values phrased positively | Fields repeating each other; values as prohibitions |
| Behaviors | Inner or broad state, tendency not a specific act, one calm state | "When in a bar fight, they punch the wall" |
| Normal / disruption / goal / stakes | Normal is a concrete ordinary day; disruption an event; stakes the cost of quitting; no ending or plan in Setup | Normal as a mood; disruption as a condition; goal containing the ending |
| Style | Era is facts, genre a tradition, lens a habit of attention | "Gloomy age"; genre as plot; lens as topic |

### 3. Craft (0, 1 or 2 each, human)

- Conflict: wants cannot all be satisfied; flaws work against them; edges are live; the goal narrows a want and touches a pressure or tie.
- Texture: everyday life has something scarce or contested; places act on people; objects have stakes; rules have costs; descriptions are concrete.
- Connectedness: every character is in a tie; every pressure bears on someone; hidden and Myth rules have someone who knows or was misled.
- Distinctness: characters differ in wants, speech and flaws; list items are not near-duplicates.
- Story-engine test: from the cards alone, can you say who wants what, who stands in the way, what the clock is, and what it costs?
- Faithfulness: keeps the spirit of the input, adds only what serves it, invents no plot-carrying entities; when over the cap, the survivors match the input's emphasis.

## Case sheet (planted material; evaluator only)

| # | Planted | Main focus |
| --- | --- | --- |
| 1 | Named relationship (Dov Haskell, late husband's brother); watch changes hands; the Mutual's present plan (take Walt's lease on Friday); a secret few know (dues are passed upstairs); an unnamed group mentioned once (Customs House); a Friday deadline; a place that silences people when a grey coat enters; minor named people (Dolly Pruitt, Maureen) | Boundaries across Entanglements; scope (does Entanglements invent the Customs House as a group?); Setup goal and chapter count invented from nothing; Style match (first person, past) |
| 2 | Two people, one kitchen, the car keys, an unspoken tension; a neighbour mentioned (Mrs. Aalto); no group, no secret | Completeness from thin input; no padding; ties and a circumstance pressure only |
| 3 | Clean notes, each card nearly correct; a Myth rule (applewood) with a stated truth; a one-sided suspicion (Pim) | Baseline run. Distinct characters, behaviors with a calm state, Knowledge recording Pim's suspicion |
| 4 | Brother relationship inside a character note; wants phrased as concrete aims; a want to get promoted; object ownership and a group's plan inside World; a Hidden rule; a theme as the goal; a condition as the disruption; story-specific names in Style; plot as the genre | Nearly every boundary pair. Information must be moved (brother becomes a tie, ownership a holding, the group's plan a pressure's next move), not dropped |
| 5 | Notes cover Ilse and Setup only; the chapter holds Matthias, Speaker Voss, the Millers' League, the Corn Exchange (mentioned once), a sealed envelope, a four o'clock vote, and a whispered Hidden rule (the Speaker's casting vote is sold) | Partial-notes coverage; notes honored only on their own cards; scope (Corn Exchange belongs to World only) |
| 6 | Eight wants for Vessa; nine places; seven characters; four groups; six hidden truths; relationship talk in character and World notes; five pressures | Caps of 5; seven distinct cards; survivors match emphasis; at most 3 active pressures; no near-duplicates |
| 7 | Dense specific names and events; a first-person gothic voice; a lens of hands; a buried object under the pecan tree | Style only: lens as habit, genre as tradition, nothing story-specific. Grade the other cards lightly |
| 8 | One-liners; no Setup note; no chapter | Role-only sketches deepened (real wants that pull against each other, fear, flaw); Setup left unfilled; no invented plot-carrying entities |
| 9 | Name variants (沈青岚 / 沈姑娘 / 青岚; 钱三 / 钱掌柜 / 掌柜); a group mentioned in the chapter that the World note also names (盐帮); a second group (威远镖局); a jade pendant; a three-day deadline | Language; variants resolve to one character each; scope (钱三 and 裴远山 are only in the chapter, so decide whether they get cards); same checks as case 1 |

## Running the tests

1. Run each case at least three times. Report pass rates, and treat structure as expected-stable and craft as allowed to vary.
2. For cases that test Entanglements or Setup (1, 3, 4, 5, 6), run twice: chained from the pipeline's own upstream output, and from a fixed hand-written upstream set, so an Entanglements failure is not blamed on World.
3. Do not grade only with the schema's judge prompts. They run inside the pipeline, so treat them as one lens, and have a human grade a sample.
4. Do not tune the fill prompts only to satisfy the judge.
