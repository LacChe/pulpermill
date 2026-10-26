# Backend notes

What was found while building and running the backend. The prompts work (phase 7) reads this. Sections marked **to measure**
are filled in from `tools/measure_engine.py` output on the Kaggle T4 x2.

## Carried over from the previous version (the old `config.py`)

- It ran the **Q4_K_M** quant at **n_ctx 16384**, `n_batch` 256, `tensor_split` 0.58 / 0.42, flash attention on (the loader
  retries without it). This version plans the 6-bit quant (about 22 GB); `ModelSettings.file` names it and must be checked
  against the repo page. The tensor split is the old one until measured.
- **Constrained (grammar) decoding was measured at about 4.5 tokens/s against about 10 without it**, because Gemma's vocabulary is
  huge. The old version wrote freely and used the grammar only to repair a broken first attempt. M3 should decide the same way
  for the calls where speed matters (the writer is free text anyway); check it again here (speed table below).
- Sampling used for chapters: temperature 1.0 (mlabonne's recommendation for this model), repeat_penalty 1.05,
  frequency_penalty 0.05, top_p 0.95, top_k 64. Summaries and extraction ran cold (0.2 to 0.3). These are the starting values in
  `pulpermill/backend/config.py`; the writer's own values replace them.
- Chinese needed different sampling (temperature 0.8, top_p 0.9, top_k 40, no repeat penalty). Not wired up here yet: the
  request's `language` is not used to pick sampling. Say if it should be.

## M2 checks (to measure, on Kaggle)

1. **Install and load.** How long the build or wheel install takes; which `llama-cpp-python` version; whether Gemma 3 loads.
2. **Tokenizer parity** (`tokens.chat_tokens` against the engine): _to measure_
3. **Context and memory** at n_ctx 8,192 / 12,288 / 16,384: _to measure_. Decides `budgets.yaml: n_ctx` and `ModelSettings.n_ctx` (the launcher refuses to start if they differ).
4. **Speed** (prefill and generation, free and constrained, 4,000-token prompt; one section; a whole `generate`): _to measure_
5. **Cancellation** during generation and during prefill: _to measure_. Prefill is done by hand in n_batch-sized steps so Stop can land between steps; this relies on llama-cpp-python reusing the evaluated prefix, which the speed table shows (a prefill much slower than the second run would mean it did not).
6. **The long request through ngrok** (a `generate` call of 15 minutes or more): _to measure_. The page's `generate` timeout is still 900 s in `web/client.js`; the handoff suggests 1,800 s (change it there and in `docs/backend-contract.md` together).
7. **CORS and both headers from the real https page** through the tunnel: _to check_

## M3: how a JSON call runs (`pulpermill/backend/pipelines/structured.py`)

- `fit_check` answers `too_long` (413) before any inference. It counts with the page's tokenizer files when they are installed and with the engine's own count when they are not.
- Two attempts at most. The second adds the note from `pulpermill/prompts/templates/en/retry.yaml` (new file, added for the backend; the prompts owner should know for the golden test and tuning) with one short line saying what was wrong. The first reply is not shown to the model. Both failing is `bad_output` (502). Stop is never retried.
- A reply fails when it is not valid JSON in the prompt's shape (a reply cut off at `max_tokens` is one of these, and the note says so), when the caller's own check fails, or when the longer sentences are not in the requested language (`language.py`: script share for Chinese, Japanese and Korean; function words for en, fr, de, es; short texts and other languages pass).
- `Config.constrain`: `"always"` (default) constrains every JSON call. `"repair"` writes the first attempt free and constrains only the retry. The old setup measured about 4.5 tok/s constrained against about 10 free, so after the speed table from `measure_engine.py` is in, decide which default stays.
- Not wired yet: different sampling for Chinese (`language` does not pick a parameter set).

## M4: the simple calls (`pulpermill/backend/pipelines/simple.py`)

- `fill`: `fill_prompt` with the schema built from the request's own lists, so a link can only name what was sent. The reply is the model's object, returned as `values`.
- `judge`: one pass per rule (`judge_prompts`), every prompt measured before the first runs, then `assemble_judge_reply`.
- `style_fit`: `fits`, and the message only when it does not fit.
- `python -m pulpermill.backend --fake` and the server tests now use the canned replies (`pipelines.run_canned`), since the fake engine's words are not JSON.
- **Card-fill runs:** `node tools/run_cardfill.mjs <address> --token T --runs 3 --label <prompt-version>` fills every fixture in `tests/cardfill/fixtures` through the page's own client and rules and writes `tests/cardfill/results/<label>/` (one JSON per fixture and run, plus `summary.csv` with the rules that fired). It does not grade: grade by hand with `tests/cardfill/03-scoring-protocol.md`. The run record per call (prompt version, parameter set, retries) comes with M6.
