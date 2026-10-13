from __future__ import annotations

import difflib
from pydantic import BaseModel, Field
from typing import Optional

from .common import (
    M,
    MAX_HABITS,
    Resolver,
    SAME_CHARACTER_SIMILARITY,
    _pooled,
    clean_uses,
    logger,
    push_recent,
    similar,
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


class CharacterUpdate(BaseModel):
    character: str = Field(description="Character id.")
    condition: Optional[str] = Field(
        default=None,
        description="Their emotional and physical condition at the end of the chapter, in one short sentence.",
    )
    change: Optional[str] = Field(
        default=None,
        description="A turning point for this character in this chapter: a lasting shift in how they behave or how they treat a "
        "specific person. One short sentence, a different kind of shift from every line already in their current state and "
        "from every other character's. Leave empty if nothing turned; most characters have none in most chapters.",
    )
    new_habit: Optional[str] = Field(
        default=None,
        description="A repeated behavior this chapter showed as a pattern, not a one-off action, that is not on their card. Otherwise empty.",
    )
    dropped_habit: Optional[str] = Field(
        default=None,
        description="A habit from their card, copied exactly, that they have clearly given up or can no longer keep. Otherwise empty.",
    )
    detail: Optional[str] = Field(
        default=None,
        description="A durable fact about this character shown for the first time in this chapter and not already on "
        "their card. Not actions or momentary feelings. Leave empty otherwise.",
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
    character_updates: list[CharacterUpdate] = Field(default_factory=list)
    location_updates: list[PlaceUpdate] = Field(default_factory=list)
    object_updates: list[ThingUpdate] = Field(default_factory=list)
    group_updates: list[GroupUpdate] = Field(default_factory=list)
    unintroduced_characters: list[UnintroducedCharacter] = Field(default_factory=list)


def apply_state_update(
    project: StoryProject, upd: StateUpdate, chapter_num: int
) -> tuple[list[str], list[dict]]:
    """
    Apply a StateUpdate and the chapter's revealed truths to the live state. A character's habits and the
    descriptions of places, objects and groups follow the story; want and blind_spot are authored personality
    traits and are never rewritten here -- a chapter's effect on them is recorded only as a `change` line in the
    wrap, same as any other turning point. Nothing else in the core is edited and nothing is added to the World.
    Returns (warnings, changes):
    warnings for anything skipped, and one structured entry for every value that
    ACTUALLY changed (nothing is recorded when the new value equals the old one).
    This is the ONE place the card rules are enforced at runtime: characters hold no
    world ids and wrap lists are trimmed to the most recent RECENT_N.

    Each change is a dict: kind, target (card id), target_name, field, before, after, text (readable),
    and `dropped` (wrap entries pushed out by the trim) where it applies.
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

    for cu in upd.character_updates:
        c = project.character_by_id(people.find(cu.character) or "")
        if c is None:
            warn.append(
                M("character_updates: unknown character '{who}'", who=cu.character)
            )
            continue
        gone = (cu.dropped_habit or "").strip()
        if gone:
            hit = next((h for h in c.habits if squash(h) == squash(gone)), None)
            if hit is None:
                warn.append(
                    M(
                        "{name}: the habit '{text}' is not on the card, so it was not dropped",
                        name=c.name,
                        text=gone[:50],
                    )
                )
            elif len(c.habits) > 1:
                c.habits = [h for h in c.habits if h != hit]
                changes.append(
                    dict(
                        kind="character_habit_dropped",
                        target=c.id,
                        target_name=c.name,
                        field="habits",
                        before=hit,
                        after=None,
                        text=M("{name} dropped a habit: {text}", name=c.name, text=hit),
                    )
                )
        fresh = (cu.new_habit or "").strip()
        if fresh and not any(
            squash(h) == squash(fresh) or similar(h, fresh) for h in c.habits
        ):
            c.habits = (c.habits + [fresh])[-MAX_HABITS:]
            changes.append(
                dict(
                    kind="character_habit_added",
                    target=c.id,
                    target_name=c.name,
                    field="habits",
                    before=None,
                    after=fresh,
                    text=M("{name} picked up a habit: {text}", name=c.name, text=fresh),
                )
            )
        if gone or fresh:
            c.uses = clean_uses(
                c.uses,
                _pooled(
                    "characters",
                    {
                        "look": c.look,
                        "habits": c.habits,
                        "sample_lines": c.sample_lines,
                    },
                ),
            )
        if cu.condition and cu.condition != c.wrap.condition:
            changes.append(
                dict(
                    kind="character_condition",
                    target=c.id,
                    target_name=c.name,
                    field="condition",
                    before=c.wrap.condition,
                    after=cu.condition,
                    text=M(
                        "{name}'s condition: {text}", name=c.name, text=cu.condition
                    ),
                )
            )
            c.wrap.condition = cu.condition
        for field, attr, label in (
            ("change", "recent_changes", "{name}, new lasting change: {text}"),
            ("detail", "recent_details", "{name}, new established detail: {text}"),
        ):
            new = getattr(cu, field)
            old = list(getattr(c.wrap, attr))
            if not new or new in old:  # nothing new, or already on the card
                continue
            if any(
                similar(new, x, SAME_CHARACTER_SIMILARITY)
                for x in old + c.wrap.recent_changes + c.wrap.recent_details
            ) or any(
                similar(new, x)
                for other in project.characters
                for x in other.wrap.recent_changes + other.wrap.recent_details
            ):
                logger.info(
                    "%s %s: dropped a %s that repeats an entry already on a card: %s",
                    ch,
                    c.name,
                    field,
                    new[:40],
                )
                continue  # models copy one character's entry onto another, or reword their own
            now = push_recent(old, new)
            dropped = [x for x in old if x not in now]
            setattr(c.wrap, attr, now)
            changes.append(
                dict(
                    kind=f"character_{field}",
                    target=c.id,
                    target_name=c.name,
                    field=attr,
                    before=old,
                    after=now,
                    dropped=dropped,
                    text=M(label, name=c.name, text=new),
                )
            )
        logger.info(
            "%s %s updated: condition=%s, change=%s, detail=%s",
            ch,
            c.name,
            cu.condition,
            cu.change,
            cu.detail,
        )

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
