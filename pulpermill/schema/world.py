from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Optional

from .common import M, Resolver, UsesMap, _as_dicts, _pooled, clean_uses, unique_ids


# ===========================================================================
# WORLD
# ===========================================================================

class LocationDraft(BaseModel):
    name: str
    description: str = Field(description="Two or three concrete sensory details of the place.")


class ObjectDraft(BaseModel):
    name: str
    description: str = Field(description="What it is and why it matters to the story.")
    owner: Optional[str] = Field(default=None, description="Name of the character who holds it now, exactly as in the cast, or null.")
    location: Optional[str] = Field(default=None, description="Name of the place it sits, or null.")


class GroupDraft(BaseModel):
    name: str
    description: str
    wants: str = Field(description="What the group wants, only if it affects the plot.")


class TruthDraft(BaseModel):
    fact: str = Field(
        description="A true thing about the story world that has not yet appeared on the page and should "
        "steer the story from behind the scenes."
    )
    known_by: list[str] = Field(default_factory=list, description="Names of the characters who already know it, exactly as in the cast.")


class WorldDraft(BaseModel):
    setting: str = Field(description="One paragraph on the time, the place, and what counts as normal there.")
    rules: list[str] = Field(
        description="Plain statements of how this world works: mechanics, laws, limits. State each as settled fact, "
        "with no instruction about tone or how to write it."
    )
    hidden_truths: list[TruthDraft] = Field(default_factory=list)
    locations: list[LocationDraft]
    objects: list[ObjectDraft] = Field(default_factory=list)
    groups: list[GroupDraft] = Field(default_factory=list)


class Location(BaseModel):
    id: str
    name: str
    description: str


class WorldObject(BaseModel):
    id: str
    name: str
    description: str
    owner: Optional[str] = None          # LIVE: character id
    location: Optional[str] = None       # LIVE: location id


class Group(BaseModel):
    id: str
    name: str
    description: str
    wants: str = ""


class HiddenTruth(BaseModel):
    id: str
    fact: str
    known_by: list[str] = Field(default_factory=list)   # LIVE: character ids


class WorldBible(BaseModel):
    setting: str
    rules: list[str]
    hidden_truths: list[HiddenTruth] = Field(default_factory=list)
    locations: list[Location]
    objects: list[WorldObject] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)
    uses: UsesMap = Field(default_factory=dict)

    @model_validator(mode="after")
    def _tidy_uses(self):
        self.uses = clean_uses(self.uses, _pooled("world", {"locations": [x.id for x in self.locations],
                                                            "objects": [x.id for x in self.objects],
                                                            "groups": [x.id for x in self.groups]}))
        return self


def finalize_world(draft: WorldDraft, cast_ids: set[str], cast: Optional[list] = None,
                   notes: Optional[list[str]] = None) -> WorldBible:
    """
    Names to ids. `cast` is the list of cast cards (dicts with id and name) so owners and `known_by` can be written as names;
    without it only ids match. A reference that matches nobody is dropped (owner/location left empty, the person left out
    of known_by) and reported in `notes`; nothing here makes the model regenerate.
    """
    notes = notes if notes is not None else []
    people = Resolver(_as_dicts(cast) if cast else [{"id": i, "name": i} for i in sorted(cast_ids)])
    loc_ids = unique_ids([l.name for l in draft.locations], "loc_")
    places = Resolver([{"id": i, "name": l.name} for l, i in zip(draft.locations, loc_ids)])
    obj_ids = unique_ids([o.name for o in draft.objects], "obj_")
    objects = []
    for o, oid in zip(draft.objects, obj_ids):
        owner = None
        if o.owner is not None:
            owner = people.find(o.owner)
            if owner is None:
                notes.append(M("object '{obj}': the owner '{who}' is not in the cast, so its owner was left empty", obj=o.name, who=o.owner))
        lid = None
        if o.location is not None:
            lid = places.find(o.location)
            if lid is None:
                notes.append(M("object '{obj}': the place '{place}' is not one of your locations, so its location was left empty", obj=o.name, place=o.location))
        objects.append(WorldObject(id=oid, name=o.name, description=o.description, owner=owner, location=lid))
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
            notes.append(M("hidden truth {n}: {names} is not in the cast, so left out of who knows it", n=n, names=names) if len(lost) == 1 else
                         M("hidden truth {n}: {names} are not in the cast, so left out of who knows it", n=n, names=names))
        truths.append(HiddenTruth(id=f"truth_{n}", fact=t.fact, known_by=known))
    return WorldBible(
        setting=draft.setting,
        rules=draft.rules,
        hidden_truths=truths,
        locations=[Location(id=i, name=l.name, description=l.description) for l, i in zip(draft.locations, loc_ids)],
        objects=objects,
        groups=[Group(id=i, **g.model_dump()) for g, i in zip(draft.groups, unique_ids([g.name for g in draft.groups], "grp_"))],
    )
