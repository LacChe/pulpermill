# Pulpermill pipeline: who does what

*Draft for the rewrite, 2026-10-20.* **Actors:** **H** human, **C** code, **M** model. **Model calls:** **W** chapter writer, **P** planner, **O** offstage pass, **X1** Events extractor, **X2** Shifts and Entanglements extractor, **F** card fill, **E** end-of-story update, **J** model-judged rules, **S** style-fit check.

## Ground rules

- The backend is stateless. The page holds the project file. Every call sends everything it needs and returns everything it produced.
- The page commits a result all or nothing. A failed or stopped call changes nothing, and retrying means pressing the button again.
- Static cards (Style, Characters, World, Setup) are locked once the story starts. Between chapters only the live fields of Entanglements and the next beat can be edited.
- Locks stop edits by anyone. When a model output would change a locked value, the page shows a confirmation (these values will be unlocked and overwritten) before committing. Confirming is the normal answer; declining drops that change.
- Output language equals the UI language. M is told the target language in English. Model-facing text (expansions, lead-ins, templates, judge prompts) is not translated; only the human-facing text is. C checks the output language and retries once if it drifted.
- Structured output: grammar forces valid JSON in the schema's shape. C then maps names to ids and checks the links. Only shape failures force a retry.
- Validation uses change tracking: C keeps a hash of each card and field as of its last successful check and rechecks only what differs. Model-judged warnings are cached by value hash.
- Planned is not done: a reveal, plant, payoff or goal change counts only once X1 confirms it landed in the text.
- Counts: place and character use counts come from planned beats, a deliberate exception to the rule above, because the beat chose them for the chapter. Behavior and thing counts come from landed Events entries.
- Precedence: Shifts and Events win over the cards. The writer sees the cards first, then Entanglements, then a 'where they stand now' block of the latest Shifts values. A human edit made after a chapter counts as newer than that chapter's shift.
- Canon and secrets: the writer sees all of World, including Hidden and Myth rules and their truths. They are hidden only from characters, through Knowledge, and a hidden truth reaches the page only through the beat's reveal.
- The data-flow doc holds the per-field detail: who reads what, and through which channel.

## 0. Setup

| Step | Actor | Notes |
| --- | --- | --- |
| Open the page, connect the backend | H, C | C runs a status check (idle or busy). |
| Import a project, individual cards, or an example chapter | H, C | C keeps valid fields only and warns on bad input. It never crashes. A card file (Style, a character, World) comes in only to a card that is not locked. H sees what would change first, and a character comes in as a new character or in place of one H has. Undo is offered afterwards. |

## 1. Card loop

Order: Style, Characters, World, Entanglements, Setup.

| Step | Actor | Reads | Writes |
| --- | --- | --- | --- |
| Write a free-form note for the card | H |  | project notes |
| Fill the card | M (grammar) | example chapter and/or that card's note, plus earlier cards | card fields |
| Map names to ids, check links | C |  |  |
| Adjust the card | H |  | card fields |
| Code rules (on every edit) | C | card | warnings, blocks |
| Model-judged warnings (changed fields only) | M | changed field plus context | warnings |
| Lock values | H |  | locks |

The fill needs an example chapter or a note for that card. There is no revise-card generation.

