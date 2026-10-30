"""Pins the design decisions made so far (P0 decision record), plus sample cards that must validate.
When you change a decision on purpose, change the matching test here. These are not lint."""
import pytest
from pydantic import ValidationError
from helpers import *
from pulpermill.schema.common import MAX_ITEMS


def test_list_cap_is_five_and_only_these_lists_are_exempt():
    assert MAX_ITEMS == 5
    assert UNCAPPED == {("entanglements", "ties"), ("entanglements", "holdings"), ("world", "places"), ("world", "objects"),
                        ("outline", "beats"), ("summary_events", "entries"), ("summary_shifts", "shifts"),
                        ("entanglements_history", "states")}


def test_card_chain_and_types():
    assert CARD_IDS == ["style", "characters", "world", "entanglements", "setup", "outline",
                        "summary_events", "summary_shifts", "entanglements_history"]
    assert {c: CARDS[c][4]["between_chapters"] for c in CARD_IDS} == {
        "style": "static", "characters": "static", "world": "static", "entanglements": "static",
        "setup": "static", "outline": "append", "summary_events": "per_chapter", "summary_shifts": "per_chapter",
        "entanglements_history": "per_chapter"}


def test_no_count_or_rotation_flags_and_no_live_fields_remain_on_the_cards():
    for cid in ("characters", "world", "entanglements", "setup", "outline"):
        for n, f in all_fields(CARDS[cid][0]):
            assert not f.json_schema_extra.get("counted"), (cid, n)
            assert not f.json_schema_extra.get("changes"), (cid, n)


def test_world_and_character_lists_are_not_counted_and_places_and_objects_stay_uncapped():
    from pulpermill.schema.characters import Characters
    from pulpermill.schema.world import World, WorldRule
    assert "counted" not in Characters.model_fields["behaviors"].json_schema_extra
    for name in ("places", "objects"):
        meta = World.model_fields[name].json_schema_extra
        assert meta["uncapped"] and "counted" not in meta and "max_items" not in meta
    assert {"statement", "cost", "when_broken"} == set(item_fields(World.model_fields["rules"])) == set(WorldRule.model_fields) - {"id"}
    assert {r.id for r in CARDS["world"][3]}.isdisjoint({"rule_false_needs_truth"})


def test_characters_sample_and_five_item_cap():
    from pulpermill.schema.characters import Characters
    base = dict(name="Mara", age=34, sex="female", appearance="Tall, grey-eyed.", sketch="A brutal enforcer who keeps bees.",
                fear="f", flaw="f", values=[{"text": "keeps her word"}], competence="c", vulnerability="v",
                speech="s", history="h", behaviors=[{"state": "feels watched", "tendency": "busy their hands"}])
    c = Characters(**base, wants=[{"text": "safety"}, {"text": "revenge"}])
    assert len(c.id) == 8 and c.behaviors[0].id != c.wants[0].id
    Characters(**base, wants=[{"text": str(i)} for i in range(5)])
    with pytest.raises(ValidationError):
        Characters(**base, wants=[{"text": str(i)} for i in range(6)])


def test_holdings_follow_the_pairing_table():
    from pulpermill.schema.entanglements import HOLDING_PAIRS, Holding
    assert HOLDING_PAIRS == {"world.objects": ["characters", "world.powers", "world.places"],
                             "world.places": ["characters", "world.powers"]}
    holdee, held_by = (Holding.model_fields[n].json_schema_extra for n in ("holdee", "held_by"))
    assert set(holdee["ref"]) == set(HOLDING_PAIRS) and held_by["ref_filter_by"] == "holdee"
    assert set(held_by["ref"]) == {s for v in HOLDING_PAIRS.values() for s in v}


def test_entanglements_hold_ties_and_holdings_only_and_are_static():
    from pulpermill.schema import entanglements as e
    assert list(fields_of(e.Entanglements)) == ["ties", "holdings"]
    assert e.RENDER_ORDER == [["ties", "holdings"]] and e.LISTS == ["ties", "holdings"]
    assert [g["id"] for g in e.GROUPS] == ["ties", "holdings"]
    assert e.CARD["between_chapters"] == "static"
    for gone in ("KnowledgeEntry", "KNOWLEDGE_LISTS", "Pressure", "PressureStatus"):
        assert not hasattr(e, gone), gone
    assert {r.id for r in e.RULES} == {"tie_not_self", "holding_pair_allowed", "link_broken", "tie_edge_is_live"}


