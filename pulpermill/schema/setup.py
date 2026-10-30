"""Setup card: the springboard. Launch (fixed), one per story, not portable, never changes.
Who we follow, what just broke, and how long the story runs. It holds no goal, no plan and no ending."""
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
    ["chapter_count"],
]


# Everything is required for now. Source doc: Normal and What's at stake are optional.
class Setup(BaseModel):
    # Opening
    protagonist: str = spec("select", "opening", "free", ref=["characters"])
    normal: str = spec("textarea", "opening", "free")                # source doc: optional
    disruption: str = spec("textarea", "opening", "free")

    # Push
    chapter_count: int = spec("number", "push", "free")              # a budget; forced in code


# [drives story] marks rules that guard what drives the story.
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
    Rule(id="protagonist_has_tie", severity="warn", fields=["protagonist"],        # drives story
         when="the protagonist is at neither end of any tie in Entanglements (advice only: a protagonist with no tie is allowed)",
         check="person_has_tie", context=["ties"]),
]
