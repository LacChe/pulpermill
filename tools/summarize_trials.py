"""Adds up the chapter trials.

    python tools/summarize_trials.py SHEET.csv [--machine RESULTS_DIR]
    python tools/summarize_trials.py --compare SHEET_A.csv SHEET_B.csv [--machine-a DIR --machine-b DIR]

SHEET is a filled copy of evals/trials/scoring/chapter-scoring.csv. Rows with no scores are skipped (not yet read). It prints, per
trial, how many chapters were read, the mean total (out of 20; chapter 1 is out of 18, so totals are compared as a share of the
possible), and the mean of each rubric line. With --machine it adds the machine flags from the runner's summary.csv: how many chapters
carry each flag. With --compare it prints the two sheets side by side with the difference (B minus A) and marks a change of 0.5 or
more in a rubric line. It measures; it does not decide which version is better.
"""
import argparse
import csv
import pathlib
from collections import defaultdict

SCORES = ["interesting", "act1_start", "act2_conflict", "act3_turn", "act4_end", "spotlight_moved", "aim_moved", "minor_roles", "style_fit", "different"]
FLAGS = ["length_flag", "person_flag", "tense_flag", "opening_repeat", "repeated_sentences", "changed_empty", "shift_flag", "unknown_count", "offstage_names"]
MOVE = 0.5


def read_sheet(path):
    """{trial: [row]} for rows that hold at least one score. A score is 0, 1 or 2; anything else raises."""
    out = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            given = {k: row[k].strip() for k in SCORES if (row.get(k) or "").strip()}
            if not given:
                continue
            for k, v in given.items():
                if v not in ("0", "1", "2"):
                    raise ValueError(f"{path}: {row['trial']} run {row['run']} chapter {row['chapter']}: {k} is {v!r}, not 0, 1 or 2")
            row["_scores"] = {k: int(v) for k, v in given.items()}
            out[row["trial"]].append(row)
    return out


def share(row):
    """The row's total as a share of what it could have been (a blank `different` is not counted against it)."""
    got = sum(row["_scores"].values())
    return got / (2 * len(row["_scores"]))


def totals(rows):
    if not rows:
        return {"chapters": 0, "share": None, **{k: None for k in SCORES}}
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    return {"chapters": len(rows), "share": mean([share(r) for r in rows]),
            **{k: mean([r["_scores"][k] for r in rows if k in r["_scores"]]) for k in SCORES}}


def read_machine(directory):
    """{trial: {flag: chapters carrying it}, ...} and the chapter count per trial, from a results folder's summary.csv."""
    counts, chapters = defaultdict(lambda: defaultdict(int)), defaultdict(int)
    with open(pathlib.Path(directory) / "summary.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["ok"] != "true":
                counts[row["trial"]]["failed"] += 1
                continue
            chapters[row["trial"]] += 1
            for flag in FLAGS:
                value = row.get(flag, "")
                if value not in ("", "false", "0"):
                    counts[row["trial"]][flag] += 1
    return counts, chapters


def fmt(x, digits=2):
    return "-" if x is None else f"{x:.{digits}f}"


def show_one(sheet, machine):
    data = read_sheet(sheet)
    print(f"{'trial':<22}{'read':>5}{'share':>7}  " + " ".join(f"{k[:8]:>8}" for k in SCORES))
    allrows = []
    for trial in sorted(data):
        t = totals(data[trial])
        allrows += data[trial]
        print(f"{trial:<22}{t['chapters']:>5}{fmt(t['share']):>7}  " + " ".join(f"{fmt(t[k]):>8}" for k in SCORES))
    t = totals(allrows)
    print(f"{'ALL':<22}{t['chapters']:>5}{fmt(t['share']):>7}  " + " ".join(f"{fmt(t[k]):>8}" for k in SCORES))
    if machine:
        counts, chapters = read_machine(machine)
        print("\nMachine flags (chapters carrying the flag / chapters written):")
        for trial in sorted(chapters):
            line = ", ".join(f"{k}={v}" for k, v in sorted(counts[trial].items())) or "none"
            print(f"  {trial:<22}{chapters[trial]:>3} chapters: {line}")


def show_compare(a, b, machine_a, machine_b):
    da, db = read_sheet(a), read_sheet(b)
    print(f"A = {a}\nB = {b}\n")
    print(f"{'trial':<22}{'A':>6}{'B':>6}{'B-A':>7}   lines that moved by {MOVE} or more (B-A)")
    for trial in sorted(set(da) | set(db)):
        ta, tb = totals(da.get(trial, [])), totals(db.get(trial, []))
        diff = None if ta["share"] is None or tb["share"] is None else tb["share"] - ta["share"]
        moved = [f"{k} {tb[k] - ta[k]:+.2f}" for k in SCORES if ta[k] is not None and tb[k] is not None and abs(tb[k] - ta[k]) >= MOVE]
        print(f"{trial:<22}{fmt(ta['share']):>6}{fmt(tb['share']):>6}{fmt(diff):>7}   {', '.join(moved) or '-'}")
    if machine_a and machine_b:
        ca, na = read_machine(machine_a)
        cb, nb = read_machine(machine_b)
        print("\nMachine flags per chapter written (A -> B):")
        for flag in FLAGS + ["failed"]:
            ra = sum(ca[t][flag] for t in ca) / max(sum(na.values()), 1)
            rb = sum(cb[t][flag] for t in cb) / max(sum(nb.values()), 1)
            print(f"  {flag:<20}{ra:>6.2f} -> {rb:>6.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sheet", nargs="?")
    ap.add_argument("--machine")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    ap.add_argument("--machine-a")
    ap.add_argument("--machine-b")
    args = ap.parse_args()
    if args.compare:
        show_compare(*args.compare, args.machine_a, args.machine_b)
    elif args.sheet:
        show_one(args.sheet, args.machine)
    else:
        ap.error("give a sheet, or --compare A B")
