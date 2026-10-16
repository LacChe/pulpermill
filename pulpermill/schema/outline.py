from __future__ import annotations

import dataclasses
import re
from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import Optional, TYPE_CHECKING

from .common import (
    M,
    MAX_CAST,
    MAX_CHAPTERS,
    MAX_CHAPTER_NUM,
    Resolver,
    _as_dicts,
    _related,
    slugify,
)

if TYPE_CHECKING:  # only the annotation of finalize_next_beat needs it; a real import would be a cycle (story imports outline)
    from .story import StoryProject


# ===========================================================================
# OUTLINE
# ===========================================================================


class Direction(str, Enum):
    better = "better"
    worse = "worse"
    mixed = "mixed"


class Agenda(BaseModel):
    character: str = Field(description="Character id or name.")
    wants: str = Field(
        description="What this person is after in this scene, including anything they are hiding or holding back."
    )


class Relationship(BaseModel):
    a: str = Field(description="Character id.")
    b: str = Field(description="Character id.")
    between: str = Field(
        description="What lies between these two in this story: a debt, a lie, a grievance, a hunger."
    )


_NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "a single": 1,
    "single": 1,
}
_ZH_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _zh_number(t: str) -> Optional[int]:
    if t.isdigit():
        return int(t)
    if "十" in t:
        a, _, b = t.partition("十")
        tens = _ZH_DIGITS.get(a, 1) if a else 1
        ones = _ZH_DIGITS.get(b, 0) if b else 0
        return (
            tens * 10 + ones
            if (not a or a in _ZH_DIGITS) and (not b or b in _ZH_DIGITS)
            else None
        )
    return _ZH_DIGITS.get(t)


def chapter_count_in(text: str) -> Optional[int]:
    """The chapter count an author states in their notes ('Three chapters', '10 chapters', '三章'), else None.
    Only the first 'N chapters' phrase counts, and ordinals like 'chapter 3' or '第三章' never match."""
    words = "|".join(sorted((re.escape(w) for w in _NUM_WORDS), key=len, reverse=True))
    found = []
    for m in re.finditer(rf"(?<![\w-])(\d{{1,2}}|{words})[ -]+chapters?\b", text, re.I):
        w = m.group(1).lower()
        found.append((m.start(), int(w) if w.isdigit() else _NUM_WORDS[w]))
    for m in re.finditer(
        r"(?<!第)([0-9]{1,2}|[一二两三四五六七八九十]{1,3})\s*(?:个)?(?:章节|章|回)",
        text,
    ):
        n = _zh_number(m.group(1))
        if n:
            found.append((m.start(), n))
    found.sort()
    return next((n for _, n in found if 1 <= n <= MAX_CHAPTERS), None)


OPENING_DOC = (
    "The first moment on the page, chosen for this chapter's job: who is doing or saying what, and where. Structure "
    "only; the writer chooses the words."
)
DIRECTION_DOC = (
    "For the main character, how things stand at the chapter's end compared with its start: better, worse, or mixed "
    "(a gain and a loss together)."
)
GOAL_DOC = (
    "What the main character wants in this chapter and, if they are hiding or avoiding something while they go "
    "after it, what that is."
)
OBSTACLE_DOC = (
    "Whose want crosses the main character's, and what that force is doing now. Prefer a person with a competing "
    "want; use an object, rule or event only when no person fits."
)
EVENTS_DOC = (
    "Three to five lines, in order, one sentence each. Each line is a change in leverage (someone gains ground, "
    "loses it, or is exposed), not a bare action."
)
ENDS_ON_DOC = (
    "The situation the chapter stops at, in a few words (for example: 'they are cornered at the vault "
    "door'). A point to arrive at, not a quoted line: the writer chooses the exact words. It must be true after "
    "this chapter's last event and must not depend on anything from an earlier or later chapter."
)
TURN_DOC = (
    "One sentence: what is true when this chapter ends that was not true when it began (a decision made, a "
    "secret out, a relationship changed, a plan broken, a new danger). If nothing changed, the chapter is not worth writing."
)
PLANTS_DOC = (
    "Concrete things that appear or happen on the page in this chapter (an object, a line of "
    "dialogue, an action) and that a LATER chapter uses again. Write the thing itself, not what it means or "
    "symbolises. Empty if there are none."
)
PAYS_OFF_DOC = (
    "For each earlier plant this chapter uses again, copy that plant's wording exactly. Empty if there are none."
)
AGENDAS_DOC = (
    "One item for each other person present: what they are after in this scene, including anything they are hiding."
)


