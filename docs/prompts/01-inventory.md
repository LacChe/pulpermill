# Prompt inventory (phase 1)

*2026-10-25. Part A, phase 1 of the implementation brief. No code. For every model call: what goes in, in what order, in what form, and what comes out. Read it, change what you disagree with, and say when to start phase 2 (the writer's brief).*

Sources: `docs/what-feeds-what.md`, `docs/who-does-what.md`, `docs/backend-contract.md`, `pulpermill/schema/contract.py`, the request builders in `web/plan.js`, `web/generate.js`, `web/logic.js`, and the wording in `pulpermill/schema/text/en/`. Where the doc and the code disagree, this inventory follows the code and says so (section 6).

## 1. Decisions

| # | Decision | Status |
| --- | --- | --- |
| D1 | The planner (P) also sees genre, lens, attitude, humor and pacing. | Decided by you |
| D2 | P also sees competence, vulnerability and history for the cast. | Decided by you |
| D3 | The Shifts extractor (X2) sees the beat's two choices, so `decided` records which was taken. | Decided by you |
| D4 | The cast suggestion also uses the pressures' `bears_on`. | Already done in `castChoices` (`web/plan.js`) |
| D5 | The chapter is written in 3 or 4 sections of about 750 words, plus a continuation pass if the total is under about 80% of 3,000 words. | Approved by you |
| D6 | Quant: Q6 (read as `Q6_K`, 22.2 GB). | Decided by you. Consequences in 2.1 |
| D7 | Shared token and the ngrok skip-warning header. | Decided by you. Consequences in 2.2 |
| D8 | The `generate` timeout is raised. | Decided by you. Value in 2.1 |
| D9 | `status` keeps the contract's stage names. All writing sections report `write`. Section progress goes to the backend log. | Proposal (the stage list is closed in `contract.py`) |
| D10 | A section that fails (empty, wrong language) is retried once inside the backend. A chapter that is merely short is returned as written and its word count is logged. Any other failure throws everything away, as the contract says. | Proposal |
| D11 | Prompts feed prose, not forms (section 3). | Your note, taken as a rule |

Open items for you are in section 6, each with a recommendation.

## 2. What the answers touch

### 2.1 Quant 6 and the timeout

These are my back-of-envelope numbers, not measurements (brief section 10, item 6). They are here so nothing surprises you in part B.

- **Memory.** `Q6_K` is 22.2 GB of weights on two T4s (about 30 GB usable in total). That leaves roughly 8 GB for the KV cache and working buffers. A 12k to 16k context fits only if the llama.cpp build keeps a sliding-window cache for Gemma 3 (recent builds do) or the KV cache is quantized. Part B step 2 checks this first. Fallbacks if it does not fit: `Q5_K_M` (19.3 GB), then `Q4_K_M` (16.6 GB).
- **Speed.** Generation is limited by memory bandwidth, so a bigger quant is slower. I expect about 8 to 10 tokens per second at Q6, against the 10 to 15 in the brief. Unmeasured.
- **Time.** A 3,000-word chapter is about 4,000 tokens. At 8 to 10 tokens per second that is 7 to 8 minutes of writing, plus reading the prompt on every pass, plus the Events and Shifts passes. I expect 12 to 15 minutes, which is at the edge of today's 900 seconds.
- **Proposal:** raise `generate` to 1800 s in `web/client.js` and in `docs/backend-contract.md` (part B step 1, with the numbers re-checked after the first real run). `end_story` (600 s) and `judge` (180 s) may need the same look. See the `judge` row in 5.6.
- **Cache.** The section passes share a long identical start (style, world, cast, entanglements, story so far, beat). If the server keeps its prompt cache, only the end of the prompt is read again. So everything that changes from one section to the next goes at the end of the prompt (section 5.1).

### 2.2 Token and ngrok header

I read "ngrok with token and skip warning, yes" as: the page sends a shared secret in a header, and also the `ngrok-skip-browser-warning` header, and the backend checks the secret. Tell me if you only meant the ngrok account token that starts the tunnel; that one is separate and never goes in the repo.

What it changes (a contract change, so it moves together with the vectors, per brief section 11). Not in this phase; it belongs to part B step 1 so CORS is right from the start:

- The page today sends only `content-type` (`web/client.js`, line 75). It would also send `ngrok-skip-browser-warning` and a token header (name to settle, for example `x-pulpermill-token`). Custom headers make the browser send a preflight, so the backend's `access-control-allow-headers` must list all three headers. The preflight itself never carries the token, so `OPTIONS` must answer without it.
- A new backend error kind for a missing or wrong token (proposal: `unauthorized`, HTTP 401) with a plain sentence for the writer. `status` also checks the token, so the Check button can tell a wrong token from a dead tunnel.
- The token is typed in the model-connection box next to the address and kept in the page's settings. It is never written into the project file or the exports.
- Files that change together: `docs/backend-contract.md`, `pulpermill/schema/contract.py`, `web/logic.js`, `web/client.js`, `web/data/text.en.json`, the connection box in `web/index.html` and `web/app.js`, `web/tests/contract-vectors.json`, and both test suites.

## 3. One rule for every prompt: feed prose, not forms

Your note: if the input is a checklist, the story comes out a checklist. So this is how the prompts are built, and it is why the "Form" column exists in the tables below.

1. **The writer (W) is briefed like a novelist.** A few paragraphs about the world, one portrait per person on stage, then the scene. Not rows of `field: value`.
2. **The scene engine is a situation, not a to-do list.** The beat's goal, block, choice, turn and ending tell the model where the scene is heading and what must be true when it stops. They are not five paragraphs to produce, in order. The model is told it may take any road there and may add what the scene needs. Only what the beat names (the reveal, the plant, the payoff, a goal change) has to land.
3. **Cards are material, not a list to cover.** Nothing on a card has to appear in a chapter. People act from who they are; a want or a fear shows up as a choice, not as a label.
4. **Empty slots disappear.** Some existing templates print their label even when the value is empty: the Events template (`Set up: … Paid off: … Came to light: …`) and the beat template (`{offstage_did} {offstage_reach} {goal_change} {goal_now}`). The renderer (phase 3) drops any clause whose value is empty.
5. **Records read as a story so far.** `earlier_events` become a few plain paragraphs, not `Chapter 3: … What changed for the protagonist: …` repeated for every chapter. Because X1's `happened` is all that later chapters ever see of a chapter, X1 is asked to write it as short plain narration of events, not as a log.
6. **Say what good looks like, in positive words.** A want meeting an obstacle, a choice that costs something, concrete detail, an ending that leaves something open. The craft wording itself is phase 2.
7. **Lists stay lists where code needs them.** Pick-lists for the extractors and the planner's shortlists are lists. The danger is only where the output is prose. So: W and O get the strictest treatment; P next, because its beat becomes W's brief; the extractors least.

## 4. How every prompt is put together

- **One user turn.** Gemma has no system role. Rules and material first, the task for this call next, a short reminder last. The model's turn format is `<start_of_turn>user … <end_of_turn><start_of_turn>model`; the template is applied by the server.
- **Names, never ids.** One exception: X2's proposed changes must point at an item the page sent. They use short handles (`T1`, `K3`) that the backend maps back to the ids the page sent. The backend never makes an id.
- **Language line** in English: write in `language`. Check the output language and retry once if it drifted.
- **Structured replies use constrained decoding.** Where the request already lists the allowed words, the grammar is built per request from those lists, so the model cannot return a word the page will not match:
  - X1: `paid_off` from the open plants, `reveals_landed` from the available reveals, `behaviors_seen` from the cast's behaviors, `things_seen` from the objects in play.
  - X2: `character` from the cast, `item` from the handles, `field` from the fields that move in that section, `status` from `knows`, `suspects`, `misled`.
  - P: `where` from the places, `shift` from `legal_shifts`, `reveal_rule` from the available reveals, `reveal_learners` and the rest from the cast, `payoff` from the open plants (at most two), `goal_change` from its three values.
  - Retry only for shape failures: two attempts in total, the first failure's message goes into the second. The page still checks names and links.
- **Token check before running.** `too_long` (413) if the prompt does not fit. For W, check the largest pass. Real budgets come in phase 5 from the tokenizer; any number in this document is a guess.
- **Stages** reported by `status` (only `offstage`, `plan`, `generate` and `end_story` are polled): `offstage` for O; `think` then `beat` for P (`retry` instead of `think` when the request carries `retry`); `write`, `events`, `shifts` for generate; `update` for E. `fill`, `judge` and `style_fit` are short and not polled.

## 5. The calls

Column key: **From** is the request field. **Form** is `prose`, `list`, `pick-list`, `verbatim` (text copied as is) or `rules` (fixed sentences from the option expansions).

### 5.1 W: the chapter writer (`generate`, write pass)

Reads: `style`, `setup`, `goal`, `cast`, `world`, `entanglements`, `standing`, `earlier_events`, `previous_ending`, `beat`, `open_plants`, `available_reveals`, `chapter`, `chapter_count`, `language`.

Runs once per section (D5). Blocks 1 to 9 are identical in every section so the server's cache can be reused; blocks 10 to 12 change.

| # | Block | From | Form | Notes |
| --- | --- | --- | --- | --- |
| 1 | Language, person, tense, distance, and what a good chapter is | `language`, `style.person`, `style.tense`, `style.distance`, backend text | rules + prose | Person and tense are hard rules. The craft text is written in phase 2. |
| 2 | Style | `style` (all fields and the four notes) | prose | Two paragraphs, genre first (`RENDER_ORDER`). Each field becomes a concrete instruction. |
| 3 | The world | `world`, `beat.where` | prose | All of World, hidden and myth rules and their truths included, grouped as what is common, what is hidden, what people wrongly believe. The beat's place in full, other places by name. Objects in the scene in full (see F1). A group's `felt` line always; `nature` and `hold` when it is in a tie or pressure on stage. Terms as vocabulary. |
| 4 | The people on stage | `cast` | prose | One portrait each: name, age, sex, appearance, sketch, wants, fear, flaw, values, behaviors, competence, vulnerability, speech, history. Fixed fields in full. |
| 5 | Their entanglements | `entanglements` | prose | Ties, holdings, knowledge per person, pressures that touch the cast. A person who is not on stage is named only and marked "not present, may be mentioned or thought of". |
| 6 | Where they stand now | `standing` | prose | Marked as overriding the cards. Left out when empty. |
| 7 | The story so far | `setup`, `goal`, `chapter`, `chapter_count`, `earlier_events` | prose | Protagonist and stakes. Chapter 1 only: normal and disruption (the page already removes them later). The current goal, or "the goal has ended, wind the story down". "Chapter n of N", and a plain statement when it is the last chapter. Earlier events as a few paragraphs. |
| 8 | How the last chapter ended | `previous_ending` | verbatim | At most 1,500 characters, cut by the page. None in chapter 1. |
| 9 | The scene | `beat`, `open_plants`, `available_reveals` | prose | A situation, not a list (rule 2 in section 3). Where, when and since when, who is there, what the protagonist is after and what stands in the way, the choice, what is different by the end, harder or easier, where it ends. If there is a reveal: the rule, its truth and who learns it. If there is a plant: what to set up. If there is a payoff: which open plants to resolve, and the chapter each was set up in. An offstage move and how it reaches the protagonist. A goal change. The spotlight pressure. Empty items are dropped. |
| 10 | This chapter so far | the backend | verbatim | The last ~300 words written. Not in section 1. |
| 11 | This section's job | the backend | prose | One or two sentences: "section 2 of 4: the choice is made", the word target, and whether this is the last section (then it must reach where the beat ends). |
| 12 | Reminder | the backend | prose | Three lines: person, tense, distance, language; the scene is not over unless this is the last section; reply with story text only. |

Reply: plain text for the section. The backend joins the sections into `chapter_text` and logs words per section and in total.

Not sent to W: unchosen characters, use counts, `legal_shifts`, notes, ids.

### 5.2 P: the planner (`plan`)

Reads: `chapter`, `chapter_count`, `style`, `setup`, `goal`, `cast`, `world`, `entanglements`, `spotlight`, `legal_shifts`, `open_plants`, `available_reveals`, `use_counts`, `earlier_beats`, `earlier_events`, `latest_shifts`, `offstage`, `retry`.

Two passes: think in free text (short and structured, so it does not ramble at 8 to 10 tokens a second), then fill the beat under a grammar. The thinking comes back and is shown to you.

| # | Block | From | Form | Notes |
| --- | --- | --- | --- | --- |
| 1 | The job | the backend | prose | Plan one chapter as a scene. Written in phase 2. |
| 2 | Where the story stands | `chapter`, `chapter_count`, `setup`, `goal` | prose | Chapter n of N, with what that means for the arc. Protagonist and stakes. Chapter 1 only: normal and disruption. The current goal, or none (then no goal change is offered). |
| 3 | The tone (D1) | `style.genre`, `lens`, `humor`, `attitude`, `pacing` | prose | Only these five. The sentence-level craft fields stay with W. |
| 4 | The world | `world` | prose | Name, era, everyday life (the normal the story breaks). All places with effects and use counts. Objects with holders and use counts. Groups. Rules with costs. |
| 5 | The people on stage | `cast` | prose | Name, sex, sketch, wants, fear, flaw, values, and (D2) competence, vulnerability and history. No behaviors. |
| 6 | Their entanglements | `entanglements` | prose | Ties, holdings, knowledge for the cast. **All** pressures with their next moves. |
| 7 | Where they stand now | `latest_shifts` | prose | Overriding. |
| 8 | The story so far | `earlier_events`, `earlier_beats` | prose | Events as a few paragraphs. Earlier beats as one line each: when, where, the turn, harder or easier. This is what the "turn is not repeated" check compares against, and the timeline for `when_time`. |
| 9 | Offstage move | `offstage` | prose | Only when present. Plan around it. |
| 10 | What the code has set | `spotlight`, `legal_shifts`, `open_plants`, `available_reveals`, `use_counts` | list | The spotlight pressure (the chapter turns on it). Which shifts are allowed. Open plants (candidates for a payoff). Reveals still available, with their truth. Use counts, phrased as what to lean towards. |
| 11 | Retry | `retry` | prose | Only when present: the failed thinking, the failed beat, and the rules' own words about what was wrong. |
| 12 | Task and format | the backend | prose | Last. |

Reply: `thinking` (text) and `beat` with `where`, `when_time`, `when_gap` (not in chapter 1), `collision_goal`, `collision_block`, `choice_a`, `choice_b`, `turn`, `shift`, `ends_on`, optional `reveal_rule`, `reveal_learners`, `plant`, `payoff`, `goal_change`, `goal_now`. Not planned by P: cast, chapter, spotlight, the offstage fields, `planned_from`.

Note: the cast is chosen by you before Plan, so P does not choose it. The brief's "cast suggestions" among P's shortlists is out of date. The choices, turn and ending are the beat's scene engine, so P is asked to build each option from a want or a value of someone on stage, and to avoid repeating an earlier turn.

### 5.3 O: the offstage pass (`offstage`)

Reads: `chapter`, `chapter_count`, `cast`, `world` (groups and places with use counts), `entanglements` (ties, holdings and pressures that touch them), `latest_events`.

| # | Block | From | Form | Notes |
| --- | --- | --- | --- | --- |
| 1 | The job | the backend | prose | What a background group or a place does between chapters, and how the change reaches the protagonist. Never about the spotlight. |
| 2 | The groups and places | `world` | prose | Groups: nature, hold, felt. Places: description, effect, how often used. |
| 3 | What touches them | `entanglements` | prose | Ties, holdings, pressures, by name. |
| 4 | Who is on stage | `cast` | prose | Names, and who the protagonist is. Nothing more. |
| 5 | What just happened | `latest_events` | prose | The last chapter's events. None in chapter 1 (O is not asked then). |
| 6 | Task and format | the backend | prose | Last. |

Reply: `did`, `reach`, both required. Written as free text under a grammar of two strings. See F2 (O is not told the spotlight).

### 5.4 X1: the Events extractor (`generate`, Events pass)

Reads: the chapter text just written, plus from the request `beat`, `open_plants`, `available_reveals`, `cast` (behaviors), `world` (objects), `goal`.

| # | Block | From | Form | Notes |
| --- | --- | --- | --- | --- |
| 1 | The job | the backend | prose | Say what the text shows happened. Conservative: a planned plant, payoff, reveal or goal change counts only if it is visibly in the text. |
| 2 | What was planned | `beat` | prose | The planned reveal (with its truth), plant, payoff, goal change. |
| 3 | The pick-lists | `open_plants`, `available_reveals`, `cast` behaviors, objects in play | pick-list | Exact wording to copy back. Behaviors are the "when …" states. All available reveals are offered, not only the planned one, so a secret that slipped out is caught. |
| 4 | The chapter | the text | verbatim | The whole chapter. |
| 5 | Task and format | the backend | prose | Last. |

Reply (`events`): `happened` (one sentence per event, usually 4 to 8, written as plain narration of events that change who knows what, who holds what or where people stand), `changed` (one short sentence, or empty), `planted` (one thing, or null), `paid_off`, `reveals_landed`, `behaviors_seen`, `things_seen` (each from the pick-lists), `goal_landed` (yes or no).

### 5.5 X2: the Shifts and Entanglements extractor (`generate`, Shifts pass)

Reads: the chapter text, plus `cast`, `entanglements`, `beat`.

| # | Block | From | Form | Notes |
| --- | --- | --- | --- | --- |
| 1 | The job | the backend | prose | Who moved, and what in the live entanglements changed. Only what the text shows. |
| 2 | The people | `cast` | prose | Name, sex, wants, fear, flaw. |
| 3 | The choice (D3) | `beat.choice_a`, `choice_b` | prose | "The chapter posed this choice. In `decided`, record the one the text shows was taken, or what they did instead." |
| 4 | The live entanglements | `entanglements` | list with handles | Ties (bond, edge), holdings (held by), knowledge (status), pressures (what, next move, bears on). Each with a handle. |
| 5 | The reveal | `beat.reveal_rule`, `reveal_learners` | prose | So X2 can propose who actually learned it. |
| 6 | The chapter | the text | verbatim | |
| 7 | Task and format | the backend | prose | Last. |

Reply: `shifts` (only people who moved, at most five, each once, with at least one of `believes`, `fears`, `wants`, `refuses`, `decided`); `changes` (`section`, handle mapped back to `item`, `field`, `value`; only the fields that move: tie `bond` and `edge`, holding `held_by`, knowledge `status`, pressure `what`, `next_move`, `bears_on`); `new_knowledge` (at most three: `person`, `status`, and exactly one of `rule` or `fact`).

### 5.6 The card calls

| Call | Reads | What goes in, in order | Reply | Notes |
| --- | --- | --- | --- | --- |
| `fill` (F) | `card`, `instance`, `note`, `example_chapter`, `values`, `related`, `language` | 1. The job and the card's scope rule (what it may invent and what it must not; the table is in `tests/cardfill/00-test-plan.md`). 2. The card's fields: help, examples and expansions from the text files. 3. The cards it reads (`related`). 4. The card as it stands (`values`). 5. The writer's note and the example chapter. 6. Task and format. | `values` by field key; links as names, choices as option values, lists as objects without ids | A first working prompt in phase 4; tuning later with the cardfill kit. Empty means no answer. |
| `judge` (J) | `card`, `instance`, `rules`, `values`, `related` | Per rule: its `judge_prompt` from the text files, the fields it is about, and the context it names (for example the protagonist's wants, the pressures, the ties). | One result per rule asked, with `hits` (`field`, optional `item`, `key`) | The judge prompts ask for a rewrite, and the reply has nowhere to put one (F5). Outline rules judge every beat, so ask one rule at a time. At 8 to 10 tokens a second and 1,000 to 3,000 tokens to read, six rules may not fit in the 180 s limit (see 2.1). |
| `style_fit` (S) | `style`, `protagonist` | Person, tense, distance and the narrator note; the protagonist's character card; the question. | `fits`, optional `message` | See F3 for which character fields. |
| `end_story` (E) | `style`, `setup`, `characters`, `world`, `events`, `shifts` | The job (what a person and a world are like after this story, never contradicting the fixed fields). Setup. Each character. The world. Events as a story so far. Shifts per person. Task. | `characters` (each with the id it was sent; fields not given stay as they were) and `world` | Reads summaries only, never the chapters. All characters, not only a cast. Likely one pass per character (stage `update`). |
| `status` | nothing | Not a model call | `state`, optional `stage` | Answers while the model works. |

## 6. Findings that need your decision

Each is something the repo's own documents disagree about, or something a prompt needs that no request carries. My recommendation comes first. None of them is applied in the files I am sending, except where it says so.

| # | Finding | Recommendation |
| --- | --- | --- |
| F1 | `what-feeds-what.md` says W sees the least-used behaviors and the objects "in the scene", chosen by code. The `generate` request carries no use counts, so the backend cannot rank them. | No contract change. Send each cast member's behaviors (at most five each, so at most 25) and let the model choose what the scene calls for. An object is "in the scene" if a cast member holds it, the beat's place holds it, or the beat names it. Revisit if W repeats the same behaviors. |
| F2 | The offstage request has no `spotlight`, yet O must never be about it, and a pressure from a group that bears on the protagonist can be the spotlight. | Add an optional `spotlight` (the pressure's text) to the offstage request. A small contract change (`contract.py`, vectors, `offstageRequest` in `web/plan.js`), done with part B step 1. |
| F3 | `what-feeds-what.md` has no row for the style-fit check (S) in the Characters table, yet it must read the protagonist. | S sees the protagonist's name, sex, sketch, wants, fear, flaw, values, competence, vulnerability and speech. |
| F4 | X2 reads only the chapter, Characters and Entanglements, so it cannot tell what is already recorded and may repeat it as a "shift". | X2 also sees `standing` (so it records only differences) and X1's `happened` and `reveals_landed` (so it knows what landed). Both are inside the backend, no contract change. |
| F5 | The judge prompts in the text files ask for a rewrite. The reply carries only hits. The contract text says a hit gives the item's `id`; the model and the page use `item`. | The backend drops the rewrite request and asks for the verdict only. Fix the contract wording in part B. |
| F6 | The Events and beat templates print empty labels (section 3, rule 4). | Handled by the renderer in phase 3. No schema change. |
| F7 | `earlier_events` grows with every chapter (4 to 8 sentences each), and W, P and E all carry it. | Decide in phase 3 how older chapters thin out for W (for example the last three in full, earlier ones as their `changed` line). Not decided now. |
| F8 | The contract's stage list is closed (`Stage` in `contract.py`), so a finer label per writing section would be a contract change. | D9: keep `write`. |

## 7. What comes next

Phase 2: `docs/prompts/02-writers-brief.md`, the craft guidance for each call in plain English, written for you to edit. The chapter writer first (each Style field as one concrete instruction, the scene engine as a scene, the failure modes), then the planner, the extractors and the rest.

Proposed folders for later phases, so the files land in one place:

| Phase | Folder |
| --- | --- |
| 2 | `docs/prompts/` |
| 3 and 4 | `pulpermill/prompts/` (renderers, and one versioned template file per prompt) |
| 5 | `tests/prompts/` (sample project, golden prompts, token counts) |
| 6 | `tests/trials/` (rubric, trial beats) |

For phase 5 I need the tokenizer: the GGUF repo has none as a separate file (the vocabulary is inside the GGUF), and this sandbox cannot reach Hugging Face. The base repo `mlabonne/gemma-3-27b-it-abliterated` has `tokenizer.json` (33 MB), `tokenizer.model` and `tokenizer_config.json`, and looks openly downloadable. Please upload `tokenizer.json` and `tokenizer_config.json` when we reach phase 5.
