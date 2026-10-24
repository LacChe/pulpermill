## Build
1. **Front-end UI/UX**
2. **Schema** (cards, project, state)
3. **Model params and prompts**
4. **Backend connections and routing**
5. **Pipeline orchestration** (stage order, retries, cancel, progress)
6. **Context assembly** (what each prompt receives)
7. **Validation and state code** (name matching, state updates, retry rules)
8. **Persistence** (storage, snapshots, export/import)
9. **Inference runtime** (where the model runs, replacing Kaggle plus ngrok)
10. **i18n** (English and Simplified Chinese, across all of the above)
11. **Eval harness** (fixed test stories to compare versions)

**Requirements from the PoC**
- No list of PoC failures was kept. One rule stands in its place: checklist-shaped input gives a checklist-shaped story. Prompts feed the model prose and ask for good storytelling, not for a list of items to cover.
- Still to avoid: repetition from chapter to chapter, and drift in person or tense.

**Prompt and param versioning**
- Prompts stored as files
- A version tag on each prompt and param set

**Error handling and observability**
- What forces a retry versus what is only logged
- Logs per stage with timings
- Failures shown plainly in the UI, with a way to resume
- Progress reporting per stage

**Repo structure and build order**
- Module boundaries (frontend, schema, prompts, pipeline, backend)
- Order to build in, with testing between steps
- A shared single copy of the schema
- Definition of “done” for the first usable version