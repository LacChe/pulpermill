from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, model_validator

from .common import UsesMap, _pooled, clean_uses


# ===========================================================================
# STYLE
# The author designs how the story is told. The design fields below are plain phrases in the author's own words (never
# codes or numbers), and `narrator` blends them into one description of how this narrator perceives the world. The
# writer reads `narrator`, not the fields, so the fields are inputs to the card and the paragraph is its result.
# ===========================================================================


class POV(str, Enum):
    first_person = "first_person"
    third_limited = "third_limited"  # the only third person: the story stays with its one main character


class Tense(str, Enum):
    past = "past"
    present = "present"


# Reference points for the range of each design field, in the order the card lists them. They are shown to the model as
# examples of the range, and the page can offer them as suggestions; a field may use any of them, a mix, or its own words.
DESIGN_ANCHORS: dict[str, list[str]] = {
    "stance": ["cynical", "tender", "weary", "awed", "clinical", "menacing"],
    "cadence": ["staccato", "rolling", "breathless", "deliberate", "mixed"],
    "dialogue_manner": ["plainly tagged", "sparingly tagged", "mostly untagged", "dialect-flavored"],
    "time_handling": ["tight continuous scenes", "summary that skips ahead", "lingering on single moments"],
}

# The dials: five choices that run along one line, picked as a level from 1 to 5 (3 is the middle and the default). Each
# level has a fixed description, and that description is what every prompt is sent, never the bare number. Each entry is
# (name, description); the order is the order of the levels.
DIAL_DEFAULT = 3
LADDERS: dict[str, list[tuple[str, str]]] = {
    "economy": [
        ("Clipped", "Each moment gets the least language that carries it: one beat, one detail at most, then the next. Anything that doesn't move the scene or reveal the character is left out."),
        ("Spare", "A few chosen details per moment, stated briefly, and then on. The prose moves faster than the events feel."),
        ("Measured", "Each moment gets enough language to ground it: what is seen, what is done, what it costs. Neither rushed nor lingered over."),
        ("Full", "Moments are given room. Detail is allowed to build up, and a scene can stay on a gesture, a room or a pause before moving on."),
        ("Expansive", "Scenes are built out slowly and abundantly. The narration takes its time over setting, bodies, objects and small shifts, and is happy to give a single moment a whole paragraph."),
    ],
    "diction": [
        ("Plain", "Everyday words a child could follow, and short ones where there is a choice. Nothing obscure, no showy vocabulary, and no word that makes the reader stop."),
        ("Simple", "Mostly everyday words, with the occasional precise or less common one when it is the right word. Easy to read without effort."),
        ("Balanced", "Ordinary and exact words side by side. The vocabulary is neither plain nor showy, and it stays natural to the narrator."),
        ("Literary", "A wider, more deliberate vocabulary. Words are chosen for connotation and sound as well as sense, and less common words are welcome when they fit."),
        ("Ornate", "Rich, elaborate, elevated language. Rare, archaic or learned words and formal phrasing are used freely, and the prose is meant to be savored as well as followed."),
    ],
    "figurative": [
        ("Literal", "No metaphor or simile. Things are described as they are, and the narration states what happens directly."),
        ("Sparing", "An image appears only when plain description would not carry it, and then briefly. Most pages have none."),
        ("Occasional", "A figure of speech now and then, usually short and drawn from the story's own world. Plain description does most of the work."),
        ("Frequent", "Images are a normal part of how things are described. Several appear in a scene, and they are expected to do work, not decorate."),
        ("Rich", "Figurative language runs through the narration. Metaphor and simile are how the narrator sees, so scenes are described through comparison more often than through direct statement."),
    ],
    "interiority": [
        ("Behaviorist", "The narration records only what can be seen and heard: actions, objects, speech. What the character thinks or feels is never stated, only shown through what they do."),
        ("Restrained", "Thoughts and feelings are given only rarely and briefly, mostly through a physical sign or a short, flat remark. The reader infers most of what the character feels."),
        ("Filtered", "The narration passes through the character's mind. It reports what they notice, think and feel in the narrator's own words, enough to follow them but not at length."),
        ("Open", "Feelings and thoughts are stated openly and are a regular part of the page. The reader is told what the character wants, fears and makes of what happens."),
        ("Stream of thought", "The narration is the character's own mind: associations, interruptions, half-formed thoughts and memories surface as they come, and the line between what happens and what they think is thin."),
    ],
    "humor": [
        ("None", "The narration is in earnest throughout, with no jokes and no irony played for laughs."),
        ("Rare", "Wit appears only occasionally, as a dry aside or a small ironic turn, and the story stays serious around it."),
        ("Present", "A light vein of humor runs through the narration: wry observations and small ironies. It does not take over serious moments."),
        ("Frequent", "Humor is a regular part of how the narrator speaks. Many paragraphs have a joke, an absurd comparison or a deflating aside, and it can sit beside serious events."),
        ("Pervasive", "The narration is comic as a default. Almost everything is seen through a joke, an exaggeration or an absurdity, even in dark moments."),
    ],
}
DIAL_FIELDS = tuple(LADDERS)


