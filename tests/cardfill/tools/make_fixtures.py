"""Builds the project-shaped fixtures and the manifest from the case files and 02-probe-inputs.md.
Run from anywhere:  python make_fixtures.py
Reads  : ../case-*.md, ../02-probe-inputs.md, ../upstream/*.json
Writes : ../fixtures/projects/<id>.json and ../fixtures/manifest.json
"""
import json, pathlib, re

KIT = pathlib.Path(__file__).resolve().parent.parent
OUT = KIT / "fixtures"
CHAIN = ["style", "characters", "world", "entanglements", "setup"]
SCHEMA_VERSION = 1

# ---- which card a probe fills, and which fixed upstream cards its project holds
CARD_OF = {"S": "style", "C": "characters", "W": "world", "E": "entanglements", "U": "setup"}
UPSTREAM = {   # probe -> (set, cards held)
    "W1": ("A", ["characters"]),
    "E1": ("A", ["characters", "world"]),
    "E2": ("B", ["characters", "world"]), "E4": ("B", ["characters", "world"]),
    "E5": ("B", ["characters", "world"]), "E6": ("B", ["characters", "world"]),
    "E3": ("C", ["characters", "world"]), "E7": ("C", ["characters", "world"]),
    **{f"U{i}": ("A", ["characters", "world", "entanglements"]) for i in range(1, 6)},
}


def load_upstream(set_name, cards):
    out = {}
    for card in cards:
        data = json.loads((KIT / "upstream" / f"set-{set_name}-{card}.json").read_text(encoding="utf-8"))
        out[card] = data
    return out


def project(fid, title, language, chapter, notes, upstream=None):
    p = {"id": fid, "title": title, "schema_version": SCHEMA_VERSION, "output_language": language}
    if chapter:
        p["example_chapter"] = chapter
    p["card_notes"] = [{"id": f"{fid}-n{i}", "card": card, "character": None, "text": text}
                       for i, (card, text) in enumerate(notes)]
    p.update(upstream or {})
    return p


def write(fid, proj):
    d = OUT / "projects"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{fid}.json").write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")


manifest = []
for stale in (OUT / "projects").glob("*.json"):   # remove fixtures from earlier runs
    stale.unlink()

# ---------------------------------------------------------------- probes
text = (KIT / "02-probe-inputs.md").read_text(encoding="utf-8")
sections = re.split(r"^### ", text, flags=re.M)[1:]
for sec in sections:
    head, _, body = sec.partition("\n")
    m = re.match(r"([SCWEU]\d+)\s*·\s*(.*)", head)
    if not m:
        continue
    pid, target = m.group(1), m.group(2).split("(")[0].strip()
    card = CARD_OF[pid[0]]
    up = UPSTREAM.get(pid)
    found = re.findall(r"^([^\n`#][^\n]*)\n```\n(.*?)\n```", body, flags=re.M | re.S)
    if not found:   # a probe with a single unlabeled input
        found = [("input", b) for b in re.findall(r"```\n(.*?)\n```", body, flags=re.S)]
    for label, block in found:
        label = label.strip()
        if label == "input":
            role = "input"
        elif label.startswith("("):
            role = "variant-" + label[1]
        elif label.startswith("Excerpt"):
            role = "excerpt-" + label.split()[1]
        else:
            r = re.match(r"(Tempting|Control)(?: ([ab]))?", label)
            role = r.group(1).lower() + ("-" + r.group(2) if r.group(2) else "")
        fid = f"{pid.lower()}-{role}"
        chapter = block.strip() if pid == "S4" else None
        notes = [] if pid == "S4" else [(card, block.strip())]
        proj = project(fid, f"{pid} {role}", "en", chapter, notes, load_upstream(up[0], up[1]) if up else None)
        write(fid, proj)
        manifest.append({"id": fid, "kind": "probe", "probe": pid, "target": target, "role": role, "fill": [card],
                         "upstream_set": up[0] if up else None, "upstream_cards": up[1] if up else []})

# ---------------------------------------------------------------- cases
for path in sorted(KIT.glob("case-*.md"), key=lambda p: int(re.search(r"case-(\d+)", p.name).group(1))):
    n = int(re.search(r"case-(\d+)", path.name).group(1))
    t = path.read_text(encoding="utf-8")
    chapter = None
    m = re.search(r"^## Example chapter\n(.*?)(?=^## |\Z)", t, flags=re.M | re.S)
    if m:
        chapter = m.group(1).strip()
    notes = []
    m = re.search(r"^## Card notes\n(.*)\Z", t, flags=re.M | re.S)
    if m:
        for part in re.split(r"^### ", m.group(1), flags=re.M)[1:]:
            h, _, body = part.partition("\n")
            card = "characters" if h.lower().startswith("characters") else h.strip().lower()
            notes.append((card, body.strip()))
    notes.sort(key=lambda x: CHAIN.index(x[0]))
    fid = f"case-{n}"
    lang = "zh-Hans" if n == 9 else "en"
    write(fid, project(fid, f"Case {n}", lang, chapter, notes))
    fill = CHAIN if chapter else [c for c in CHAIN if any(card == c for card, _ in notes)]
    manifest.append({"id": fid, "kind": "case", "file": path.name, "fill": fill,
                     "input": "chapter" if chapter and not notes else "chapter+notes" if chapter else "notes",
                     "output_language": lang})

(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{sum(1 for e in manifest if e['kind']=='probe')} probe fixtures, {sum(1 for e in manifest if e['kind']=='case')} case fixtures")
