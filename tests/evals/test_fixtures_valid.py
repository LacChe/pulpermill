"""P6a: the card-fill eval kit's sample data is valid under the current schema.

Covers the generated fixtures (evals/cardfill/fixtures/projects/*.json), the manifest that describes them, and the
hand-written upstream sets they are built from (evals/cardfill/upstream/*.json).

Two things need saying about "valid as a Project":

* pydantic ignores keys a model does not declare, so a removed field (pressures, knowledge, rule status or truth...)
  would load without complaint. unknown_keys() walks the data against the models and fails on any such key.
* A fixture is a project nobody has finished starting: the card the fill is meant to produce, and any card the kit never
  provides (Style and Setup have no upstream data), are absent on purpose, and the kit does not invent content for
  them. Those cards, and only those, may be reported missing. Every other problem fails the test."""
import json
import pathlib
import sys
from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pulpermill.schema import CARDS                                    # noqa: E402
from pulpermill.schema.characters import Characters                    # noqa: E402
from pulpermill.schema.entanglements import Entanglements              # noqa: E402
from pulpermill.schema.project import Project, SCHEMA_VERSION          # noqa: E402
from pulpermill.schema.world import World                              # noqa: E402

KIT = REPO / "evals" / "cardfill"
PROJECTS = KIT / "fixtures" / "projects"
MANIFEST = json.loads((KIT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
UPSTREAM = KIT / "upstream"

# The cards a fixture may leave out (the chain the fill works through). Nothing else may be missing.
CHAIN = {"style", "characters", "world", "entanglements", "setup"}
FIXTURE_FILES = sorted(PROJECTS.glob("*.json"))
BY_ID = {e["id"]: e for e in MANIFEST}


def _models(annotation):
    """The pydantic models named by a field annotation (inside list[...] or Optional[...] too)."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    return [m for a in get_args(annotation) for m in _models(a)]


def unknown_keys(model, data, path=""):
    """Every key in `data` that `model` (or a model nested in it) does not declare, as dotted paths."""
    if not isinstance(data, dict):
        return []
    found = []
    for key, value in data.items():
        field = model.model_fields.get(key)
        if field is None:
            found.append(f"{path}{key}")
            continue
        nested = _models(field.annotation)
        if not nested:
            continue
        for i, item in enumerate(value if isinstance(value, list) else [value]):
            where = f"{path}{key}[{i}]." if isinstance(value, list) else f"{path}{key}."
            found += unknown_keys(nested[0], item, where)
    return found


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the manifest and the files agree
def test_there_are_fixtures():
    assert len(FIXTURE_FILES) == len(MANIFEST) > 0


def test_manifest_and_project_files_match_one_to_one():
    assert {p.stem for p in FIXTURE_FILES} == set(BY_ID)
    assert len(BY_ID) == len(MANIFEST), "a manifest id appears twice"


def test_generator_writes_the_current_schema_version():
    assert SCHEMA_VERSION == 3, "the project schema version changed: re-read P0 A4 and regenerate the fixtures"
    versions = {load(p)["schema_version"] for p in FIXTURE_FILES}
    assert versions == {SCHEMA_VERSION}


# ---------------------------------------------------------------- every fixture is a valid project
@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_fixture_is_a_valid_project(path):
    data = load(path)

    # 1. Nothing the schema no longer has (pydantic would silently ignore it).
    assert unknown_keys(Project, data) == []

    # 2. It loads as a Project. The only allowed complaint is a whole chain card that is absent.
    try:
        Project.model_validate(data)
        problems = []
    except ValidationError as e:
        problems = e.errors()
    for p in problems:
        assert p["type"] == "missing" and len(p["loc"]) == 1 and p["loc"][0] in CHAIN, \
            f"{path.stem}: {p['loc']} {p['type']}: {p['msg']}"

    # 3. What is absent is exactly what the manifest says: the fill's own cards, plus cards with no upstream data.
    entry = BY_ID[path.stem]
    missing = {p["loc"][0] for p in problems}
    held = set(entry.get("upstream_cards", []))
    assert not (held & missing), f"{path.stem}: upstream cards {sorted(held & missing)} are not in the fixture"
    assert held <= set(data), f"{path.stem}: upstream cards not present"
    assert not (set(entry["fill"]) & set(data)), f"{path.stem}: a card the fill must produce is already present"
    assert missing == CHAIN - set(data)

    # 4. The records of a project that has not started are there and empty.
    assert data["chapters"] == [] and data["outline"]["beats"] == []
    assert data["summary_events"]["entries"] == [] and data["shifts"]["entries"] == []


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_fixture_links_resolve(path):
    """Ties, holdings and notes point at things the fixture really holds (a removed pressure used to point at people)."""
    data = load(path)
    people = {c["id"] for c in data.get("characters", [])}
    world = data.get("world", {})
    powers = {x["id"] for x in world.get("powers", [])}
    places = {x["id"] for x in world.get("places", [])}
    objects = {x["id"] for x in world.get("objects", [])}
    ent = data.get("entanglements")
    if ent:
        for t in ent["ties"]:
            assert {t["tie_from"], t["tie_to"]} <= people | powers, t["id"]
        for h in ent["holdings"]:
            assert h["holdee"] in objects | places, h["id"]
            assert h["held_by"] in people | powers | places, h["id"]
    for n in data["card_notes"]:
        assert n["card"] in CHAIN


# ---------------------------------------------------------------- the upstream sets themselves
UPSTREAM_FILES = sorted(UPSTREAM.glob("set-*.json"))


def test_upstream_sets_are_present():
    assert len(UPSTREAM_FILES) == 7


@pytest.mark.parametrize("path", UPSTREAM_FILES, ids=lambda p: p.stem)
def test_upstream_set_is_valid(path):
    kind = path.stem.split("-", 2)[2]
    model = {"characters": Characters, "world": World, "entanglements": Entanglements}[kind]
    assert model is CARDS[kind][0]
    data = load(path)
    for card in data if isinstance(data, list) else [data]:      # a Characters set is a list of cards
        assert unknown_keys(model, card) == []
        model.model_validate(card)
