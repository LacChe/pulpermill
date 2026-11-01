"""Adds up filled scoring sheets.

  python summarize_scoring.py --probes scoring/probe-scoring.csv [second.csv] [--cases scoring/case-scoring.csv [second.csv]]

Probes: one graded row per fixture and run, with `result` one of right, wrong-flagged, wrong-silent, control-damaged.
Prints, per probe, per tier and in total, how many results are right, wrong but flagged and wrong and silent. A control-damaged
result counts as wrong (plan), but the protocol does not say which bucket, so it is shown in its own column and in none of the three.
Rows with no result yet are counted as `ungraded`. Given a second sheet, prints the difference (second minus first) for every count.

Cases: one row per case and run, with the boundary errors found: `boundary_wrong_silent` and `boundary_wrong_flagged` are summed per case and
in total (a case has no "right" count: the boundaries it did not get wrong are not counted). `structure_failures`,
`stated_facts_dropped_or_changed` and `scope_invented_upstream` are summed too when they are numbers.
"""
import argparse
import csv
import pathlib
from collections import OrderedDict

BUCKETS = ["right", "wrong-flagged", "wrong-silent"]
EXTRA = ["control-damaged", "ungraded"]
COLUMNS = BUCKETS + EXTRA


def _rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _blank():
    return {c: 0 for c in COLUMNS}


def _count(row):
    result = (row.get("result") or "").strip().lower()
    return result if result in BUCKETS + ["control-damaged"] else "ungraded"


def summarize_probes(path):
    """{'probes': {id: counts}, 'tiers': {tier: counts}, 'total': counts}. Counts are dicts over COLUMNS."""
    probes, tiers, total = OrderedDict(), OrderedDict(), _blank()
    for row in _rows(path):
        key, tier = row["probe"], f"Tier {row['tier']}"
        which = _count(row)
        for table, k in ((probes, key), (tiers, tier)):
            table.setdefault(k, _blank())[which] += 1
        total[which] += 1
    return {"probes": probes, "tiers": OrderedDict(sorted(tiers.items())), "total": total}


def _number(value):
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return 0


CASE_COLUMNS = ["boundary_wrong_silent", "boundary_wrong_flagged", "structure_failures",
                "stated_facts_dropped_or_changed", "scope_invented_upstream"]


def summarize_cases(path):
    """{'cases': {id: sums}, 'total': sums, 'graded_rows': n}. A row counts as graded when any column holds a number."""
    cases, total, graded = OrderedDict(), {c: 0 for c in CASE_COLUMNS}, 0
    for row in _rows(path):
        sums = cases.setdefault(row["case"], {c: 0 for c in CASE_COLUMNS})
        if any((row.get(c) or "").strip() for c in CASE_COLUMNS):
            graded += 1
        for c in CASE_COLUMNS:
            sums[c] += _number(row.get(c))
            total[c] += _number(row.get(c))
    return {"cases": cases, "total": total, "graded_rows": graded}


def difference(first, second):
    """second minus first, on the same shape (nested dicts of numbers). A key in only one is treated as zero in the other."""
    if isinstance(first, dict) or isinstance(second, dict):
        first, second = first or {}, second or {}
        return OrderedDict((k, difference(first.get(k), second.get(k))) for k in list(second) + [k for k in first if k not in second])
    return (second or 0) - (first or 0)


def _line(name, counts, signed=False):
    fmt = (lambda v: f"{v:+d}") if signed else (lambda v: f"{v}")
    return f"{name:<22}" + "".join(f"{fmt(counts[c]):>17}" for c in COLUMNS)


def print_probes(summary, signed=False, out=print):
    out(f"{'':<22}" + "".join(f"{c:>17}" for c in COLUMNS))
    for title, table in (("per probe", summary["probes"]), ("per tier", summary["tiers"])):
        out(f"-- {title}")
        for k, counts in table.items():
            out(_line(k, counts, signed))
    out("-- total")
    out(_line("all probes", summary["total"], signed))


def print_cases(summary, signed=False, out=print):
    fmt = (lambda v: f"{v:+d}") if signed else (lambda v: f"{v}")
    out(f"{'':<12}" + "".join(f"{c:>34}" for c in CASE_COLUMNS))
    for k, sums in summary["cases"].items():
        out(f"{k:<12}" + "".join(f"{fmt(sums[c]):>34}" for c in CASE_COLUMNS))
    out(f"{'all cases':<12}" + "".join(f"{fmt(summary['total'][c]):>34}" for c in CASE_COLUMNS))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probes", nargs="+", metavar="CSV", help="a filled probe-scoring.csv, then optionally a second one to compare")
    ap.add_argument("--cases", nargs="+", metavar="CSV", help="a filled case-scoring.csv, then optionally a second one to compare")
    args = ap.parse_args(argv)
    if not args.probes and not args.cases:
        ap.error("give --probes and/or --cases")
    for name, files, summarize, show in (("probes", args.probes, summarize_probes, print_probes), ("cases", args.cases, summarize_cases, print_cases)):
        if not files:
            continue
        if len(files) > 2:
            ap.error(f"--{name} takes one sheet, or two to compare")
        first = summarize(files[0])
        print(f"== {name}: {pathlib.Path(files[0]).name}")
        show(first)
        if len(files) == 2:
            second = summarize(files[1])
            print(f"== {name}: {pathlib.Path(files[1]).name}")
            show(second)
            print(f"== {name}: difference (second minus first)")
            show(difference(first, second), signed=True)


if __name__ == "__main__":
    main()
