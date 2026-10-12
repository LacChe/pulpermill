"""The chapter engine. STATELESS: everything a chapter needs arrives in the request and everything that changed goes back in the result. Nothing is read from or written to disk, so a Kaggle restart loses nothing but the chapter in flight."""

import json
import re
from pydantic import ValidationError

from . import config, generation, model, runtime
from .runtime import Cancelled, LLM_LOCK, logger
from .prompts import (
    EXTRACT_STATE_UPDATE_PROMPT, EXTRACT_STATE_UPDATE_RETRY_SUFFIX, GENERATE_CHAPTER_PROMPT,
    SUMMARIZE_CHAPTER_PROMPT, WRITER_TAIL_CHARS, language_head, next_beat_prompt
)
from .stages import lang_post
from .schema import (
    Location, M, MAX_CAST, Msg, NextBeatD, Resolver, StateUpdate, StoryProject, _content_words, apply_state_update,
    count_units, est_words, finalize_next_beat, squash, validate_project
)


def _lang(code):
    return config.LANGUAGES.get(code) or config.LANGUAGES["en"]


def _why(e):
    """The message of an exception, keeping it translatable when it carries one."""
    return e.args[0] if e.args and isinstance(e.args[0], Msg) else (generation.friendly_error(e) or str(e))


_SENTENCE_END = re.compile(r"[.!?…。！？][\"'”’」』）)\]]*$")    # . ! ? … 。！？ and any closing quote or bracket after it


def summary_cut_off(text, finish):
    """True when a summary ran into the token limit and stops before the end of its last sentence. A summary that hit the limit
    but ended on a full stop is complete as it stands."""
    return finish == "length" and not _SENTENCE_END.search(text)


def summarize_chapter(chapter_text, chapter_num, language="en", narrator=""):
    """3-5 sentence continuity summary. It is the only record of ordinary story events (and of who learned what),
    since the world card tracks only object owners and locations and who knows each hidden truth. A summary that is cut off in the
    middle of a sentence is written again, up to config.SUMMARY_RETRIES times, each time with a different seed; if every try is cut
    off, the longest one is kept, as before."""
    prompt = SUMMARIZE_CHAPTER_PROMPT.format(chapter_num=chapter_num, chapter_text=chapter_text, language=_lang(language)["name"],
                                           narrator=narrator or "the point-of-view character")
    tries = max(config.SUMMARY_RETRIES, 0) + 1
    best = ""
    for attempt in range(tries):
        label = f"chapter {chapter_num} summary" + (f" (try {attempt + 1})" if attempt else "")
        # the first try is exactly what it always was; a retry adds the job's seed shifted by the try number
        raw, finish = generation.llm_text([{"role": "user", "content": prompt}], label,
                                          **config.SUMMARY_GEN, **(runtime.seed_kw(attempt) if attempt else {}))
        # Strip markdown noise; underscores are left alone so snake_case ids in the text survive.
        text = re.sub(r"[*#]{1,3}", "", raw.strip()).strip()
        if not summary_cut_off(text, finish):
            return text
        best = max(best, text, key=len)
        again = f"; writing it again with another seed (try {attempt + 2} of {tries})" if attempt + 1 < tries else ""
        logger.warning("Chapter %d summary stopped at the %s-token limit in the middle of a sentence%s",
                       chapter_num, config.SUMMARY_GEN.get("max_tokens"), again)
    if tries > 1:
        logger.warning("Chapter %d summary: all %d tries were cut off; keeping the longest, which may end mid-sentence", chapter_num, tries)
    return best