class Dial(BaseModel):
    level: int = Field(
        ge=1,
        le=5,
        description="A whole number from 1 to 5. The levels for this field are listed in the instructions; choose the one "
        "whose description fits. 3 is the middle.",
    )
    note: str = Field(
        default="",
        description="An optional short phrase that bends the level for this story (for example, which kind of humor). "
        "Leave it empty when the level says it all.",
    )

    @model_validator(mode="before")
    @classmethod
    def _loose(cls, v):
        """Accept a bare number, or a bare phrase (an older card): the phrase becomes the note at the middle level."""
        if isinstance(v, bool):
            return {"level": DIAL_DEFAULT}
        if isinstance(v, int):
            return {"level": v}
        if isinstance(v, str):
            return {"level": DIAL_DEFAULT, "note": v}
        return v


def ladder_name(field: str, dial: "Dial") -> str:
    return LADDERS[field][min(5, max(1, dial.level)) - 1][0]


def ladder_text(field: str, dial: "Dial") -> str:
    """What a prompt is sent for this dial: the level's name and description, then the author's note if there is one."""
    name, text = LADDERS[field][min(5, max(1, dial.level)) - 1]
    note = dial.note.strip()
    return f"{name}. {text}" + (f" Author's note: {note}" if note else "")


def ladders_for_prompt() -> str:
    """Every level of every dial, for the style generator, so it can see what each number means."""
    out = []
    for field, rungs in LADDERS.items():
        out.append(f"{field.replace('_', ' ')}:")
        out += [f"  {i}. {n}: {t}" for i, (n, t) in enumerate(rungs, 1)]
    return "\n".join(out)


class StyleCard(BaseModel):
    label: str = Field(
        description="A short name for this style, two to four words, naming the genre flavor."
    )
    pov: POV = Field(
        description="The person the whole story is told in: first_person or third_limited. It never changes, "
        "and the story is always told from its one main character's side."
    )
    tense: Tense

    # ---- the design fields: one plain phrase each, in order of how the narrator takes the world in
    lens: str = Field(
        description="What the narrator perceives and what it ignores: how this narrator takes in the world, in one or "
        "two sentences. Name what draws its attention and what it never registers. No names or plot."
    )
    stance: str = Field(
        description="The narrator's attitude toward what happens, in a few words (for example cynical, tender, wry, awed, "
        "clinical, menacing). Add a clause if it needs one."
    )
    economy: Dial = Field(
        description="How much language each moment gets (1 clipped to 5 expansive). A quantity only, not the kind of words."
    )
    diction: Dial = Field(
        description="How plain or ornate the words are (1 plain to 5 ornate). Whether fancy or obscure words are welcome."
    )
    figurative: Dial = Field(
        description="How much metaphor and simile there is (1 literal to 5 rich)."
    )
    cadence: str = Field(
        description="How the sentences move, described by feel and not by a formula: short and chopped or long and "
        "looping, plain statements set side by side or clauses nested inside clauses (staccato, rolling, breathless, "
        "deliberate, or a stated mix)."
    )
    interiority: Dial = Field(
        description="How far the narration goes inside the main character's mind (1 behaviorist to 5 stream of thought)."
    )
    humor: Dial = Field(
        description="How much comedy there is in the narration (1 none to 5 pervasive). Put the kind of humor in the note."
    )
    dialogue_manner: str = Field(
        description="How speech is written down: how tagged it is, and whether characters talk differently from the "
        "narration."
    )
    time_handling: str = Field(
        description="How the narration treats time inside a chapter: tight continuous scenes, summary that skips ahead, "
        "or lingering on single moments."
    )

    narrator: str = Field(
        description="Four to six sentences in which the narrator takes in the world: what it notices, what it ignores, "
        "what it makes of what it sees, and how that sounds on the page. One coherent way of perceiving that blends every "
        "design field above, including how plain or ornate its words are. Not a list of settings and not a set of rules. Describe the narration only. Leave out "
        "names, plot, and anything that belongs to one story."
    )
    signature_moves: list[str] = Field(
        description="Three to five things this narrator does again and again that a reader would recognise, each a "
        "specific device and not a rule (a way of closing a paragraph, of reacting to a lie, of handling silence). Each "
        "should hold for any story in this style."
    )
    off_limits: list[str] = Field(
        default_factory=list,
        description="What the narration must never do, each named plainly. Only what the author said or what this "
        "narrator conspicuously never does. Leave the list empty when there is nothing to name.",
    )
    chapter_shapes: list[str] = Field(
        default_factory=list,
        description="Zero to six chapter shapes. Each shape is one short instruction for how a single chapter is built: how it "
        "opens, how it closes, and the balance of dialogue and narration. The shapes differ clearly from one another and describe "
        "structure only, never plot. Leave the list empty when no shape was asked for.",
    )
    exemplars: list[str] = Field(
        description="Two or three short passages in this style about ordinary, unrelated everyday situations. "
        "No proper nouns. The passages show rhythm and tone only."
    )
    uses: UsesMap = Field(default_factory=dict)

    @model_validator(mode="after")
    def _tidy_uses(self):
        self.uses = clean_uses(
            self.uses, _pooled("style", {"exemplars": self.exemplars})
        )
        return self
