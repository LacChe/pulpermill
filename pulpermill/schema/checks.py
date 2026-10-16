from __future__ import annotations

import re
from pydantic import BaseModel

from .characters import PORTRAIT_FIELDS, CharacterCard
from .common import M, _CJK_RE, _TITLES, _related, est_words, similar
from .outline import PlotOutline
from .story import StoryProject
from .style import StyleCard
from .world import WORLD_TARGETS, WorldBible


# ===========================================================================
# VALIDATION (looks backward only; run before the human reviews anything)
# ===========================================================================


# Dial settings that pull against each other when one narrator is meant to use both: (field, test, field, test, message).
# A flag, never a rejection: the author may want the tension, and the narrator paragraph is where it is reconciled.
_DIAL_CONFLICTS = [
    ("economy", lambda n: n <= 2, "figurative", lambda n: n >= 5, "style dials pull against each other: clipped economy with rich figurative language"),
    ("economy", lambda n: n <= 2, "diction", lambda n: n >= 5, "style dials pull against each other: clipped economy with ornate diction"),
    ("economy", lambda n: n >= 5, "interiority", lambda n: n <= 1, "style dials pull against each other: expansive economy with purely behaviorist interiority"),
    ("diction", lambda n: n <= 1, "figurative", lambda n: n >= 5, "style dials pull against each other: plain diction with rich figurative language"),
    ("interiority", lambda n: n <= 1, "humor", lambda n: n >= 5, "style dials pull against each other: purely behaviorist interiority with pervasive humor"),
]


def check_style_dials(style: StyleCard) -> list[str]:
    """Light coherence check: flags dial levels that oppose each other."""
    out = []
    for fa, ta, fb, tb, what in _DIAL_CONFLICTS:
        if ta(getattr(style, fa).level) and tb(getattr(style, fb).level):
            out.append(M(what))
    return out


def check_style(style: StyleCard, cast_names: list[str]) -> list[str]:
    """Style must be story-agnostic: no character names. Also flags dials that conflict."""
    text = style.model_dump_json().lower()
    out = check_style_dials(style)
    for name in cast_names:
        for part in {name.lower(), *name.lower().split()}:
            if _CJK_RE.search(part):
                hit = len(part) >= 2 and part in text
            else:
                hit = len(part) > 2 and re.search(rf"\b{re.escape(part)}\b", text)
            if hit:
                out.append(M("style mentions character name '{name}'", name=part))
    return out


THIN_FIELD_WORDS = 4  # a portrait field shorter than this is a label, not a sentence about the person

# The fields that should differ from one character to the next: no two characters share a drive, a defense, a tell or a manner of speaking.
_DISTINCT_FIELDS = (
    "want",
    "wound",
    "armor",
    "tell",
    "with_people",
    "soft_spot",
    "limits",
    "blind_spot",
    "voice",
)


def _name_forms(name: str) -> set[str]:
    """The ways a person's name can turn up in another card's text: the whole name, and each word of it that is not a title
    or an article. Matched with the capital letters as written, so that a name like Mark is not found in 'a mark'."""
    name = name.strip()
    forms = {name} if name else set()
    for w in re.findall(r"[^\W_]+", name):
        if not _CJK_RE.search(w) and len(w) > 2 and w.lower() not in _TITLES:
            forms.add(w)
    return forms


def _text_has(form: str, text: str) -> bool:
    if _CJK_RE.search(form):
        return len(form) >= 2 and form in text
    return re.search(rf"\b{re.escape(form)}\b", text) is not None


