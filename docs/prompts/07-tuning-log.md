# Tuning log (phase 7)

One entry per change, newest last. Each says what the evidence was, what changed, and how to check it. The evidence for the first
round is the test-3 run (cozy fantasy, 6 chapters) and `Pulpermill_revision_brief_why_test-3_stalled.md`. Prompt versions are in the
template files; every result is recorded with them.

## Step 1: a two-section chapter (`writer-0.2`)

**Evidence.** Chapters ran 2,919 to 3,565 words whatever the beat held. About twelve long paragraphs appeared twice word for word, and
the same exchange recurred inside chapters. Sections were cut mid-word at the token limit ("It wasn'"). The extra-section text told
the writer to "take it further" when a chapter was short. Each later section saw only the last ~300 words.

**What changed.**
- A chapter is two sections: `open_press` (open the scene, meet the obstacle, let the pressure build) and `choice_close` (play the
  choice out with its cost, show what is different, end on the beat's moment). The plant and reveal hints sit with the first, the
  payoff and the "anything not yet on the page" hint with the second.
- Length is a ceiling: "up to about 1500 words, and ends sooner when the scene has done its work". `limits.yaml: chapter.target_words`
  (3,000) is now the ceiling for the whole chapter, shared by the sections.
- The padding is gone: the extra section, `needs_extra`, `short_ratio`, `tail_words` and the 3/4-section roles.
- The second section is shown the whole first section, labelled "The first section of the chapter, as written", with "let every
  paragraph show something the passage has not shown yet". The reminder's `fresh` line now covers images, gestures and turns of talk,
  not only images and gestures.
- `max_output.writer` is 2,400 tokens (a 1,500-word section is about 2,000).
- A section cut at the token limit is cut back to its last whole sentence (`chapter_checks.whole_sentences`, used by the backend's
  `_write` and by `run_chapter`). A new code check, `repeat-paragraph`, flags a paragraph written twice.
- Tests: the section tests, the backend story tests and the trial runner tests now describe two sections. The golden prompt
  `writer-4-close.txt` is replaced by `writer-2-close.txt`.

**Cost.** The second section carries the whole first one (up to ~2,000 tokens). The Salt Coast prompts still fit comfortably (3,900 and
5,400 tokens against 9,600), but a five-person story with a sentence or two in every field needs its caps squeezed to 0.7 for the first
section and 0.4 for the second (see `samples/budget-report.md`). If that squeeze is too hard, the lever is `n_ctx`: the load log of the
test-3 session shows 1.8 GB and 4.7 GB of VRAM free at 12,288, so 16,384 may fit. Done in the next step (below).

**Not changed here (still open from the brief).** The `lingering` pacing directive ("a full paragraph on at least two moments") and the
craft line "let the scene take the time it needs" still push towards length. They are the next thing to look at if chapters run long
with two sections.

**How to check.** Chapter length varies with the beat's weight; no duplicate paragraphs; no section ends mid-word; the second section
does not retell the first. Run the four trials (`tests/trials/`) three times each and read them with `06-reading-rubric.md`, rows 2, 7 and 9
first.

## Step 1b: `n_ctx` 16,384

**Why.** The second section carries the whole first one, which made a five-person story need its caps at 0.4. The test-3 load log
(`model loaded in 125 s; free VRAM after=[1839, 4723] MB` at 12,288) leaves room for the extra cache.

**What changed.** `n_ctx` is 16,384 in `budgets.yaml`, `backend/config.py` and the fake engine (the launcher refuses to start if the
first two differ). All budgets follow: every prompt now has 4,096 more tokens of room. A story of eight full people (every text at its cap) now fits when squeezed (writer 0.3 to 0.4, planner 0.7); five people with ordinary texts need no squeeze. The test for "too long" uses sixteen people (`tier("huge")`).

**If it does not load.** Out of memory at load means set 12,288 again in `budgets.yaml` and `backend/config.py`. Nothing else changes.
The real figure is still to be measured: `memory_by_ctx` in the notebook, in a fresh session where the server has not been started.

## Step 2: goal and planner wording (planner-0.2)

- Goal changes are three kinds, each with its relation to the old goal: achieved (new aim set by what was won or lost), redefined (same thread, later stage), abandoned (turn to what matters more).
- An ended goal no longer says the story is winding down; the story goes on from what is still open.
- Freshness is the goal moving or the story turning, not a new room or props.
- Think steps: state the goal now and which way the chapter moves it; three directions that differ in who drives the scene, one with a pressure's agent on stage; choices that cost something carried forward; one moment to slow down and one to skip.
- Hook pickup: the last chapter's closing moment shows in the planner's timeline as an open question to answer, turn aside on purpose, or pay off within two chapters.
- Late and last chapters list open threads and live pressures and resolve the one or two that carry the most plot.
- Reveals wait past the first third unless the goal depends on them, and a person suspects before knowing. A payoff is a consequence of a plant, never a repeat.
- Reveal, payoff and plant are left empty when none applies.

## Step 2b: temperature and spotlight rotation

- `tools/run_trials.py` samples at temperature 1.0, the same as the backend's prose default.
- A pressure the beat put in the spotlight counts as used even when the chapter never showed it (its agent stayed off stage), so the spotlight and the suggested cast move on to the next pressure instead of repeating one. Code is in `web/plan.js::spotlightUse`.

## Step 3: Events and Shifts rules (events-0.2, shifts-0.2)

- Events: "changed" is worked out from the chapter's text with a quoted phrase as evidence, and says nothing changed when no line shows a difference. List answers stay empty when the text does not show them, even when the beat planned them.
- Shifts: the baseline is where each person stood at the end of the previous chapter, and an empty list is the right answer when nobody moved.
- A tie's bond or edge changes only when the footing changed; a rewording of the same footing stands. Knowledge lines are for matters of plot, not small facts of a scene. A false belief goes under misled, with the false thing in belief.

## Step 4: Fill and Offstage (fill-0.2, offstage-0.2)

- Fill: an example for the suspects rule (the line's subject is the thing suspected, with the person under suspects and knows left empty). The world card gives every object the note mentions its own entry under the note's name.
- Offstage: the request carries `earlier_offstage` ([{chapter, did}], oldest first; contract, page and prompt all updated) and the prompt asks for a different kind of move that complicates the protagonist's goal.

## Step 5: the spotlight rotates and pressures move (shifts-0.3)

**Why.** In the six-chapter test run the spotlight was the same pressure every chapter. `entanglements_shown` over-reports (10 to 14 ids a chapter, usually all three pressures), so counts tied and the first-listed pressure won each time. `spotlightUse` also added a count for a planned spotlight, against the page's rule that planned is not used. Nothing asked a pressure to change after its chapter, so its text and `next_move` stood still.

**What changed.**
- A pressure's use is the spotlight. `usageOf` marks the pressure a written chapter's beat put in the spotlight, and no longer reads pressures out of `entanglements_shown` (`web/usage.js`). `spotlightUse` is gone.
- `pickSpotlight` and `duePressure` rotate by fewest chapters in the spotlight, then the one spotlit longest ago, then list order (`web/plan.js::byAttention`).
- A pressure has a `status`: `active` or `resolved`. A resolved pressure is passed over by the spotlight and is not sent to the planner, the writer or the offstage pass. When every pressure is resolved the rotation falls back to all of them, so a story always has a spotlight. The "more than three active" rule counts active pressures only (`item_count` takes `skip`).
- Shifts (`shifts-0.3`): the pressure the beat put in the spotlight is named by its handle, and the pass is asked to give its new `what` and `next_move` as the chapter leaves them, and `status: resolved` once its next move has happened on the page. `shown` no longer lists pressures (schema, prompt, contract doc, `summary_events.entanglements_shown`).
- The spotlighted pressure is always among the pressures sent to the pass, even when its people are not on stage.

**How to check.** Rerun the test project. The spotlight should visit each active pressure in turn; a pressure's text and `next_move` should differ from chapter to chapter after its turn; a pressure whose agent has acted should end up resolved and stop coming back.

**Not done here.** Goal changes still come from the planner (step 6 moves them to the pass after the chapter).

## Step 6: the goal and the pressure meet; the chapter decides how it ends (planner-0.3, writer-0.3, events-0.3, shifts-0.4)

**Why.** In the six-chapter test run `goal_change` was empty in every beat, so the goal machinery never ran; `goal_now` crawled with each scene (the weather loaf became "acknowledge pearwood's effectiveness"); and the planner decided in advance how each chapter would turn out, which the chapter then had to match. The goal and the pressure never had to meet, so the story stalled in the bakery.

**What changed.**
- The beat plans no outcome. `goal_change`, `goal_now`, `collision_block`, `turn`, `choice_a` and `choice_b` are gone. A beat is where it opens, the cast, `collision_goal` (the scene's one step toward the goal now, written so that it already runs into the pressure in focus), the shift, how it ends, and the optional reveal, plant, payoff and offstage move. `reveal_learners` is optional and the planner no longer fills it: the shifts pass reads who learned a reveal from the chapter. The rules `goal_now_*`, `turn_*`, `choice_is_costly` and `reveal_learners_needed` are gone; `turn_not_repeated` became `aim_not_repeated` (the aim against earlier aims and changed lines).
- Planner (`planner-0.3`): think steps put the goal and the pressure in focus against each other (three ways they could meet, how the chosen meeting plays out, and where each ends up) and the beat is filled from that. It is told the pressure's next move.
- Writer (`writer-0.3`): the scene frame sets the aim and then names the pressure in focus: let it meet the aim, let the scene decide how that goes (the protagonist may get through, be stopped or be turned, the pressure may act, ease or take a new shape), and that is what the story carries on. No choices are set up. The goal the chapter begins from is the "The protagonist is now trying to" line.
- Events (`events-0.3`): every chapter the pass says how it left the goal (`goal_change`: achieved, redefined, abandoned) and `goal_now` (what the protagonist wants from here on). It is shown the goal the chapter began with, the story's own goal, the goals before, the scene's aim and, in the last chapter, that the goal ends there. `goal_now` takes a step on from the old goal or names the aim a new obstacle exposed, and holds for more than one chapter. `goal_landed` is gone: nothing is planned for it to match. A new judged warning, `goal_now_advances`, is declared on the Events card.
- Shifts (`shifts-0.4`): it is shown how the goal ended up and moves the spotlighted pressure to match, in the same breath (see step 5). The protagonist's `decided` records what they did when the aim met the pressure.
- Page: the current goal is Setup's goal, replaced by each written chapter's `goal_now` (a goal worded again as it stood does not restart its age). There is always a goal, so `needs_goal`, `ended`, `goalDirections` and `goalWarnings` are gone; the goal arc only advises the last two chapters. The planner timeline no longer carries a planned turn (earlier chapters' outcomes come from the story so far). The generate request carries `story_goal` and `earlier_goals`.
- Schema version 2 (project files from before this step are not read as current).

**Cost.** Every tier still fits `budgets.yaml`; the planner and writer prompts are a few lines shorter (no choice lines, no block line, no direction list).

**Not done here.** Loose threads (the beat naming the open threads it settles, and the page checking the claim) and a "goal stands" answer for the Events pass (it must pick one of the three, as the handoff asked).

**How to check.** Rerun the test project. `goal_change` should vary and `goal_now` should read as a later stage each time without being reworded; the spotlight should rotate and each pressure's text and next move should change after its turn; chapters should leave the bakery; the planner's thinking should name how the goal and the pressure meet.
