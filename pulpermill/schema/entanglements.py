"""Entanglements card: the connections between people, groups, things and places.
Glue (static): reads Characters and World, not portable. It holds ties and holdings only. The card is locked once the
story starts and changes only through shifts (see shifts.py). A tie's two ends and a holding's holdee are its identity (`identity=True`).
It is the only card that links to other cards, always by id. The writer prompt shows names."""
from .common import spec, Rule, Item

CARD = {
    "id": "entanglements",
    "type": "glue",
    "reads": ["characters", "world"],
    "portable": False,
    "between_chapters": "static",
}

GROUPS = [
    {"id": "ties", "collapsed": False},
    {"id": "holdings", "collapsed": False},
]

RENDER_ORDER = [
    ["ties", "holdings"],
]

# Who or what may hold or control what. Keys and values are reference sources (see conventions: refs).
HOLDING_PAIRS = {
    "world.objects": ["characters", "world.powers", "world.places"],
    "world.places": ["characters", "world.powers"],
}

# Reference sources: "characters" or "<card>.<list field>". Values are item ids; names are shown in prose.
PEOPLE = ["characters", "world.powers"]


class Tie(Item):
    tie_from: str = spec("select", None, "note", ref=PEOPLE, identity=True)
    tie_to: str = spec("select", None, "note", ref=PEOPLE, identity=True)
    bond: str = spec("text", None, "note")      # what the tie is ("mother")
    edge: str = spec("text", None, "note")      # what the tie means for the 'from' person: their driver ("to care for him")


class Holding(Item):
    holdee: str = spec("select", None, "note", ref=["world.objects", "world.places"], identity=True)
    held_by: str = spec("select", None, "note", ref=["characters", "world.powers", "world.places"],
                        ref_filter_by="holdee")


# Everything is required for now. Source doc: "an empty section is fine".
class Entanglements(Item):
    ties: list[Tie] = spec(None, "ties", "pairs", repeat=True, uncapped=True)   # a cast has many ties; the page sends the relevant ones
    holdings: list[Holding] = spec(None, "holdings", "pairs", repeat=True, uncapped=True)


LISTS = ["ties", "holdings"]

# Blocking rules guard structure the pipeline cannot work around. Warn rules are advice.
# Rules that guard what drives the story are marked [drives story].
RULES = [
    Rule(id="tie_not_self", severity="block", fields=["ties"],
         when="a tie goes from someone to themselves",
         check="fields_differ", params={"fields": ["tie_from", "tie_to"]}),
    Rule(id="holding_pair_allowed", severity="block", fields=["holdings"],
         when="the holder is not allowed for that kind of thing under HOLDING_PAIRS",
         check="holding_pairs_allowed", params={"table": "HOLDING_PAIRS"}),
    Rule(id="link_broken", severity="block", fields=LISTS,
         when="a link points to a character, thing, place or group that no longer exists (a root card was changed)",
         check="ref_exists", context=["character_ids", "world_item_ids"]),
    Rule(id="tie_edge_is_live", severity="warn", fields=["ties"],                  # drives story
         when="an edge is a bare label or a passing mood instead of what the tie means to that person, the thing that drives them in it",
         needs_model=True),
]