def generate_chapter(story, chapter_num, chapter_summaries, last_chapter_text, target_words, progress=None, language="en",
                     note="", feed=None, prev_changes=None):
    """Returns (text, finish_reason, prompt_tokens). Streams, so the page can show how far along the chapter is.
    Logs the real prompt size so the context budget is checked against n_ctx instead of estimated.

    `prev_changes` is the plain-fact "what changed" list the state-update step already produced after the previous
    chapter (empty or None for chapter 1). It carries the facts of what happened in full; the chapter's own prose is
    given only as a short tail (WRITER_TAIL_CHARS), for voice and to physically pick the scene back up — not reread in
    full, which only invited the writer to rephrase it instead of moving the story forward."""
    context = story.context_for_chapter(chapter_num, feed)
    beat_block = story.render_beat(chapter_num)
    named_cast = ", ".join(c.name for c in story.characters)
    prior_summary_block = (
        "\n".join(f"Chapter {i + 1}: {s}" for i, s in enumerate(chapter_summaries))
        if chapter_summaries else "(no prior chapters)"
    )
    last_chapter_tail = (last_chapter_text.strip()[-WRITER_TAIL_CHARS:]
                         if last_chapter_text and last_chapter_text.strip() else "(chapter 1, no prior text)")
    changes_block = ("\n".join(f"- {c}" for c in prev_changes) if prev_changes else
                     "(chapter 1, nothing yet)" if chapter_num == 1 else "(nothing notable changed)")

    note_block = (f"\nTHE AUTHOR READ THE LAST VERSION OF THIS CHAPTER AND ASKED FOR THIS CHANGE: {note.strip()}\n"
                  "Write a genuinely different version that applies the change, without breaking the beat above or the "
                  "cards.\n") if note and note.strip() else ""
    prompt = GENERATE_CHAPTER_PROMPT.format(
        chapter_num=chapter_num, target_words=target_words, named_cast=named_cast, beat_block=beat_block,
        context=context, prior_summary_block=prior_summary_block, changes_block=changes_block,
        last_chapter_tail=last_chapter_tail, note_block=note_block,
        language=_lang(language)["name"], unit=_lang(language)["unit"],
    )

    max_tokens = int(target_words * config.CHAPTER_TOKENS_PER_WORD)
    prompt_tokens = len(runtime.llm.tokenize(prompt.encode("utf-8")))
    n_ctx = runtime.llm.n_ctx()
    room = n_ctx - prompt_tokens
    logger.info("Chapter %d prompt: %d tokens (context %d tokens, cards %d chars, previous chapter %d chars); "
                "%d tokens left for generation, max_tokens=%d",
                chapter_num, prompt_tokens, n_ctx, len(context), len(last_chapter_tail), room, max_tokens)
    if room < target_words * config.CHAPTER_MIN_ROOM_PER_WORD:
        raise ValueError(M("too much to send: chapter {n}'s prompt is {prompt} tokens, which leaves {room} for writing, "
                           "and a {target}-word chapter needs about {need}. Lower the target word count or shorten the cards.",
                           n=chapter_num, prompt=f"{prompt_tokens:,}", room=f"{max(room, 0):,}", target=f"{target_words:,}",
                           need=f"{int(target_words * config.CHAPTER_MIN_ROOM_PER_WORD):,}"))
    if room < max_tokens:
        logger.warning("Chapter %d: only %d tokens of room but max_tokens=%d; the end may be cut off by the "
                       "context limit", chapter_num, room, max_tokens)
        max_tokens = room

    text, finish = generation.llm_text([{"role": "user", "content": prompt}], f"chapter {chapter_num}",
                            progress=(lambda t: progress(words=count_units(t))) if progress else None,
                            max_tokens=max_tokens, **{**config.CHAPTER_GEN, **_lang(language).get("gen", {})})
    text = text.strip()
    if progress:
        progress(words=count_units(text))
    return text, finish, prompt_tokens


def check_copied_lines(story, chapter_text):
    """Logs, never rejects: character sample lines and style exemplar sentences that appear word for word in
    the chapter (the writer is told never to reuse them). Returns what it found."""
    hay = squash(chapter_text)
    found = []
    for c in story.characters:
        for line in c.sample_lines:
            if est_words(line) >= 3 and squash(line) in hay:
                found.append(M("{name}'s sample line: {line}", name=c.name, line=repr(line)))
    for ex in story.style.exemplars:
        for sent in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s*", ex):
            if est_words(sent) >= 5 and squash(sent) in hay:
                found.append(M("style exemplar: {line}", line=repr(sent)))
    for f in found:
        logger.warning("Copied from a card, word for word: %s", f)
    return found


_OVERUSE_LABEL = {"habits": M("habit"), "look": M("look")}
HABIT_OVERUSE_MIN = 3        # a habit or look fed for one use that turns up in this many different sentences gets a warning
HABIT_OVERUSE_RATIO = 0.4    # a sentence counts as a reuse of the phrase when it shares at least this share of its content words


def _overuse_words(text):
    """A phrase's content words, filtered harder than the general-purpose `_content_words`: this check is about one
    short phrase recurring, so a stray shared short word ('air', 'even') should not by itself count as a match."""
    return {w for w in _content_words(text) if len(w) >= 4}


