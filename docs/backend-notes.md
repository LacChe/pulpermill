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