class ChapterBeat(BaseModel):
    chapter_num: int = Field(ge=1, le=MAX_CHAPTER_NUM)
    when: str = Field(description="The day and the time of day this chapter begins.")
    location: str = Field(description="Location id from the world.")
    present: list[str] = Field(
        description="Character ids of everyone in the scene, including the main character."
    )
    opening: str = Field(description=OPENING_DOC)
    direction: Direction = Field(description=DIRECTION_DOC)
    goal: str = Field(description=GOAL_DOC)
    obstacle: str = Field(description=OBSTACLE_DOC)
    agendas: list[Agenda] = Field(description=AGENDAS_DOC)
    events: list[str] = Field(description=EVENTS_DOC)
    ends_on: str = Field(description=ENDS_ON_DOC)
    turn: str = Field(default="", description=TURN_DOC)
    plants: list[str] = Field(default_factory=list, description=PLANTS_DOC)
    pays_off: list[str] = Field(default_factory=list, description=PAYS_OFF_DOC)
    reveals: list[str] = Field(
        default_factory=list,
        description="Ids of hidden truths (like truth_1) that become known on the page to everyone present.",
    )


ARC_END_DOC = (
    "How this person ends up, stated with the concrete thing they do or say on the page that shows it, plus what in "
    "this story forces the change and what it costs them."
)
PREMISE_DOC = (
    "One or two sentences: who wants what, what stands in the way, and what winning or losing would cost."
)
OPPOSITION_DOC = (
    "Who or what stands against the main character (a person, a group, the world's pressure, their own flaw), what it "
    "wants, and what it does if nobody stops it."
)
THEME_DOC = (
    "The choice the story forces, written as two goods set against each other. Steers the plot; no character ever "
    "states it."
)
SHAPE_DOC = (
    "A few plain sentences saying where hope, the false win, the low point, the peak and the coda fall, with chapter "
    "numbers, scaled to the total number of chapters. Rising and falling, not a steady climb."
)
ENDING_DOC = (
    "The answer to the story's central question and its price: what has been done or said, what it cost, and what is "
    "still open. A situation, not only what the characters now understand."
)
BETWEEN_DOC = (
    "What lies between these two in this story: a debt, a lie, a grievance, a hunger."
)


class CharacterArc(BaseModel):
    character: str = Field(description="Character id.")
    end: str = Field(description=ARC_END_DOC)


class PlotOutline(BaseModel):
    premise: str = Field(description=PREMISE_DOC)
    protagonist: str = Field(
        description="Character id of the story's one main character. Every chapter is told from this person's side, in "
        "the person (first or third) the style card sets, and never from anyone else's.",
    )
    opposition: str = Field(description=OPPOSITION_DOC)
    relationships: list[Relationship]
    theme: str = Field(description=THEME_DOC)
    shape: str = Field(description=SHAPE_DOC)
    ending: str = Field(description=ENDING_DOC)
    arcs: list[CharacterArc]
    leave_open: list[str] = Field(
        default_factory=list,
        description="What the author says must stay unresolved or unexplained. Empty if they said nothing.",
    )
    total_chapters: int = Field(
        ge=1,
        le=MAX_CHAPTERS,
        description="How many chapters the whole story has. Fixed when the story is set up; each chapter's own beat is written "
        "after the chapter before it, so this list holds only the beats up to the chapter being worked on.",
    )
    chapter_beats: list[ChapterBeat] = Field(min_length=1)


# --- what the model writes for an outline: names instead of ids -------------------------------------------


class AgendaD(BaseModel):
    character: str = Field(description="Character name.")
    wants: str = Field(
        description="What this person is after in this scene, including anything they are hiding or holding back."
    )


class RelationshipD(BaseModel):
    a: str = Field(description="Exact character name from the cast list.")
    b: str = Field(description="Exact character name from the cast list.")
    between: str = Field(description=BETWEEN_DOC)


