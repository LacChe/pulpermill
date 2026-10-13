from __future__ import annotations

from pydantic import BaseModel, Field
from typing import ClassVar, Optional

from .characters import CharacterCard
from .common import M, POOLS, _beat_seq, _mentions, _related, _shown, pick_least_used
from .outline import (
    BEAT_CLASH,
    ChapterBeat,
    PlotOutline,
    beat_similarity,
    stage_lines_for,
)
from .style import POV, StyleCard
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
        and groups): {"style": {field: [...]}, "characters": {id: {field: [...]}}, "world": {field: [...]}}. A list that is
        not rotating is simply absent, and the writer gets it whole. Only characters in the scene get a share."""
        b = self.beat_for(chapter_num)
        seq = self._beat_seq(chapter_num)
        out: dict = {"style": {}, "characters": {}, "world": {}}

        def pick(owner, card, field, keys, required=()):
            k = POOLS.get(f"{card}.{field}")
            return (
                None
                if k is None
                else pick_least_used(keys, owner.uses.get(field, {}), k, required)
            )

        for f, keys in (
            ("exemplars", self.style.exemplars),
            ("chapter_shapes", self.style.chapter_shapes),
        ):
            if (ch := pick(self.style, "style", f, keys)) is not None:
                out["style"][f] = ch
        for c in self.characters:
            if c.id not in b.present:
                continue
            for f in ("look", "habits", "sample_lines"):
                if (ch := pick(c, "characters", f, getattr(c, f))) is not None:
                    out["characters"].setdefault(c.id, {})[f] = ch
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
        for cid, fields in feed.get("characters", {}).items():
            if (c := self.character_by_id(cid)) is not None:
                for f, keys in fields.items():
                    bump(c, f, keys)
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
        shapes = _shown(
            st.chapter_shapes, ((feed or {}).get("style") or {}).get("chapter_shapes")
        )

        def bullets(items):
            return "\n".join(f"- {i}" for i in items)

        parts = [
            f"STYLE: {st.label} (hold this flavor throughout)",
            f"Voice (how the narrator sounds and how its humor, tension or sentiment works; hold it "
            f"throughout): {st.voice}",
        ]
        if st.prose_habits:
            parts.append(
                "Prose habits (concrete habits; follow them):\n"
                + bullets(st.prose_habits)
            )
        if st.avoid:
            parts.append("Never do these:\n" + bullets(st.avoid))
        if shapes:
            parts.append(
                "Chapter shape (how this chapter opens, closes and balances dialogue and narration; it was chosen for "
                "this chapter alone, so build the chapter this way):\n"
                + bullets(shapes)
            )
        if exemplars:
            parts.append(
                "Exemplars (rhythm and register only; never reproduce or closely paraphrase):\n"
                + bullets(exemplars)
            )
        return "\n".join(parts)

    CHARACTER_GUIDE: ClassVar[str] = (
        "Each character below is given as a person, not a form. What drives them is a lasting trait, not this "
        "story's particular goal -- the beat and where they end up are what to pursue this chapter. Their blind "
        "spot is how they see themselves versus what they actually do: show the contradiction in action, never "
        "explain it. Looks, habits and sample lines are established facts, a selection for this chapter -- use "
        "one when a moment calls for it, never contradict them, and never reuse a sample line verbatim. History "
        "is background: surface it only if the beat calls for it. How they feel toward someone else in the scene "
        "is from their side only. What comes last -- their condition and anything that's shifted lately -- is the "
        "truth of them as this chapter opens; write them as they are now. Where a character ends the story, if "
        "given, is a destination to land, not to explain early."
    )

    def _character_text(
        self,
        c: CharacterCard,
        present: set[str],
        arc_end: Optional[str],
        feed: Optional[dict] = None,
    ) -> str:
        mine = ((feed or {}).get("characters") or {}).get(c.id) or {}
        look, habits, lines = (
            _shown(getattr(c, f), mine.get(f))
            for f in ("look", "habits", "sample_lines")
        )
        strip = lambda s: s.rstrip(".") if s else s
        bits = [
            f"is {strip(c.role)}.",
            f"What drives them: {strip(c.want)}.",
            f"Their blind spot: {strip(c.blind_spot)}.",
        ]
        if look:
            bits.append("Physically: " + "; ".join(look) + ".")
        if habits:
            bits.append("Habits: " + "; ".join(habits) + ".")
        bits.append(f"Voice: {strip(c.voice)}.")
        if lines:
            bits.append(
                "They might say something like "
                + ", or ".join(f'"{l}"' for l in lines)
                + "."
            )
        if c.history:
            bits.append(
                c.history if c.history.endswith((".", "!", "?")) else c.history + "."
            )
        toward = [
            f"toward {self.name_of(a.toward)}, {strip(a.attitude)}"
            for a in c.toward
            if a.toward in present
        ]
        if toward:
            joined = "; ".join(toward)
            bits.append(joined[:1].upper() + joined[1:] + ".")
        if c.wrap.condition:
            bits.append(f"Right now: {strip(c.wrap.condition)}.")
        if c.wrap.recent_changes:
            bits.append("Lately: " + "; ".join(c.wrap.recent_changes) + ".")
        if c.wrap.recent_details:
            bits.append("Also established: " + "; ".join(c.wrap.recent_details) + ".")
        if arc_end:
            bits.append(f"By the end of the story: {strip(arc_end)}.")
        return f"{c.name} " + " ".join(bits)

    def _world_text(self, feed: Optional[dict] = None) -> str:
        w = self.world
        loc = {l.id: l.name for l in w.locations}
        mine = (feed or {}).get("world") or {}
        locations, objects, groups = (
            _shown(getattr(w, f), mine.get(f), lambda x: x.id)
            for f in ("locations", "objects", "groups")
        )
        parts = ["WORLD", f"Setting (the place and occasion): {w.setting}"]
        if w.rules:
            parts.append(
                "Rules (permanent facts; never contradict them and do not re-explain them):\n"
                + "\n".join(f"- {r}" for r in w.rules)
            )
        if w.hidden_truths:
            rows = []
            for t in w.hidden_truths:
                who = ", ".join(self.name_of(k) for k in t.known_by) or "nobody yet"
                rows.append(f"- {t.fact} (known by: {who})")
            parts.append(
                "Hidden truths (true facts the story keeps back; a character may act on one only if it "
                "lists them as knowing it, or if this chapter's beat reveals it):\n"
                + "\n".join(rows)
            )
        parts.append(
            "Locations:\n"
            + "\n".join(f"- {l.name}: {l.description}" for l in locations)
        )
        if objects:
            rows = []
            for o in objects:
                row = f"- {o.name}: {o.description}"
                if o.owner:
                    row += f" Held by {self.name_of(o.owner)}."
                if o.location:
                    row += f" At {loc.get(o.location, o.location)}."
                rows.append(row)
            parts.append(
                "Objects (who holds each and where it sits are current; respect them):\n"
                + "\n".join(rows)
            )
        if groups:
            rows = []
            for g in groups:
                row = f"- {g.name}: {g.description}"
                if g.wants:
                    row += f" Wants: {g.wants}"
                rows.append(row)
            parts.append(
                "Groups (background collectives; they may appear as unnamed crowds or officials, their "
                "wants shape how they act, and they are never given proper names):\n"
                + "\n".join(rows)
            )
        return "\n".join(parts)

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
            self._character_text(c, present, arcs.get(c.id) if final else None, feed)
            for c in self.characters
            if c.id in present
        ]
        others = [
            f"- {c.name}: {c.role}" for c in self.characters if c.id not in present
        ]

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
                "OTHER CHARACTERS (reference only, keep out of scenes):\n"
                + "\n".join(others)
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
