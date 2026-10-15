from __future__ import annotations

import difflib
from pydantic import BaseModel, Field
from typing import Optional

from .common import (
    M,
    Resolver,
    logger,
    squash,
)
from .story import StoryProject


# ===========================================================================
# STATE UPDATE (written after each chapter)
# ===========================================================================


class ObjectMove(BaseModel):
    object: str = Field(description="Existing object id, or its name.")
    new_owner: Optional[str] = Field(
        default=None,
        description="Character id or name, 'none' to clear, or null for no change.",
    )
    new_location: Optional[str] = Field(
        default=None,
        description="Location id or name, 'none' to clear, or null for no change.",
    )


class PlaceUpdate(BaseModel):
    place: str = Field(description="Existing location id.")
    description: str = Field(
        description="The place as it is now, if this chapter physically changed it (damaged, rebuilt, "
        "emptied, taken over, closed): its description with the change folded in, one or two sentences."
    )


class ThingUpdate(BaseModel):
    object: str = Field(description="Existing object id.")
    description: str = Field(
        description="The object as it is now, if this chapter changed what it is or its condition "
        "(broken, opened, emptied, used up): its description with the change folded in, one or two sentences."
    )


class GroupUpdate(BaseModel):
    group: str = Field(description="Existing group id.")
    description: Optional[str] = Field(
        default=None,
        description="The group as it is now, only if this chapter changed what it is or "
        "who is in it. Otherwise empty.",
    )
    wants: Optional[str] = Field(
        default=None,
        description="What the group now wants, only if this chapter changed it. Otherwise empty.",
    )


class UnintroducedCharacter(BaseModel):
    name_mentioned: str
    role_hint: str


class StateUpdate(BaseModel):
    object_moves: list[ObjectMove] = Field(default_factory=list)
    location_updates: list[PlaceUpdate] = Field(default_factory=list)
    object_updates: list[ThingUpdate] = Field(default_factory=list)
    group_updates: list[GroupUpdate] = Field(default_factory=list)
    unintroduced_characters: list[UnintroducedCharacter] = Field(default_factory=list)


