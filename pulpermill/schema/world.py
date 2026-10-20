"""World card: what exists and what is true. Root, portable, static.
Names no characters and never says who holds, knows or wants something (that is Entanglements)."""
from typing import Literal
from .common import spec, Rule, Item

CARD = {
    "id": "world",
    "type": "root",
    "reads": [],
    "portable": True,
    "between_chapters": "static",
}

GROUPS = [
    {"id": "overview", "collapsed": False},
    {"id": "places", "collapsed": False},
    {"id": "things", "collapsed": True},
    {"id": "powers", "collapsed": True},
    {"id": "truths", "collapsed": False},
    {"id": "vocabulary", "collapsed": True},
]

RENDER_ORDER = [
    ["name", "era_and_technology", "everyday_life", "history"],
    ["places", "objects", "powers"],
    ["rules", "terms"],
]

RuleStatus = Literal["common", "uncommon", "false_belief"]


class Place(Item):
    name: str = spec("text", None, "note")
    description: str = spec("textarea", None, "note")
    effect: str = spec("textarea", None, "note")          # what the place does to the people in it


class Thing(Item):
    name: str = spec("text", None, "note")
    description: str = spec("textarea", None, "note")
    significance: str = spec("textarea", None, "note")    # what it can do, or what it means to whoever wants it


class Power(Item):
    name: str = spec("text", None, "note")
    nature: str = spec("textarea", None, "note")          # what it is
    hold: str = spec("textarea", None, "note")            # how it holds power
    felt: str = spec("textarea", None, "note")            # how ordinary people feel it day to day


class WorldRule(Item):
    statement: str = spec("textarea", None, "note")
    cost: str = spec("textarea", None, "note")
    status: RuleStatus = spec("select", None, "axis")
    when_broken: str = spec("textarea", None, "note")
    truth: str | None = spec("textarea", None, "note", required=False)   # only for 'false_belief' rules


class Term(Item):
    term: str = spec("text", None, "note")
    meaning: str = spec("text", None, "note")


# Everything is required for now. Comments note what the source doc marked optional.
class World(Item):
    # Overview
    name: str = spec("text", "overview", "free")
    era_and_technology: str = spec("textarea", "overview", "free")
    everyday_life: str = spec("textarea", "overview", "free")
    history: str = spec("textarea", "overview", "free")                       # source doc: optional

    # Places
    places: list[Place] = spec(None, "places", "pairs", repeat=True, counted=True)

    # Things
    objects: list[Thing] = spec(None, "things", "pairs", repeat=True, counted=True)   # source doc: optional

    # Powers (labelled "Groups" in the UI)
    powers: list[Power] = spec(None, "powers", "pairs", repeat=True)          # source doc: optional

    # Truths (labelled "Rules" in the UI)
    rules: list[WorldRule] = spec(None, "truths", "pairs", repeat=True)

    # Vocabulary
    terms: list[Term] = spec(None, "vocabulary", "pairs", repeat=True)        # source doc: optional


ALL_TEXT = ["era_and_technology", "everyday_life", "history", "places", "objects", "powers", "rules", "terms"]

# Rules that guard fields meant to cause trouble for people (friction, cost, pressure) are marked [drives story].
RULES = [
    Rule(id="world_names_people", severity="warn", fields=ALL_TEXT,
         when="text names a character that exists in this project (a world must work with any cast)",
         check="mentions_known_names", context=["character_names"]),
    Rule(id="history_no_people", severity="warn", fields=["history"],
         when="history involves specific individuals instead of events and forces (that belongs in Entanglements)",
         needs_model=True),
    Rule(id="era_is_fact_not_mood", severity="warn", fields=["era_and_technology"],
         when="era and technology describe mood instead of facts (mood belongs to Style)",
         needs_model=True),
    Rule(id="everyday_has_friction", severity="warn", fields=["everyday_life"],   # drives story
         when="everyday life says nothing is scarce, expensive or contested, so there is no normal for the story to break",
         needs_model=True),
    Rule(id="place_acts_on_people", severity="warn", fields=["places"],           # drives story
         when="a place's effect only describes scenery and does nothing to the people in it",
         needs_model=True),
    Rule(id="object_has_stakes", severity="warn", fields=["objects"],             # drives story
         when="an object's significance does not say what it can do or what it means to whoever wants it",
         needs_model=True),
    Rule(id="object_unowned", severity="warn", fields=["objects"],
         when="an object names an owner or a location (ownership is state and belongs in Entanglements)",
         needs_model=True),
    Rule(id="power_felt_daily", severity="warn", fields=["powers"],               # drives story
         when="a group is not felt by ordinary people in daily life (a tax, a curfew, a whisper)",
         needs_model=True),
    Rule(id="power_no_current_goals", severity="warn", fields=["powers"],
         when="a group states what it wants right now (present wants are state and belong in Entanglements)",
         needs_model=True),
    Rule(id="rule_has_cost", severity="warn", fields=["rules"],                   # drives story
         when="a rule has no real price, so it is only a fact and gives nobody a choice",
         needs_model=True),
    Rule(id="rule_when_broken_clear", severity="warn", fields=["rules"],
         when="'when broken' does not say whether breaking the rule is impossible, punished, shameful or has a side effect",
         needs_model=True),
    Rule(id="rule_false_needs_truth", severity="block", fields=["rules"],
         when="a rule marked as a Myth has no truth stated",
         check="required_if", params={"field": "truth", "when": {"status": "false_belief"}}),
]
