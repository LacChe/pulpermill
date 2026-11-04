# Prompter decisions

Recorded in step A1. Plain statements; change one only on purpose.

## Decisions
- **Name.** The new prompter is `mill`, in `pulpermill/prompter/mill/`.
- **Bar for becoming the default.** 13 Tier 1 card-fill probes right or flagged, with no silent error; plus the rebuilt chapter trials, read by a human.
- **When the default changes.** Only after a clean real-model run (stage D). Until then the stub stays the default in `pulpermill/backend/config.py`.
- **Chapter count is 10 to 20, and a chapter is at most 1,200 words (decided 3 Nov; before: 5 to 10 chapters, about 1,800 words).** The writer prompt asks for a complete chapter of up to 1,200 words (2,400 Han characters for Chinese), aiming for roughly 900 to 1,200, and the `write` step flags a chapter over 1,500 words (3,000 characters) for a second attempt; a short chapter is never rejected. The range of 10 to 20 chapters is used in wording and trials only for now: there is no rule that catches an out-of-range `chapter_count` on a card or in the page, because that needs a new check in `web/logic.js` (`number_in_range`), a rule in `schema/setup.py`, its text and tests, which is a separate step (a `warn` rule on `chapter_count`, `min: 10`, `max: 20`). Until then a card can hold any whole number: the card-fill kit keeps a number the note states exactly, and only chooses from 10 to 20 when the note states none.

## Design rules
1. Every card value must be used somewhere (reach at least one call), unless it is code-only (ids, `chapter`, `stale`, `planned_from`).
2. Structured values are converted to longer, explanatory text before they reach the model.
3. The writer call encourages interesting stories; how this is worded follows what works best in prompt design for this model.
4. The planner collides the protagonist's aim with the spotlight tie into a plan that moves forward.
5. Minor characters never carry the plot, and appear only by role, with no names.
6. Every chapter settles the collision of the protagonist's aim and the spotlight tie for good, and ends with both in a new state that grows out of that outcome. Only the last chapter's state is final. Position is told as first, last or in between, and nothing else.
7. Every chapter is designed in four points: Act 1 starting point (who, where, when); Act 2 central conflict emerges; Act 3 climax or turning point; Act 4 end point. This is per chapter and does not depend on the chapter count. Chapter count is 10 to 20, and a chapter is at most 1,200 words (decided 3 Nov).

## Deferred
- Repo docs (`docs/` is stale on purpose)
- i18n of model-facing wording
- Rotation weighting
- Post-pass quality
- Stalled-edge detection
- Human editing of shifts
- A rerun of the post-pass alone
