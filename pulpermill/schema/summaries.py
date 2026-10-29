"""Pipeline records made while a chapter is generated, so an unfinished story can resume and a chapter can be redone.
Hidden from the user and never edited by hand. One entry per chapter, found through the chapter's beat (a beat link,
never a stored chapter number); regenerating a chapter replaces its entries as a whole, keeping their ids. Three cards:
  summary_events        what happened (the outer story), plus the changed line, planted and paid-off plants
  summary_shifts        how people changed (the inner story)
  entanglements_history the Entanglements card as each chapter was written from (what the user saw when generating)
Use counts for behaviors, places and things are tallied from these entries and from Outline beats, never stored as counters."""
from .common import spec, Rule, Item
from .entanglements import Entanglements

MAX_OPEN_PLANTS = 2        # a chapter plants at most one thing (a single field), and at most two plants stay open

# ---------------------------------------------------------------- Events
EVENTS_CARD = {
    "id": "summary_events",
    "type": "record",
    "reads": ["chapter_text"],
    "portable": False,
    "between_chapters": "per_chapter",
    "hidden": True,
    "sent_to_model": True,
}
EVENTS_GROUPS = [{"id": "entries", "collapsed": False}]
EVENTS_RENDER_ORDER = [["entries"]]


class EventsEntry(Item):
    beat: str = spec("select", None, "note", ref=["outline.beats"], filled_by="code")      # which chapter; its number lives on the beat
    happened: str = spec("textarea", None, "note", filled_by="extractor")
    changed: str | None = spec("text", None, "note", required=False, filled_by="extractor")      # empty if nothing changed
    planted: str | None = spec("text", None, "note", required=False, filled_by="extractor")      # at most one per chapter
    paid_off: list[str] | None = spec("select-multiple", None, "note", required=False, max_selected=MAX_OPEN_PLANTS,
                                      ref=["summary_events.entries"], filled_by="extractor")     # entries whose plant was resolved here
    reveals_landed: list[str] | None = spec("select-multiple", None, "note", required=False, max_selected=5,
                                            ref=["world.rules"], filled_by="extractor")
    behaviors_seen: list[str] | None = spec("select-multiple", None, "note", required=False, max_selected=5,
                                            ref=["characters.behaviors"], filled_by="extractor")
    things_seen: list[str] | None = spec("select-multiple", None, "note", required=False, max_selected=5,
                                         ref=["world.objects"], filled_by="extractor")
    entanglements_shown: list[str] | None = spec("select-multiple", None, "note", required=False,
                                                 ref=["entanglements.pressures", "entanglements.knowledge", "entanglements.ties", "entanglements.holdings"],
                                                 filled_by="extractor")     # the pressures, knowledge, ties and holdings the chapter actually showed
    goal_landed: bool = spec("checkbox", None, "note", required=False, default=False, filled_by="extractor")   # the beat's goal change actually happened in the text


class SummaryEvents(Item):
    entries: list[EventsEntry] = spec(None, "entries", "pairs", repeat=True, uncapped=True)


EVENTS_RULES = [
    Rule(id="events_beat_unique", severity="block", fields=["entries"],
         when="two entries are for the same chapter (the same beat)",
         check="unique_across_items", params={"field": "beat"}),
    Rule(id="open_plants_max", severity="block", fields=["entries"],
         when="more than two plants are open at once (a plant is open from the chapter that plants it until a later chapter pays it off)",
         check="open_plants_max", params={"max": MAX_OPEN_PLANTS}),
    Rule(id="paid_off_valid", severity="block", fields=["entries"],
         when="a payoff points at an entry that planted nothing, is not earlier, or was already paid off",
         check="paid_off_valid"),
    Rule(id="events_link_broken", severity="block", fields=["entries"],
         when="a beat, rule, behavior or thing pointed to no longer exists",
         check="ref_exists", context=["beat_ids", "world_item_ids", "behavior_ids"]),
    Rule(id="changed_is_one_sentence", severity="warn", fields=["entries"],
         when="the changed line is longer than one short sentence",
         needs_model=True),
]

# ---------------------------------------------------------------- Inner shifts
SHIFTS_CARD = {
    "id": "summary_shifts",
    "type": "record",
    "reads": ["chapter_text", "characters", "entanglements"],
    "portable": False,
    "between_chapters": "per_chapter",
    "hidden": True,
    "sent_to_model": True,
}
SHIFTS_GROUPS = [{"id": "entries", "collapsed": False}]
SHIFTS_RENDER_ORDER = [["shifts"]]
SHIFT_TEXT = ["believes", "fears", "wants", "refuses", "decided"]


class CharacterShift(Item):
    """One character who moved in one chapter. Only characters who moved, only changes that matter."""
    beat: str = spec("select", None, "note", ref=["outline.beats"], filled_by="code")      # which chapter; its number lives on the beat
    character: str = spec("select", None, "note", ref=["characters"], filled_by="extractor")
    believes: str | None = spec("text", None, "note", required=False, filled_by="extractor")
    fears: str | None = spec("text", None, "note", required=False, filled_by="extractor")
    wants: str | None = spec("text", None, "note", required=False, filled_by="extractor")
    refuses: str | None = spec("text", None, "note", required=False, filled_by="extractor")
    decided: str | None = spec("text", None, "note", required=False, filled_by="extractor")


class SummaryShifts(Item):
    shifts: list[CharacterShift] = spec(None, "entries", "pairs", repeat=True, uncapped=True)


SHIFTS_RULES = [
    Rule(id="shift_not_empty", severity="block", fields=["shifts"],
         when="a character entry has none of: believes, fears, wants, refuses, decided",
         check="at_least_one", params={"fields": SHIFT_TEXT}),
    Rule(id="shift_unique_per_chapter", severity="block", fields=["shifts"],
         when="the same character appears twice in one chapter",
         check="unique_across_items", params={"fields": ["beat", "character"]}),
    Rule(id="shifts_per_chapter_max", severity="block", fields=["shifts"],
         when="more than five characters are recorded for one chapter",
         check="max_per_group", params={"group_by": "beat", "max": 5}),
    Rule(id="shifts_link_broken", severity="block", fields=["shifts"],
         when="a beat or character pointed to no longer exists",
         check="ref_exists", context=["beat_ids", "character_ids"]),
    Rule(id="shift_is_a_change", severity="warn", fields=["shifts"],
         when="an entry states a standing trait instead of something that changed this chapter",
         needs_model=True),
]

# ---------------------------------------------------------------- Entanglements history
HISTORY_CARD = {
    "id": "entanglements_history",
    "type": "record",
    "reads": ["entanglements"],
    "portable": False,
    "between_chapters": "per_chapter",
    "hidden": True,
    "sent_to_model": False,
}
HISTORY_GROUPS = [{"id": "entries", "collapsed": False}]
HISTORY_RENDER_ORDER: list = []


class ChapterState(Item):
    """Entanglements as the chapter was written from: the values the user saw when pressing generate. There is no
    chapter 0. The current Entanglements is the result of the latest chapter and is not compared with this record."""
    beat: str = spec("select", None, "note", ref=["outline.beats"], filled_by="code")      # which chapter; its number lives on the beat
    state: Entanglements = spec(None, None, "snapshot", snapshot_of="entanglements", filled_by="code")


class EntanglementsHistory(Item):
    states: list[ChapterState] = spec(None, "entries", "pairs", repeat=True, uncapped=True)


HISTORY_RULES = [
    Rule(id="history_beat_unique", severity="block", fields=["states"],
         when="two snapshots are for the same chapter (the same beat)",
         check="unique_across_items", params={"field": "beat"}),
]
