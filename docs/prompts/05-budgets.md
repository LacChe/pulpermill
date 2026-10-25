# Token budgets and the harness (phase 5)

*2026-10-25. Part A, phase 5. Every prompt is now measured in real Gemma tokens, with no GPU. The caps are checked against a very large story, and a prompt that does not fit is squeezed or refused before it reaches the model.*

## 1. What is in the box

| File | Where it goes | What it is |
| --- | --- | --- |
| `tokens.py` | `pulpermill/prompts/` | A Gemma 3 tokenizer in plain Python, run on the model's own `tokenizer.json`. No outside packages. `chat_tokens(prompt)` counts what the model sees: `<bos>` plus the chat template. |
| `tokenizer.json`, `tokenizer_config.json` | `pulpermill/prompts/tokenizer/` | The model's tokenizer files from `mlabonne/gemma-3-27b-it-abliterated` (33 MB and 1 MB). Tests that need them skip when they are missing. |
| `budget.py`, `budgets.yaml` | `pulpermill/prompts/` | `measure`, `check`, `fit` (the squeeze), `PromptTooLong`. Context size, reply room per call, margin. |
| `prompt_cases.py`, `test_budget.py` | `tests/prompts/` | The sample, medium and very large stories, and 15 new tests. |
| `budget_report.py` | `tools/` | Writes the report. |
| `budget-report.md` | `docs/prompts/samples/` | The generated report: the numbers behind this page. |
| `render.py`, `blocks.py`, `limits.yaml`, `textfiles.py` | `pulpermill/prompts/` | **Changed.** Caps on three kinds of text that had none, and the squeeze. Replace the old ones. |
| `test_render.py` | `tests/prompts/` | **Changed.** The limits test knows the new caps. |
| `render_prompts.py` | `tools/` | **Changed.** Now writes the golden prompts, from `prompt_cases.py`. |

## 2. The tokenizer

The sandbox has no `tokenizers` package and no way to install one, and CI and the backend should count the same way, so `tokens.py` runs the merges from `tokenizer.json` itself. It follows the file: cut at the special tokens, spaces become `▁`, characters fall back to bytes, lowest merge rank first. The tests pin the chat template's ids against the ones Gemma is known to use (`<bos>` 2, `<start_of_turn>` 105, `user` 2364, `model` 4368). A 4,000-word chapter takes about a tenth of a second.

The answer is exact for ordinary text. I have not been able to compare it against the Hugging Face tokenizer on a large sample, because that is not reachable from here. Part B should run one comparison on the Kaggle machine, where `transformers` is installed.

Words to tokens, measured: English prose is about 1.12 tokens a word, and the prompts about 1.3 tokens a word (the structure and names cost more). Characters per token: about 4.3.

## 3. The budget

A prompt may use `n_ctx - reply room - margin`. In `budgets.yaml`:

- **`n_ctx: 12288`.** My assumption, not a measurement. The Q6 weights are about 22 GB of the 30 GB on the T4x2. Gemma 3 27B keeps about 0.25 MB of cache per token, so 12,288 tokens is about 3 GB. 16,384 might fit and 8,192 certainly does. Part B tries it on the machine; change the number and the tests and report follow.
- **Reply room:** writer 1,600 (a 750-word section is about 900 tokens, a test checks this), planner 1,200 / 900, events 900, shifts 1,000, fill 1,000, end_story 1,800, the short calls 400–500.
- **Margin 300.**

## 4. What the report says (details in `budget-report.md`)

| Story | Result |
| --- | --- |
| **Salt Coast sample** (3 people) | Every prompt fits with at least 60% of its room left. Writer 3,850–4,220 tokens, planner 2,620 and 3,700, events 3,800 (with a 3,000-word chapter), shifts 4,520. |
| **Medium** (5 people, 3 items a list, 8 chapters, sentence-long texts) | The writer is a little over at full caps and fits when every cap is squeezed to 0.85. The rest fit as they are. |
| **Very large** (8 people, 5 items in every list, 12 chapters, every text at its cap) | The planner fits only squeezed to 0.4. **The writer does not fit even at 0.3**: its eight full portraits alone are about 13,000 tokens. Events and Shifts fit. |

How many people fit with no squeeze, on ordinary texts (a sentence or two a field): the writer takes 4, the planner 6. With every text at its cap, none of the sizes I tried fit the writer.

So the caps in `limits.yaml` are generous: one person with every field at its cap is about 1,600 tokens in the writer. The squeeze is the safety net. The caps are not the plan.

## 5. The squeeze and `too_long`

`budget.fit(build)` builds the prompt at caps 1.0, 0.85, 0.7, 0.55, 0.4, 0.3 times the `limits.yaml` values and returns the first that fits, so the model gets the fullest prompt that fits. Counts (`max_behaviors`, the number of full chapters) and the chapter settings stay as they are. Every cut is recorded in the render report, so a clip is never silent. If nothing fits, `PromptTooLong` is raised and the backend answers the contract's `too_long` (413).

## 6. Caps that were missing

The harness found three kinds of text a model wrote that came back into prompts with no cap. They have one now, in `limits.yaml`:

- `standing.field: 300`, the "where they stand now" lines from the Shifts extractor.
- `code.plant: 250`, the open plants.
- `offstage.field: 350`, what happened out of sight. The spotlight pressure and the available reveals use the caps their own cards already have.

## 7. Golden prompts

`docs/prompts/samples/prompts/*.txt` are now golden. `test_the_golden_prompts_are_what_the_code_makes` fails if a prompt changes and the files were not written again. After a wording change on purpose: `python tools/render_prompts.py`, read the diff, commit it. This is also how you will see exactly what a tuning change did in phase 7.

## 8. Decisions for you

1. **Do you want to commit the tokenizer files?** They are 34 MB. GitHub allows it (the limit is 100 MB a file), and the backend and CI both need them. The other choice is Git LFS, or CI that downloads them. I assumed they go in.
2. **Is `n_ctx` 12,288 the right plan?** If you would rather start at 8,192, change one line; the sample story still fits, a medium one squeezes harder.
3. **Bigger casts.** Today the writer gets a full portrait of every person in the cast, so a cast over 4 or 5 leans on the squeeze. If you want stories with 6 to 8 people at full detail, the clean fix is a short portrait for the people who are not in the beat (the writer rarely needs a minor person's competence and history for a scene they are not in). That changes what the writer sees, so I have not done it. Say so and I will, in phase 7 or earlier.
4. **Time.** On a T4 a long prompt is slow to read before the first word comes out. I have no number yet; Part B measures it, and if it is too slow the same budgets are where to cut.