def test_a_tie_has_a_bond_and_an_edge_that_are_both_required_and_ends_that_are_people_and_groups():
    from pulpermill.schema.entanglements import Tie, PEOPLE
    assert Tie.model_fields["bond"].is_required() and Tie.model_fields["edge"].is_required()
    assert Tie.model_fields["tie_from"].json_schema_extra["ref"] == Tie.model_fields["tie_to"].json_schema_extra["ref"] == PEOPLE == ["characters", "world.powers"]
    rules = {r.id: r for r in CARDS["entanglements"][3]}
    assert rules["tie_edge_is_live"].severity == "warn" and rules["tie_edge_is_live"].needs_model
    assert rules["link_broken"].fields == ["ties", "holdings"] and "tie_ids" not in rules["link_broken"].context


def test_setup_has_no_goal_or_stakes_and_warns_when_the_protagonist_has_no_tie():
    from pulpermill.schema.setup import Setup, RENDER_ORDER, GROUPS
    assert list(fields_of(Setup)) == ["protagonist", "normal", "disruption", "chapter_count"]
    assert RENDER_ORDER == [["protagonist", "normal", "disruption"], ["chapter_count"]]
    assert {f.json_schema_extra["group"]: 0 for f in fields_of(Setup).values()} == {"opening": 0, "push": 0}
    assert [n for n, f in fields_of(Setup).items() if f.json_schema_extra["group"] == "push"] == ["chapter_count"]
    rules = {r.id: r for r in CARDS["setup"][3]}
    assert set(rules) == {"protagonist_link_broken", "normal_is_concrete", "disruption_is_event", "protagonist_has_tie"}
    rule = rules["protagonist_has_tie"]
    assert rule.severity == "warn" and not rule.needs_model and rule.check == "person_has_tie"   # advice, never a block


def test_beat_fields_and_who_fills_them():
    from pulpermill.schema.outline import Beat
    assert list(fields_of(Beat)) == ["chapter", "stale", "where", "when_time", "cast", "spotlight", "aim", "plan", "planned_from"]
    filled = {n: f.json_schema_extra["filled_by"] for n, f in fields_of(Beat).items()}
    assert filled == {"chapter": "code", "stale": "code", "where": "planner", "when_time": "planner", "cast": "human",
                      "spotlight": "code", "aim": "planner", "plan": "planner", "planned_from": "code"}
    meta = {n: f.json_schema_extra for n, f in fields_of(Beat).items()}
    assert meta["spotlight"]["ref"] == ["entanglements.ties"] and meta["where"]["ref"] == ["world.places"]
    assert meta["cast"]["ref"] == ["characters"] and meta["cast"]["max_selected"] == 5
    assert meta["aim"]["input"] == "text" and meta["plan"]["input"] == "textarea"


def test_beat_sample_cast_cap_and_defaults():
    from pulpermill.schema.outline import Beat
    base = dict(chapter=1, where="p1", when_time="Dawn", cast=["c1"], spotlight="t1", aim="the ledger", plan="Ines opens the shop.")
    b = Beat(**base)
    assert b.stale is False and b.planned_from is None and "written" not in Beat.model_fields
    with pytest.raises(ValidationError):
        Beat(**{**base, "cast": [str(i) for i in range(6)]})
    with pytest.raises(ValidationError):
        Beat(**{k: v for k, v in base.items() if k != "aim"})


def test_no_plants_reveals_offstage_shifts_or_pressure_spotlight_on_the_beat_or_in_events():
    from pulpermill.schema.outline import Beat
    import pulpermill.schema.outline as outline, pulpermill.schema.summaries as summaries
    for gone in ("collision_goal", "shift", "ends_on", "when_gap", "reveal_rule", "reveal_learners", "plant", "payoff",
                 "offstage_did", "offstage_reach"):
        assert gone not in Beat.model_fields, gone
    for gone in ("Shift",):
        assert not hasattr(outline, gone)
    for gone in ("GoalChange", "MAX_OPEN_PLANTS"):
        assert not hasattr(summaries, gone)
    assert Beat.model_fields["spotlight"].json_schema_extra["ref"] != ["entanglements.pressures"]


