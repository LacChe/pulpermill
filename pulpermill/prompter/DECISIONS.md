# Prompter decisions

Recorded in step A1. Plain statements; change one only on purpose.

## Decisions
- **Name.** The new prompter is `mill`, in `pulpermill/prompter/mill/`.
- **Bar for becoming the default.** 13 Tier 1 card-fill probes right or flagged, with no silent error; plus the rebuilt chapter trials, read by a human.
- **When the default changes.** Only after a clean real-model run (stage D). Until then the stub stays the default in `pulpermill/backend/config.py`.
- **Chapter count is 5 to 10.** The schema (version 3, frozen) has no numeric bound, and a check for one would need new code in `web/logic.js`, which A1 may not edit. So for now the range is a prompt-level rule: the planner and the trials treat 5 to 10 as the range. A `warn` rule `chapter_count_in_range` (new check `number_in_range`, params `min: 5`, `max: 10`) is the schema-level follow-up.

## Design rules
1. Every card value must be used somewhere (reach at least one call), unless it is code-only (ids, `chapter`, `stale`, `planned_from`).
2. Structured values are converted to longer, explanatory text before they reach the model.
3. The writer call encourages interesting stories; how this is worded follows what works best in prompt design for this model.
4. The planner collides the protagonist's aim with the spotlight tie into a plan that moves forward.
5. Minor characters never carry the plot, and appear only by role, with no names.
6. By the end of every chapter the spotlight tie's edge and the protagonist's aim must each have moved to a distinctly new state.
7. Every chapter is designed in four points: Act 1 starting point (who, where, when); Act 2 central conflict emerges; Act 3 climax or turning point; Act 4 end point. This is per chapter and does not depend on the chapter count. Chapter count is 5 to 10.

## Deferred
- Repo docs (`docs/` is stale on purpose)
- i18n of model-facing wording
- Rotation weighting
- Post-pass quality
- Stalled-edge detection
- Human editing of shifts
- A rerun of the post-pass alone
