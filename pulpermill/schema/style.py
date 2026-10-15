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
    "economy": ["clipped", "spare", "measured", "full", "expansive"],
    "diction": ["plain", "street", "technical", "literary", "archaic", "ornate"],
    "figurative": ["literal", "sparing", "rich"],
    "cadence": ["staccato", "rolling", "breathless", "deliberate", "mixed"],
    "interiority": ["behaviorist", "filtered thought", "open feeling", "stream of thought"],
    "humor": ["none", "dry", "absurd", "gallows", "light"],
    "dialogue_manner": ["plainly tagged", "sparingly tagged", "mostly untagged", "dialect-flavored"],
    "time_handling": ["tight continuous scenes", "summary that skips ahead", "lingering on single moments"],
}


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
    economy: str = Field(
        description="How much language the narration gives each moment, in a few words: anywhere from clipped and to the "
        "point to full and expansive. This is about quantity, not the kind of words."
    )
    diction: str = Field(
        description="How plain or elaborate the words are, in a few words: everyday words anyone follows at once at one "
        "end, literary, technical, archaic, street or ornate words at the other. Say whether fancy or obscure words are "
        "welcome or kept out."
    )
    figurative: str = Field(
        description="How much metaphor and simile the narration uses and what they are drawn from. Say literal if it "
        "uses none."
    )
    cadence: str = Field(
        description="How the sentences move, described by feel and not by a formula: short and chopped or long and "
        "looping, plain statements set side by side or clauses nested inside clauses (staccato, rolling, breathless, "
        "deliberate, or a stated mix)."
    )
    interiority: str = Field(
        description="How far the narration goes inside the main character's mind: only actions and objects, filtered "
        "thought, open feeling, or stream of thought."
    )
    humor: str = Field(
        description="Whether and how comedy works in the narration (none, dry, absurd, gallows, light)."
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
