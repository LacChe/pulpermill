from __future__ import annotations

import re
from pydantic import BaseModel

from .characters import CharacterCard
from .common import M, _CJK_RE, _related, est_words, squash
from .outline import LAST_STAGE, PlotOutline
from .story import StoryProject
from .style import StyleCard
from .world import WorldBible


# ===========================================================================
# VALIDATION (looks backward only; run before the human reviews anything)
# ===========================================================================


def check_style(style: StyleCard, cast_names: list[str]) -> list[str]:
    """Style must be story-agnostic: no character names."""
    text = style.model_dump_json().lower()
    out = []
    for name in cast_names:
        for part in {name.lower(), *name.lower().split()}:
            if _CJK_RE.search(part):
                hit = len(part) >= 2 and part in text
            else:
                hit = len(part) > 2 and re.search(rf"\b{re.escape(part)}\b", text)
            if hit:
                out.append(M("style mentions character name '{name}'", name=part))
    return out


def check_characters(chars: list[CharacterCard], world_ids: set[str]) -> list[str]:
    out = []
    ids = {c.id for c in chars}
    for c in chars:
        core = c.model_dump(exclude={"wrap", "id"})
        blob = str(core).lower()
        for wid in world_ids:
            if wid.lower() in blob:
                out.append(M("{id}: core mentions world id '{wid}'", id=c.id, wid=wid))
        for a in c.toward:
            if a.toward not in ids:
                out.append(
                    M("{id}: toward unknown character '{who}'", id=c.id, who=a.toward)
                )
        n_words = est_words(c.role)
        if n_words <= 1:
            out.append(
                (
                    M(
                        "{id}: role is empty. Say what this person is and does in this story; a bare title leaves the model to fill in its own idea of it",
                        id=c.id,
                    )
                    if n_words == 0
                    else M(
                        "{id}: role is one word ('{role}'). Say what this person is and does in this story; a bare title leaves the model to fill in its own idea of it",
                        id=c.id,
                        role=c.role,
                    )
                ).on("characters.role", c.id, c.role)
            )
    seen: dict[str, tuple[str, str]] = {}
    for c in chars:
        for line in c.sample_lines:
            key = squash(line)
            if key and seen.setdefault(key, (c.id, line))[0] != c.id:
                other_id, other_line = seen[key]
                out.append(
                    M(
                        "{a} and {b} have the same sample line: '{line}'",
                        a=c.id,
                        b=other_id,
                        line=line[:60],
                    )
                    .on("characters.sample_lines", c.id, line)
                    .on("characters.sample_lines", other_id, other_line)
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
    given = [b.stage for b in ordered]
    if any(x is not None for x in given):
        if any(x is None for x in given):
            m = M("some chapters have no story stage (1-6); set one on every chapter")
            for b in ordered:
                if b.stage is None:
                    m.on("outline.chapter_beats.stage", b.chapter_num, None)
            out.append(m)
        elif any(a > b for a, b in zip(given, given[1:])):
            m = M(
                "story stages go backwards between chapters: {stages}",
                stages=", ".join(map(str, given)),
            )
            for prev, b in zip(ordered, ordered[1:]):
                if prev.stage > b.stage:
                    m.on("outline.chapter_beats.stage", b.chapter_num, b.stage)
            out.append(m)
        elif given[-1] != LAST_STAGE and len(ordered) >= plot.total_chapters:
            out.append(
                M(
                    "the last chapter should be story stage {last} (Aftermath), not {got}",
                    last=LAST_STAGE,
                    got=given[-1],
                ).on("outline.chapter_beats.stage", ordered[-1].chapter_num, given[-1])
            )
    revealed: dict[str, list[int]] = {}
    for b in beats:
        n = b.chapter_num
        if b.location not in locs:
            out.append(M("ch{n}: unknown location '{where}'", n=n, where=b.location))
        for cid in [*b.present, *[s.character for s in b.shifts]]:
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
