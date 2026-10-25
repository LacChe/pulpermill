# The reading rubric and the trial set (phase 6)

*2026-10-25. Part A, phase 6. How a chapter is judged, and the four chapters every prompt version is run against. Modelled on `tests/cardfill/03-scoring-protocol.md`: read and grade first, look at what the code flagged second.*

## 1. What is in the box

| File | Where it goes | What it is |
| --- | --- | --- |
| `chapter_checks.py` | `pulpermill/prompts/` | The code checks: 10 small heuristics that return pointers (`Flag`). The backend can reuse them. |
| `trial_set.py`, `test_trials.py` | `tests/prompts/` | The four trials, built from the Salt Coast story, and 22 new tests (checks, trials, runner loop). |
| `run_trials.py` | `tools/` | Runs the trials: `--dry` writes the first prompts, `--url` asks a llama.cpp server for every section. The `--url` path has not met a real server yet. |
| `README.md`, `scoring/chapter-scoring.csv`, `results/.gitkeep` | `tests/trials/` | How to run and record, and a sheet with 12 empty rows (4 trials x 3 runs). |
| `06-reading-rubric.md` | `docs/prompts/` | This page. |

## 2. The trials

Each is the Salt Coast story with a different beat and voice. The cards are the same, so a difference in the output comes from the chapter and the prompt, not the material.

| Trial | Chapter | Voice | What it tests |
| --- | --- | --- | --- |
| **T1-pressure** | 5 | first, past, close, dry | A scene with dialogue and a hard choice. The beat as a scene and not a list; subtext; a myth that must not be explained; the planted lock. |
| **T2-quiet** | 6 | third, **present**, deep, warm, lingering | An easier chapter with no chase. A style change you can see; interior life. |
| **T3-fast** | 7 | third, past, **external, brisk, terse** | A short fast chapter. Pace without a list of events; action that stays specific; an ending that hooks. |
| **T4-opening** | 1 | third, past, close, wry | No history. The normal life and the break; people introduced without a roll call; not telling the whole story at once. |

Three runs each, so 12 chapters per prompt version. A trial is never edited once results exist: add a T5 and keep the old ones.

## 3. The rubric

Grade each chapter 0, 1 or 2 on nine questions, by reading it through once like a reader, then again with the beat beside it. Total out of 18. The first two matter most: a chapter can tick every other box and still be a checklist.

| # | Question | 0 | 1 | 2 |
| --- | --- | --- | --- | --- |
| 1 | **Voice match.** Does it sound like the Style asked for (person, tense, distance, humor, rhythm, the narrator and lens notes)? | Could be anyone, or the wrong person or tense. | Right on the big settings, flat on the rest. | You could tell the Style from the prose alone. |
| 2 | **Reads as story.** Does it move like a scene, or like the beat's parts in order? | Paragraph per beat part; the beat's words echoed; summary instead of scene. | Mostly scene, with stretches of listing or summary. | Specific, surprising detail; people do things for their own reasons; the beat is felt, not announced. |
| 3 | **Beat landed.** Goal, block, the choice, the turn, the shift and any reveal, plant or payoff all happen. | A main part is missing or only told. | All there, but one is thin or rushed. | All there and each does work in the scene. |
| 4 | **Person and tense held.** Start to end, including the seams between sections. | Drifts, or changes at a seam. | One slip. | Held. |
| 5 | **Continuity.** Names, facts, who knows what, the last chapter's ending picked up, and the cards obeyed. | A contradiction of a card or of the story so far. | Small vagueness; nothing contradicted. | Earlier chapters and the standing lines are felt. |
| 6 | **Secrets kept.** Hidden truths stay hidden unless the beat names them; a myth is believed, not explained. | A hidden truth is stated. | Hinted too hard, or a myth is half-explained. | Kept, and it shows in what people avoid. |
| 7 | **Freshness.** No repeated phrases, pet words, sentence shapes or paragraph openers; no copy of the last section. | Repeats you notice without looking. | A few repeats. | Varied throughout. |
| 8 | **People alive.** Each speaks differently (when the Style says distinct), wants something in the room, and has something unsaid. | Interchangeable voices. | Some difference. | You could cover the names and know who is talking. |
| 9 | **Ending.** Stops on the moment the beat names, with the question hanging; the sections join without a seam. | Wraps up, summarises, or misses the moment. | Right moment, weak landing. | Lands and leaves it open. |

Length is a code check, not a reading score. A chapter under 2,400 or over 3,900 words is recorded as such.

## 4. The loop for one run

1. Run the trial. `tools/run_trials.py` writes one file per run in `tests/trials/results/<writer version>/` with the chapter first and the flags after it.
2. **Read the chapter and give the nine scores before you open the flags.** This keeps the flags from shaping your reading.
3. Look at the flags. For each, write down whether it was right (`flags_that_were_right`). A flag that fired on something you scored 2 is a false alarm, and worth a note.
4. Record the row in `scoring/chapter-scoring.csv`: the prompt version, the model and settings, the words, nine scores, and what failed or was retried.

The flags are small heuristics for English. They find what a machine can find: length, person and tense drift, repeated phrases, structure leaking in (headings, bullets, "Here is the next section"), beat sentences copied word for word, a hidden truth said early, a cast member missing or an offstage one crowding in, an ending that is cut or misses its moment, almost no dialogue or only dialogue, mixed quote marks, another script. They never score a chapter.

## 5. Thresholds and what to do about them

- **Good version:** a mean of 14 or more of 18 across the 12 runs, no chapter under 10, and rows 1 and 2 never 0.
- **Silent failure:** a chapter you scored 0 on rows 4, 6 or 7 where no flag fired. Fix these first; the flag may need a rule.
- **Unstable:** three runs of one trial that differ by 4 or more points. Look at what differs in the prompt's room to move.
- **Checklist story:** rows 2 and 3 split (3 high, 2 low). The prompt is making the model tick boxes. Read `docs/prompts/02-writers-brief.md` section 2.4 before changing anything.

## 6. Tuning rules (phase 7)

1. One change at a time. Bump the template's `version`, regenerate the golden prompts (`python tools/render_prompts.py`) and read the diff.
2. Rerun all four trials, three times. Do not judge a change on one chapter.
3. Check that no trial that was good got worse.
4. Do not tune to a flag. If a flag fires and the chapter reads well, the flag is wrong.
5. First thing in phase 7: the **style change test**. Take T1, change one Style option (say humor from `dry` to `none`), keep everything else, run it. If the prose does not visibly change, the style directives are not reaching the writer, and nothing else matters until that is fixed.

## 7. Decisions for you

1. **The trials.** Four chapters from one story, in four voices. If you want a different genre in the set (a fantasy or a sci-fi one), tell me and I will add T5 and T6 on a second sample story. I did not, because every story needs its own cards and the first run would then be mostly about the cards.
2. **Who grades.** I assume you do, and I will help in phase 7 by reading chapters alongside you and scoring them separately for comparison, as the card-fill tests did. Say if you want a different split.
3. **Temperature.** `run_trials.py` defaults to 0.8. Part B decides the real setting; the score sheet records it on every row, so results made at different settings stay separate.
