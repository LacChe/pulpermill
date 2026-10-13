"""
schema_v2.py  --  Pulpermill story cards, v2

DEPENDENCY ORDER (each card may only read cards to its left):

    Style  <-  Characters  <-  World  <-  Outline

  * Style      : portable narration style. No names, no plot, no world nouns.
  * Characters : who people are. No object/location ids, no future arc.
                 Characters may refer to each other (by name while authoring).
  * World      : rules, hidden truths, places, objects, groups. May point at
                 characters by id (owner, known_by). Never holds story events.
  * Outline    : what happens and how characters change. May point at everything.

CORE + LIVE STATE
  Every Character has an authored CORE (reviewed by the human, edited by
  nobody afterwards) and a WRAP: live state that Pulpermill updates after each
  chapter (model-added wrap lists keep only the most recent 5). The World is
  fully authored: the model never adds entries to it. Only three things in it
  change during a story: an object's owner, an object's location, and a
  truth's known_by.

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
    RECENT_N,
    DUPLICATE_SIMILARITY,
    SAME_CHARACTER_SIMILARITY,
    MAX_HABITS,
    DUPLICATE_MIN_CHARS,
    MAX_CHARACTERS,
    MAX_CAST,
    MAX_CHAPTERS,
    MAX_CHAPTER_NUM,
    logger,
    _keep_recent,
    Recent,
    push_recent,
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
from .style import POV, Tense, StyleCard
from .characters import (
    Attitude,
    CharacterDraft,
    CastDraft,
    CharacterWrap,
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
    CharacterUpdate,
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
