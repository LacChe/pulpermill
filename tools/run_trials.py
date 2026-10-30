"""Runs the trial set (tests/prompts/trial_set.py) against a model and writes what came out, for reading with the rubric.
Run from the repository root.

  python tools/run_trials.py --dry                       writes the first prompt of every trial (no model); checks the whole loop
  python tools/run_trials.py --url http://localhost:8080 --runs 3
                                                         asks a llama.cpp server (OpenAI-style /v1/chat/completions) for every section

Each run writes evals/trials/results/<writer version>/<trial>-run<N>.md: the chapter, then the code flags (read the chapter FIRST), and
evals/trials/results/<writer version>/summary.csv gets one row per run. `run_chapter(request, complete)` is the same loop the backend
will use: `complete(text) -> str` is any function that sends one prompt and returns the reply.
The --url mode has not run against a real server yet (phase 7 does that)."""
import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "prompts"))

import trial_set                                                                     # noqa: E402
from pulpermill.prompts import prompts as P                                         # noqa: E402
from pulpermill.prompts.chapter_checks import run_checks, whole_sentences, words                     # noqa: E402

RESULTS = ROOT / "evals" / "trials" / "results"


def run_chapter(request: dict, complete, target_words: int = 3000) -> tuple[str, list[str]]:
    """Writes one chapter in two sections, as the backend does. The second section is shown the whole first one, and a section cut
    short at the token limit is cut back to its last whole sentence. Returns the chapter and the section texts."""
    plan = P.writer_plan()
    sections: list[str] = []
    for i in range(len(plan)):
        prompt = P.writer_prompt(request, plan, i, "\n\n".join(sections), target_words)
        sections.append(whole_sentences(complete(prompt.text).strip()))
    return "\n\n".join(sections), sections


def http_complete(url: str, max_tokens: int = 1600, temperature: float = 1.0):
    def complete(text: str) -> str:
        body = json.dumps({"messages": [{"role": "user", "content": text}], "max_tokens": max_tokens, "temperature": temperature}).encode()
        req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1800) as r:
            return json.load(r)["choices"][0]["message"]["content"]
    return complete


def write_result(out: Path, name: str, run: int, request: dict, chapter: str, version: str, settings: str) -> dict:
    flags = run_checks(chapter, request)
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"# {name}, run {run}", "", f"writer prompt: {version}; model and settings: {settings}", "",
             f"{len(words(chapter))} words. **Read the chapter and grade it before you read the flags.**", "", "---", "", chapter, "", "---", "",
             "## Code flags (pointers, not verdicts)", ""]
    lines += [f"- {f}" for f in flags] or ["- none"]
    (out / f"{name}-run{run}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"trial": name, "run": run, "prompt_version": version, "model_and_settings": settings, "words": len(words(chapter)),
            "flags": "; ".join(f.id for f in flags)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--url")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--settings", default="gemma-3-27b-it-abliterated Q6, temperature 1.0")
    ap.add_argument("--trial", action="append")
    a = ap.parse_args()
    version = P.writer_prompt(trial_set.trial("T1-pressure"), P.writer_plan(), 0).version
    out = RESULTS / version
    if a.dry:
        for name in a.trial or trial_set.TRIALS:
            prompt = P.writer_prompt(trial_set.trial(name), P.writer_plan(), 0)
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{name}-prompt1.txt").write_text(prompt.text, encoding="utf-8")
            print(f"{name}: {len(prompt.text.split())} words")
        return
    if not a.url:
        ap.error("give --url or --dry")
    complete, rows = http_complete(a.url), []
    for name in a.trial or trial_set.TRIALS:
        request = trial_set.trial(name)
        for run in range(1, a.runs + 1):
            chapter, _ = run_chapter(request, complete)
            rows.append(write_result(out, name, run, request, chapter, version, a.settings))
            print(rows[-1])
    with open(out / "summary.csv", "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        if f.tell() == 0:
            w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