**Story start gate.** C requires every block rule to pass. M runs the style-fit check (does the protagonist's personality allow the chosen person, tense and voice). Then the static cards lock.

## 2. Plan (button; chapter 1 and every later chapter)

| Step | Actor | Notes |
| --- | --- | --- |
| Pick the cast (up to 5, protagonist always in) | H | C pre-selects the least-used characters as a suggestion. |
| Compute chapter number, spotlight, legal shifts, least-used places, current goal, available reveals, open plants | C | Spotlight rotation and shift legality are code. Available reveals are those that have not landed. |
| Offstage change (only when due) | C, O (M, free text) | C decides occasionally that a change is due. It is about background groups or places, never the spotlight, which always involves someone in the cast. O reads the groups, places and this chapter's Events, and writes `offstage_did` and `offstage_reach`. |
| Think | M (free text) | Reads open pressures and their next moves, ties, latest shifts, open plants, available reveals, use counts, summaries, and any offstage move. Proposes 2 or 3 directions, picks one with a reason, says how the chapter should be written, and decides whether to plant something or pay off an open plant. |
| Fill the beat | M (grammar) | Includes the optional `plant` and `payoff`. The thinking text is in context. Code discards it afterward. |
| Block rules, then model-judged beat warnings | C, M | turn is a change, choice is costly, ends on an open question. |
| Retry | C | Two attempts in total; the first failure's message goes into the second. Still failing: H sees the rule's message and fix, and Generate stays disabled. Warnings are shown but do not block. |
| Assess, edit, replan | H |  |
| Store a hash of the Entanglements the beat was planned from | C | If live fields change later, the beat is marked planned from older state and Plan is highlighted. It is never replanned automatically, and Generate warns about such a plan but does not block. |

## 3. Generate chapter

| Step | Actor | Reads | Writes |
| --- | --- | --- | --- |
| Gate: validate what changed, beat valid | C |  |  |
| Snapshot Entanglements as seen (history) | C | what was sent | history entry |
| Assemble context: cards rendered to prose with names and only the chosen cast, then Entanglements, then 'where they stand now' (latest Shifts values, overriding), earlier Events summaries, the current goal, the language line | C |  |  |
| Token count check against the context size | C |  | clear error if too long |
| Write the chapter | M (free text) | context plus the beat | chapter text |
| Events pass | M (grammar) | chapter text plus the beat's planned reveal, plant, payoff and goal change | happened, changed, planted, paid off, reveals landed, behaviors seen, things seen, goal landed; each planned item marked landed or not |
| Shifts and Entanglements pass | M (grammar) | chapter, Characters, Entanglements | per-character shifts (believes, fears, wants, refuses, decided); proposed changes to live fields, including knowledge status |
| Map names to ids; check block rules (for example no more than two open plants) | C |  |  |
| Apply X2's proposed changes to live fields; warn if a reveal landed but nobody's knowledge changed; list any locked values the changes would overwrite and ask H to confirm; compute diffs; tally counts | C, H |  | new Entanglements |
| Commit chapter, records, history and new Entanglements as one unit | C |  | project file |
| Review the chapter and the diffs | H |  |  |

Any failure leaves nothing committed. Shape failures retry up to the same two attempts, then the error is shown.

**Stop.** The page aborts the request. The backend checks a cancel flag inside the generation loop and stops inference. The page unlocks only when the status check reports idle.

## 4. Between chapters

- H edits live Entanglements fields and the next beat. C tracks changes and flags a stale plan.
- **Regenerate chapter N.** C restores N's history snapshot, reuses its beat, replaces its records, sets the current Entanglements to the new result, and marks every later beat stale. Later chapters stay until H regenerates them.

## 5. End of story

| Step | Actor | Notes |
| --- | --- | --- |
| Press the button after the last chapter | H |  |
| Update Characters and World | M (grammar) | Always reads the Events and Shifts summaries (one sentence per event, so they stay small), never the full chapters, plus the current cards. Works like card creation. |
| Force fixed fields (name, age, sex, appearance) back to their original values; keep ids | C |  |
| Store as the after-story copy; originals untouched | C |  |
| Review, edit, download | H |  |

## 6. Export

H exports the story as markdown (required), the cards as a zip, and the project file. C builds them.

## Schema and project-file changes this implies

- `Beat.cast` is filled by the human (code suggests a default), not the planner.
- New optional `Beat.plant` and `Beat.payoff`; new `Events.goal_landed`.
- `Shifts.hides` is dropped.
- A small project-file field for the hash a beat was planned from.
- The resume-point rule is no longer needed because commits are atomic.
- Knowledge changes are proposed by X2, so they need no new fields.
- The full list for the schema pass is at the end of the data-flow doc.

## Open or parked

- Store the planner's thinking text in the project, or discard it (open).
- Run the thinking pass several times and have a judge pick the best (try only if single plans are bland).
- Model revise pass over the chapter (revisit only if stories are still bad).
- Model, generation settings and prompt versions come later.
