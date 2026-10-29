"""Entanglements card: the live connections between people, things, knowledge and pressures.
Glue (live): reads Characters and World, not portable, revised after every chapter (the revising is pipeline).
It is the only card that links to other cards, always by id. The writer prompt shows names."""
from typing import Literal
from .common import spec, Rule, Item

CARD = {
    "id": "entanglements",
    "type": "glue",
    "reads": ["characters", "world"],
    "portable": False,
    "between_chapters": "mutable",     # fields flagged changes=True are the ones that move
}

GROUPS = [
    {"id": "ties", "collapsed": False},
    {"id": "holdings", "collapsed": False},
    {"id": "knowledge", "collapsed": False},
    {"id": "pressures", "collapsed": False},
]

RENDER_ORDER = [
    ["ties", "holdings"],
    ["knowledge", "pressures"],
]

# Who or what may hold or control what. Keys and values are reference sources (see conventions: refs).
HOLDING_PAIRS = {
    "world.objects": ["characters", "world.powers", "world.places"],
    "world.places": ["characters", "world.powers"],
}

# Reference sources: "characters" or "<card>.<list field>". Values are item ids; names are shown in prose.
PEOPLE = ["characters", "world.powers"]


class Tie(Item):
    tie_from: str = spec("select", None, "note", ref=PEOPLE)
    tie_to: str = spec("select", None, "note", ref=PEOPLE)
    bond: str = spec("text", None, "note", changes=True)
    edge: str = spec("text", None, "note", changes=True)


class Holding(Item):
    holdee: str = spec("select", None, "note", ref=["world.objects", "world.places"])
    held_by: str = spec("select", None, "note", ref=["characters", "world.powers", "world.places"],
                        ref_filter_by="holdee", changes=True)


# One thing (a world rule or a fact), and everyone's standing towards it: three lists of people and groups, a person in at most one.
KNOWLEDGE_LISTS = ["knows", "suspects", "misled"]


class KnowledgeEntry(Item):
    rule: str | None = spec("select", None, "note", required=False, ref=["world.rules"])   # one of rule / fact
    fact: str | None = spec("text", None, "note", required=False)
    knows: list[str] = spec("select-multiple", None, "note", required=False, default=[], ref=PEOPLE, changes=True)
    suspects: list[str] = spec("select-multiple", None, "note", required=False, default=[], ref=PEOPLE, changes=True)
    misled: list[str] = spec("select-multiple", None, "note", required=False, default=[], ref=PEOPLE, changes=True)
    belief: str | None = spec("text", None, "note", required=False, changes=True)   # only with someone misled: what they wrongly believe


PressureStatus = Literal["active", "resolved"]


class Pressure(Item):
    what: str = spec("textarea", None, "note", changes=True)
    source_agent: str | None = spec("select", None, "note", required=False, ref=PEOPLE)   # one of agent / circumstance
    source_circumstance: str | None = spec("text", None, "note", required=False)
    next_move: str | None = spec("text", None, "note", required=False, changes=True)       # only with an agent
    bears_on: list[str] = spec("select-multiple", None, "note", ref=PEOPLE, changes=True)   # people and groups only, not ties
    status: PressureStatus = spec("select", None, "axis", required=False, default="active", changes=True)   # resolved once its next move has happened on the page; the story's pressures stop rotating onto it


# Everything is required for now. Source doc: "an empty section is fine".
class Entanglements(Item):
    ties: list[Tie] = spec(None, "ties", "pairs", repeat=True, uncapped=True)   # a cast has many ties
    holdings: list[Holding] = spec(None, "holdings", "pairs", repeat=True, uncapped=True)
    knowledge: list[KnowledgeEntry] = spec(None, "knowledge", "pairs", repeat=True, uncapped=True)   # no cap: the pipeline sends the relevant, least used
    pressures: list[Pressure] = spec(None, "pressures", "pairs", repeat=True)


LISTS = ["ties", "holdings", "knowledge", "pressures"]

# Blocking rules guard structure the pipeline cannot work around. Warn rules are advice.
# Rules that guard what drives the story are marked [drives story].
RULES = [
    Rule(id="tie_not_self", severity="block", fields=["ties"],
         when="a tie goes from someone to themselves",
         check="fields_differ", params={"fields": ["tie_from", "tie_to"]}),
    Rule(id="holding_pair_allowed", severity="block", fields=["holdings"],
         when="the holder is not allowed for that kind of thing under HOLDING_PAIRS",
         check="holding_pairs_allowed", params={"table": "HOLDING_PAIRS"}),
    Rule(id="knowledge_one_fact", severity="block", fields=["knowledge"],
         when="an entry gives both a world rule and a free-text fact, or neither",
         check="exactly_one", params={"fields": ["rule", "fact"]}),
    Rule(id="knowledge_someone", severity="block", fields=["knowledge"],
         when="an entry names no one who knows, suspects or is misled",
         check="any_filled", params={"fields": KNOWLEDGE_LISTS}),
    Rule(id="knowledge_one_standing", severity="block", fields=["knowledge"],
         when="the same person or group is in more than one of knows, suspects and misled",
         check="disjoint_lists", params={"fields": KNOWLEDGE_LISTS}),
    Rule(id="pressure_one_source", severity="block", fields=["pressures"],
         when="a pressure gives both an agent and a circumstance, or neither",
         check="exactly_one", params={"fields": ["source_agent", "source_circumstance"]}),
    Rule(id="next_move_for_agents", severity="block", fields=["pressures"],
         when="a pressure has an agent but no next move",
         check="required_if", params={"field": "next_move", "when_present": "source_agent"}),
    Rule(id="link_broken", severity="block", fields=LISTS,
         when="a link points to a character, thing, place, group or rule that no longer exists (a root card was changed)",
         check="ref_exists", context=["character_ids", "world_item_ids"]),
    Rule(id="tie_edge_is_live", severity="warn", fields=["ties"],                  # drives story
         when="an edge states a feeling or a standing fact instead of what one side wants from or hides from the other right now",
         needs_model=True),
    Rule(id="pressure_has_consequence", severity="warn", fields=["pressures"],     # drives story
         when="a pressure does not say what happens if it is ignored",
         needs_model=True),
    Rule(id="pressure_next_move_in_situation", severity="warn", fields=["pressures"],   # drives story
         when="an agent's next move states the agent's general wants instead of what it wants in this situation",
         needs_model=True),
    Rule(id="pressures_active_count", severity="warn", fields=["pressures"],       # drives story
         when="more than three pressures are active at once (a resolved pressure is not active)",
         check="item_count", params={"max": 3, "skip": {"status": "resolved"}}),
]
