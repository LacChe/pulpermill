from __future__ import annotations

from pydantic import BaseModel, Field
from typing import ClassVar, Optional

from .characters import PORTRAIT_FIELDS, CharacterCard
from .common import M, POOLS, _beat_seq, _mentions, _related, _shown, pick_least_used
from .outline import (
    BEAT_CLASH,
    ChapterBeat,
    PlotOutline,
    beat_similarity,
    stage_lines_for,
)
from .style import DIAL_FIELDS, POV, StyleCard, ladder_text
from .world import WorldBible


# ===========================================================================
# PROJECT + CHAPTER CONTEXT
# ===========================================================================


class StoryProject(BaseModel):
    style: StyleCard
    characters: list[CharacterCard]
    world: WorldBible
    plot: PlotOutline
    roster: list[CharacterCard] = Field(
        default_factory=list, exclude=True
    )  # everyone in the project, when `characters` is only this chapter's cast

    def character_by_id(self, cid: str) -> Optional[CharacterCard]:
        return next((c for c in self.characters if c.id == cid), None)

    def name_of(self, cid: str) -> str:
        c = self.character_by_id(cid) or next(
            (x for x in self.roster if x.id == cid), None
        )
        return c.name if c else cid

    def with_cast(self, ids) -> "StoryProject":
        """The project as one chapter sees it: only these characters exist for the model (the writer, the reader of the chapter
        and the planner of the next beat), while the cards themselves are shared, so what the chapter changes lands on the
        full cards. Names of everyone else still resolve through `roster`."""
        keep = set(ids)
        return self.model_copy(
            update={
                "characters": [c for c in self.characters if c.id in keep],
                "roster": list(self.roster or self.characters),
            }
        )

    def beat_for(self, chapter_num: int) -> ChapterBeat:
        beat = next(
            (b for b in self.plot.chapter_beats if b.chapter_num == chapter_num), None
        )
        if beat is None:
            raise ValueError(M("no beat for chapter {n}", n=chapter_num))
        return beat

    def is_final_chapter(self, chapter_num: int) -> bool:
        return chapter_num == self.plot.total_chapters

    def unrevealed_truths(self, through: int) -> list:
        """The hidden truths no beat up to chapter `through` has revealed. Once a beat reveals one it is part of what
        happened, so it is not offered again."""
        done = {
            r
            for b in self.plot.chapter_beats
            if b.chapter_num <= through
            for r in b.reveals
        }
        return [t for t in self.world.hidden_truths if t.id not in done]

    def least_used(self, through: int, k: int = 3):
        """(places, people) that have been in the fewest beats up to chapter `through`: where and who the story has not
        been with lately. Ties keep card order. The main character is left out of the people (they are in every chapter)."""
        beats = [b for b in self.plot.chapter_beats if b.chapter_num <= through]
        seen_at = [b.location for b in beats]
        seen_who = [c for b in beats for c in b.present]
        places = sorted(self.world.locations, key=lambda l: seen_at.count(l.id))[:k]
        people = sorted(
            (c for c in self.characters if c.id != self.plot.protagonist),
            key=lambda c: seen_who.count(c.id),
        )[:k]
        return (
            [(l.name, seen_at.count(l.id)) for l in places],
            [(c.name, seen_who.count(c.id)) for c in people],
        )

    def least_used_world(self, through: int, k: int = 3):
        """(objects, groups) the story has made the least use of so far, the same idea as `least_used` but for cards
        that have no `present`-style field of their own: counted by whether each beat's own text (goal, events, ends_on,
        etc.) names them. Ties keep card order."""
        beats = [b for b in self.plot.chapter_beats if b.chapter_num <= through]
        seqs = [self._beat_seq(b.chapter_num) for b in beats]

        def tally(items):
            return sorted(
                items, key=lambda x: sum(1 for seq in seqs if _mentions(seq, x.name))
            )[:k]

        objects = tally(self.world.objects)
        groups = tally(self.world.groups)
        return (
            [
                (o.name, sum(1 for seq in seqs if _mentions(seq, o.name)))
                for o in objects
            ],
            [
                (g.name, sum(1 for seq in seqs if _mentions(seq, g.name)))
                for g in groups
            ],
        )

    def beat_clash(self, beat: "ChapterBeat"):
        """(chapter number, similarity) of the earlier beat this one repeats most, or None if it is new enough."""
        best = max(
            (
                (b.chapter_num, beat_similarity(beat, b))
                for b in self.plot.chapter_beats
                if b.chapter_num < beat.chapter_num
            ),
            key=lambda x: x[1],
            default=None,
        )
        return best if best and best[1] >= BEAT_CLASH else None

    def open_plants(self, through: int) -> list[str]:
        """Plants from the beats up to chapter `through` that no beat has paid off yet, in the order they were planted.
        A plant that has been paid off is part of what happened and is not offered again."""
        beats = [b for b in self.plot.chapter_beats if b.chapter_num <= through]
        paid = [p for b in beats for p in b.pays_off]
        return [
            pl
            for b in beats
            for pl in b.plants
            if not any(_related(pl, p) for p in paid)
        ]

    # ------------------------------------------------------------------ writer-facing text
    # The writer gets labeled text, not JSON. Every field is shown with a short note on what it is for, empty
    # fields are left out, and ids never appear (the extractor, which needs ids, builds its own text).

    # ------------------------------------------------------------------ rotating lists (see POOLS)
    def _beat_seq(self, chapter_num: int) -> list[str]:
        """The words of everything this chapter's own beat says (not the next chapter's, which the writer must not start)."""
        b = self.beat_for(chapter_num)
        parts = [
            b.when,
            b.goal,
            b.obstacle,
            b.ends_on,
            b.tone or "",
            *b.events,
            *b.plants,
            *b.pays_off,
            *(sh.movement for sh in b.shifts),
        ]
        return _beat_seq("\n".join(parts))

    def feed(self, chapter_num: int) -> dict:
        """What the writer is handed from the rotating lists for this chapter, as item keys (text, or id for places, objects
        and groups): {"style": {field: [...]}, "world": {field: [...]}}. A list that is not rotating is simply absent, and
        the writer gets it whole. Characters have no rotating lists: a portrait is always given whole."""
        b = self.beat_for(chapter_num)
        seq = self._beat_seq(chapter_num)
        out: dict = {"style": {}, "world": {}}

        def pick(owner, card, field, keys, required=()):
            k = POOLS.get(f"{card}.{field}")
            return (
                None
                if k is None
                else pick_least_used(keys, owner.uses.get(field, {}), k, required)
            )

        for f, keys in (("exemplars", self.style.exemplars),):
            if (ch := pick(self.style, "style", f, keys)) is not None:
                out["style"][f] = ch
        w, here = self.world, set(b.present)
        need = {
            "locations": {
                x.id
                for x in w.locations
                if x.id == b.location or _mentions(seq, x.name)
            },
            "objects": {
                x.id
                for x in w.objects
                if x.owner in here or x.location == b.location or _mentions(seq, x.name)
            },
            "groups": {x.id for x in w.groups if _mentions(seq, x.name)},
        }
        for f in ("locations", "objects", "groups"):
            if (
                ch := pick(w, "world", f, [x.id for x in getattr(w, f)], need[f])
            ) is not None:
                out["world"][f] = ch
        return out

    def record_feed(self, feed: dict) -> None:
        """Count one more use for everything the writer was handed."""

        def bump(owner, field, keys):
            if not keys:
                return
            row = owner.uses.setdefault(field, {})
            for k in keys:
                row[k] = row.get(k, 0) + 1

        for f, keys in feed.get("style", {}).items():
            bump(self.style, f, keys)
        for f, keys in feed.get("world", {}).items():
            bump(self.world, f, keys)

    def narration_rule(self, b: ChapterBeat) -> str:
        """Person and tense come from the style card, and the narrator is always the story's one main character."""
        name = self.name_of(self.plot.protagonist)
        tense = self.style.tense.value
        if self.style.pov == POV.first_person:
            return (
                f"Narrate in first person, {tense} tense, as {name}. {name} is the narrator of the whole story, so every "
                f"chapter is told by {name} and never from anyone else's side."
            )
        return (
            f"Narrate in third person limited, {tense} tense, staying with {name} in every chapter: only what {name} sees, "
            f"hears and thinks; everyone else only through what they say and do. Never move into anyone else's head, "
            f"and no 'I' outside quoted dialogue."
        )

    def _story_text(self) -> str:
        return (
            "STORY\n"
            f"Premise (what the whole story is about): {self.plot.premise}\n"
            f"Theme (what the story steers toward; never state it aloud): {self.plot.theme}"
        )

    def _style_text(self, feed: Optional[dict] = None) -> str:
        st = self.style
        exemplars = _shown(
            st.exemplars, ((feed or {}).get("style") or {}).get("exemplars")
        )

        def bullets(items):
            return "\n".join(f"- {i}" for i in items)

        parts = [
            f"STYLE: {st.label} (hold this flavor throughout)",
            f"Narrator (how this narrator perceives the world and puts it on the page; write every sentence of "
            f"the chapter through it): {st.narrator}",
        ]
        mechanics = [
            f"{label}: {getattr(st, key).strip()}"
            for key, label in (
                ("dialogue_manner", "Dialogue"),
                ("time_handling", "Time"),
            )
            if getattr(st, key, "").strip()
        ]
        if mechanics:
            parts.append(
                "Hard settings (these apply exactly as written): "
                + "; ".join(mechanics)
            )
        parts.append(
            "How this narrator writes (apply each description as written):\n"
            + bullets(
                f"{f.capitalize()}: {ladder_text(f, getattr(st, f))}" for f in DIAL_FIELDS
            )
        )
        if st.signature_moves:
            parts.append(
                "Signature moves (things this narrator does again and again; let them recur when a moment calls "
                "for them, never in every paragraph):\n" + bullets(st.signature_moves)
            )
        if st.off_limits:
            parts.append("Never do these:\n" + bullets(st.off_limits))
        if exemplars:
            parts.append(
                "Exemplars (rhythm and register only; never reproduce or closely paraphrase):\n"
                + bullets(exemplars)
            )
        return "\n".join(parts)

    CHARACTER_GUIDE: ClassVar[str] = (
        "Each character below is a portrait of a person: who they are in any story, never what has happened to them. "
        "What has happened comes from the story so far and from what the last chapter changed, so let those decide "
        "how fresh or worn they are as this chapter opens. Their want is a lasting trait, not this story's goal; the "
        "beat and the destination are what to pursue. Show the way they armor themselves, the way they treat people "
        "and the contradiction in how they see themselves through what they do, never by explaining it. What they "
        "do under pressure is a tendency, not a prop to produce on cue: show it once, when pressure truly builds, "
        "and otherwise leave it alone. Their voice and the lines that show it are register only, never lines to "
        "repeat. Their wound and limits are background: surface them only if the beat calls for it. Where a "
        "character ends the story, if given, is a destination to land, not to explain early."
    )

    def _character_text(self, c: CharacterCard, arc_end: Optional[str] = None) -> str:
        """One person as a paragraph of prose: the portrait fields in reading order, never a form or a list."""
        strip = lambda s: s.rstrip(".") if s else s
        bits = [
            v if v.endswith((".", "!", "?")) else v + "."
            for v in (getattr(c, f).strip() for f in PORTRAIT_FIELDS)
            if v
        ]
        if arc_end:
            bits.append(f"By the end of the story: {strip(arc_end)}.")
        return f"{c.name}. " + " ".join(bits)

    def _world_text(self, feed: Optional[dict] = None) -> str:
        w = self.world
        loc = {l.id: l.name for l in w.locations}
        mine = (feed or {}).get("world") or {}
        locations, objects, groups = (
            _shown(getattr(w, f), mine.get(f), lambda x: x.id)
            for f in ("locations", "objects", "groups")
        )
        def sentence(t: str) -> str:
            t = t.strip()
            return t if not t or t[-1] in ".!?" else t + "."

        # The world reads as a short page, not a form: no ids, no labelled rule lists.
        parts = ["WORLD"]
        opening = " ".join(sentence(x) for x in (w.setting, w.pressure) if x.strip())
        if opening:
            parts.append(opening)
        if w.rules:
            parts.append(
                "How things work here (settled; do not re-explain them):\n"
                + " ".join(sentence(r) for r in w.rules)
            )
        if locations:
            parts.append(
                "Places the story can go:\n"
                + "\n".join(f"{l.name}: {sentence(l.description)}" for l in locations)
            )
        if objects:
            rows = []
            for o in objects:
                row = f"{o.name}: {sentence(o.description)}"
                where = loc.get(o.location, o.location) if o.location else None
                if o.owner and where:
                    row += f" {self.name_of(o.owner)} has it, at {where}."
                elif o.owner:
                    row += f" {self.name_of(o.owner)} has it."
                elif where:
                    row += f" It is at {where}."
                rows.append(row)
            parts.append(
                "Things that matter (who has each and where it is are current; respect them):\n"
                + "\n".join(rows)
            )
        if groups:
            rows = []
            for g in groups:
                row = f"{g.name}: {sentence(g.description)}"
                if g.wants.strip():
                    row += f" They want {g.wants.strip().rstrip('.')}."
                rows.append(row)
            parts.append(
                "People to reckon with (they act through unnamed officials or crowds, never through a named person):\n"
                + "\n".join(rows)
            )
        if w.hidden_truths:
            rows = []
            for t in w.hidden_truths:
                who = ", ".join(self.name_of(k) for k in t.known_by) or "nobody yet"
                row = f"{sentence(t.fact)} Known by: {who}."
                if t.stake.strip():
                    row += f" At stake: {sentence(t.stake)}"
                rows.append(row)
            parts.append(
                "Unspoken (true, but not yet on the page; a character acts on one only if listed as knowing it, "
                "or if this chapter reveals it):\n" + "\n".join(rows)
            )
        parts.append(
            "The places, things and groups above are a selection made for this chapter, not everything in the world."
        )
        return "\n\n".join(parts)

    def context_for_chapter(self, chapter_num: int, feed: Optional[dict] = None) -> str:
        """
        Cards only, as labeled text for the writer: story, style, characters, world, and (final chapter only)
        the ending. The beat, story-so-far and previous-chapter text come from the notebook's prompt
        (see render_beat), so nothing appears twice.
        """
        beat = self.beat_for(chapter_num)
        final = self.is_final_chapter(chapter_num)
        present = set(beat.present)
        arcs = {a.character: a.end for a in self.plot.arcs}
        feed = feed if feed is not None else self.feed(chapter_num)

        here = [
            self._character_text(c, arcs.get(c.id) if final else None)
            for c in self.characters
            if c.id in present
        ]
        others = "; ".join(
            f"{c.name}, {c.role.strip().rstrip('.')}"
            for c in self.characters
            if c.id not in present
        )

        parts = [
            self._story_text(),
            self._style_text(feed),
            "CHARACTERS IN THIS CHAPTER\n"
            + self.CHARACTER_GUIDE
            + "\n\n"
            + "\n\n".join(here),
        ]
        if others:
            parts.append(
                "OTHER CHARACTERS (reference only, keep out of scenes): " + others + "."
            )
        parts.append(self._world_text(feed))
        if final:
            parts.append(
                f"ENDING (this is the final chapter; land this situation):\n{self.plot.ending}"
            )
        return "\n\n".join(parts)

    def stage_lines(self, chapter_num: int) -> list[str]:
        """What story stage(s) this chapter has to portray. Empty for outlines that predate the stage field."""
        b = self.beat_for(chapter_num)
        if b.stage is None:
            return []
        before = [
            x for x in self.plot.chapter_beats if x.chapter_num == chapter_num - 1
        ]
        prev = (
            before[0].stage if before else 0
        )  # 0: the first chapter starts from Setup
        return stage_lines_for(prev, b.stage)

    def render_beat(self, chapter_num: int) -> str:
        """Readable text for the chapter's beat: every line says what it is for, and no ids appear."""
        b = self.beat_for(chapter_num)
        loc = next((l for l in self.world.locations if l.id == b.location), None)
        where = loc.name if loc else b.location
        name = self.name_of(self.plot.protagonist)
        lines = [
            self.narration_rule(b),
            *self.stage_lines(chapter_num),
            f"The chapter opens at {where}, {b.when}, with {', '.join(self.name_of(p) for p in b.present)} on the page.",
            f"{name} is after this: {b.goal} Standing in the way: {b.obstacle}",
            "What happens, in order (write only this; nothing from the next chapter begins here):",
            *[f"  {i}. {e}" for i, e in enumerate(b.events, 1)],
            f"Stop the chapter as soon as this is reached, writing nothing past it -- a situation to arrive at, "
            f"not a line to copy: {b.ends_on}",
        ]
        if b.tone:
            lines.append(f"The telling itself: {b.tone}")
        if b.shifts:
            lines.append(
                "Dramatize these in action or dialogue, not just implied consistency:"
            )
            lines += [
                f"  - {self.name_of(s.character)}: {s.movement}" for s in b.shifts
            ]
        if b.plants:
            lines.append(
                "Place quietly on the page, without resolving it: "
                + "; ".join(b.plants)
            )
        if b.pays_off:
            lines.append("Earlier setups that resolve now: " + "; ".join(b.pays_off))
        if b.reveals:
            facts = {t.id: t.fact for t in self.world.hidden_truths}
            lines.append(
                "Everyone present learns this on the page now: "
                + "; ".join(facts.get(r, r) for r in b.reveals)
            )
        facts = {t.id: t.fact for t in self.world.hidden_truths}
        later = [t.fact for t in self.unrevealed_truths(chapter_num)]
        if later:
            lines.append(
                "Not revealed yet -- no one states, explains or hints at these now, even a "
                "character who knows them: " + "; ".join(dict.fromkeys(later))
            )
        if self.plot.leave_open:
            lines.append(
                "Never resolve or explain in this story: "
                + "; ".join(self.plot.leave_open)
            )
        return "\n".join(lines)
