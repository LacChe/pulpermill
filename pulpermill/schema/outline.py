"""Outline card: one springboard beat per chapter, generated one at a time from current state.
Growing: gains one beat per chapter. A beat is frozen while a chapter points at it (that is what "written" means);
a beat nobody has written yet may be replaced. It is the only place a chapter number is stored: chapter text and
the summary records point at a beat by id. Not portable. Reads everything above plus the summaries.
The human picks the cast before Plan. A beat may plan a plant and a payoff; they count only once the extractor confirms they landed."""
from typing import Literal
from .common import spec, Rule, Item

CARD = {
    "id": "outline",
    "type": "growing",
    "reads": ["style", "characters", "world", "entanglements", "setup", "summary_events", "summary_shifts"],
    "portable": False,
    "between_chapters": "append",
}

GROUPS = [
    {"id": "beats", "collapsed": False},
]

RENDER_ORDER = [["beats"]]

Shift = Literal["harder", "easier"]
GoalChange = Literal["achieved", "redefined", "abandoned"]


class Beat(Item):
    chapter: int = spec("number", None, "note", filled_by="code")
    stale: bool = spec("checkbox", None, "note", required=False, default=False, filled_by="code")   # an earlier chapter was regenerated since this beat was planned

    where: str = spec("select", None, "note", ref=["world.places"], filled_by="planner")
    when_time: str = spec("text", None, "note", filled_by="planner")
    when_gap: str | None = spec("text", None, "note", required=False, filled_by="planner")      # blank for chapter 1
    cast: list[str] = spec("select-multiple", None, "note", ref=["characters"], max_selected=5, filled_by="human")      # the human picks it before Plan; code suggests the least-used characters

    collision_goal: str = spec("text", None, "note", filled_by="planner")
    collision_block: str = spec("text", None, "note", filled_by="planner")
    choice_a: str = spec("text", None, "note", filled_by="planner")
    choice_b: str = spec("text", None, "note", filled_by="planner")
    turn: str = spec("text", None, "note", filled_by="planner")
    shift: Shift = spec("select", None, "axis", limited_by="code", filled_by="planner")
    ends_on: str = spec("text", None, "note", filled_by="planner")

    reveal_rule: str | None = spec("select", None, "note", required=False, ref=["world.rules"],
                                   ref_where={"status": ["uncommon", "false_belief"]}, filled_by="planner")
    reveal_learners: list[str] | None = spec("select-multiple", None, "note", required=False,
                                             ref=["characters"], filled_by="planner")
    plant: str | None = spec("text", None, "note", required=False, filled_by="planner")      # one thing this chapter should set up; open only once the chapter has actually planted it
    payoff: list[str] | None = spec("select-multiple", None, "note", required=False, max_selected=2,
                                    ref=["summary_events.entries"], filled_by="planner")     # open plants (earlier entries that planted and were not paid off) this chapter should resolve

    offstage_did: str | None = spec("text", None, "note", required=False, filled_by="planner")
    offstage_reach: str | None = spec("text", None, "note", required=False, filled_by="planner")
    goal_change: GoalChange | None = spec("select", None, "axis", required=False, filled_by="planner")
    goal_now: str | None = spec("text", None, "note", required=False, filled_by="planner")      # only when redefined

    spotlight: str = spec("select", None, "note", ref=["entanglements.pressures"], filled_by="code")
    planned_from: str | None = spec("text", None, "note", required=False, filled_by="code")   # hash of the Entanglements this beat was planned from; a mismatch marks the plan as made from older state


class Outline(Item):
    beats: list[Beat] = spec(None, "beats", "pairs", repeat=True, uncapped=True)   # one per chapter, up to the chapter count


