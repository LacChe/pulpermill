from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Optional

from .common import M, MAX_CHARACTERS, Recent, Resolver, UsesMap, _pooled, clean_uses, unique_ids


# ===========================================================================
# CHARACTERS
# ===========================================================================

class Attitude(BaseModel):
    toward: str = Field(description="The name of another character in the cast.")
    attitude: str = Field(
        description="One or two sentences, from this character's side only: what they want from that person "
        "and how they act around them."
    )


class CharacterDraft(BaseModel):
    """What the model writes. Core definition: does not change after review."""
    name: str
    role: str = Field(
        description="What this person is to the story, in the source's own words for their job or place. "
        "Never a title that belongs to someone else. Say what they do, not only a one-word title."
    )
    want: str = Field(
        description="A lasting personal drive -- the kind of thing they generally chase or need, as a standing "
        "trait, not a goal belonging to any one story. What they're after in this particular story lives in the "
        "outline and chapter beats, not here."
    )
    blind_spot: str = Field(
        description="State how they see themselves and the specific thing they do that contradicts it. "
        "A nervous tic is not a blind spot."
    )
    look: list[str] = Field(description="Two or three physical details a reader would notice.")
    habits: list[str] = Field(
        description="Two or three things they do repeatedly, especially when nervous, lying, or avoiding something."
    )
    voice: str = Field(
        description="How they talk: vocabulary, rhythm, what they never say. Different from the narrator's voice."
    )
    sample_lines: list[str] = Field(
        description="Two or three lines of dialogue showing how they talk, about situations outside this story. "
        "Never a line from the source, never a plot reveal."
    )
    history: str = Field(description="Two or three sentences of past events that still drive present behavior.")
    toward: list[Attitude] = Field(
        default_factory=list, description="One entry for each other main character this person has a stake in."
    )


class CastDraft(BaseModel):
    characters: list[CharacterDraft] = Field(
        min_length=2,
        max_length=MAX_CHARACTERS,
        description="The whole cast, written together. Compare them as you write: no two characters may share "
        "a want, a blind spot, a habit, or a manner of speaking.",
    )


class CharacterWrap(BaseModel):
    """Live state. Updated by Pulpermill after each chapter. Plain text only: no object or location ids."""
    condition: str = Field(default="", description="Current emotional and physical condition.")
    recent_changes: Recent = Field(
        default_factory=list, description="Latest shifts in what they want, how they act, or how they see someone."
    )
    recent_details: Recent = Field(
        default_factory=list, description="Latest newly established facts about them, including past events."
    )


class CharacterCard(CharacterDraft):
    id: str
    wrap: CharacterWrap = Field(default_factory=CharacterWrap)
    uses: UsesMap = Field(default_factory=dict)

    @model_validator(mode="after")
    def _tidy_uses(self):
        self.uses = clean_uses(self.uses, _pooled("characters", {"look": self.look, "habits": self.habits,
                                                                 "sample_lines": self.sample_lines}))
        return self


def finalize_cast(draft: CastDraft, notes: Optional[list[str]] = None) -> list[CharacterCard]:
    """Assign ids from names and rewrite `toward` from names to ids. A `toward` that names nobody in the cast is dropped
    and reported in `notes` (it is not worth regenerating the whole cast for)."""
    notes = notes if notes is not None else []
    ids = unique_ids([c.name for c in draft.characters])
    who = Resolver([{"id": i, "name": c.name} for c, i in zip(draft.characters, ids)])
    cards = []
    for c, cid in zip(draft.characters, ids):
        data = c.model_dump()
        resolved, seen = [], set()
        for a in data["toward"]:
            tid = who.find(a["toward"])
            if tid is None:
                notes.append(M("{name}: feelings toward '{other}' were dropped, because nobody in the cast has that name", name=c.name, other=a["toward"]))
            elif tid == cid:
                notes.append(M("{name}: an attitude toward themselves was dropped", name=c.name))
            elif tid not in seen:
                seen.add(tid)
                resolved.append({"toward": tid, "attitude": a["attitude"]})
        data["toward"] = resolved
        cards.append(CharacterCard(id=cid, **data))
    return cards
