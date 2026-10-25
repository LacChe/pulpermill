# Card renderers (phase 3)

*2026-10-25. Part A, phase 3. The first code. It turns the cards and records a request carries into the prose a model reads. No model, no server, no GPU: text in, text out. Phase 4 puts the craft text at the top and the task at the end, and makes one prompt file per call.*

**Please read the two sample files first** (`docs/prompts/samples/writer-material.txt` and `planner-material.txt`). They are exactly what the renderers make from the sample story (the Salt Coast, chapter 5), and reading them is the check that matters. Nothing here has run against the real model yet.

## 1. What is in the box

| File | Where it goes | What it is |
| --- | --- | --- |
| `render.py` | `pulpermill/prompts/render.py` | One function per card or record: `render_style`, `render_cast`, `render_world`, `render_entanglements`, `render_setup`, `render_standing`, `render_story_so_far`, `render_earlier_beats`, `render_scene`, `render_code_numbers`. |
| `blocks.py` | `pulpermill/prompts/blocks.py` | `writer_blocks(request)` and `planner_blocks(request)`: the rendered material for each call in its fixed order, as named blocks. `assemble` joins them under headings. |
| `textfiles.py`, `__init__.py` | `pulpermill/prompts/` | Loading the wording and the limits. |
| `style_directives.yaml` | `pulpermill/prompts/text/en/` | The concrete line for every Style option (the table you approved in the writer's brief, 2.3), including seven separate attitude lines. |
| `frames.yaml` | `pulpermill/prompts/text/en/` | Every framing sentence: the portraits note, the knowledge note, "where they stand now", the scene sentences, the planner's code numbers, the headings. |
| `limits.yaml` | `pulpermill/prompts/limits.yaml` | A length cap for every free-text field, and how many chapters are told in full. |
| `test_render.py` | `tests/prompts/test_render.py` | 37 tests. |
| `salt-coast-generate.json` | `tests/prompts/fixtures/` | The sample story as a `generate` request. The planner's request is made from it inside the test file. |
| `render_samples.py` | `tools/render_samples.py` | Regenerates the two sample files. |
| the two samples | `docs/prompts/samples/` | Generated output, for reading. |

The existing schema files are not touched. The new wording lives in new files next to the new code, so none of the schema's own lint and parity tests are affected.

**Commit message:** `Phase 3: card renderers, wording files, length caps and tests`

## 2. How it works

1. **One scope per call.** `scope="writer"` (also what the extractors will use, since they see the same cast) or `scope="planner"`. The planner gets the tone only (genre, lens, humor, attitude, pacing), no age, appearance, speech or dispositions, every place and thing with its use count, and every pressure.
2. **The schema's own wording is reused** wherever it exists: the option expansions (person, tense, distance and so on), the lead-ins, and the item templates for places, things, groups, rules, ties, holdings and pressures.
3. **Empty slots leave nothing behind.** An item template is read as clauses, and a clause after the first that holds an empty value is dropped. A pressure from a circumstance has no "Next move:" line. A beat with no plant has no plant paragraph.
4. **A fixed order**, from the schema's `RENDER_ORDER` where it has one. The writer's blocks are: style, world, people, entanglements, where they stand now, where the story stands, the last chapter's ending, the scene. "Where they stand now" comes after the cards and says it is newer than them.
5. **Names, never ids.** A test collects every id in the sample request and fails if any appears in the output.
6. **A length cap per field.** A field over its cap is cut at the last sentence that keeps most of it, and the cut is recorded in a `Report`. The backend logs it, so a clipped field is never silent. Fixed fields (name, age, sex, appearance) have no cap. The caps are guesses until phase 5 measures tokens.
7. **The scene is a situation.** Your own wording for the goal, the block, the choices, the turn and the ending is quoted as written, never recased, because it may start with a name ("Ines learns…"). Only words that cannot be names (the, she, a…) are ever lowered, and only where a sentence continues ("Right now, she owes him…").

Size on the sample story: the writer's material is 14,500 characters (about 2,600 words) and the planner's 9,300 (about 1,700 words). My estimate is 3,500 and 2,300 tokens. That is before the craft text, the previous section's words and the reminder, and phase 5 gives the real count.

## 3. Where I changed what was approved, and why

Reading the first output showed problems the tests did not catch. Each fix below is small, but you should know about all of them.

| # | Change | Why |
| --- | --- | --- |
| C1 | A myth reveal is worded as "the truth comes out behind something people believe. The belief: … The truth: …". A hidden rule is "something hidden comes to light". | My first draft said the reader "learns that" the false statement. For a myth that is the opposite of the reveal. The planner's list of reveals has the same split. |
| C2 | "Who learns it: Suvi and Aino." replaces "Suvi and Aino come to know it". | The verb broke for one person ("Suvi come"). |
| C3 | The choice is "either choice costs her the other" (he, him, they, them for the others). | "whichever she pick" broke agreement. |
| C4 | Three lines of the Characters wording are rewritten in `frames.yaml`: fear ("protects herself"), flaw ("sabotages her own aims") and dispositions ("when she is calm, the tendency is to recount the till"). | The schema's lead-ins say "themselves" and "they" for everyone, which read wrongly beside a named woman or man. The schema text is unchanged. For a character whose sex is "other" the first two read "themselves" and "their own aims"; the dispositions line changes for everyone. |
| C5 | Knowledge reads "Suvi has been misled about: The cellar floods…". | The existing template gave "Suvi has been misled about The cellar floods…", which has a capital in mid-sentence and no verb for the statement. |
| C6 | The genre line from the brief is dropped. The lens line stays. | The existing genre lead-in already says "Let it shape mood, conventions and texture". Saying it twice was noise. |
| C7 | "(offstage)" became "[offstage]". | A pressure read "(from The Harbour Board (offstage); …)". |
| C8 | Four directives were reworded to be positive: distance external, humor none, imagery literal, voice distinct. A test now fails on "don't", "do not", "never", "avoid", "without" and "must not" in the directives and the writer-facing frames. | Your phrasing rule. My brief's own table broke it. |
| C9 | The scene's goal and block are written as "What Suvi is after: …" and "What stands in the way: …", not as one flowing sentence with "but". | The writer's field may start with a name, so it cannot be merged into a sentence without risking a wrong capital. This is still more of a list than the brief's 2.4 draft, so please judge it in the sample. |
| C10 | **F7 settled:** the writer is told the latest 3 chapters in full and earlier ones as their "changed" line. The planner gets the latest 4. | The brief left this to phase 3. Both numbers are in `limits.yaml`. |

## 4. Findings for you

1. **The style block repeats itself.** Each option prints its existing expansion and then my concrete line, and the two often say the same thing ("Sentence length follows the moment… Match sentence length to the moment…"). It is about 500 of the writer's 2,600 words. You approved keeping both, so that is what it does. My suggestion: keep both for the first real runs, then try directive-only for the writer and compare in phase 7. It is one line to change in `render_style`.
2. **`use_counts` is mostly unused.** The planner's request carries counts for behaviors and things, but the planner sees no behaviors, and the counts for things already arrive on the world's objects. Only the characters' counts are used. The front end could stop sending the rest. Not urgent.
3. **The writer sees every rule, but only the beat's reveal as an instruction.** The other entries of `available_reveals` reach the writer only as World rules, which is what the data-flow document says. They matter to the Events extractor in phase 4.
4. **Tests ran, but not under pytest.** This sandbox has no access to the package index, so I ran the 37 tests with a small runner that calls each function. They are plain asserts and the CI command (`python -m pytest tests`) needs only pytest, pyyaml and pydantic, which the workflow already installs. Please let the CI run confirm it.

## 5. Not done in this phase

- The craft text, the tasks, the reminders and the retry block: phase 4.
- The renderers for the extractors' material (the pick-lists, X2's handles), `fill`, `judge` and `end_story`: phase 4. The cast and entanglements renderers are written to be reused there.
- Real token budgets: phase 5, which needs the Gemma tokenizer files.

## 6. Next

Phase 4 drafts the prompts in the order you set: the chapter writer, the planner, the Events and Shifts extractors, `fill`, `judge` and `style_fit`, then `offstage` and `end_story`. Each is a template file with a version tag. I need nothing from you first, except that I would like you to read the samples and tell me if the chapter's scene block reads the way you want (C9), and what to do about finding 1.

For phase 5, please have `tokenizer.json` and `tokenizer_config.json` ready to upload (from `mlabonne/gemma-3-27b-it-abliterated` on Hugging Face).