# Block rules are the source doc's "checks with a retry": the beat cannot reach the writer until fixed.
# [drives story] marks warnings that guard choice, change and open questions.
RULES = [
    Rule(id="outline_link_broken", severity="block", fields=["beats"],
         when="a beat points to a place, character, rule or pressure that no longer exists",
         check="ref_exists", params={"skip": ["payoff"]}, context=["character_ids", "world_item_ids", "pressure_ids"]),   # a payoff has its own rule: once the chapter is written, the plant it paid is no longer open
    Rule(id="cast_has_protagonist", severity="block", fields=["beats"],
         when="the cast does not include the protagonist named in Setup",
         check="includes_value", params={"field": "cast", "value_from": "setup.protagonist"}),
    Rule(id="when_gap_after_first", severity="block", fields=["beats"],
         when="a beat after chapter 1 has no 'how long since the last chapter'",
         check="required_if", params={"field": "when_gap", "unless": {"chapter": 1}}),
    Rule(id="reveal_learners_needed", severity="block", fields=["beats"],
         when="a reveal names no characters who learn it",
         check="required_if", params={"field": "reveal_learners", "when_present": "reveal_rule"}),
    Rule(id="reveal_not_repeated", severity="block", fields=["beats"],
         when="the rule has already landed in an earlier written chapter (a planned reveal that did not land may be tried again)",
         check="not_already_landed", params={"field": "reveal_rule", "landed_in": "summary_events.reveals_landed"},
         context=["landed_reveals"]),
    Rule(id="payoff_is_open_plant", severity="block", fields=["beats"],
         when="a payoff points at an entry that planted nothing, is not earlier, or was already paid off",
         check="paid_off_valid", params={"field": "payoff"}),
    Rule(id="offstage_both_or_neither", severity="block", fields=["beats"],
         when="an offstage move gives what changed but not how it reaches the protagonist, or the reverse",
         check="all_or_none", params={"fields": ["offstage_did", "offstage_reach"]}),
    Rule(id="goal_now_for_redefined", severity="block", fields=["beats"],
         when="the goal is redefined but the new goal is not stated",
         check="required_if", params={"field": "goal_now", "when": {"goal_change": "redefined"}}),
    Rule(id="shift_legal", severity="block", fields=["beats"],
         when="the shift is not allowed by the pacing limits (set in code from the chapter number, the chapter count and the earlier shifts)",
         check="legal_shift", context=["chapter", "chapter_count", "earlier_shifts"]),
    Rule(id="goal_now_is_action", severity="warn", fields=["beats"],               # drives story
         when="the new goal is a theme or a feeling and not something to act on in scenes",
         needs_model=True),
    Rule(id="goal_now_checkable", severity="warn", fields=["beats"],               # drives story
         when="a reader could not tell whether the new goal succeeded, failed or stopped mattering",
         needs_model=True),
    Rule(id="goal_now_touches_cards", severity="warn", fields=["beats"],           # drives story
         when="the new goal does not narrow one of the protagonist's wants, or bears on no pressure or tie in Entanglements",
         needs_model=True, context=["protagonist_wants", "pressures", "ties"]),
    Rule(id="spotlight_in_cast", severity="warn", fields=["beats"],
         when="the spotlighted pressure involves nobody in the cast: its agent is not in the cast and nothing in its bears_on is",
         check="pressure_touches_cast", params={"field": "spotlight", "cast": "cast"}, context=["pressures"]),
    Rule(id="turn_not_repeated", severity="warn", fields=["beats"],                # drives story
         when="the turn is too similar to an earlier turn or to the changed lines",
         check="similar_to_earlier", context=["earlier_turns", "changed_lines"]),
    Rule(id="turn_is_a_change", severity="warn", fields=["beats"],                 # drives story
         when="the turn does not say what is different by the end of the chapter",
         needs_model=True),
    Rule(id="choice_is_costly", severity="warn", fields=["beats"],                 # drives story
         when="a choice option is not a want or a value, or picking one does not cost the other",
         needs_model=True, context=["protagonist_wants", "protagonist_values"]),
    Rule(id="ends_on_open_question", severity="warn", fields=["beats"],            # drives story
         when="the chapter's stopping point does not leave a question open",
         needs_model=True),
]