def check_habit_overuse(story, chapter_text, feed):
    """Logs, never rejects: a habit or look handed to this chapter for one use (see POOLS) that instead turns up again
    and again. The writer is told to use each at most once; nothing stops a vivid one (a coin, a pen) from being reached
    for every time the character appears. A sentence counts as a reuse when it shares a real share of the phrase's own
    content words (HABIT_OVERUSE_RATIO), which catches the common case of a weaker model repeating a card's phrase
    near-verbatim, but will not catch every paraphrase: a habit written as 'warms a coin' that the chapter reworks into
    an invented prop ('a sovereign') shares no words with the card and is not something this check can see. Phrases of
    fewer than two sturdy (4+ letter) content words are skipped, since a single shared word is not a reliable signal."""
    sentences = [s for s in re.split(r"(?<=[.!?。！？])\s+", chapter_text) if s.strip()]
    sentence_words = [_overuse_words(s) for s in sentences]
    found = []
    for cid, fields in (feed or {}).get("characters", {}).items():
        c = next((x for x in story.characters if x.id == cid), None)
        if c is None:
            continue
        for field in ("habits", "look"):
            for phrase in fields.get(field, []):
                words = _overuse_words(phrase)
                if len(words) < 2:
                    continue
                hits = sum(1 for sw in sentence_words if sw and len(sw & words) / len(words) >= HABIT_OVERUSE_RATIO)
                if hits >= HABIT_OVERUSE_MIN:
                    found.append(M("{name}'s {field} '{phrase}' shows up in about {n} different sentences in this "
                                   "chapter; the cards ask for it once", name=c.name, field=_OVERUSE_LABEL[field],
                                   phrase=phrase, n=hits))
    for f in found:
        logger.warning("Habit or look used far more than once: %s", f)
    return found


def _character_block(c):
    """One character as the extractor should see them: the authored core (minus voice and sample
    lines, which never produce facts) plus current wrap, so it can tell what is already established."""
    core = c.model_dump(exclude={"wrap", "id", "voice", "sample_lines", "uses"})
    state = {"condition": c.wrap.condition, "recent_changes": c.wrap.recent_changes,
             "recent_details": c.wrap.recent_details}
    return (f"- {c.id} ({c.name})\n  CARD: {json.dumps(core, ensure_ascii=False)}\n"
            f"  CURRENT STATE: {json.dumps(state, ensure_ascii=False)}")


def extract_state_update(story, chapter_text, chapter_num, retries=None, language="en"):
    """Ask the model for a structured StateUpdate describing what changed. On a validation failure the error is
    shown back to the model and it gets another attempt, up to `retries` extra tries."""
    if retries is None:
        retries = config.EXTRACT_RETRIES               # read when called, so a changed setting applies
    schema_json = json.dumps(StateUpdate.model_json_schema(), indent=2)
    known_characters = "\n".join(_character_block(c) for c in story.characters)
    known_objects = "\n".join(
        f"- {o.id}: {o.name}: {o.description} (owner={o.owner}, location={o.location})" for o in story.world.objects) or "(none yet)"
    known_locations = "\n".join(f"- {l.id}: {l.name}: {l.description}" for l in story.world.locations) or "(none yet)"
    known_groups = "\n".join(f"- {g.id}: {g.name}: {g.description} Wants: {g.wants}" for g in story.world.groups) or "(none)"
    base_prompt = EXTRACT_STATE_UPDATE_PROMPT.format(
        schema=schema_json, known_characters=known_characters, known_objects=known_objects,
        known_locations=known_locations, known_groups=known_groups, chapter_num=chapter_num, chapter_text=chapter_text,
        language=_lang(language)["name"])

    prompt, last_error, cut_off = base_prompt, None, False
    for attempt in range(1, retries + 2):
        raw, finish = generation.llm_text([{"role": "user", "content": prompt}], f"chapter {chapter_num} state update (try {attempt})", **config.EXTRACT_GEN, **runtime.seed_kw(attempt - 1))
        try:
            return StateUpdate.model_validate(generation.extract_json(raw))
        except Exception as e:
            logger.warning("State update attempt %d/%d failed to validate: %s", attempt, retries + 1, e)
            generation.log_bad_reply(f"chapter {chapter_num} state update (try {attempt})", raw, finish, e)
            last_error, cut_off = e, finish == "length"
            # Each retry restates the original prompt plus the specific failure, not stacked corrections.
            prompt = base_prompt + EXTRACT_STATE_UPDATE_RETRY_SUFFIX.format(error=str(e)[:config.RETRY_ERROR_CHARS])
    if cut_off:                                  # the last reply ran into the token limit: say that, not "did not validate"
        raise ValueError(M("chapter {n}: the state update hit the {limit}-token limit before it was complete, after {tries} attempt(s)",
                           n=chapter_num, limit=config.EXTRACT_GEN.get("max_tokens"), tries=retries + 1)) from last_error
    raise ValueError(M("chapter {n}: state update did not validate after {tries} attempt(s)", n=chapter_num, tries=retries + 1)) from last_error


