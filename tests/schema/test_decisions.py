"""Pins the design decisions made so far, plus sample cards that must validate.
When you change a decision on purpose, change the matching test here. These are not lint."""
import pytest
from pydantic import ValidationError
from helpers import *
from schema.common import MAX_ITEMS


def test_list_cap_is_five_and_only_these_lists_are_exempt():
    assert MAX_ITEMS == 5
    assert UNCAPPED == {("entanglements", "ties"), ("outline", "beats"), ("summary_events", "entries"),
                        ("summary_shifts", "shifts"), ("entanglements_history", "states")}


def test_card_chain_and_types():
    assert CARD_IDS == ["style", "characters", "world", "entanglements", "setup", "outline",
                        "summary_events", "summary_shifts", "entanglements_history"]
    assert {c: CARDS[c][4]["between_chapters"] for c in CARD_IDS} == {
        "style": "static", "characters": "static", "world": "static", "entanglements": "mutable",
        "setup": "static", "outline": "append", "summary_events": "per_chapter", "summary_shifts": "per_chapter",
        "entanglements_history": "per_chapter"}


def test_characters_sample_and_five_item_cap():
    from schema.characters import Characters
    base = dict(name="Mara", age=34, sex="female", appearance="Tall, grey-eyed.", sketch="A brutal enforcer who keeps bees.",
                fear="f", flaw="f", values=[{"text": "keeps her word"}], competence="c", vulnerability="v",
                speech="s", history="h", behaviors=[{"state": "feels watched", "tendency": "busy their hands"}])
    c = Characters(**base, wants=[{"text": "safety"}, {"text": "revenge"}])
    assert len(c.id) == 8 and c.behaviors[0].id != c.wants[0].id
    Characters(**base, wants=[{"text": str(i)} for i in range(5)])
    with pytest.raises(ValidationError):
        Characters(**base, wants=[{"text": str(i)} for i in range(6)])


def test_holdings_follow_the_pairing_table():
    from schema.entanglements import HOLDING_PAIRS, Holding
    assert HOLDING_PAIRS == {"world.objects": ["characters", "world.powers", "world.places"],
                             "world.places": ["characters", "world.powers"]}
    holdee, held_by = (Holding.model_fields[n].json_schema_extra for n in ("holdee", "held_by"))
    assert set(holdee["ref"]) == set(HOLDING_PAIRS) and held_by["ref_filter_by"] == "holdee"
    assert set(held_by["ref"]) == {s for v in HOLDING_PAIRS.values() for s in v}


def test_beat_sample_cast_cap_and_filled_by():
    from schema.outline import Beat
    base = dict(chapter=1, where="p1", when_time="Dawn", cast=["c1"], collision_goal="the ledger",
                collision_block="a locked door", choice_a="safety", choice_b="loyalty", turn="the door opens",
                shift="harder", ends_on="a knock", spotlight="pr1")
    b = Beat(**base)
    assert b.stale is False and b.when_gap is None and b.reveal_rule is None and "written" not in Beat.model_fields
    for bad in ({"cast": [str(i) for i in range(6)]}, {"shift": "sideways"}):
        with pytest.raises(ValidationError):
            Beat(**{**base, **bad})
    assert {f.json_schema_extra["filled_by"] for n, f in fields_of(Beat).items()} == {"planner", "code", "human"}
    assert Beat.model_fields["cast"].json_schema_extra["filled_by"] == "human"      # the human picks the cast before Plan
    assert Beat.model_fields["spotlight"].json_schema_extra["filled_by"] == "code"


def test_plants_are_one_per_chapter_two_open_two_payoffs():
    from schema.summaries import EventsEntry, MAX_OPEN_PLANTS
    assert MAX_OPEN_PLANTS == 2
    assert EventsEntry.model_fields["planted"].annotation == (str | None)       # a single field: at most one
    assert [m.max_length for m in EventsEntry.model_fields["paid_off"].metadata] == [2]
    assert {r.id: r for r in CARDS["summary_events"][3]}["open_plants_max"].params == {"max": 2}


def test_records_and_shifts_sample():
    from schema.summaries import CharacterShift, EventsEntry
    CharacterShift(beat="b1", character="c1", decided="to stay")
    e = EventsEntry(beat="b2", happened="x", planted="a locked box", paid_off=["e1"])
    assert e.changed is None and e.reveals_landed is None


def test_style_everything_set_by_the_human_is_a_field_with_text():
    from schema.style import Style
    assert len(Style.model_fields) == 22 and {"person", "tense"} <= set(Style.model_fields)


def test_pressures_bear_on_people_and_groups_only():
    from schema.entanglements import Pressure, PEOPLE
    assert Pressure.model_fields["bears_on"].json_schema_extra["ref"] == PEOPLE == ["characters", "world.powers"]
    rules = {r.id: r for r in CARDS["entanglements"][3]}
    assert "tie_ids" not in rules["link_broken"].context


def test_shift_legality_uses_chapter_count_and_earlier_shifts_only():
    rules = {r.id: r for r in CARDS["outline"][3]}
    assert rules["shift_legal"].context == ["chapter", "chapter_count", "earlier_shifts"]


def test_chapter_number_lives_only_on_the_beat_and_everything_else_links_to_it():
    from schema.outline import Beat
    from schema.project import Chapter
    from schema.summaries import EventsEntry, CharacterShift, ChapterState
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


def test_plants_and_payoffs_are_planned_on_the_beat_and_checked_when_landed():
    from schema.outline import Beat
    from schema.summaries import EventsEntry
    plant, payoff = (Beat.model_fields[n] for n in ("plant", "payoff"))
    assert not plant.is_required() and not payoff.is_required()
    assert payoff.json_schema_extra["ref"] == ["summary_events.entries"] and payoff.json_schema_extra["max_selected"] == 2
    rules = {r.id: r for r in CARDS["outline"][3]}
    assert rules["payoff_is_open_plant"].severity == "block" and rules["payoff_is_open_plant"].check == "paid_off_valid"
    # a reveal counts as used only when it landed, not when it was planned
    assert rules["reveal_not_repeated"].check == "not_already_landed"
    assert rules["reveal_not_repeated"].params["landed_in"] == "summary_events.reveals_landed"
    # the extractor says whether the planned goal change happened; a change that did not land stays pending
    goal_landed = EventsEntry.model_fields["goal_landed"]
    assert goal_landed.default is False and not goal_landed.is_required()
    assert goal_landed.json_schema_extra["filled_by"] == "extractor"


def test_a_redefined_goal_gets_the_same_warnings_as_setups_goal():
    rules = {r.id: r for r in CARDS["outline"][3]}
    for rid in ("goal_now_is_action", "goal_now_checkable", "goal_now_touches_cards"):
        assert rules[rid].severity == "warn" and rules[rid].needs_model, rid


def test_shifts_hold_abstract_inner_change_and_no_hides():
    from schema.summaries import CharacterShift, SHIFT_TEXT
    assert "hides" not in CharacterShift.model_fields
    assert SHIFT_TEXT == ["believes", "fears", "wants", "refuses", "decided"]
    rule = {r.id: r for r in CARDS["summary_shifts"][3]}["shift_not_empty"]
    assert rule.params["fields"] == SHIFT_TEXT


def test_a_beat_remembers_what_state_it_was_planned_from():
    from schema.outline import Beat
    planned_from = Beat.model_fields["planned_from"]
    assert not planned_from.is_required() and planned_from.json_schema_extra["filled_by"] == "code"
