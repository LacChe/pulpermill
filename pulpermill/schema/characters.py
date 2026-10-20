"""Characters card: one individual. Root, portable, static. A project holds any number of these.
Names no other person, place or object, and holds no ties (those live in Entanglements)."""
from typing import Literal
from .common import spec, Rule, Item, TextItem

CARD = {
    "id": "characters",
    "type": "root",
    "reads": [],
    "portable": True,
    "between_chapters": "static",
    "many_per_project": True,
}

GROUPS = [
    {"id": "identity", "collapsed": False},
    {"id": "drive", "collapsed": False},
    {"id": "inner_conflict", "collapsed": False},
    {"id": "texture", "collapsed": True},
    {"id": "past", "collapsed": True},
]

# Prose assembly: a short description of the person, in three paragraphs.
RENDER_ORDER = [
    ["name", "age", "sex", "appearance", "sketch"],
    ["wants", "fear", "flaw", "values", "behaviors"],
    ["competence", "vulnerability", "speech", "history"],
]

Sex = Literal["female", "male", "other"]


class Behavior(Item):
    state: str = spec("text", None, "note")      # "When ..." an inner or broad social state
    tendency: str = spec("text", None, "note")   # "they ..." a tendency, not a specific act


# Everything is required for now. Comments note what the source doc marked optional.
class Characters(Item):
    # Identity
    name: str = spec("text", "identity", "free", fixed=True)
    age: int = spec("number", "identity", "free", fixed=True)
    sex: Sex = spec("select", "identity", "axis", fixed=True)
    appearance: str = spec("textarea", "identity", "free", fixed=True)
    sketch: str = spec("textarea", "identity", "note")

    # Drive
    wants: list[TextItem] = spec(None, "drive", "items", repeat=True)
    fear: str = spec("textarea", "drive", "free")                       # source doc: optional

    # Inner conflict
    flaw: str = spec("textarea", "inner_conflict", "free")
    values: list[TextItem] = spec(None, "inner_conflict", "items", repeat=True)   # source doc: optional
    behaviors: list[Behavior] = spec(None, "inner_conflict", "pairs", repeat=True, counted=True)  # source doc: optional

    # Texture
    competence: str = spec("textarea", "texture", "free")               # source doc: optional
    vulnerability: str = spec("textarea", "texture", "free")            # source doc: optional
    speech: str = spec("textarea", "texture", "free")                   # source doc: optional

    # Past
    history: str = spec("textarea", "past", "free")                     # source doc: optional


PORTABLE_TEXT = ["appearance", "sketch", "wants", "fear", "flaw", "values", "behaviors",
                 "competence", "vulnerability", "speech", "history"]

RULES = [
    Rule(id="char_other_names", severity="warn", fields=PORTABLE_TEXT,
         when="text names another character, place or object that exists in this project (a character must work in any project)",
         check="mentions_known_names", context=["character_names", "world_names"]),
    Rule(id="char_no_relationships", severity="warn", fields=PORTABLE_TEXT,
         when="text describes a relationship to someone else (brother, former partner, boss) instead of a trait of this person",
         needs_model=True),
    Rule(id="sketch_describes_person", severity="warn", fields=["sketch"],
         when="the sketch only names a role or occupation ('thief', 'detective') and does not describe what the person is like",
         needs_model=True),
    Rule(id="appearance_concrete", severity="warn", fields=["appearance"],
         when="appearance gives impressions instead of concrete, checkable details",
         needs_model=True),
    Rule(id="wants_count", severity="warn", fields=["wants"],
         when="wants has fewer than two items, so there is nothing for a want to pull against",
         check="item_count", params={"min": 2}),
    Rule(id="wants_conflict", severity="warn", fields=["wants"],
         when="all the wants could be fully satisfied at the same time, so there is no internal conflict (a suggested opposing want may be offered, never added silently)",
         needs_model=True),
    Rule(id="values_positive", severity="warn", fields=["values"],
         when="a value is phrased as a prohibition instead of something the character protects",
         needs_model=True),
    Rule(id="behavior_state_is_inner", severity="warn", fields=["behaviors"],
         when="a 'when' box holds a concrete situation instead of an inner or broad social state",
         needs_model=True),
    Rule(id="behaviors_include_calm", severity="warn", fields=["behaviors"],
         when="none of the 'when' states is calm or happy",
         needs_model=True),
    Rule(id="behavior_is_tendency", severity="warn", fields=["behaviors"],
         when="a 'they' box holds one specific act instead of a tendency",
         needs_model=True),
]