class _BeatReq:
    """What tail() and the language checks read from a request, for a planner call that has no request of its own."""
    def __init__(self, language="en"):
        self.language, self.feedback, self.mode = language, None, "notes"


def plan_next_beat(story, n, summaries, prev_text, language="en"):
    """Writes chapter n's beat and attaches it to `story`: new places go on the World card and any revisions of the setup are
    applied to the plot. A beat that repeats an earlier chapter gets one more try with that told to the model. Returns the
    notes for the author."""
    req = _BeatReq(language)
    base = next_beat_prompt(story, n, summaries, prev_text, language)
    schema = f"\n\nSCHEMA:\n{json.dumps(NextBeatD.model_json_schema())}" + ("" if language == "en" else f"\n\nREMINDER: write every text value in {_lang(language)['name']}.")

    def once(extra=""):
        got = {}

        def post(d):
            got["beat"], got["notes"], got["new"], got["changes"] = finalize_next_beat(d, story, n)
            return d
        generation.structured_call(language_head(req) + base + extra + schema, NextBeatD, max_tokens=config.MAX_TOKENS["beat"], temperature=config.TEMPS["beat"],
                        min_tokens=config.MIN_TOKENS["beat"], post=lang_post(req, post))
        return got

    got = once()
    story.plot.chapter_beats.append(got["beat"])                      # so the repeat check sees the new beat next to the old ones
    clash = story.beat_clash(got["beat"])
    story.plot.chapter_beats.remove(got["beat"])
    if clash:
        k = clash[0]
        again = once(f"\n\nYOUR FIRST PLAN FOR THIS CHAPTER REPEATED CHAPTER {k}: {got['beat'].goal} {got['beat'].turn}\n"
                     f"Write a different chapter: another situation, other people or a different kind of obstacle, with a `turn` that "
                     f"is not about the same thing.")
        got = again
        story.plot.chapter_beats.append(got["beat"])
        still = story.beat_clash(got["beat"])
        story.plot.chapter_beats.remove(got["beat"])
        if still:
            got["notes"] = [*got["notes"], M("chapter {n} may repeat chapter {k}; check its beat", n=n, k=still[0])]
    story.plot.chapter_beats.append(got["beat"])
    story.plot.chapter_beats.sort(key=lambda b: b.chapter_num)
    for loc in got["new"]:
        story.world.locations.append(Location(**loc))
    for field, value in got["changes"].items():
        setattr(story.plot, field, value)
    return got["notes"]


def build_story(cards):
    missing = [k for k in ("style", "characters", "world", "outline") if not (cards or {}).get(k)]
    if missing:
        raise ValueError(M("missing cards: {names}", names=", ".join(missing)))
    try:
        return StoryProject(style=cards["style"], characters=cards["characters"], world=cards["world"],
                            plot=cards["outline"])
    except ValidationError as e:
        bits = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()[:6]]
        raise ValueError(M("the cards do not validate: {why}", why="; ".join(bits))) from e


def cards_dict(story):
    """The four cards in the shape the page keeps them (the outline is called `plot` inside StoryProject)."""
    d = story.model_dump(mode="json")
    return {"style": d["style"], "characters": d["characters"], "world": d["world"], "outline": d["plot"]}


