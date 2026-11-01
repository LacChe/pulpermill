"""P6b: summarize_scoring.py counts a filled sheet right. A small hand-made sheet, checked by hand."""
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "evals" / "cardfill" / "tools"
sys.path.insert(0, str(TOOLS))

import summarize_scoring as s  # noqa: E402

PROBE_HEADER = ["fixture", "probe", "tier", "role", "run", "result"]
FIRST = [   # fixture, probe, tier, role, run, result
    ("e1-tempting", "E1", "1", "tempting", 1, "right"),
    ("e1-tempting", "E1", "1", "tempting", 2, "wrong-silent"),
    ("e1-tempting", "E1", "1", "tempting", 3, "wrong-silent"),
    ("e1-control", "E1", "1", "control", 1, "right"),
    ("e1-control", "E1", "1", "control", 2, "control-damaged"),
    ("e1-control", "E1", "1", "control", 3, ""),
    ("w1-tempting", "W1", "2", "tempting", 1, "wrong-flagged"),
    ("w1-tempting", "W1", "2", "tempting", 2, "right"),
    ("w1-tempting", "W1", "2", "tempting", 3, "Right "),      # case and spaces do not matter
    ("u3-tempting", "U3", "1", "tempting", 1, "wrong-silent"),
]
SECOND = [
    ("e1-tempting", "E1", "1", "tempting", 1, "right"),
    ("e1-tempting", "E1", "1", "tempting", 2, "right"),
    ("e1-tempting", "E1", "1", "tempting", 3, "wrong-silent"),
    ("w1-tempting", "W1", "2", "tempting", 1, "right"),
    ("w1-tempting", "W1", "2", "tempting", 2, "right"),
    ("w1-tempting", "W1", "2", "tempting", 3, "right"),
    ("u3-tempting", "U3", "1", "tempting", 1, "right"),
]


def write(path, rows, header=PROBE_HEADER):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def test_counts_per_probe_per_tier_and_in_total(tmp_path):
    got = s.summarize_probes(write(tmp_path / "a.csv", FIRST))
    e1 = got["probes"]["E1"]
    assert (e1["right"], e1["wrong-flagged"], e1["wrong-silent"], e1["control-damaged"], e1["ungraded"]) == (2, 0, 3, 1, 1)
    w1 = got["probes"]["W1"]
    assert (w1["right"], w1["wrong-flagged"], w1["wrong-silent"]) == (2, 1, 0)
    assert list(got["probes"]) == ["E1", "W1", "U3"]
    t1, t2 = got["tiers"]["Tier 1"], got["tiers"]["Tier 2"]
    assert (t1["right"], t1["wrong-flagged"], t1["wrong-silent"], t1["control-damaged"], t1["ungraded"]) == (2, 0, 4, 1, 1)
    assert (t2["right"], t2["wrong-flagged"], t2["wrong-silent"]) == (2, 1, 0)
    total = got["total"]
    assert (total["right"], total["wrong-flagged"], total["wrong-silent"], total["control-damaged"], total["ungraded"]) == (4, 1, 4, 1, 1)
    assert sum(total[c] for c in s.BUCKETS + ["ungraded"]) == len(FIRST)


def test_a_blank_template_is_all_ungraded():
    got = s.summarize_probes(ROOT / "evals" / "cardfill" / "scoring" / "probe-scoring.csv")
    assert got["total"]["ungraded"] == 159 and got["total"]["right"] == 0
    assert set(got["tiers"]) == {"Tier 1", "Tier 2"} and len(got["probes"]) == 26


def test_the_difference_between_two_sheets(tmp_path):
    a = s.summarize_probes(write(tmp_path / "a.csv", FIRST))
    b = s.summarize_probes(write(tmp_path / "b.csv", SECOND))
    d = s.difference(a, b)
    assert (d["probes"]["E1"]["right"], d["probes"]["E1"]["wrong-silent"]) == (0, -2)      # right 2 -> 2, wrong-silent 3 (one a damaged control) -> 1
    assert d["total"]["wrong-silent"] == -3 and d["total"]["wrong-flagged"] == -1
    assert d["probes"]["W1"]["right"] == 1 and d["probes"]["W1"]["wrong-flagged"] == -1
    assert d["probes"]["U3"]["wrong-silent"] == -1 and d["probes"]["U3"]["right"] == 1


CASE_HEADER = ["case", "run", "structure_failures", "stated_facts_dropped_or_changed", "scope_invented_upstream",
               "boundary_wrong_silent", "boundary_wrong_flagged"]


def test_case_boundary_errors_are_summed(tmp_path):
    path = write(tmp_path / "c.csv", [
        ("case-1", 1, 0, 1, 0, 2, 1), ("case-1", 2, 1, 0, 0, 0, 3), ("case-1", 3, "", "", "", "", ""),
        ("case-2", 1, 0, 0, 2, 1, 0),
    ], CASE_HEADER)
    got = s.summarize_cases(path)
    assert got["cases"]["case-1"]["boundary_wrong_silent"] == 2 and got["cases"]["case-1"]["boundary_wrong_flagged"] == 4
    assert got["cases"]["case-1"]["structure_failures"] == 1 and got["cases"]["case-2"]["scope_invented_upstream"] == 2
    assert got["total"]["boundary_wrong_silent"] == 3 and got["graded_rows"] == 3


def test_the_command_line_prints_a_table_and_a_difference(tmp_path):
    a, b = write(tmp_path / "a.csv", FIRST), write(tmp_path / "b.csv", SECOND)
    one = subprocess.run([sys.executable, str(TOOLS / "summarize_scoring.py"), "--probes", str(a)], capture_output=True, text=True)
    assert one.returncode == 0 and "-- per tier" in one.stdout and "all probes" in one.stdout
    two = subprocess.run([sys.executable, str(TOOLS / "summarize_scoring.py"), "--probes", str(a), str(b)], capture_output=True, text=True)
    assert two.returncode == 0 and "difference (second minus first)" in two.stdout and "-2" in two.stdout
