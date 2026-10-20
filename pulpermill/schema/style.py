"""Style card: how the story is told. Root, portable, static. Story-agnostic."""
from typing import Literal
from pydantic import BaseModel
from .common import spec, Rule

CARD = {
    "id": "style",
    "type": "root",
    "reads": [],
    "portable": True,
    "between_chapters": "static",
}

# Groups in form order. 'collapsed' = hidden until opened in the UI.
GROUPS = [
    {"id": "narration", "collapsed": False},
    {"id": "narrator", "collapsed": True},
    {"id": "sentences", "collapsed": True},
    {"id": "stance", "collapsed": False},
    {"id": "dialogue", "collapsed": True},
    {"id": "free", "collapsed": False},
]

# Prose assembly: two paragraphs. Genre leads because naming a tradition is the strongest lever.
RENDER_ORDER = [
    ["genre", "person", "tense", "distance", "humor", "pacing", "narrator_note",
     "attitude", "stance_note", "lens"],
    ["rhythm", "diction", "formality", "imagery", "edge", "explicitness", "sentences_note",
     "amount", "directness", "polish", "voice_difference", "dialogue_note"],
]

Person = Literal["first", "third"]
Tense = Literal["past", "present"]
Distance = Literal["external", "close", "deep"]
Humor = Literal["none", "dry", "absurd", "dark"]
Pacing = Literal["lingering", "balanced", "brisk"]
Rhythm = Literal["terse", "varied", "flowing"]
Diction = Literal["plain", "ornate"]
Register = Literal["formal", "casual"]
Imagery = Literal["literal", "occasional", "lush"]
Edge = Literal["clean", "coarse"]
Explicitness = Literal["implied", "shown"]
Attitude = Literal["earnest", "warm", "wry", "sardonic", "clinical", "melancholic", "wondering"]
Amount = Literal["sparse", "abundant"]
Directness = Literal["direct", "subtext"]
Polish = Literal["naturalistic", "stylised"]
VoiceDifference = Literal["distinct", "uniform"]


class Style(BaseModel):
    # Everything is required for now (the human will loosen this later).
    # Narration: the only mechanical rules. Setup's protagonist must fit them.
    person: Person = spec("select", "narration", "rule")
    tense: Tense = spec("select", "narration", "rule")

    # Narrator
    distance: Distance = spec("select", "narrator", "axis")
    humor: Humor = spec("select", "narrator", "axis")
    pacing: Pacing = spec("select", "narrator", "axis")
    narrator_note: str = spec("textarea", "narrator", "note")

    # Sentences and words
    rhythm: Rhythm = spec("select", "sentences", "axis")
    diction: Diction = spec("select", "sentences", "axis")
    formality: Register = spec("select", "sentences", "axis")
    imagery: Imagery = spec("select", "sentences", "axis")
    edge: Edge = spec("select", "sentences", "axis")
    explicitness: Explicitness = spec("select", "sentences", "axis")
    sentences_note: str = spec("textarea", "sentences", "note")

    # Stance
    attitude: Attitude = spec("select", "stance", "axis")
    stance_note: str = spec("textarea", "stance", "note")

    # Dialogue
    amount: Amount = spec("select", "dialogue", "axis")
    directness: Directness = spec("select", "dialogue", "axis")
    polish: Polish = spec("select", "dialogue", "axis")
    voice_difference: VoiceDifference = spec("select", "dialogue", "axis")
    dialogue_note: str = spec("textarea", "dialogue", "note")

    # Free text
    lens: str = spec("textarea", "free", "free")
    genre: str = spec("text", "free", "free")


TEXT_FIELDS = ["narrator_note", "sentences_note", "stance_note", "dialogue_note", "lens", "genre"]

# Judgment rules. Missing / invalid values are handled by built-in reject and block rules.
RULES = [
    Rule(
        id="style_agnostic", severity="warn", fields=TEXT_FIELDS,
        when="free text names a character, place or object that exists in this project (Style must work with any story)",
        check="mentions_known_names", context=["character_names", "world_names"],
    ),
    Rule(
        id="lens_is_habit", severity="warn", fields=["lens"],
        when="the lens reads as a subject or theme ('a story about X') instead of a habit of attention",
        needs_model=True,
    ),
    Rule(
        id="genre_not_plot", severity="warn", fields=["genre"],
        when="the genre asks for specific events instead of a tradition, mood or feeling",
        needs_model=True,
    ),
]
