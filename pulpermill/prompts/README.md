# pulpermill/prompts

Generic code that turns cards into prose and counts what that prose costs. It holds no story prompts and no model wording for a particular call.

| What | Files |
| --- | --- |
| Card renderers: style, cast, world, entanglements, setup, the story so far (the Events record), earlier beats | `render.py`, with the wording frames in `text/en/frames.yaml` and `text/en/style_directives.yaml` |
| Token budget: measure, fit, squeeze | `budget.py`, `budgets.yaml` |
| Tokenizer and the Gemma chat template | `tokens.py`, `tokenizer/` |
| Wording-file loader and length limits (the caps come from the schema fields, plus `limits.yaml`) | `textfiles.py`, `limits.yaml` |

`pulpermill/backend/` imports only `budget` and `tokens` from here.

Story wording (what a writer, planner, extractor or judge is told) belongs in a prompter under `pulpermill/prompter/<name>/`, not here. The old story prompt code was removed in P7.5; it is reachable through the git tag `pre-prompt-design`.
