# Prompter decisions

Recorded in step A1. Plain statements; change one only on purpose.

## Decisions
- **Name.** The new prompter is `mill`, in `pulpermill/prompter/mill/`.
- **Bar for becoming the default.** 13 Tier 1 card-fill probes right or flagged, with no silent error; plus the rebuilt chapter trials, read by a human.
- **When the default changes.** Only after a clean real-model run (stage D). Until then the stub stays the default in `pulpermill/backend/config.py`.
- **Chapter count is 5 to 10 by default, and a chapter is at most 1,200 words (decided 3 Nov; before: 5 to 10 chapters, about 1,800 words; the count was 10 to 20 from 3 Nov until plan 5 step 1 set it back to 5 to 10).** The writer prompt asks for a complete chapter of up to 1,200 words (2,400 Han characters for Chinese), aiming for roughly 900 to 1,200, and the `write` step flags a chapter over 1,500 words (3,000 characters) for a second attempt; a short chapter is never rejected. The range of 5 to 10 chapters is used in wording and trials only for now: there is no rule that catches an out-of-range `chapter_count` on a card or in the page, because that needs a new check in `web/logic.js` (`number_in_range`), a rule in `schema/setup.py`, its text and tests, which is a separate step (a `warn` rule on `chapter_count`, `min: 5`, `max: 10`). Until then a card can hold any whole number: the card-fill kit keeps a number the note states exactly, and only chooses from 5 to 10 when the note states none.
- **The plan call may choose its tie and pressure (5 Nov).** When the request has `choose`, a `select` step runs before the brainstorm and picks three tie-and-pressure combinations by number, never by id; the brainstorm writes one idea for each and the plan chooses one idea and answers with its pair as `picked`. With fewer than three pairs, or when `select` cannot be used, the call is the single-pair one.
- **A Characters fill names the person from the card's `name` value (7 Nov).** The writer types the name as the example chapter spells it, and the fill prompt says the card is for that person; without it every character's prompt was identical. No other current value of the card is shown.
- **The brainstorm writes exactly three ideas (8 Nov).** One idea for each combination in choose mode (idea N is built on combination N and no other), and the outcome is fixed by the idea's number: 1 is reached at a price, 2 is lost, 3 is given up. A reply that has options but not exactly three (or, in choose mode, not numbered 1, 2, 3) is refused and retried once with a line saying what to fix; after two such replies the plan goes ahead without a brainstorm. A reply that cannot be split into options is not refused: it passes as before.
- **The decider compares three options and the code picks (8 Nov).** Between the brainstorm and the plan one call compares exactly the brainstorm's three options (one per combination, the outcome fixed by the number) on one criterion, `move` (plan 9: which option moves the story forward the most, set against what the story holds now; a new named person alone is not movement). The reply reasons before it judges: `held` (what the story holds now; from the setup and disruption in chapter 1), then a short text per option (what it adds that is new, or repeats), then the best and the worst; it gives no pick. Code scores best +1, worst -1, sums with equal weights and picks the highest, with a random choice among equal totals; a reply that cannot be used after two attempts picks a random option, never the first. The criterion judges what an option sets up and changes, never how it ends, so no outcome is favored by default. Each option is shown with the tie, the rule or object and the reason it is built on, never its combination number. An option that names a person on no card (and in no earlier chapter's record) loses one point: a penalty, not an elimination, and none for a story in a language the name detector does not read. The old model-written `pick` and the `loss`, `irreversible` and `opposed` fields are gone.
- **Act 4 is told in actions, and the plan keeps the chosen idea's outcome (8 Nov).** Act 4 asks for how the collision came out and where the chapter leaves the people, told through what they do and what is now different, in facts and actions a reader could watch; no thoughts, feelings or explanation are asked for. Every chapter but the last ends Act 4 on the one consequence the outcome leaves standing (with a person, an object or a date in it); the last chapter keeps "nothing left open". After the decider the plan prompt says the picked idea's outcome stands (1 reached at a price, 2 lost, 3 given up, fixed by the idea's number): Act 3 decides the collision that way and Act 4 shows its price, loss or turn. No check is added; the wording and the `idea_use` line (which now also names how the idea ends) carry it.
- **JSON replies may hold raw newlines and tabs inside strings (8 Nov).** The parse is not strict about control characters in a string, because discarding a whole select, brainstorm, decide and plan pass for a line break in the plan cost a full re-run. Cut-off, wrong-shape and otherwise malformed replies are refused as before.

## Design rules
1. Every card value must be used somewhere (reach at least one call), unless it is code-only (ids, `chapter`, `stale`, `planned_from`).
2. Structured values are converted to longer, explanatory text before they reach the model.
3. The writer call encourages interesting stories; how this is worded follows what works best in prompt design for this model.
4. The planner collides the protagonist's aim with the spotlight tie into a plan that moves forward.
5. Minor characters never carry the plot, and appear only by role, with no names.
6. Every chapter settles the collision of the protagonist's aim and the spotlight tie for good, and ends with both in a new state that grows out of that outcome. Only the last chapter's state is final. Position is told as first, last or in between, and nothing else.
7. Every chapter is designed in four points: Act 1 starting point (who, where, when); Act 2 central conflict emerges; Act 3 climax or turning point; Act 4 end point. This is per chapter and does not depend on the chapter count. Chapter count defaults to 5 to 10 (was 10 to 20), and a chapter is at most 1,200 words.

## Deferred
- Repo docs (`docs/` is stale on purpose)
- i18n of model-facing wording
- Rotation weighting
- Post-pass quality
- Stalled-edge detection
- Human editing of shifts
- A rerun of the post-pass alone
