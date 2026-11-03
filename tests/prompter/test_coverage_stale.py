"""C1 item 7: no stale numbers. After the 3 Nov decisions (10 to 20 chapters; at most 1,200 words a chapter), no prompt text, wording file, trials file,
README or tool under `pulpermill/prompter/`, `pulpermill/prompts/`, `evals/trials/` or `tools/` still says "5 to 10" chapters or "1,800" words.
The one place that may still say them is the decision record's own history line, which says what the numbers were *before* (marked "before:")."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = ("pulpermill/prompter", "pulpermill/prompts", "evals/trials", "tools")
SUFFIXES = {".py", ".yaml", ".yml", ".md", ".json", ".mjs", ".js", ".txt", ".csv", ".toml"}
SKIP = {"tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "added_tokens.json"}
STALE = [("5 to 10 chapters", r"\b(?:5|five)\s*(?:to|-|–|—|and)\s*(?:10|ten)\b"),
         ("1,800 words", r"\b1[,.]?800[- ]?words?\b|\babout 1[,.]?800\b|\b1[,.]?800 to 2[,.]?400 words\b")]
# These may say the old numbers on a line that says it is history ("before:", "was", "old"): the decision record, and one comment in the trial
# checks that explains why its minimum word count was raised. Nothing else may.
HISTORY = ("pulpermill/prompter/DECISIONS.md", "tools/trial_checks.mjs")


def text_files():
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix in SUFFIXES and path.name not in SKIP and "__pycache__" not in path.parts and path.stat().st_size < 2_000_000:
                yield path


def stale_lines():
    for path in text_files():
        rel = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for label, pattern in STALE:
                if re.search(pattern, line, flags=re.I):
                    if rel in HISTORY and re.search(r"\bbefore:|\bwas\b|\(was |\bold\b", line):
                        continue
                    yield f"{rel}:{number}: says {label}: {line.strip()[:120]}"


def test_the_scan_reads_the_folders_the_brief_names():
    rel = [p.relative_to(ROOT).as_posix() for p in text_files()]
    for folder in FOLDERS:
        assert any(r.startswith(folder + "/") for r in rel), folder
    assert sum(1 for _ in text_files()) > 50


def test_the_patterns_catch_the_old_numbers_in_their_usual_clothes():
    for old in ("a story of 5 to 10 chapters", "five to ten chapters", "5-10 chapters", "about 1,800 words", "1800 words", "a 1,800-word chapter"):
        assert any(re.search(p, old, flags=re.I) for _, p in STALE), old
    for fine in ("10 to 20 chapters", "at most 1,200 words", "1,800 to 2,400 Chinese characters", "chapters 5 to 10 of the story"[:0] or "chapter 5"):
        assert not any(re.search(p, fine, flags=re.I) for _, p in STALE), fine


def test_no_stale_chapter_range_or_word_count_remains():
    assert not list(stale_lines()), "\n" + "\n".join(stale_lines())
