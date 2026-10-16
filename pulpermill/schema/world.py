from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Optional

from .common import M, Resolver, UsesMap, _as_dicts, _pooled, clean_uses, unique_ids


# ===========================================================================
# WORLD
# ===========================================================================


# How many of each the prompt asks for. Guidance and soft warnings only: never a pydantic limit, so a hand-edited card
# with more or fewer still loads.
WORLD_TARGETS = {
    "rules": (3, 6),
    "locations": (3, 6),
    "objects": (2, 5),
    "groups": (1, 4),
    "hidden_truths": (2, 4),
}


class LocationDraft(BaseModel):
    name: str
    description: str = Field(
        description="What the place does to people: who belongs there and who does not, what is done or hidden there."
    )


class ObjectDraft(BaseModel):
    name: str
    description: str = Field(
        description="Why people want it, fear it, or have paid for it."
    )
    owner: Optional[str] = Field(
        default=None,
        description="Name of the character who holds it now, exactly as in the cast, or null.",
    )
    location: Optional[str] = Field(
        default=None, description="Name of the place it sits, or null."
    )


class GroupDraft(BaseModel):
    name: str
    description: str = Field(
        description="How the group is felt in daily life, by the people who live near it or under it."
    )
    wants: str = Field(description="What the group wants.")


class TruthDraft(BaseModel):
    fact: str = Field(
        description="A true thing about the world that has not yet appeared on the page and steers the story from behind the scenes."
    )
    stake: str = Field(
        description="Who is guarding it, and what exposure would cost them or others."
    )
    known_by: list[str] = Field(
        default_factory=list,
        description="Names of the characters who already know it, exactly as in the cast.",
    )


class WorldDraft(BaseModel):
    # Field order is the order the model writes them: the secrets come last so they can lean on everything before.
    setting: str = Field(
        description="Where and when, and what an ordinary day is like. It may carry one past event that people still live under."
    )
    pressure: str = Field(
        description="One or two sentences on what living here costs: what is scarce, forbidden or owed, and who feels it."
    )
    rules: list[str] = Field(
        description="Short statements of how this world works. Each gives a mechanic or custom and the price it puts on someone."
    )
    locations: list[LocationDraft]
    groups: list[GroupDraft] = Field(default_factory=list)
    objects: list[ObjectDraft] = Field(default_factory=list)
    hidden_truths: list[TruthDraft] = Field(default_factory=list)


class Location(BaseModel):
    id: str
    name: str
    description: str


class WorldObject(BaseModel):
    id: str
    name: str
    description: str
    owner: Optional[str] = None  # LIVE: character id
    location: Optional[str] = None  # LIVE: location id


class Group(BaseModel):
    id: str
    name: str
    description: str
    wants: str = ""


class HiddenTruth(BaseModel):
    id: str
    fact: str
    stake: str
    known_by: list[str] = Field(default_factory=list)  # LIVE: character ids


class WorldBible(BaseModel):
    setting: str
    pressure: str
    rules: list[str]
    hidden_truths: list[HiddenTruth] = Field(default_factory=list)
    locations: list[Location]
    objects: list[WorldObject] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)
    uses: UsesMap = Field(default_factory=dict)

    @model_validator(mode="after")
    def _tidy_uses(self):
        self.uses = clean_uses(
            self.uses,
            _pooled(
                "world",
                {
                    "locations": [x.id for x in self.locations],
                    "objects": [x.id for x in self.objects],
                    "groups": [x.id for x in self.groups],
                },
            ),
        )
        return self


def finalize_world(
    draft: WorldDraft,
    cast_ids: set[str],
    cast: Optional[list] = None,
    notes: Optional[list[str]] = None,
) -> WorldBible:
    """
    Names to ids. `cast` is the list of cast cards (dicts with id and name) so owners and `known_by` can be written as names;
    without it only ids match. A reference that matches nobody is dropped (owner/location left empty, the person left out
    of known_by) and reported in `notes`; nothing here makes the model regenerate.
    """
    notes = notes if notes is not None else []
    people = Resolver(
        _as_dicts(cast) if cast else [{"id": i, "name": i} for i in sorted(cast_ids)]
    )
    loc_ids = unique_ids([l.name for l in draft.locations], "loc_")
    places = Resolver(
        [{"id": i, "name": l.name} for l, i in zip(draft.locations, loc_ids)]
    )
    obj_ids = unique_ids([o.name for o in draft.objects], "obj_")
    objects = []
    for o, oid in zip(draft.objects, obj_ids):
        owner = None
        if o.owner is not None:
            owner = people.find(o.owner)
            if owner is None:
                notes.append(
                    M(
                        "object '{obj}': the owner '{who}' is not in the cast, so its owner was left empty",
                        obj=o.name,
                        who=o.owner,
                    )
                )
        lid = None
        if o.location is not None:
            lid = places.find(o.location)
            if lid is None:
                notes.append(
                    M(
                        "object '{obj}': the place '{place}' is not one of your locations, so its location was left empty",
                        obj=o.name,
                        place=o.location,
                    )
                )
        objects.append(
            WorldObject(
                id=oid,
                name=o.name,
                description=o.description,
                owner=owner,
                location=lid,
            )
        )
    truths = []
    for n, t in enumerate(draft.hidden_truths, 1):
        known, lost = [], []
        for k in t.known_by:
            r = people.find(k)
            if r is None:
                lost.append(k)
            elif r not in known:
                known.append(r)
        if lost:
            names = ", ".join(repr(x) for x in lost)
            notes.append(
                M(
                    "hidden truth {n}: {names} is not in the cast, so left out of who knows it",
                    n=n,
                    names=names,
                )
                if len(lost) == 1
                else M(
                    "hidden truth {n}: {names} are not in the cast, so left out of who knows it",
                    n=n,
                    names=names,
                )
            )
        truths.append(HiddenTruth(id=f"truth_{n}", fact=t.fact, stake=t.stake, known_by=known))
    return WorldBible(
        setting=draft.setting,
        pressure=draft.pressure,
        rules=draft.rules,
        hidden_truths=truths,
        locations=[
            Location(id=i, name=l.name, description=l.description)
            for l, i in zip(draft.locations, loc_ids)
        ],
        objects=objects,
        groups=[
            Group(id=i, **g.model_dump())
            for g, i in zip(
                draft.groups, unique_ids([g.name for g in draft.groups], "grp_")
            )
        ],
    )
