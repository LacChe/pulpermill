from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator

from .common import UsesMap, _pooled, clean_uses


# ===========================================================================
# STYLE
# ===========================================================================

class POV(str, Enum):
    first_person = "first_person"
    third_limited = "third_limited"        # the only third person: the story stays with its one main character


class Tense(str, Enum):
    past = "past"
    present = "present"


class StyleCard(BaseModel):
    label: str = Field(description="A short name for this style, two to four words, naming the genre flavor.")
    pov: POV = Field(description="The person the whole story is told in: first_person or third_limited. It never changes, "
                                 "and the story is always told from its one main character's side.")
    tense: Tense

    @model_validator(mode="before")
    @classmethod
    def _drop_old_chapter_shape(cls, data):     # the old single `chapter_shape` text applied to every chapter alike; it is gone
        if isinstance(data, dict) and "chapter_shape" in data:
            data = {k: v for k, v in data.items() if k != "chapter_shape"}
        return data

    @field_validator("pov", mode="before")
    @classmethod
    def _only_two_persons(cls, v):           # older cards may say omniscient; the story now always stays with one person
        return POV.third_limited if v in ("third_omniscient", "third_person") else v
    voice: str = Field(
        description="Three or four sentences on how the narrator sounds and how its humor, tension, or "
        "sentiment works. Describe the narration only. Leave out names, plot, and anything that belongs to one story."
    )
    prose_habits: list[str] = Field(
        description="Four to six concrete rules a reader could check on the page: sentence length, dialogue tags, "
        "type of imagery, pacing. Each rule should hold for any story in this genre."
    )
    avoid: list[str] = Field(
        description="Five to eight writing habits this style must never show. Name each habit plainly."
    )
    chapter_shapes: list[str] = Field(
        default_factory=list,
        description="Zero to six chapter shapes. Each shape is one short instruction for how a single chapter is built: how it "
        "opens, how it closes, and the balance of dialogue and narration. The shapes differ clearly from one another and describe "
        "structure only, never plot. Leave the list empty when no shape was asked for."
    )
    exemplars: list[str] = Field(
        description="Two or three short passages in this style about ordinary, unrelated everyday situations. "
        "No proper nouns. The passages show rhythm and tone only."
    )
    uses: UsesMap = Field(default_factory=dict)

    @model_validator(mode="after")
    def _tidy_uses(self):
        self.uses = clean_uses(self.uses, _pooled("style", {"exemplars": self.exemplars}))
        return self