class BeatD(BaseModel):
    when: str = Field(description="The day and the time of day this chapter begins.")
    location: str = Field(description="Exact location name from the list.")
    present: list[str] = Field(
        description="Names of everyone in the scene, including the main character."
    )
    opening: str = Field(description=OPENING_DOC)
    direction: Direction = Field(description=DIRECTION_DOC)
    goal: str = Field(description=GOAL_DOC)
    obstacle: str = Field(description=OBSTACLE_DOC)
    agendas: list[AgendaD] = Field(description=AGENDAS_DOC)
    events: list[str] = Field(description=EVENTS_DOC)
    ends_on: str = Field(description=ENDS_ON_DOC)
    turn: str = Field(default="", description=TURN_DOC)
    plants: list[str] = Field(default_factory=list, description=PLANTS_DOC)
    pays_off: list[str] = Field(default_factory=list, description=PAYS_OFF_DOC)
    reveals: list[str] = Field(
        default_factory=list,
        description="Ids of hidden truths (like truth_1) that become known on the page to everyone present. Only ids from the "
        "list of truths not yet revealed. Empty if none fits this chapter.",
    )


class ArcD(BaseModel):
    character: str = Field(description="Character name.")
    end: str = Field(description=ARC_END_DOC)


class NextBeatD(BeatD):
    """What the next-beat planner writes: the beat, plus optional changes to the story's setup that the chapter just
    written calls for. A revision field left empty means "no change"."""

    turn: str = Field(
        description="One sentence: what is true when this chapter ends that was not true when it began (a decision made, a "
        "secret out, a relationship changed, a plan broken, a new danger). It must differ from the turns of the earlier chapters."
    )
    revised_premise: str = Field(
        default="",
        description="Only if the story has really changed since the premise was written: the premise as it should now read. Otherwise empty.",
    )
    revised_opposition: str = Field(
        default="",
        description="Only if events have changed who or what stands against the main character: the opposition as it should now read. Otherwise empty.",
    )
    revised_theme: str = Field(
        default="",
        description="Only if the story's real subject has shifted: the theme as it should now read. Otherwise empty.",
    )
    revised_shape: str = Field(
        default="",
        description="Only if events have bent the story's course: the shape as it should now read, with chapter numbers. Otherwise empty.",
    )
    revised_ending: str = Field(
        default="",
        description="Only if what has happened makes the planned ending wrong: the broad destination as it should now read. Otherwise empty.",
    )
    revised_arcs: list[ArcD] = Field(
        default_factory=list,
        description="Only if a person is now heading somewhere else: ALL the arcs as they should now read, "
        "each person once. Otherwise empty.",
    )
    revised_leave_open: list[str] = Field(
        default_factory=list,
        description="Only to replace the list of things that must stay unresolved: the full new list. Otherwise empty.",
    )
    closed_leave_open: list[str] = Field(
        default_factory=list,
        description="Items of the current 'leave open' list, copied exactly, that this chapter has now settled. Otherwise empty.",
    )
    why_revised: str = Field(
        default="",
        description="One short sentence on why the setup was changed. Empty if nothing was.",
    )


class OutlineDraft(BaseModel):
    premise: str = Field(description=PREMISE_DOC)
    protagonist: str = Field(
        description="Exact name, from the character list, of the story's one main character. The whole story is told "
        "from this person's side in every chapter."
    )
    opposition: str = Field(description=OPPOSITION_DOC)
    relationships: list[RelationshipD]
    theme: str = Field(description=THEME_DOC)
    shape: str = Field(description=SHAPE_DOC)
    ending: str = Field(description=ENDING_DOC)
    arcs: list[ArcD]
    leave_open: list[str] = Field(
        default_factory=list,
        description="What the author says must stay unresolved or unexplained. Empty if they said nothing.",
    )
    chapter_count: int = Field(
        default=0,
        ge=0,
        le=MAX_CHAPTERS,
        description=f"How many chapters the whole story has, from 1 to {MAX_CHAPTERS}. Fixed from now on.",
    )
    chapter_beats: list[BeatD] = Field(
        min_length=1,
        max_length=1,
        description="Exactly one item: the beat of chapter 1. Later chapters are planned one at a time as the story is written.",
    )