def check_characters(chars: list[CharacterCard], world_ids: set[str]) -> list[str]:
    out = []
    for c in chars:
        blob = str(c.model_dump(exclude={"id"})).lower()
        for wid in world_ids:
            if wid.lower() in blob:
                out.append(M("{id}: core mentions world id '{wid}'", id=c.id, wid=wid))
        for field in PORTRAIT_FIELDS:
            value = getattr(c, field)
            n_words = est_words(value)
            if n_words == 0:
                out.append(
                    M(
                        "{id}: {field} is empty. Write it as one or two sentences about this person, so the writer is not left to invent it",
                        id=c.id,
                        field=field,
                    ).on(f"characters.{field}", c.id, value)
                )
            elif n_words < THIN_FIELD_WORDS:
                out.append(
                    M(
                        "{id}: {field} is only a few words ('{value}'). Write it as one or two full sentences about this person, not a label",
                        id=c.id,
                        field=field,
                        value=value[:60],
                    ).on(f"characters.{field}", c.id, value)
                )
        for other in chars:
            if other.id == c.id:
                continue
            forms = _name_forms(other.name)
            for field in PORTRAIT_FIELDS:
                value = getattr(c, field)
                hit = next((f for f in sorted(forms) if _text_has(f, value)), None)
                if hit:
                    out.append(
                        M(
                            "{id}: {field} names another character ('{who}'). A card should hold up in any story, so write it without other people's names",
                            id=c.id,
                            field=field,
                            who=hit,
                        ).on(f"characters.{field}", c.id, value)
                    )
                    break  # one note for each person named, however many fields name them
    for field in _DISTINCT_FIELDS:
        for i, a in enumerate(chars):
            for b in chars[i + 1 :]:
                va, vb = getattr(a, field), getattr(b, field)
                if similar(va, vb):
                    out.append(
                        M(
                            "{a} and {b} have nearly the same {field}; no two characters should share one",
                            a=a.id,
                            b=b.id,
                            field=field,
                        )
                        .on(f"characters.{field}", a.id, va)
                        .on(f"characters.{field}", b.id, vb)
                    )
    return out


def check_world(world: WorldBible, cast: set[str]) -> list[str]:
    out = []
    locs = {l.id for l in world.locations}
    for o in world.objects:
        if o.owner and o.owner not in cast:
            out.append(M("object {id}: unknown owner '{who}'", id=o.id, who=o.owner))
        if o.location and o.location not in locs:
            out.append(
                M("object {id}: unknown location '{where}'", id=o.id, where=o.location)
            )
    for t in world.hidden_truths:
        for k in t.known_by:
            if k not in cast:
                out.append(M("{id}: unknown known_by '{who}'", id=t.id, who=k))
        if not t.stake.strip():
            out.append(
                M(
                    "{id}: the stake is empty. Say who is guarding this secret and what exposure would cost",
                    id=t.id,
                ).on("world.hidden_truths.stake", t.id, t.stake)
            )
    if not world.pressure.strip():
        out.append(
            M(
                "The world has no pressure. Say in a sentence or two what living here costs, and who feels it"
            ).on("world.pressure", None, world.pressure)
        )
    if not world.locations:
        out.append(
            M("The world has no places. The outline needs at least one location").on(
                "world.locations", None, []
            )
        )
    for field, (_, hi) in WORLD_TARGETS.items():
        n = len(getattr(world, field))
        if n > hi:
            out.append(
                M(
                    "The world has {n} {field}; about {hi} is the most the writer can keep in view, so anything more is better left to the scene",
                    n=n,
                    field=field.replace("_", " "),
                    hi=hi,
                )
            )
    return out


