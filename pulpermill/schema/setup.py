"""Setup card: the springboard. Launch (fixed), one per story, not portable, never changes.
Who we follow, what just broke, and what pushes them forward. It holds no plan and no ending."""
from pydantic import BaseModel
from .common import spec, Rule

CARD = {
    "id": "setup",
    "type": "launch",
    "reads": ["style", "characters", "world", "entanglements"],
    "portable": False,
    "between_chapters": "static",
}

GROUPS = [
    {"id": "opening", "collapsed": False},
    {"id": "push", "collapsed": False},
]

RENDER_ORDER = [
    ["protagonist", "normal", "disruption"],
    ["goal", "stakes", "chapter_count"],
]


# Everything is required for now. Source doc: Normal and What's at stake are optional.
class Setup(BaseModel):
    # Opening
    protagonist: str = spec("select", "opening", "free", ref=["characters"])
    normal: str = spec("textarea", "opening", "free")                # source doc: optional
    disruption: str = spec("textarea", "opening", "free")

    # Push
    goal: str = spec("textarea", "push", "free")
    stakes: str = spec("textarea", "push", "free")                   # source doc: optional
    chapter_count: int = spec("number", "push", "free")              # a budget; forced in code


# [drives story] marks rules that guard what pushes the protagonist.
RULES = [
    Rule(id="protagonist_link_broken", severity="block", fields=["protagonist"],
         when="the protagonist was removed or renamed in Characters",
         check="ref_exists", context=["character_ids"]),
    Rule(id="normal_is_concrete", severity="warn", fields=["normal"],
         when="the normal names no people, places or routines, or does not say what that normal gave the protagonist",
         needs_model=True),
    Rule(id="disruption_is_event", severity="warn", fields=["disruption"],
         when="the disruption is a condition ('things are tense') and not an event",
         needs_model=True),
    Rule(id="goal_is_action", severity="warn", fields=["goal"],                    # drives story
         when="the goal is a theme or a feeling ('find peace') and not something to act on in scenes",
         needs_model=True),
    Rule(id="goal_checkable", severity="warn", fields=["goal"],                    # drives story
         when="a reader could not tell whether the goal succeeded, failed or stopped mattering",
         needs_model=True),
    Rule(id="goal_touches_cards", severity="warn", fields=["goal"],                # drives story
         when="the goal does not narrow one of the protagonist's wants, or bears on no pressure or tie in Entanglements",
         needs_model=True, context=["protagonist_wants", "pressures", "ties"]),
    Rule(id="stakes_has_cost", severity="warn", fields=["stakes"],                 # drives story
         when="the stakes name no cost or gain (it can be a friendship, a reputation or a chance at happiness)",
         needs_model=True),
    Rule(id="stakes_tie_to_cards", severity="warn", fields=["stakes"],             # drives story
         when="the stakes are tied to no want, value or pressure already on the cards",
         needs_model=True, context=["protagonist_wants", "protagonist_values", "pressures"]),
]