@dataclasses.dataclass
class OutlineResult:
    plot: PlotOutline
    notes: list[str]  # things the human should know (people left out, places added)
    new_locations: list[
        dict
    ]  # places the outline used that the World card did not have


def finalize_outline(
    draft: OutlineDraft, cast, world, n_chapters: Optional[int] = None, start: int = 1
) -> OutlineResult:
    """
    Names to ids. `cast` is a list of character cards (or dicts with `id`/`name`); `world` is a WorldBible or dict.
    Chapter numbers come from list order. Nothing here raises for a name that does not match: an unknown main
    character falls back to someone in the first scene, unknown people in present, agendas, relationships or arcs and unknown reveals are dropped, and
    all of it is reported in `notes` (people can still appear in the events text). An unknown place is matched
    to a clear near-neighbour, or else added as a new location and returned in `new_locations`.
    The draft holds one beat. It is chapter `start` (1 for the outline itself, later for a rolling next beat); the total
    is the author's count (`n_chapters`) or else the draft's own.
    """
    cast = _as_dicts(cast)
    world = world.model_dump() if isinstance(world, BaseModel) else world
    notes: list[str] = []
    new_locs: list[dict] = []

    cres = Resolver(cast)
    locations = list(world["locations"])
    lres = Resolver(locations)
    truths = {t["id"] for t in world.get("hidden_truths", [])}

    def truth(x, n):
        x = x.strip().lower()
        x = f"truth_{x}" if x.isdigit() else x
        if x in truths:
            return x
        notes.append(
            M(
                "chapter {n}: it reveals '{truth}', which is not one of your hidden truths, so that reveal was left out",
                n=n,
                truth=x,
            )
        )
        return None

    def choose_protagonist():
        r = cres.find(draft.protagonist)
        if r:
            return r
        for b in (
            draft.chapter_beats
        ):  # not a cast member: the first person it can recognise in the first chapter
            for x in b.present:
                r = cres.find(x)
                if r:
                    break
            break
        r = r or cast[0]["id"]
        notes.append(
            M(
                "the main character '{who}' is not in your cast, so {name} was used; check the setup",
                who=draft.protagonist,
                name=next(c["name"] for c in cast if c["id"] == r),
            )
        )
        return r

    def place(name, n):
        nonlocal lres
        r = lres.find(name)
        if r:
            return r
        new_id = "loc_" + slugify(name)
        new_locs.append(
            {
                "id": new_id,
                "name": name.strip(),
                "description": "(added from the setup: describe this place)",
            }
        )
        locations.append(new_locs[-1])
        lres = Resolver(locations)
        notes.append(
            M(
                "chapter {n}: '{place}' was not in your World, so it was added to the World card; fill in its description",
                n=n,
                place=name.strip(),
            ).on(
                "world.locations.description",
                new_id,
                "(added from the setup: describe this place)",
            )
        )
        return new_id

    def soft(x, n, where):
        r = cres.find(x)
        if r is None:
            notes.append(
                M(
                    "chapter {n}: '{who}' is not in your cast, so it was left out of {where} (it can still appear in the events)",
                    n=n,
                    who=x,
                    where=where,
                )
                if n
                else M(
                    "'{who}' is not in your cast, so it was left out of {where} (it can still appear in the events)",
                    who=x,
                    where=where,
                )
            )
        return r

    total = n_chapters or draft.chapter_count
    if (
        not 1 <= total <= MAX_CHAPTERS
    ):  # raised inside the retry loop, so the model is told and tries again
        raise ValueError(
            M(
                "chapter_count must be a number from 1 to {max}: how many chapters the whole story has",
                max=MAX_CHAPTERS,
            )
        )
    protagonist = choose_protagonist()
    beats = []
    for n, b in enumerate(draft.chapter_beats, start):
        data = b.model_dump()
        present = list(
            dict.fromkeys(
                [protagonist]
                + [
                    r
                    for r in (soft(x, n, M("the people present")) for x in b.present)
                    if r
                ]
            )
        )
        if len(present) > MAX_CAST:
            notes.append(
                M(
                    "chapter {n}: more than {max} people were present, so only the first {max} were kept",
                    n=n,
                    max=MAX_CAST,
                )
            )
            present = present[:MAX_CAST]
        data.update(
            chapter_num=n,
            location=place(b.location, n),
            present=present,
            agendas=[
                {"character": r, "wants": ag.wants}
                for ag in b.agendas
                if (r := soft(ag.character, n, M("the agendas")))
            ],
            reveals=list(
                dict.fromkeys(t for t in (truth(x, n) for x in b.reveals) if t)
            ),
        )
        beats.append(ChapterBeat(**data))
    relationships = []
    for rel in draft.relationships:
        ra, rb = cres.find(rel.a), cres.find(rel.b)
        if ra is None or rb is None:
            notes.append(
                M(
                    "the relationship between '{a}' and '{b}' was left out because one of them is not in your cast",
                    a=rel.a,
                    b=rel.b,
                )
            )
        elif ra == rb:
            notes.append(
                M(
                    "a relationship between '{a}' and '{b}' was left out because they are the same person",
                    a=rel.a,
                    b=rel.b,
                )
            )
        else:
            relationships.append(Relationship(a=ra, b=rb, between=rel.between))
    plot = PlotOutline(
        premise=draft.premise,
        protagonist=protagonist,
        opposition=draft.opposition,
        relationships=relationships,
        total_chapters=total,
        theme=draft.theme,
        shape=draft.shape,
        ending=draft.ending,
        leave_open=draft.leave_open,
        arcs=[
            CharacterArc(character=r, end=a.end)
            for a in draft.arcs
            if (r := soft(a.character, 0, M("the arcs")))
        ],
        chapter_beats=beats,
    )
    return OutlineResult(plot=plot, notes=sorted(set(notes)), new_locations=new_locs)