def apply_state_update(
    project: StoryProject, upd: StateUpdate, chapter_num: int
) -> tuple[list[str], list[dict]]:
    """
    Apply a StateUpdate and the chapter's revealed truths to the live state. Only the world follows the story: an
    object's owner and location, who knows a hidden truth, and the descriptions of places, objects and groups.
    Character cards are never touched: what a chapter did to a person is carried by the chapter summaries.
    Returns (warnings, changes): warnings for anything skipped, and one structured entry for every value that
    ACTUALLY changed (nothing is recorded when the new value equals the old one).

    Each change is a dict: kind, target (id), target_name, field, before, after, text (readable).
    """
    w = project.world
    warn: list[str] = []
    changes: list[dict] = []
    ch = f"Chapter {chapter_num}:"
    people = Resolver([{"id": c.id, "name": c.name} for c in project.characters])
    things = Resolver([{"id": o.id, "name": o.name} for o in w.objects])
    places = Resolver([{"id": l.id, "name": l.name} for l in w.locations])
    cast = {c.id for c in project.characters}
    objs = {o.id: o for o in w.objects}
    locs = {l.id: l.name for l in w.locations}
    truths = {t.id: t for t in w.hidden_truths}
    groups = Resolver([{"id": g.id, "name": g.name} for g in w.groups])

    def really_new(new, old) -> bool:
        """Is `new` a different statement from `old`, not the same one reworded? (A rewritten text that keeps nearly every
        word is the same thing.)"""
        n, o = squash(new or ""), squash(old or "")
        return bool(n) and n != o and difflib.SequenceMatcher(None, n, o).ratio() < 0.9

    def clear_or(v, res, kind, label):
        if v is None:
            return "keep"
        if v.lower() == "none":
            return None
        r = res.find(v)
        if r is None:
            warn.append(
                M("{label}: unknown {kind} '{value}'", label=label, kind=kind, value=v)
            )
            return "keep"
        return r

    def who(cid):
        return project.name_of(cid) if cid else M("nobody")

    for m in upd.object_moves:
        o = objs.get(things.find(m.object) or "")
        if o is None:
            warn.append(M("object_moves: unknown object '{obj}'", obj=m.object))
            continue
        mv = M("move {obj}", obj=m.object)
        ow = clear_or(m.new_owner, people, M("character"), mv)
        lo = clear_or(m.new_location, places, M("location"), mv)
        if ow != "keep" and ow != o.owner:
            text = (
                M("{obj} is no longer held by {was}", obj=o.name, was=who(o.owner))
                if ow is None
                else M(
                    "{obj} is now held by {who} (was {was})",
                    obj=o.name,
                    who=who(ow),
                    was=who(o.owner),
                )
                if o.owner
                else M("{obj} is now held by {who}", obj=o.name, who=who(ow))
            )
            changes.append(
                dict(
                    kind="object_owner",
                    target=o.id,
                    target_name=o.name,
                    field="owner",
                    before=o.owner,
                    after=ow,
                    text=text,
                )
            )
            o.owner = ow
        if lo != "keep" and lo != o.location:
            text = (
                M(
                    "{obj} is no longer at {was}",
                    obj=o.name,
                    was=locs.get(o.location, o.location),
                )
                if lo is None
                else M(
                    "{obj} is now at {where} (was {was})",
                    obj=o.name,
                    where=locs[lo],
                    was=locs.get(o.location, o.location),
                )
                if o.location
                else M("{obj} is now at {where}", obj=o.name, where=locs[lo])
            )
            changes.append(
                dict(
                    kind="object_location",
                    target=o.id,
                    target_name=o.name,
                    field="location",
                    before=o.location,
                    after=lo,
                    text=text,
                )
            )
            o.location = lo
        logger.info(
            "%s object moved: %s (owner=%s, location=%s)", ch, o.id, o.owner, o.location
        )

    beat = project.beat_for(chapter_num)
    for tid in beat.reveals:
        tr = truths.get(tid)
        if tr is None:
            warn.append(M("reveals: unknown truth '{truth}'", truth=tid))
            continue
        for cid in beat.present:
            if cid in cast and cid not in tr.known_by:
                tr.known_by.append(cid)
                changes.append(
                    dict(
                        kind="truth_known",
                        target=tr.id,
                        target_name=tr.fact,
                        field="known_by",
                        before=None,
                        after=cid,
                        text=M("{who} now knows: {fact}", who=who(cid), fact=tr.fact),
                    )
                )
                logger.info("%s %s now knows %s", ch, cid, tr.id)

    for kind, items, res, store, label_tpl in (
        (
            "location",
            upd.location_updates,
            places,
            {l.id: l for l in w.locations},
            None,
        ),
        ("object", upd.object_updates, things, objs, None),
    ):
        for u in items:
            key = u.place if kind == "location" else u.object
            target = store.get(res.find(key) or "")
            if target is None:
                warn.append(
                    M("location_updates: unknown location '{place}'", place=key)
                    if kind == "location"
                    else M("object_updates: unknown object '{obj}'", obj=key)
                )
                continue
            new = (u.description or "").strip()
            if really_new(new, target.description):
                changes.append(
                    dict(
                        kind=f"{kind}_description",
                        target=target.id,
                        target_name=target.name,
                        field="description",
                        before=target.description,
                        after=new,
                        text=M("{name} changed: {text}", name=target.name, text=new),
                    )
                )
                target.description = new
    gstore = {g.id: g for g in w.groups}
    for u in upd.group_updates:
        g = gstore.get(groups.find(u.group) or "")
        if g is None:
            warn.append(M("group_updates: unknown group '{group}'", group=u.group))
            continue
        new = (u.description or "").strip()
        if really_new(new, g.description):
            changes.append(
                dict(
                    kind="group_description",
                    target=g.id,
                    target_name=g.name,
                    field="description",
                    before=g.description,
                    after=new,
                    text=M("{name} changed: {text}", name=g.name, text=new),
                )
            )
            g.description = new
        new = (u.wants or "").strip()
        if really_new(new, g.wants):
            changes.append(
                dict(
                    kind="group_wants",
                    target=g.id,
                    target_name=g.name,
                    field="wants",
                    before=g.wants,
                    after=new,
                    text=M("{name} now wants: {text}", name=g.name, text=new),
                )
            )
            g.wants = new

    for u in upd.unintroduced_characters:
        logger.info(
            "%s new character mentioned, may need a card: %s (%s)",
            ch,
            u.name_mentioned,
            u.role_hint,
        )
    for msg in warn:
        logger.warning("%s skipped: %s", ch, msg)
    return warn, changes