def check_outline(plot: PlotOutline, cast: set[str], world: WorldBible) -> list[str]:
    out = []
    if plot.protagonist not in cast:
        out.append(
            M("the main character '{who}' is not in the cast", who=plot.protagonist)
        )
    locs = {l.id for l in world.locations}
    truth_ids = {t.id for t in world.hidden_truths}
    beats = plot.chapter_beats
    nums = sorted(b.chapter_num for b in beats)
    if len(nums) > plot.total_chapters:
        out.append(
            M(
                "the setup has {n} chapter beats but the story has {total} chapters",
                n=len(nums),
                total=plot.total_chapters,
            )
        )
    if nums != list(range(1, len(nums) + 1)):
        out.append(
            M(
                "chapter numbers are not 1..{n} in sequence: {nums}",
                n=len(nums),
                nums=str(nums),
            )
        )
    for a in plot.arcs:
        if a.character not in cast:
            out.append(M("arc: unknown character '{who}'", who=a.character))
    ordered = sorted(beats, key=lambda b: b.chapter_num)
    if not plot.opposition.strip():
        out.append(
            M("the setup has no opposition: who or what stands against the main character").on(
                "outline.opposition", None, ""
            )
        )
    if not plot.shape.strip():
        out.append(
            M("the setup has no shape: where hope, the low point and the peak fall").on(
                "outline.shape", None, ""
            )
        )
    for r in plot.relationships:
        for who in (r.a, r.b):
            if who not in cast:
                out.append(M("relationship: unknown character '{who}'", who=who))
        if r.a == r.b:
            out.append(
                M("relationship: '{who}' is paired with themselves", who=r.a)
            )
    dirs = [b.direction.value for b in ordered]
    for i in range(2, len(ordered)):
        run = dirs[i - 2 : i + 1]
        if run[0] != "mixed" and run[0] == run[1] == run[2]:
            out.append(
                M(
                    "chapters {a} to {b} all leave the main character better off; a story that only climbs reads flat"
                    if run[0] == "better"
                    else "chapters {a} to {b} all leave the main character worse off; a story that only falls reads flat",
                    a=ordered[i - 2].chapter_num,
                    b=ordered[i].chapter_num,
                ).on(
                    "outline.chapter_beats.direction",
                    ordered[i].chapter_num,
                    run[0],
                )
            )
    revealed: dict[str, list[int]] = {}
    for b in beats:
        n = b.chapter_num
        if b.location not in locs:
            out.append(M("ch{n}: unknown location '{where}'", n=n, where=b.location))
        for cid in [*b.present, *[a.character for a in b.agendas]]:
            if cid not in cast:
                out.append(M("ch{n}: unknown character '{who}'", n=n, who=cid))
        if plot.protagonist not in b.present:
            out.append(
                M(
                    "ch{n}: the main character '{who}' is not in present",
                    n=n,
                    who=plot.protagonist,
                ).on("outline.chapter_beats.present", n, plot.protagonist, "lacks")
            )
        for r in b.reveals:
            if r not in truth_ids:
                out.append(M("ch{n}: reveals unknown truth '{truth}'", n=n, truth=r))
            else:
                revealed.setdefault(r, []).append(n)
    for tid, where in revealed.items():
        if len(where) > 1:
            m = M(
                "{truth} is revealed in chapters {where}; reveal each hidden truth once",
                truth=tid,
                where=", ".join(map(str, where)),
            )
            for n in where[
                1:
            ]:  # the first reveal is the right one; the later ones are the problem
                m.on("outline.chapter_beats.reveals", n, tid)
            out.append(m)
    # payoffs: one note, so a human sees the pattern rather than a wall of warnings. A plant nobody has used yet is not a
    # problem: later beats are not written yet, and not every plant has to be paid off.
    orphan, orphan_at = [], []
    for b in beats:
        earlier = [
            pl for c in beats if c.chapter_num < b.chapter_num for pl in c.plants
        ]
        for p in b.pays_off:
            if not any(_related(p, pl) for pl in earlier):
                orphan.append(M("chapter {n} ('{text}')", n=b.chapter_num, text=p[:50]))
                orphan_at.append((b.chapter_num, p))
    if orphan:
        m = M(
            "payoffs with no earlier plant: {items}. Plant them earlier or remove them",
            items="; ".join(orphan),
        )
        for n, text in orphan_at:
            m.on("outline.chapter_beats.pays_off", n, text)
        out.append(m)
    return out


def check_markdown_leak(obj: BaseModel) -> list[str]:
    return (
        [M("stray markdown asterisks in output")]
        if "*" in obj.model_dump_json()
        else []
    )


def validate_project(p: StoryProject) -> list[str]:
    cast = {c.id for c in p.characters}
    world_ids = {l.id for l in p.world.locations} | {o.id for o in p.world.objects}
    return (
        check_style(p.style, [c.name for c in p.characters])
        + check_characters(p.characters, world_ids)
        + check_world(p.world, cast)
        + check_outline(p.plot, cast, p.world)
        + check_markdown_leak(p)
    )