# Words ignored when comparing two chapter plans (_gist). The same words the comparison has always ignored; kept apart from the
# plant/payoff list below so that changing one feature's list cannot change the other.
_BEAT_STOP = {
    "the",
    "and",
    "but",
    "for",
    "with",
    "when",
    "then",
    "this",
    "that",
    "they",
    "she",
    "her",
    "his",
    "him",
    "its",
    "one",
    "two",
    "who",
    "what",
    "where",
    "after",
    "before",
    "while",
    "about",
    "into",
    "from",
    "has",
    "had",
    "was",
    "were",
    "are",
    "not",
    "out",
    "off",
    "all",
    "any",
    "her",
    "their",
    "them",
    "there",
    "than",
}


def _gist(text: str) -> set:
    """The content words of a sentence (Latin words of 3+ letters, or pairs of CJK characters) for comparing two plans."""
    t = (text or "").casefold()
    words = {w for w in re.findall(r"[a-z\u00c0-\u024f]{3,}", t) if w not in _BEAT_STOP}
    cjk = re.findall(r"[\u4e00-\u9fff]", t)
    return words | {a + b for a, b in zip(cjk, cjk[1:])}


def _scene_closeness(gap: int) -> float:
    """How much returning to the same place with the same people counts against a beat, based on how many chapters
    separate the two: back-to-back, it reads as nothing having moved; much later, the same place and people can be a
    deliberate callback (a climax returning to the opening scene), so it counts for much less."""
    return 1.0 if gap <= 1 else 0.6 if gap == 2 else 0.35 if gap == 3 else 0.15


def beat_similarity(a: "ChapterBeat", b: "ChapterBeat") -> float:
    """0..1: how much two beats are the same plan. Combines what the chapter is for and what it changes (gist: words
    shared by `goal`+`turn`, so a chapter that merely rephrases an earlier one in different words still scores high)
    with whether it is staged in the same place with the same people, weighted down by how far apart the two chapters
    are. Two consecutive beats that put the same cast back in the same room read as the same scene even when their
    goal and turn are worded differently enough that the gist score alone misses it."""
    ga, gb = _gist(a.goal + " " + a.turn), _gist(b.goal + " " + b.turn)
    gist = len(ga & gb) / len(ga | gb) if ga and gb else 0.0
    pa, pb = set(a.present), set(b.present)
    cast_overlap = len(pa & pb) / len(pa | pb) if pa and pb else 0.0
    scene = cast_overlap if a.location == b.location else cast_overlap * 0.3
    return max(gist, scene * _scene_closeness(abs(a.chapter_num - b.chapter_num)))


