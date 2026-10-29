# Pulpermill data flow: what feeds what

*Draft audit of the schema zip against the pipeline, 2026-10-20. The four open items were settled on 2026-10-25.*

## Legend

**Calls:** **W** chapter writer · **P** planner (think, then fill the beat) · **O** offstage pass · **X1** Events extractor · **X2** Shifts and Entanglements extractor · **F** card fill · **E** end-of-story update · **J** model-judged rules · **S** style-fit check · **C** code only.

**Channels (how data reaches a call):**

1. **Prose.** The card is rendered into paragraphs by its render kinds. Names, never ids.
2. **Pick-lists.** The model sees names and picks from a list; code maps the names back to ids. Used only for detection (extractors confirm which behaviors, things, reveals, plants and goal changes appeared in the text) and for creative fit (P chooses among a code-made shortlist).
3. **Code-derived.** Counts, last appeared, spotlight, legal shifts, chapter n of N, open plants, available reveals, current goal, and rotation picks (behaviors, things in the scene, least-used places) fed to the model as prose.
4. **Human only.** Labels, help text, locks, notes, the stale flag.

**Scope rule.** W, X1 and X2 see only the chosen cast and what is in play for the beat (their ties, holdings, knowledge, the beat's place, objects in the scene). Unchosen characters are invisible. P gets the same, plus the open-pressure lines. The one exception is O, which also reads the background groups and places it changes.

**Offstage pass (O).** Runs inside Plan, only occasionally, when code says a change is due. The spotlight pressure always involves someone in the cast, so offstage changes are not about it: they are background groups acting or places changing. It reads the groups, places and ties involved, and this chapter's Events. It writes `offstage_did` and `offstage_reach` as free text. P then plans around the offstage change.

## Style

| Field | Reaches | Notes |
| --- | --- | --- |
| person, tense | W (rules), S, C | C can check drift in the output. |
| distance, narrator\_note | W, S |  |
| genre, lens | W, P | Decided: P sees them too. |
| humor, attitude, pacing | W, P | Decided: P sees them too. |
| rhythm, diction, register, imagery, edge, explicitness, amount, directness, polish, voice\_difference, and the four notes | W only | Sentence-level craft. P and the extractors do not need it. |

## Characters (cast only)

| Field | Reaches | Notes |
| --- | --- | --- |
| name, sex | W, P, X1, X2, F, E | The name list is what code uses for name matching. Fixed. |
| age, appearance | W | Fixed, always sent in full. |
| sketch | W, P |  |
| wants | W, P, X2, J | P builds choices from them. Abstract desires only (succeed at school); concrete aims toward people live in Tie.edge. Not counted, so nothing rotates them. |
| fear, flaw | W, P, X2 |  |
| values | W, P | The costly choice is a want or a value. |
| behaviors | W (least-used subset), X1 (pick-list), C (counts) | A full round trip. |
| competence, vulnerability | W, P | Decided: P sees them too. |
| speech | W only |  |
| history | W, P, E | Decided: P sees it too. |

## World

| Field | Reaches | Notes |
| --- | --- | --- |
| name, era\_and\_technology | W, P |  |
| everyday\_life | W, P | It is the normal the story breaks. |
| history | W | Background only. |
| places | W (the beat's place in full, others by name), P (all, with use counts and effects), C (counts from Outline `where`) |  |
| objects | W (those in the scene), P (with holders and counts), X1 (pick-list), C |  |
| powers (Groups) | W (the `felt` line always; `nature` and `hold` when in a tie or pressure), P | Not counted. |
| rules | W (through Knowledge, per cast member; common ones as background), P (cost builds choices; hidden and myth rules form the reveal list), X1 (pick-list), C |  |
| terms | W only |  |

## Entanglements (filtered to the cast and what is in play)

| Field | Reaches | Notes |
| --- | --- | --- |
| ties (bond, edge) | W, P, X2 | `bond` is the relationship. `edge` is a concrete aim between two people (wants to pass the teacher's test). X2 proposes changes to both. |
| holdings | W, P, X2 | X2 proposes changes to `held_by`. |
| knowledge | W (per person), P, X2, C | Measured against canon, which cannot be wrong: knows, suspects or misled. X2 proposes the status changes and any new lines (a person and a rule or fact with no line yet), and C applies them. If a reveal landed but nobody's status changed or no line was added, C warns. |
| pressures | W, P, X2 | X2 proposes changes to `what`, `next_move` and `bears_on`. |

**One-sided links.** A tie is shown when the on-stage person is `tie_from`, labeled offstage and not present: a name only, never a description. It is skipped when the offstage person is `tie_from`, because that edge may be something the on-stage person does not know. Holdings and knowledge follow the same rule. The writer is told offstage people may be mentioned or thought of but do not appear.

## Setup

| Field | Reaches | Notes |
| --- | --- | --- |
| protagonist | W, P, S, C | C requires the protagonist in every cast. |
| normal, disruption | W and P in chapter 1 only | Used once, by design. Later chapters carry it through the Events summaries. |
| goal | W, P | The current goal is derived: Setup's goal, replaced by each landed `redefined` beat. After a landed `achieved` or `abandoned` there is no goal and the story winds down. |
| stakes | P, W |  |
| chapter\_count | C (forces the count), P (chapter n of N), W (told when it is the last chapter) |  |

## Outline (one beat per chapter)

| Field | Reaches | Notes |
| --- | --- | --- |
| chapter, stale | C, human |  |
| where | W, P, C | Place counts are tallied from here. |
| when\_time, when\_gap | W, P | W anchors the opening. P sees the earlier beats' times as a timeline. |
| cast | W, X2, C | Chosen by the human before Plan (code suggests). Counts and last-appeared come from here. |
| collision\_goal | W, X1, J, C | The scene's one step toward the goal now, written so that it meets the pressure in focus. X1 sees it with the goal. The writer plays the meeting; how it goes is not planned. C warns when it repeats an earlier aim or a changed line. |
| shift (harder or easier) | W, C | C limits the legal values. |
| ends\_on | W, J |  |
| reveal\_rule, reveal\_learners | W, X1, X2, C | X1 confirms it landed. Only landed reveals leave the available list. X2 proposes who actually learned it, so `reveal_learners` is optional and the planner does not fill it. |
| plant (new, optional) | W, X1, C | What this chapter plants. X1 confirms it landed (Events `planted`). It is open once landed. |
| payoff (new, optional) | W, X1, C | Picked from the open plants. X1 confirms it landed (Events `paid_off`). A payoff that did not land stays open. |
| offstage\_did, offstage\_reach | W | Written by the offstage pass (O), only when a change is due. Free text about background groups and places, never about the spotlight. |
| (no goal fields) | | The beat plans no goal change, no turn and no choice. Goal changes live on the Events entry (below). |
| spotlight | W, P | C picks it, always a pressure that involves someone in the cast. |

## Records and project data

| Data | Reaches | Notes |
| --- | --- | --- |
| Chapter text | W (the previous chapter's ending, as much as the context allows), X1, X2 (this chapter), export | E never reads it. |
| Events: happened | W, P, E | Earlier chapters as a running summary. One sentence per event, usually 4 to 8 sentences. An event changes who knows what, who holds what or where people stand. E always reads these, never the full chapters. |
| Events: changed | P, W, C (aim-not-repeated) |  |
| Events: planted, paid\_off | P, C | X1 fills them by checking the chapter against the beat's `plant` and `payoff`. C computes the status: planned, open, resolved. |
| Events: reveals\_landed, behaviors\_seen, things\_seen | C (counts, available reveals), P | `reveals_landed` is checked against the beat's reveal. |
| Events: goal\_landed (new) | C | Says whether the beat's goal change happened. |
| Shifts | W (latest value per field per cast member, shown after the cards and marked as overriding), P, E | Fields: believes, fears, wants, refuses, decided. `hides` is dropped. |
| Entanglements history | C (restore for regenerate) | Never sent to a model. |
| Example chapter, card notes | F |  |
| Model notes (`plan_notes`, `chapter_notes`, `end_note`) | human only | What the model said and what the page showed, kept so H can read it after reopening the file. Display only: never sent to a model, never read by the pipeline. Each is replaced when its beat, chapter or after-story copy is made again, and goes with it. The end note also holds `made_from`, a fingerprint of the chapters and records the copy was made from, so the page can say the copy is out of date. |
| after\_story | export, a new story |  |
| Language | W (target language line) | Model-facing text stays English; only the human-facing text is translated. The judge prompts are English too. |

**Precedence.** Where Characters, Entanglements and the summaries disagree, Shifts and Events win. The writer's prompt orders the cards first, then Entanglements, then a 'where they stand now' block (the latest value per field per character) marked as overriding. A human edit to a live field made after a chapter counts as newer than that chapter's shift.

**Counts.** Place and character use counts are tallied from planned beats, a deliberate exception to 'planned is not done': the beat chose them for the chapter. Behavior and thing counts come from landed Events entries.

**Canon and secrets.** The writer sees all of World, including Hidden and Myth rules and their truths. They are hidden only from characters, through Knowledge, and a hidden truth reaches the page only through the beat's reveal.

## Findings: where data had no home, and how each is settled

1. **Plants (settled).** The planner plans them with new optional `Beat.plant` and `Beat.payoff` (picked from the open plants). X1 confirms each landed against the beat. C computes the status: planned, open (landed, not yet paid off) or resolved.
2. **Reveals (settled).** X1 confirms the planned reveal landed. Only landed reveals leave the available list. X2 proposes who actually learned it and C applies that, warning if nobody's knowledge changed. `reveal_not_repeated` counts landed reveals plus the beat being planned.
3. **Current goal (settled).** Nobody plans a goal change. X1 says, every chapter, how the chapter left the goal it began with (Events `goal_change`: achieved, redefined or abandoned) and what the protagonist wants from there on (Events `goal_now`). C derives the current goal as Setup's goal, replaced by the last written chapter's `goal_now`; a goal worded again as it stood is the same goal. There is always a goal. X2 is shown the result so that it moves the spotlighted pressure to match (new `what` and `next_move`, `status: resolved` once its next move has happened). A pressure's use is the spotlight, and the rotation takes the pressure spotlit longest ago.
4. **Offstage changes (settled).** The spotlight always involves someone in the cast, so agents outside the cast are never moved offstage. The offstage pass only changes background groups and places, and P never needs their cards.
5. **One-sided links (settled).** See the rule under Entanglements.
6. **Setup's normal and disruption (intended).** Used only for chapter 1.
7. **Entanglements and Shifts overlap (settled).** `edge` is a concrete aim between two people. Shifts `wants` are abstract, and nothing concrete or relational sits on a character. Knowledge is measured against canon, which cannot be wrong. `believes` is a personal conviction that can be proven wrong; a belief about a canon fact goes in Knowledge instead. `hides` is dropped from Shifts.
8. **Static card against Shifts (settled).** Shifts and Events take precedence (see Precedence).

## Decided and still open

**Folded in above:** the offstage pass, precedence, the plant, payoff and goal fields, landed checks for reveals, plants and goals, the one-sided link rule, `hides` dropped, the writer seeing all canon, X2 proposing knowledge changes, confirmation before overwriting locked values, English-only model text, and one sentence per event in Events. Settled on 2026-10-25: P also sees genre, lens, attitude, humor and pacing; P also sees competence, vulnerability and history for the cast; X2 sees the beat's choices so `decided` records which was taken; and the cast suggestion also uses the pressures' `bears_on` (done in `castChoices`, `web/plan.js`).

**Still open:** none. Gaps found while writing the prompt inventory are listed in `docs/prompts/01-inventory.md`, section 6.

**Schema changes this implies (for the schema pass):**

- New optional `Beat.plant` and `Beat.payoff`; `Beat.cast` filled by the human.
- New `Events.goal_landed`.
- Drop `Shifts.hides` and update the `shift_not_empty` field list.
- Rewrite `reveal_not_repeated` to count landed reveals.
- Give `goal_now` the same warnings as Setup's goal.
- Hint text: `edge` is concrete between two people, `wants` abstract, `believes` a conviction not tracked as Knowledge.
- A small project-file field for the hash a beat was planned from.
