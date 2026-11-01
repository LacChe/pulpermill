"""Builds the blank scoring sheet from the manifest.

    python evals/trials/tools/make_scoring.py [--check]

One row per trial, run (1 to 3) and chapter. Copy the sheet for each prompter version (for example chapter-scoring-writer-0.2.csv) so
earlier versions stay. With --check it writes nothing and exits 1 when the file on disk is not what the manifest gives.
"""
import csv
import io
import json
import pathlib
import sys

KIT = pathlib.Path(__file__).resolve().parents[1]
RUNS = 3
SCORES = ["interesting", "act1_start", "act2_conflict", "act3_turn", "act4_end", "spotlight_moved", "aim_moved", "minor_roles", "style_fit", "different"]
COLUMNS = ["trial", "run", "chapter", "prompt_version", "model_and_settings", *SCORES, "total_0_to_20", "flags_that_fired", "flags_that_were_right",
           "calls_failed", "graded_by", "notes"]


def sheet() -> str:
    manifest = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for entry in manifest:
        for run in range(1, RUNS + 1):
            for chapter in range(1, entry["chapters"] + 1):
                writer.writerow([entry["id"], run, chapter] + [""] * (len(COLUMNS) - 3))
    return buffer.getvalue()


if __name__ == "__main__":
    path = KIT / "scoring" / "chapter-scoring.csv"
    text = sheet()
    if "--check" in sys.argv:
        sys.exit(0 if path.exists() and path.read_text(encoding="utf-8") == text else 1)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path.relative_to(KIT)}: {text.count(chr(10)) - 1} rows")