BEAT_CLASH = (
    0.4  # at or above this, a new beat is treated as a repeat of an earlier one
)


def finalize_next_beat(draft, story: "StoryProject", n: int):
    """The beat the model wrote for chapter `n`, as a ChapterBeat: names to ids, and the
    picks checked against what is still available (a truth already revealed or a payoff with no open plant is dropped, with a
    note). The draft may be a NextBeatD: its revisions of the setup are checked here and returned, not applied.
    Returns (beat, notes, new_locations, changes); the caller adds the new places to the World card and applies `changes`
    ({"premise"/"opposition"/"theme"/"shape"/"ending": text, "leave_open": list, "arcs": [CharacterArc]}) to the plot."""
    plot = story.plot
    base = BeatD.model_validate(
        {k: v for k, v in draft.model_dump().items() if k in BeatD.model_fields}
    )
    new_arcs = list(getattr(draft, "revised_arcs", None) or [])
    od = OutlineDraft(
        premise=plot.premise,
        protagonist=story.name_of(plot.protagonist),
        opposition=plot.opposition,
        relationships=[],
        theme=plot.theme,
        shape=plot.shape,
        ending=plot.ending,
        arcs=new_arcs,
        chapter_count=plot.total_chapters,
        chapter_beats=[base],
    )
    res = finalize_outline(
        od, story.characters, story.world, plot.total_chapters, start=n
    )
    beat, notes = res.plot.chapter_beats[0], list(res.notes)
    open_truths = {t.id for t in story.unrevealed_truths(n - 1)}
    for r in [r for r in beat.reveals if r not in open_truths]:
        notes.append(
            M(
                "chapter {n}: '{truth}' was already revealed earlier, so it was not revealed again",
                n=n,
                truth=r,
            )
        )
    beat.reveals = [r for r in beat.reveals if r in open_truths]
    plants, fixed = story.open_plants(n - 1), []
    for p in beat.pays_off:
        match = next((pl for pl in plants if _related(p, pl)), None)
        if match is None:
            notes.append(
                M(
                    "chapter {n}: the payoff '{text}' matches no plant that is still open, so it was left out",
                    n=n,
                    text=p[:50],
                )
            )
        elif match not in fixed:
            fixed.append(match)  # the plant's own wording, so the two always match
    beat.pays_off = fixed
    # revisions of the setup: only what really differs from what is there now
    changes, shown = {}, []
    for field, label in (
        ("premise", M("premise")),
        ("opposition", M("opposition")),
        ("theme", M("theme")),
        ("shape", M("shape")),
        ("ending", M("ending")),
    ):
        new = (getattr(draft, "revised_" + field, "") or "").strip()
        old = getattr(plot, field)
        if new and new.casefold() != old.strip().casefold():
            changes[field] = new
            shown.append((label, new, old))
    closed = set(getattr(draft, "closed_leave_open", None) or [])
    keep = [x for x in plot.leave_open if x not in closed]
    new_open = [
        x.strip()
        for x in (getattr(draft, "revised_leave_open", None) or [])
        if x.strip()
    ] or keep
    if new_open != list(plot.leave_open):
        changes["leave_open"] = new_open
        shown.append(
            (
                M("things left open"),
                "; ".join(new_open) or M("(nothing)"),
                "; ".join(plot.leave_open) or M("(nothing)"),
            )
        )
    if res.plot.arcs:
        nm = lambda arcs: "; ".join(
            f"{story.name_of(a.character)}: {a.end}" for a in arcs
        )
        if nm(res.plot.arcs) != nm(plot.arcs):
            changes["arcs"] = res.plot.arcs
            shown.append((M("character arcs"), nm(res.plot.arcs), nm(plot.arcs)))
    why = (getattr(draft, "why_revised", "") or "").strip()
    for label, new, old in shown:
        notes.append(
            M(
                "after chapter {n} the story's {what} was changed. Now: {new} Before: {old}",
                n=n - 1,
                what=label,
                new=new,
                old=old,
            )
        )
    if shown and why:
        notes.append(
            M("reason given for the changes after chapter {n}: {why}", n=n - 1, why=why)
        )
    return beat, sorted(set(notes)), res.new_locations, changes
