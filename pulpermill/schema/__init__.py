"""
schema_v2.py  --  Pulpermill story cards, v2

DEPENDENCY ORDER (each card may only read cards to its left):

    Style  <-  Characters  <-  World  <-  Outline

  * Style      : portable narration style. No names, no plot, no world nouns.
  * Characters : who people are, written to hold in any story. No object or
                 location ids, no plot, no future arc, and no reference to
                 another character.
  * World      : rules, hidden truths, places, objects, groups. May point at
                 characters by id (owner, known_by). Never holds story events.
  * Outline    : what happens and how characters change. May point at everything.

PORTABLE CHARACTERS
  A Character is authored once, reviewed by the human and never edited by
  Pulpermill afterwards: it holds who the person is, never what has happened to
  them. What happens to people during a story is carried by the chapter
  summaries, the beats and the World's live values, so a card can be taken out
  of one project and dropped into another. The World is fully authored: the
  model never adds entries to it. Only three things in it change during a
  story: an object's owner, an object's location, and a truth's known_by.

HIDDEN TRUTHS
  The outline decides when each truth is revealed (ChapterBeat.reveals). After
  that chapter, code adds everyone in the beat's `present` list to the truth's
  known_by. The model is never asked to judge who learned what.

MODEL-FACING vs HUMAN-FACING TEXT
  `description=` on a Field is a PROMPT HINT and is sent to the model.
  Human help notes live in the HTML UI only and never enter a prompt.
  Hints are written as plain instructions so they cannot double as answers.
  Put worked examples in the prompt builder (different genre), not here.

MODEL vs CODE
  Models generate the *Draft classes. Code assigns ids and resolves names.
  The model is never asked to invent an id.
"""

from .common import (
    Msg,
    M,
    to_json,
    _CJK,
    _CJK_RE,
    _WORD_RE,
    count_units,
    est_words,
    squash,
    similar,
    DUPLICATE_SIMILARITY,
    DUPLICATE_MIN_CHARS,
    MAX_CHARACTERS,
    MAX_CAST,
    MAX_CHAPTERS,
    MAX_CHAPTER_NUM,
    logger,
    POOLS,
    _lenient_uses,
    UsesMap,
    _pooled,
    clean_uses,
    _shown,
    pick_least_used,
    _beat_seq,
    _mentions,
    slugify,
    unique_ids,
    _TITLES,
    _TITLES_ZH,
    _tokens,
    _name_tokens,
    Resolver,
    _as_dicts,
    _words,
    _PAYOFF_STOP,
    _content_words,
    _related,
)
from .style import (
    DESIGN_ANCHORS,
    DIAL_FIELDS,
    LADDERS,
    POV,
    Dial,
    Tense,
    StyleCard,
    ladder_name,
    ladder_text,
    ladders_for_prompt,
)
from .characters import (
    PORTRAIT_FIELDS,
    CharacterDraft,
    CastDraft,
    CharacterCard,
    finalize_cast,
)
from .world import (
    LocationDraft,
    ObjectDraft,
    GroupDraft,
    TruthDraft,
    WorldDraft,
    Location,
    WorldObject,
    Group,
    HiddenTruth,
    WorldBible,
    WORLD_TARGETS,
    finalize_world,
)
from .outline import (
    Shift,
    STORY_STAGES,
    LAST_STAGE,
    spread_stages,
    _NUM_WORDS,
    _ZH_DIGITS,
    _zh_number,
    chapter_count_in,
    stages_valid,
    STAGE_FIELD_DOC,
    stage_lines_for,
    ChapterBeat,
    CharacterArc,
    PlotOutline,
    ShiftD,
    BeatD,
    ArcD,
    NextBeatD,
    OutlineDraft,
    OutlineResult,
    finalize_outline,
    _BEAT_STOP,
    _gist,
    beat_similarity,
    BEAT_CLASH,
    finalize_next_beat,
)
from .story import StoryProject
from .updates import (
    ObjectMove,
    PlaceUpdate,
    ThingUpdate,
    GroupUpdate,
    UnintroducedCharacter,
    StateUpdate,
    apply_state_update,
)
from .checks import (
    check_style,
    check_characters,
    check_world,
    check_outline,
    check_markdown_leak,
    validate_project,
)
from .hints import REFS, CHOICES, GENERATOR_HIDDEN, ui_hints
