# The prompts (phase 4)

*2026-10-25. Part A, phase 4. A first working draft of every prompt, one builder per call, with the reply shape for constrained decoding. No model has seen any of it yet; phase 7 tunes against the real one.*

**Read first:** the files in `docs/prompts/samples/prompts/`. Each is a complete prompt for the Salt Coast story (or a contract sample for the card calls), followed by its reply shape. `writer-1-open.txt` and `planner-1-think.txt` matter most.

## 1. What is in the box

| File | Where it goes | What it is |
| --- | --- | --- |
| `prompts.py` | `pulpermill/prompts/` | One builder per call. Each returns a `Prompt` (text for one user turn, template version, reply shape, stage, meta). |
| `schemas.py` | `pulpermill/prompts/` | The reply shape for each call as JSON Schema, with enums taken from the request's own word lists. |
| `templates/en/*.yaml` (9) | `pulpermill/prompts/templates/en/` | The craft text, jobs, tasks and reminders, each with a version tag. |
| `render.py`, `textfiles.py`, `limits.yaml`, `__init__.py` | `pulpermill/prompts/` | **Changed** phase 3 files (extractor renderers, `template()` loader, the `chapter:` limits, exports). Replace the old ones. |
| `test_prompts.py`, `schema_lite.py` | `tests/prompts/` | 22 new tests and a small JSON Schema checker (CI has no `jsonschema`). |
| `render_prompts.py` | `tools/` | Regenerates the sample prompts. |
| 11 sample files | `docs/prompts/samples/prompts/` | Generated, for reading. |

## 2. How each call is built

- **Writer:** two sections (revised in `writer-0.2`, see `07-tuning-log.md`): the first opens and builds the pressure, the second makes the choice and closes. Each runs up to half the chapter ceiling and ends sooner when its job is done. The second is shown the whole first section. Rules and craft, then the rendered material, then the job, then a short reminder as the last lines. Stage `write`.
- **Planner:** two prompts, think then beat. Both carry the tone, cast, world, entanglements, an arc line for early, middle, late or last chapter, and, on a retry, the refused attempt with the rules' words. The beat prompt adds the planner's own thinking. Constrained to the places, reveals, plants and shifts that were sent.
- **Events and Shifts:** the page's lists as pick-lists. Shifts sees short handles (T1, H1, K1, P1), never ids; `resolve_changes` maps them back and drops any it does not know.
- **`assemble_generate_reply`** joins the three passes into the contract's reply; a test round-trips it through `contract.parse_reply`.
- **Fill:** the card's fields described from the schema text, related cards turned from ids to names, link fields limited to those names.
- **Judge:** one prompt per rule asked, items numbered `field.N`, hits mapped back to the item ids.
- **Style fit, offstage:** short prompts; offstage takes an optional `spotlight`.
- **End story:** one prompt per character, then the world. These show JSON with real ids because the contract requires each existing item to carry its id back.

## 3. Findings and decisions for you

1. **Size.** The writer's prompt is about 3,000 words and the planner's about 2,000, before tokens are counted. Phase 5 measures it against the context.
2. **Judge scalar fields.** For a field that is one text, the prompt still says "each with its handle", but there is none; the reply's `item` is then null. Harmless, tidy in tuning.
3. **Events and myth reveals.** The Events lists say "hidden truths and false beliefs that may come to light", because a myth is matched by its false statement.
4. **Tolerant events.** Entries in `events` without a `chapter` number are numbered by position, since the contract's own samples have none.
5. **Run under plain asserts, not pytest** (no package index here): 59 tests pass (37 old, 22 new). Please let CI confirm.

## 4. Not done

Token budgets (phase 5), the reading rubric and trial set (phase 6), and all tuning (phase 7).
