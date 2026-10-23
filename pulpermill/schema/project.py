"""Project: the save-and-load file. One project is one story in progress or finished.
Not a card: the user never sees it as a form. It holds every card, the written chapters, the end-of-story
copy, the generation inputs the user gave (example chapter, per-card notes) and the field locks, so a user
or the pipeline can stop mid-story and resume from the file alone.
Written out and read back as JSON (Project.model_dump_json / model_validate_json); ids survive the round trip."""
from typing import Literal
from .common import spec, Rule, Item, TextItem
from .style import Style
from .characters import Characters
from .world import World
from .entanglements import Entanglements
from .setup import Setup
from .outline import Outline
from .summaries import SummaryEvents, SummaryShifts, EntanglementsHistory

SCHEMA_VERSION = 1          # bump when the file format changes, so older files can be recognised and migrated

# Which project field holds each registered card (checked by a test so a new card cannot be forgotten).
CARD_FIELDS = {
    "style": "style",
    "characters": "characters",          # a list: a project holds any number of characters
    "world": "world",
    "entanglements": "entanglements",    # the current state; history keeps the state each chapter was written from
    "setup": "setup",
    "outline": "outline",
    "summary_events": "summary_events",
    "summary_shifts": "summary_shifts",
    "entanglements_history": "entanglements_history",
}


# The cards a user fills in (everything except the hidden records). Notes and locks point at these.
UserCard = Literal["style", "characters", "world", "entanglements", "setup", "outline"]


class CardNote(Item):
    """Free-form text the user pastes to describe one card, kept so the model can fill that card in.
    Characters is many per project, so a note for it names the character it is about."""
    card: UserCard = spec("select", None, "note")
    character: str | None = spec("select", None, "note", required=False, ref=["characters"])   # only when card is "characters"
    text: str = spec("textarea", None, "note")


class Lock(Item):
    """A lock the user puts on something editable: while it exists no one can change the value, the human included
    (removing the lock is how it is edited again).
    It reads from the outside in: card, then (for Characters) which character, then a field, then one list item
    in that field, then one box inside that item. Each level left empty means the lock covers everything beneath
    it, so card alone locks the whole card, and card + field locks a whole list."""
    card: UserCard = spec("select", None, "note")
    owner: str | None = spec("select", None, "note", required=False, ref=["characters"])   # only when card is "characters"
    field: str | None = spec("text", None, "note", required=False)       # a field key on the card
    item: str | None = spec("text", None, "note", required=False)        # the id of one list item in that field
    part: str | None = spec("text", None, "note", required=False)        # a box key inside that item


class Chapter(Item):
    """The written text of one chapter, found through its beat (the chapter number lives only on the beat).
    Regenerating a chapter replaces its text and its records and reuses its beat; every later beat is marked stale."""
    beat: str = spec("select", None, "note", ref=["outline.beats"], filled_by="code")
    text: str = spec("textarea", None, "note", filled_by="writer")


class AfterStory(Item):
    """The end-of-story copy: the portable root cards updated to reflect what happened. The originals stay
    untouched in the project, so a new story can start fresh or from this copy. The user can download it."""
    style: Style = spec(None, None, "card", card_of="style", filled_by="code")
    characters: list[Characters] = spec(None, None, "card", repeat=True, uncapped=True, card_of="characters", filled_by="code")
    world: World = spec(None, None, "card", card_of="world", filled_by="code")


# ---- What the model said, kept so the user can read it again after reopening the file -------------------------
# Display records: the page shows them and nobody edits them. They are never sent to a model, and the pipeline does not
# read them. Each is replaced as a whole when the thing it is about is made again, and goes when that thing goes.

class PlanNote(Item):
    """How the planner thought about one chapter, shown to the user. Planning the chapter again replaces it."""
    beat: str = spec("select", None, "note", ref=["outline.beats"], filled_by="code")
    thinking: str = spec("textarea", None, "note", filled_by="planner")
    retried: bool = spec("checkbox", None, "note", required=False, default=False, filled_by="code")   # the first try broke a rule


class ChangeLine(Item):
    """One value the chapter changed in Entanglements, as the user was shown it (words, not ids)."""
    label: str = spec("text", None, "note", filled_by="code")
    before: str | None = spec("text", None, "note", required=False, filled_by="code")
    after: str | None = spec("text", None, "note", required=False, filled_by="code")


class ChapterNote(Item):
    """What the page showed the user when a chapter was made: the changes it applied to Entanglements and what it noticed.
    `before` is the chapter's text from before it was written again (only on a chapter that was), shown beside the new one."""
    chapter: str = spec("select", None, "note", ref=["chapters"], filled_by="code")
    changes: list[ChangeLine] = spec(None, None, "pairs", required=False, default=[], repeat=True, uncapped=True)
    warnings: list[TextItem] = spec(None, None, "pairs", required=False, default=[], repeat=True, uncapped=True)
    before: str | None = spec("textarea", None, "note", required=False, filled_by="code")


class ForcedFields(Item):
    """Fixed fields of one character that the model changed at the end of the story and the page put back."""
    character: str = spec("text", None, "note", filled_by="code")      # the name as the user saw it
    fields: str = spec("text", None, "note", filled_by="code")         # the fields' keys, separated by commas


class EndNote(Item):
    """What the page noticed about the end-of-story copy: fixed fields put back, fields dropped because they did not fit,
    and how many problems the copy has that its card would stop generating on."""
    forced: list[ForcedFields] = spec(None, None, "pairs", required=False, default=[], repeat=True, uncapped=True)
    dropped: str | None = spec("text", None, "note", required=False, filled_by="code")     # field keys, separated by commas
    problems: int = spec("number", None, "note", required=False, default=0, filled_by="code")
    # A short fingerprint of the written chapters the copy was made from. The page compares it with the chapters as they are
    # now, and says the copy may be out of date when they differ. Display only; a note without it is never called out of date.
    made_from: str | None = spec("text", None, "note", required=False, filled_by="code")


