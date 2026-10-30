"""Pipeline record made while a chapter is generated, so an unfinished story can resume and a chapter can be redone.
Hidden from the user and never edited by hand. One entry per chapter, found through the chapter's beat (a beat link,
never a stored chapter number); regenerating a chapter replaces its entry as a whole, keeping its id. One card:
  summary_events        what happened (the outer story), plus the changed line
What changed for the cards (characters, world, ties) is the shifts record, see shifts.py."""
from .common import spec, Rule, Item

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


class SummaryEvents(Item):
    entries: list[EventsEntry] = spec(None, "entries", "pairs", repeat=True, uncapped=True)


EVENTS_RULES = [
    Rule(id="events_beat_unique", severity="block", fields=["entries"],
         when="two entries are for the same chapter (the same beat)",
         check="unique_across_items", params={"field": "beat"}),
    Rule(id="events_link_broken", severity="block", fields=["entries"],
         when="a beat pointed to no longer exists",
         check="ref_exists", context=["beat_ids"]),
    Rule(id="changed_is_one_sentence", severity="warn", fields=["entries"],
         when="the changed line is longer than one short sentence",
         needs_model=True),
]
