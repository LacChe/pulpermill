"""The project (save-and-load) file: coverage of every card, a full save/load round trip, and its integrity rules."""
import pytest
from pydantic import ValidationError
from helpers import *
from typing import get_args
from schema.project import Project, AfterStory, Chapter, CardNote, Lock, UserCard, CARD_FIELDS, PROJECT_RULES, SCHEMA_VERSION
from schema.common import MAX_ITEMS

PROJECT_CHECKS = {"chapter_sequence", "chapter_markers", "links_resolve",
                  "after_story_ready", "ids_match", "required_if", "unique_across_items", "lock_target_exists"}
PROJECT_UNCAPPED = {"characters", "chapters", "after_story.characters", "card_notes", "locks"}   # any number of characters, notes and locks


def sample(model):
    """Builds one valid instance by filling every required field with a plausible value."""
    return model(**{n: sample_value(f) for n, f in fields_of(model).items() if f.is_required()})


def sample_value(f):
    meta = f.json_schema_extra
    if is_list_field(f):
        return [sample(item_model(f))]
    if meta["kind"] in ("card", "snapshot"):
        return sample(f.annotation)
    if meta["input"] == "select-multiple":
        return ["x"]
    if options_of(f):
        return options_of(f)[0]
    return {"number": 1, "checkbox": False}.get(meta["input"], "x")


def test_every_registered_card_has_a_home_in_the_project():
    assert set(CARD_FIELDS) == set(CARDS)
    fields = fields_of(Project)
    for cid, name in CARD_FIELDS.items():
        meta = fields[name].json_schema_extra
        assert meta["kind"] == "card" and meta["card_of"] == cid, cid
        model = item_model(fields[name]) if is_list_field(fields[name]) else fields[name].annotation
        assert model is CARDS[cid][0], cid
    extra = set(fields) - set(CARD_FIELDS.values())
    assert extra == {"title", "schema_version", "output_language", "example_chapter", "card_notes", "chapters", "after_story", "locks"}


def test_after_story_holds_updated_copies_of_the_portable_root_cards():
    fields = fields_of(AfterStory)
    assert {f.json_schema_extra["card_of"] for f in fields.values()} == {"style", "characters", "world"}
    assert all(CARDS[c][4]["portable"] for c in ("style", "characters", "world"))


def test_only_characters_chapters_notes_and_locks_are_uncapped_in_the_project():
    uncapped = {n for n, f in fields_of(Project).items() if is_list_field(f) and f.json_schema_extra.get("uncapped")}
    uncapped |= {f"after_story.{n}" for n, f in fields_of(AfterStory).items() if is_list_field(f) and f.json_schema_extra.get("uncapped")}
    assert uncapped == PROJECT_UNCAPPED


def test_full_project_round_trips_through_json_with_ids_intact():
    p = sample(Project)
    p.schema_version = SCHEMA_VERSION
    p.after_story = sample(AfterStory)
    back = Project.model_validate_json(p.model_dump_json())
    assert back == p
    assert back.id == p.id and back.characters[0].id == p.characters[0].id
    assert back.entanglements_history.states[0].state.ties[0].id == p.entanglements_history.states[0].state.ties[0].id


def test_a_story_in_progress_has_no_after_story():
    assert sample(Project).after_story is None


def test_a_project_missing_a_card_is_rejected():
    data = sample(Project).model_dump()
    del data["world"]
    with pytest.raises(ValidationError):
        Project(**data)


def test_json_schema_can_be_exported_for_the_pipeline():
    schema = Project.model_json_schema()
    assert {"title", "style", "characters", "chapters", "after_story"} <= set(schema["properties"])


def test_project_rules_are_well_formed():
    names = set(fields_of(Project))
    assert len({r.id for r in PROJECT_RULES}) == len(PROJECT_RULES)
    for r in PROJECT_RULES:
        assert r.severity == "block" and r.check in PROJECT_CHECKS and not r.needs_model, r.id
        assert set(r.fields) <= names and r.when, r.id
    assert {r.check for r in PROJECT_RULES} == PROJECT_CHECKS


def test_chapter_is_just_a_beat_link_and_text():
    assert set(fields_of(Chapter)) == {"beat", "text"}


def test_example_chapter_notes_and_locks_are_optional_so_a_bare_project_is_valid():
    p = sample(Project)
    assert p.example_chapter is None and p.card_notes == [] and p.locks == []
    fields = fields_of(Project)
    assert not any(fields[n].is_required() for n in ("example_chapter", "card_notes", "locks"))


def test_notes_and_locks_round_trip_with_ids_intact():
    p = sample(Project)
    char_id = p.characters[0].id
    p.example_chapter = "A whole chapter pasted in."
    p.card_notes = [CardNote(card="style", text="dry, noir"), CardNote(card="characters", character=char_id, text="a bee-keeping enforcer")]
    p.locks = [Lock(card="style"), Lock(card="characters", owner=char_id, field="wants", item="w1", part="text")]
    back = Project.model_validate_json(p.model_dump_json())
    assert back == p and back.card_notes[1].character == char_id and back.locks[1].part == "text"


def test_notes_and_locks_point_only_at_cards_the_user_fills_in():
    user_cards = {cid for cid, c in CARDS.items() if not c[4].get("hidden")}
    assert set(get_args(UserCard)) == user_cards
    assert fields_of(CardNote)["card"].json_schema_extra["input"] == "select"
    assert fields_of(Lock)["owner"].json_schema_extra["ref"] == ["characters"]
    assert fields_of(CardNote)["character"].json_schema_extra["ref"] == ["characters"]


def test_a_lock_reads_outside_in_and_only_the_card_is_required():
    required = {n for n, f in fields_of(Lock).items() if f.is_required()}
    assert required == {"card"}
    assert list(fields_of(Lock)) == ["card", "owner", "field", "item", "part"]
