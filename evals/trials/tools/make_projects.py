"""Builds the trial projects and the manifest from the stories.

    python evals/trials/tools/make_projects.py [--check]

Reads evals/trials/stories/*.yaml (written with names, not ids) and writes evals/trials/projects/<id>.json (a project file under
schema version 3, with cards filled and ids that are the same on every run) and evals/trials/manifest.json (what each trial tests).
With --check it writes nothing and exits 1 if the files on disk differ from what the stories give.
"""
import hashlib
import json
import pathlib
import sys

import yaml

KIT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 3

# Every Style axis a story does not name. The stories name the ones that make them what they are.
DEFAULT_STYLE = {"distance": "close", "humor": "none", "pacing": "balanced", "rhythm": "varied", "diction": "plain", "formality": "casual",
                 "imagery": "occasional", "edge": "clean", "explicitness": "shown", "attitude": "earnest", "amount": "sparse",
                 "directness": "subtext", "polish": "naturalistic", "voice_difference": "distinct"}
STYLE_ORDER = ["person", "tense", "distance", "humor", "pacing", "narrator_note", "rhythm", "diction", "formality", "imagery", "edge",
               "explicitness", "sentences_note", "attitude", "stance_note", "amount", "directness", "polish", "voice_difference",
               "dialogue_note", "lens", "genre"]


def make_id(*parts) -> str:
    return hashlib.sha1(":".join(parts).encode("utf-8")).hexdigest()[:8]


def build(story: dict) -> dict:
    sid = story["id"]
    ident = lambda *p: make_id(sid, *p)
    style = {**DEFAULT_STYLE, **story["style"]}
    style = {k: style[k] for k in STYLE_ORDER if k in style}

    people = {}
    characters = []
    for c in story["characters"]:
        cid = ident("character", c["name"])
        people[c["name"]] = cid
        characters.append({
            "id": cid, "name": c["name"], "age": c["age"], "sex": c["sex"], "appearance": c["appearance"], "sketch": c["sketch"],
            "wants": [{"id": ident(c["name"], "want", str(i)), "text": t} for i, t in enumerate(c["wants"])],
            "fear": c["fear"], "flaw": c["flaw"],
            "values": [{"id": ident(c["name"], "value", str(i)), "text": t} for i, t in enumerate(c["values"])],
            "behaviors": [{"id": ident(c["name"], "behavior", str(i)), **b} for i, b in enumerate(c["behaviors"])],
            "competence": c["competence"], "vulnerability": c["vulnerability"], "speech": c["speech"], "history": c["history"]})

    w = story["world"]
    world = {"name": w["name"], "era_and_technology": w["era_and_technology"], "everyday_life": w["everyday_life"], "history": w["history"]}
    ids = {}
    for key, label in (("places", "name"), ("objects", "name"), ("powers", "name"), ("rules", "statement"), ("terms", "term")):
        items = []
        for i, item in enumerate(w[key]):
            iid = ident(key, item[label])
            ids[item[label]] = iid if key in ("places", "objects", "powers") else ids.get(item[label])
            items.append({"id": iid, **item})
        world[key] = items

    def link(name, allowed):
        found = {**{n: i for n, i in people.items()}, **{x["name"]: x["id"] for k in allowed for x in world[k]}}
        if name not in found:
            raise SystemExit(f"{sid}: {name!r} is not a character or an item of {allowed}")
        return found[name]

    ties = [{"id": ident("tie", t["from"], t["to"]), "tie_from": link(t["from"], ["powers"]), "tie_to": link(t["to"], ["powers"]),
             "bond": t["bond"], "edge": t["edge"]} for t in story["ties"]]
    holdings = []
    for h in story["holdings"]:
        holdee = {x["name"]: x["id"] for k in ("objects", "places") for x in world[k]}[h["holdee"]]
        holdings.append({"id": ident("holding", h["holdee"]), "holdee": holdee, "held_by": link(h["held_by"], ["powers", "places"])})

    s = story["setup"]
    setup = {"protagonist": people[s["protagonist"]], "normal": s["normal"], "disruption": s["disruption"], "chapter_count": s["chapter_count"]}
    return {"id": sid, "title": story["title"], "schema_version": SCHEMA_VERSION, "output_language": story["language"],
            "example_chapter": None, "card_notes": [], "style": style, "characters": characters, "world": world,
            "entanglements": {"id": ident("entanglements"), "ties": ties, "holdings": holdings}, "setup": setup,
            "outline": {"id": ident("outline"), "beats": []}, "summary_events": {"id": ident("events"), "entries": []},
            "shifts": {"id": ident("shifts"), "entries": []}, "chapters": [], "locks": []}


def manifest_entry(story: dict, project: dict) -> dict:
    protagonist = project["setup"]["protagonist"]
    ties = project["entanglements"]["ties"]
    groups = {g["id"] for g in project["world"]["powers"]}
    count = project["setup"]["chapter_count"]
    return {"id": story["id"], "title": story["title"], "language": story["language"], "chapters": count,
            "characters": len(project["characters"]), "genre": project["style"]["genre"],
            "person": project["style"]["person"], "tense": project["style"]["tense"],
            "protagonist_has_ties": any(protagonist in (t["tie_from"], t["tie_to"]) for t in ties),
            "ties": len(ties), "ties_to_groups": sum(bool({t["tie_from"], t["tie_to"]} & groups) for t in ties),
            "tests": story["tests"], "read": story["read"]}


def main(check: bool) -> int:
    stories = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((KIT / "stories").glob("*.yaml"))]
    files = {}
    manifest = []
    for story in stories:
        project = build(story)
        files[KIT / "projects" / f"{story['id']}.json"] = json.dumps(project, ensure_ascii=False, indent=2) + "\n"
        manifest.append(manifest_entry(story, project))
    files[KIT / "manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    stale = [p for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if check:
        for p in stale:
            print(f"out of date: {p.relative_to(KIT)}")
        return 1 if stale else 0
    for p, text in files.items():
        p.write_text(text, encoding="utf-8")
    print(f"wrote {len(stories)} projects and the manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
