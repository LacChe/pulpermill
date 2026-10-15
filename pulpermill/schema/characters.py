from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional

from .common import MAX_CHARACTERS, unique_ids


# ===========================================================================
# CHARACTERS
# A character is a portrait of a person that holds in any story: who they are, never what has happened to them.
# Pulpermill never edits a card after it is reviewed, so a card can be taken out of one project and dropped into another.
# ===========================================================================


# The prose fields in the order they are read: this is the order the writer is given them.
PORTRAIT_FIELDS = (
    "role",
    "want",
    "wound",
    "armor",
    "tell",
    "with_people",
    "soft_spot",
    "limits",
    "blind_spot",
    "voice",
    "presence",
)


class CharacterDraft(BaseModel):
    """One person, written as a portrait that would hold in any story. Every text field is plain prose: one or two full
    sentences in the third person, naming nothing that belongs to a single story (no plot, no places, no objects, no other
    characters), and reading naturally when the fields are joined in order."""

    name: str
    role: str = Field(
        description="How this person would be introduced to a stranger: the trade, station or bearing they would carry "
        "into any story. Never a one-word title, and nothing about what happens to them in this story."
    )
    want: str = Field(
        description="What they chase and what they are running from, as lasting traits of the person and not as a goal "
        "belonging to any one story. Name the fear underneath the want."
    )
    wound: str = Field(
        description="What happened to them long ago and the rule about the world it taught them, in setting-neutral "
        "terms: no named people, places or institutions."
    )
    armor: str = Field(
        description="Their default stance when cornered or threatened, and how they keep people at a distance: how they "
        "meet conflict, not what any particular conflict is."
    )
    tell: str = Field(
        description="What pressure does to their body: a repeated motion and the kind of thing they do it with, described "
        "so that any setting could supply the object. Never a named prop."
    )
    with_people: str = Field(
        description="How they handle other people and what people hold back: what they hide, how they dig for what others "
        "hide, and how they treat someone who can do nothing for them."
    )
    soft_spot: str = Field(
        description="What gets past the armor: what they love, what makes them laugh, and how they are when they stop "
        "defending themselves."
    )
    limits: str = Field(
        description="What they will never do, and what it would take to make them do it."
    )
    blind_spot: str = Field(
        description="How they see themselves, and the specific thing they do that contradicts it. "
        "A nervous tic is not a blind spot."
    )
    voice: str = Field(
        description="How they talk: vocabulary, rhythm, what they never say, with one or two lines of them speaking about "
        "something outside any story. Different from the narrator's voice. Never a line from the source."
    )
    presence: str = Field(
        description="How they carry themselves and take up space, with the one physical detail a person would remember."
    )


class CastDraft(BaseModel):
    characters: list[CharacterDraft] = Field(
        min_length=1,
        max_length=MAX_CHARACTERS,
        description="The whole cast, written together. Compare them as you write: no two characters may share "
        "a want, a blind spot, a tell, or a manner of speaking.",
    )


class CharacterCard(CharacterDraft):
    id: str


def finalize_cast(
    draft: CastDraft, notes: Optional[list[str]] = None
) -> list[CharacterCard]:
    """Assign ids from names. A character holds no reference to another card, so nothing else needs resolving. `notes` is
    not used any more; it stays in the signature only so the callers do not have to change yet."""
    ids = unique_ids([c.name for c in draft.characters])
    return [
        CharacterCard(id=cid, **c.model_dump())
        for c, cid in zip(draft.characters, ids)
    ]