def run_chapter(req, progress=None):
    """One chapter, start to finish. `progress(**fields)` is called with step names and word counts."""
    progress = progress or (lambda **kw: None)
    n = req.chapter_num
    story = build_story(req.cards)
    total = story.plot.total_chapters
    if n < 1 or n > total:
        raise ValueError(M("the story has {total} chapter(s); there is no chapter {n}", total=total, n=n))
    lang = req.language if req.language in config.LANGUAGES else "en"
    warnings = []
    if len(req.summaries) != n - 1:
        raise ValueError(M("chapter {n} needs {k} earlier summary, got {got}", n=n, k=n - 1, got=len(req.summaries)) if n == 2 else
                         M("chapter {n} needs {k} earlier summaries, got {got}", n=n, k=n - 1, got=len(req.summaries)))
    if n > 1 and not req.prev_text.strip():
        raise ValueError(M("chapter {n} needs the text of chapter {prev}", n=n, prev=n - 1))
    # who this chapter is about: the person's choice, with the main character always in. Everyone else does not exist for the model.
    lead = story.plot.protagonist
    chosen = [c for c in dict.fromkeys(req.cast) if story.character_by_id(c)] if req.cast else \
        [c for b in story.plot.chapter_beats if b.chapter_num == n for c in b.present if story.character_by_id(c)]
    selected = list(dict.fromkeys([lead, *chosen]))
    if len(selected) > MAX_CAST:
        if req.cast:
            raise ValueError(M("a chapter can be about at most {max} characters, the main character included; {n} were chosen", max=MAX_CAST, n=len(selected)))
        selected = selected[:MAX_CAST]
    vw = lambda: story.with_cast(selected)          # the project as this chapter sees it
    if not any(b.chapter_num == n for b in story.plot.chapter_beats):      # its beat is normally written when the chapter before ends
        progress(step="planning", tokens=0, max_tokens=0, attempt=1)
        warnings.append(M("Chapter {n} had no beat, so one was written now.", n=n))
        warnings += plan_next_beat(vw(), n, req.summaries, req.prev_text, lang)
    own = next((b for b in story.plot.chapter_beats if b.chapter_num == n), None)
    if own is not None and any(p not in selected for p in own.present):
        progress(step="planning", tokens=0, max_tokens=0, attempt=1)
        warnings.append(M("The beat for chapter {n} named people who are not in this chapter's cast, so it was written again for the cast you chose.", n=n))
        story.plot.chapter_beats = [b for b in story.plot.chapter_beats if b.chapter_num != n]
        warnings += plan_next_beat(vw(), n, req.summaries, req.prev_text, lang)
    card_checks = validate_project(story)
    for problem in card_checks:
        logger.warning("Card check: %s", problem)

    with LLM_LOCK:
        runtime.llm.reset()                               # every chapter starts from an empty context
    progress(step="writing", words=0, target_words=req.target_words, tokens=0, max_tokens=0, attempt=1)
    feed = vw().feed(n)                           # which items of the rotating lists this chapter is handed
    text, finish, prompt_tokens = generate_chapter(vw(), n, req.summaries, req.prev_text, req.target_words, progress, lang,
                                                   req.note or "", feed, getattr(req, "prev_changes", None))
    vw().record_feed(feed)                        # counted before the state update, so a failed update keeps the counts
    words = count_units(text)
    logger.info("Chapter %d generated (~%d words); GPU memory: %s", n, words, model.gpu_report())
    if finish == "length":
        warnings.append(M("The chapter stopped at the length limit, so its ending may be cut off."))
    for line in check_copied_lines(vw(), text):
        warnings.append(M("Copied from a card, word for word: {what}", what=line))
    for line in check_habit_overuse(vw(), text, feed):
        warnings.append(line)

    before = cards_dict(story)
    progress(step="extracting", tokens=0, max_tokens=0, attempt=1)
    changes, unintroduced, update_failed = [], [], False
    try:
        update = extract_state_update(vw(), text, n, language=lang)
        skipped, changes = apply_state_update(vw(), update, n)
        warnings += [M("State update skipped: {why}", why=s) for s in skipped]
        known = Resolver([{"id": x.id, "name": x.name} for x in story.characters])     # "Queen Ann" is not new if "Princess Ann" is in the cast
        unintroduced = [{"name": u.name_mentioned, "role": u.role_hint} for u in update.unintroduced_characters
                        if known.find(u.name_mentioned) is None]
    except Cancelled:
        raise
    except Exception as e:                        # keep the chapter: losing a finished chapter is worse than stale cards
        logger.exception("state update failed for chapter %d", n)
        update_failed = True
        story = build_story(before)                    # discard any half-applied update
        warnings.append(M("The cards were NOT updated for this chapter ({why}). Edit the next chapter's starting cards by hand.", why=_why(e)))

    progress(step="summarizing", tokens=0, max_tokens=0, attempt=1)
    summary = summarize_chapter(text, n, lang, story.name_of(story.plot.protagonist))
    logger.info("Chapter %d summary: %s", n, summary)
    if n < total and not any(b.chapter_num == n + 1 for b in story.plot.chapter_beats):
        progress(step="next", tokens=0, max_tokens=0, attempt=1)      # the next beat, now that this chapter's events are known
        try:
            warnings += plan_next_beat(vw(), n + 1, [*req.summaries, summary], text, lang)
        except Cancelled:
            raise
        except Exception as e:                    # keep the chapter: the beat is written when the next chapter starts
            logger.exception("next beat failed after chapter %d", n)
            warnings.append(M("The beat for chapter {next} could not be written ({why}). It will be written when you start that chapter.",
                              next=n + 1, why=_why(e)))
    return {"chapter_num": n, "text": text, "summary": summary, "words": words, "prompt_tokens": prompt_tokens,
            "cards_after": cards_dict(story), "changes": changes, "warnings": warnings,
            "unintroduced": unintroduced, "card_checks": card_checks, "update_failed": update_failed}
