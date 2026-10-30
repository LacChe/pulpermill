"""Outline card: one springboard beat per chapter, generated one at a time from current state.
Growing: gains one beat per chapter. A beat is frozen while a chapter points at it (that is what "written" means);
a beat nobody has written yet may be replaced. It is the only place a chapter number is stored: chapter text and
the summary records point at a beat by id. Not portable. Reads everything above plus the summaries.
The human picks the cast before Plan. Code picks the spotlight tie at random (the human may change it). The planner
writes what the protagonist is after and the plan the writer sees."""
from .common import spec, Rule, Item

CARD = {
    "id": "outline",
    "type": "growing",
    "reads": ["style", "characters", "world", "entanglements", "setup", "summary_events", "shifts"],
    "portable": False,
    "between_chapters": "append",
}

GROUPS = [
    {"id": "beats", "collapsed": False},
]

RENDER_ORDER = [["beats"]]


class Beat(Item):
    chapter: int = spec("number", None, "note", filled_by="code")
    stale: bool = spec("checkbox", None, "note", required=False, default=False, filled_by="code")   # an earlier chapter was regenerated since this beat was planned

    where: str = spec("select", None, "note", ref=["world.places"], filled_by="planner")
    when_time: str = spec("text", None, "note", filled_by="planner")
    cast: list[str] = spec("select-multiple", None, "note", ref=["characters"], max_selected=5, filled_by="human")      # the human picks it before Plan

    spotlight: str = spec("select", None, "note", ref=["entanglements.ties"], filled_by="code")      # the tie this chapter is about: code picks one at random, the human may change it
    aim: str = spec("text", None, "note", filled_by="planner")                 # what the protagonist is after in this chapter; it and the spotlight tie must collide
    plan: str = spec("textarea", None, "note", filled_by="planner")            # the planner's plan text; the writer sees it
    planned_from: str | None = spec("text", None, "note", required=False, filled_by="code")   # hash of what this beat was planned from (P5a redefines what is hashed)


class Outline(Item):
    beats: list[Beat] = spec(None, "beats", "pairs", repeat=True, uncapped=True)   # one per chapter, up to the chapter count


# Block rules are the beats' structural checks: the beat cannot reach the writer until fixed.
# [drives story] marks warnings that guard choice and change.
RULES = [
    Rule(id="outline_link_broken", severity="block", fields=["beats"],
         when="a beat points to a place, character or tie that no longer exists",
         check="ref_exists", context=["character_ids", "world_item_ids", "tie_ids"]),
    Rule(id="cast_has_protagonist", severity="block", fields=["beats"],
         when="the cast does not include the protagonist named in Setup",
         check="includes_value", params={"field": "cast", "value_from": "setup.protagonist"}),
    Rule(id="spotlight_pair_in_cast", severity="block", fields=["beats"],
         when="a character at either end of the spotlight tie is not in the cast (an end that is a group is ignored)",
         check="tie_ends_in_cast", params={"field": "spotlight", "cast": "cast"}, context=["ties"]),
    Rule(id="aim_not_repeated", severity="warn", fields=["beats"],                 # drives story
         when="the aim is too similar to an earlier aim or to what an earlier chapter changed",
         check="similar_to_earlier", params={"field": "aim"}, context=["earlier_aims", "changed_lines"]),
]