class Project(Item):
    # About the file
    title: str = spec("text", "about", "note")
    schema_version: int = spec("number", "about", "note", filled_by="code")
    output_language: str = spec("text", "about", "note")        # the same setting as the UI language; passed to the writer, never stored on a card

    # What the user gave the model to fill cards from. Both are optional, but the model may only fill a card
    # when there is an example chapter or a note for that card.
    example_chapter: str | None = spec("textarea", "generation", "note", required=False)
    card_notes: list[CardNote] = spec(None, "generation", "pairs", required=False, default=[], repeat=True, uncapped=True)

    # The cards, as they stand now
    style: Style = spec(None, "cards", "card", card_of="style")
    characters: list[Characters] = spec(None, "cards", "card", repeat=True, uncapped=True, card_of="characters")
    world: World = spec(None, "cards", "card", card_of="world")
    setup: Setup = spec(None, "cards", "card", card_of="setup")
    entanglements: Entanglements = spec(None, "cards", "card", card_of="entanglements")
    outline: Outline = spec(None, "cards", "card", card_of="outline")

    # Records
    summary_events: SummaryEvents = spec(None, "records", "card", card_of="summary_events")
    summary_shifts: SummaryShifts = spec(None, "records", "card", card_of="summary_shifts")
    entanglements_history: EntanglementsHistory = spec(None, "records", "card", card_of="entanglements_history")

    # The story
    chapters: list[Chapter] = spec(None, "story", "pairs", repeat=True, uncapped=True)
    after_story: AfterStory | None = spec(None, "story", "card", required=False, card_of="after_story")

    # What the model said (display only; see PlanNote)
    plan_notes: list[PlanNote] = spec(None, "notes", "pairs", required=False, default=[], repeat=True, uncapped=True)
    chapter_notes: list[ChapterNote] = spec(None, "notes", "pairs", required=False, default=[], repeat=True, uncapped=True)
    end_note: EndNote | None = spec(None, "notes", "card", required=False, card_of="end_note")

    # Locks on what the user edits (the UI sets them; they say nothing about the story itself)
    locks: list[Lock] = spec(None, "locks", "pairs", required=False, default=[], repeat=True, uncapped=True)


# Integrity checks run when a file is loaded or saved. They have no user wording: a failure means a damaged
# or half-saved file, reported to the pipeline. Descriptions are for people reading the schema.
PROJECT_RULES = [
    Rule(id="chapter_sequence", severity="block", fields=["chapters", "outline", "setup"],
         when="beat numbers do not start at 1 without gaps, there are more beats than Setup's chapter count, "
              "a chapter's beat does not exist, or two chapters share a beat",
         check="chapter_sequence"),
    Rule(id="chapter_markers", severity="block", fields=["chapters", "summary_events", "entanglements_history"],
         when="a written chapter is missing its events entry, its history snapshot or (when anyone moved) its shifts. "
              "The backend is stateless and the page commits a chapter with all its records as one unit, so a chapter is "
              "either complete or does not exist; a failed call leaves nothing behind and is redone by pressing generate again",
         check="chapter_markers"),
    Rule(id="links_resolve", severity="block",
         fields=["characters", "world", "setup", "entanglements", "outline", "summary_events", "summary_shifts",
                 "entanglements_history", "chapters", "card_notes", "plan_notes", "chapter_notes", "locks"],
         when="a link in any card, note or lock points at something that does not exist in this project (for example a protagonist who is not among the characters)",
         check="links_resolve"),
    Rule(id="after_story_ready", severity="block", fields=["after_story", "chapters", "setup"],
         when="an end-of-story copy exists before every chapter up to Setup's chapter count is written",
         check="after_story_ready"),
    Rule(id="after_story_ids_match", severity="block", fields=["after_story", "characters", "world"],
         when="the updated characters and world do not keep the ids of the originals (so links and comparisons stay meaningful)",
         check="ids_match"),
    Rule(id="note_character_for_characters", severity="block", fields=["card_notes"],
         when="a note for the Characters card does not say which character it is about",
         check="required_if", params={"field": "character", "when": {"card": "characters"}}),
    Rule(id="note_unique_per_target", severity="block", fields=["card_notes"],
         when="two notes are for the same card (or, for Characters, the same character)",
         check="unique_across_items", params={"fields": ["card", "character"]}),
    Rule(id="plan_note_unique", severity="block", fields=["plan_notes"],
         when="two plan notes are for the same beat",
         check="unique_across_items", params={"fields": ["beat"]}),
    Rule(id="chapter_note_unique", severity="block", fields=["chapter_notes"],
         when="two chapter notes are for the same chapter",
         check="unique_across_items", params={"fields": ["chapter"]}),
    Rule(id="lock_item_needs_field", severity="block", fields=["locks"],
         when="a lock names a list item without the field the item is in",
         check="required_if", params={"field": "field", "when_present": "item"}),
    Rule(id="lock_part_needs_item", severity="block", fields=["locks"],
         when="a lock names a box inside an item without naming the item",
         check="required_if", params={"field": "item", "when_present": "part"}),
    Rule(id="lock_unique", severity="block", fields=["locks"],
         when="the same thing is locked twice",
         check="unique_across_items", params={"fields": ["card", "owner", "field", "item", "part"]}),
    Rule(id="lock_target_exists", severity="block", fields=["locks"],
         when="a lock points at a card, field, list item or box that does not exist (an edit removed it)",
         check="lock_target_exists", context=["card_fields", "item_ids"]),
]