def test_outline_rules():
    rules = {r.id: r for r in CARDS["outline"][3]}
    assert set(rules) == {"outline_link_broken", "cast_has_protagonist", "spotlight_pair_in_cast", "aim_not_repeated"}
    assert "tie_ids" in rules["outline_link_broken"].context and "pressure_ids" not in rules["outline_link_broken"].context
    assert "skip" not in rules["outline_link_broken"].params
    pair = rules["spotlight_pair_in_cast"]
    assert pair.severity == "block" and pair.check == "tie_ends_in_cast" and not pair.needs_model
    assert rules["cast_has_protagonist"].severity == "block"
    aim = rules["aim_not_repeated"]
    assert aim.severity == "warn" and aim.params == {"field": "aim"}


def test_events_keep_what_happened_and_what_changed_only():
    from pulpermill.schema.summaries import EventsEntry
    assert list(fields_of(EventsEntry)) == ["beat", "happened", "changed"]
    e = EventsEntry(beat="b2", happened="x")
    assert e.changed is None
    assert {r.id for r in CARDS["summary_events"][3]} == {"events_beat_unique", "events_link_broken", "changed_is_one_sentence"}
    assert {r.id: r for r in CARDS["summary_events"][3]}["events_link_broken"].context == ["beat_ids"]


def test_the_plan_is_on_the_beat_and_the_project_keeps_no_plan_notes():
    from pulpermill.schema import project
    assert project.SCHEMA_VERSION == 3
    assert not hasattr(project, "PlanNote") and "plan_notes" not in project.Project.model_fields
    assert "plan_note_unique" not in {r.id for r in project.PROJECT_RULES}


def test_style_everything_set_by_the_human_is_a_field_with_text():
    from pulpermill.schema.style import Style
    assert len(Style.model_fields) == 22 and {"person", "tense"} <= set(Style.model_fields)


def test_chapter_number_lives_only_on_the_beat_and_everything_else_links_to_it():
    from pulpermill.schema.outline import Beat
    from pulpermill.schema.project import Chapter
    from pulpermill.schema.summaries import EventsEntry, CharacterShift, ChapterState
    assert Beat.model_fields["chapter"].json_schema_extra["filled_by"] == "code"
    for model in (Chapter, EventsEntry, CharacterShift, ChapterState):
        assert "chapter" not in model.model_fields, model.__name__
        assert model.model_fields["beat"].json_schema_extra["ref"] == ["outline.beats"], model.__name__
    assert Beat.model_fields["stale"].json_schema_extra["filled_by"] == "code" and Beat.model_fields["stale"].default is False


def test_records_are_one_per_beat_and_replaced_not_appended():
    assert {r.id: r for r in CARDS["summary_events"][3]}["events_beat_unique"].params == {"field": "beat"}
    assert {r.id: r for r in CARDS["entanglements_history"][3]}["history_beat_unique"].params == {"field": "beat"}
    shifts = {r.id: r for r in CARDS["summary_shifts"][3]}
    assert shifts["shift_unique_per_chapter"].params == {"fields": ["beat", "character"]}
    assert shifts["shifts_per_chapter_max"].params == {"group_by": "beat", "max": 5}


def test_shifts_hold_abstract_inner_change_and_no_hides():      # P2 replaces this record
    from pulpermill.schema.summaries import CharacterShift, SHIFT_TEXT
    assert "hides" not in CharacterShift.model_fields
    assert SHIFT_TEXT == ["believes", "fears", "wants", "refuses", "decided"]
    CharacterShift(beat="b1", character="c1", decided="to stay")


def test_a_beat_remembers_what_it_was_planned_from():
    from pulpermill.schema.outline import Beat
    planned_from = Beat.model_fields["planned_from"]
    assert not planned_from.is_required() and planned_from.json_schema_extra["filled_by"] == "code"
