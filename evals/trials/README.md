The chapter-trial harness described below (`tools/run_trials.py` and `tests/prompts/trial_set.py`) was removed in P7.5. It exists at the git tag `pre-prompt-design`. The trials are redone in prompt design.

# The trials

Four chapters of the Salt Coast story, each a different kind of chapter in a different voice. They were defined in `tests/prompts/trial_set.py` (see the tag) and read with `docs/prompts/06-reading-rubric.md`.

```
# at the tag pre-prompt-design only:
python tools/run_trials.py --dry                          # write the first prompt of each trial, no model
python tools/run_trials.py --url http://localhost:8080    # run all four, three times each, against a llama.cpp server
```

- `results/<writer version>/<trial>-run<N>.md`: the chapter, then the code flags. Read the chapter first.
- `results/<writer version>/summary.csv`: one row per run, written by the runner.
- `scoring/chapter-scoring.csv`: your scores, 4 trials x 3 runs. Copy it for each prompt version (for example `chapter-scoring-writer-0.2.csv`) so earlier versions stay.

Never edit a trial once results exist. Add T5.
