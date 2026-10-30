"""Builds the scoring sheets from the manifest, the probe catalog and the plan.
Run from anywhere:  python make_scoring.py
Reads  : ../fixtures/manifest.json, ../01-probe-catalog.md, ../00-test-plan.md
Writes : ../scoring/probe-scoring.csv and ../scoring/case-scoring.csv
Run make_fixtures.py first if you changed any input.
"""
import csv, json, pathlib, re

KIT = pathlib.Path(__file__).resolve().parent.parent
RUNS = 3
(KIT / "scoring").mkdir(exist_ok=True)

cat = {}
for line in (KIT / "01-probe-catalog.md").read_text(encoding="utf-8").splitlines():
    m = re.match(r"^\| ([SCWEU]\d+)(?: ★)? \|(.*)\|\s*$", line)
    if m:
        cells = [c.strip() for c in m.group(2).split("|")]   # target, tempting, control, right, flag, tier
        cat[m.group(1)] = {"target": cells[0], "right": cells[3], "flags": cells[4], "tier": cells[5],
                           "star": "★" in line.split("|")[1]}

plan = (KIT / "00-test-plan.md").read_text(encoding="utf-8")
sec = plan.split("## Where each case overlaps the probes")[1].split("## Running the tests")[0]
overlap = {int(m.group(1)): m.group(2) for m in re.finditer(r"^\| (\d+) \| (.*) \|\s*$", sec, re.M)}

manifest = json.loads((KIT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))

with open(KIT / "scoring" / "probe-scoring.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["prompt_version", "model_and_settings", "fixture", "probe", "tier", "starred", "target", "role", "run",
                "result", "flags_that_fired", "also_seen_elsewhere", "calls_failed_or_retried", "right_looks_like",
                "expected_flag", "graded_by", "notes"])
    for e in manifest:
        if e["kind"] == "probe":
            c = cat[e["probe"]]
            for run in range(1, RUNS + 1):
                w.writerow(["", "", e["id"], e["probe"], c["tier"], "yes" if c["star"] else "", c["target"], e["role"],
                            run, "", "", "", "", c["right"], c["flags"], "", ""])

with open(KIT / "scoring" / "case-scoring.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["prompt_version", "model_and_settings", "case", "input", "cards_filled", "run",
                "structure_failures", "stated_facts_dropped_or_changed", "scope_invented_upstream",
                "boundary_wrong_silent", "boundary_wrong_flagged", "boundary_details",
                "story_engine_0_to_2", "distinctness_0_to_2", "calls_failed_or_retried", "graded_by",
                "probes_to_look_for", "notes"])
    for e in manifest:
        if e["kind"] == "case":
            n = int(e["id"].split("-")[1])
            for run in range(1, RUNS + 1):
                w.writerow(["", "", e["id"], e["input"], " > ".join(e["fill"]), run] + [""] * 10 + [overlap.get(n, ""), ""])
print("scoring sheets written")
