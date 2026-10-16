"""All the text sent to the model: the chapter templates, and the builders for every card prompt and for the next-beat planner. Builders only assemble strings from the data they are given; sending and checking is done in stages.py and chapter.py."""

import json

from . import config
from .schema import (
    CastDraft,
    CharacterDraft,
    DESIGN_ANCHORS,
    DIAL_FIELDS,
    MAX_CAST,
    MAX_CHAPTERS,
    MAX_CHARACTERS,
    OutlineDraft,
    PORTRAIT_FIELDS,
    STORY_STAGES,
    StyleCard,
    WORLD_TARGETS,
    WorldDraft,
    ladder_text,
    ladders_for_prompt,
    Dial,
    spread_stages,
    stage_lines_for,
)


SUMMARIZE_CHAPTER_PROMPT = """Read the chapter text below and write a summary of it: 3-5 sentences of
        plain prose covering key plot events, revelations, and character actions. Also state who learns
        or is told what, and any object that changes hands. End with one sentence on how each person who
        acted in the chapter is feeling as it closes, and where things stand between them. Focus on facts that matter for continuity
        — do not include stylistic commentary. Do NOT use markdown bold, headers, asterisks, or any
        formatting, and do not add a label or preamble: begin directly with the summary. Refer to every
        person by name. Never write "I" or "we": the chapter is narrated by {narrator}, so use that name.

        CHAPTER {chapter_num} TEXT:
        {chapter_text}

        Write the summary in {language}, with that language's usual punctuation."""


GENERATE_CHAPTER_PROMPT = """LANGUAGE (this overrides everything else below): write the whole chapter, narration and dialogue, in
        {language}. The cards, notes, earlier chapters and these instructions may be written in other languages;
        that never changes the language you write in.

        You're continuing a story already in progress. Read who's here and what the world is like, catch up on
        what's happened, then write chapter {chapter_num} as a scene you're actually inside -- felt and specific,
        not a report that certain facts occurred. ~{target_words} {unit}, prose only, no meta-commentary, no
        chapter title or heading at the top: begin directly with the prose.

        THE STORY (style, cast, and the world it happens in):
        {context}

        HOW TO READ THE CARDS: each section says what it is for. Each character is a portrait of who they are;
        what they have lived through in this story comes from the story so far, and the summary's last lines say
        how they feel as this chapter opens. Never contradict how things work in the world, and follow the beat's narration
        line for person and tense. The world is a short page: what living there costs, how things work, the
        places the story can go, the things and groups that matter, and what is unspoken. The lists of exemplars,
        places, things and groups are a selection made for this chapter, not everything on the
        cards. If an ENDING section appears, this is the final chapter: land it.

        STORY SO FAR (summary of earlier chapters):
        {prior_summary_block}

        WHAT THE LAST CHAPTER CHANGED (plain facts, already true as this chapter opens; treat every one of them as
        settled and already known to the characters who were there -- do not re-establish, re-explain, or have a
        character rediscover any of them):
        {changes_block}

        THIS CHAPTER -- what has to happen, and where it has to land. Chapters aren't necessarily back to back,
        so don't assume this one picks up right where the last one left off:
        {beat_block}
        {note_block}

        Everything above is the scene itself. A few hard lines around it, to hold in mind rather than check off
        one by one:
        - Cast: the only named, recurring people in this chapter are {named_cast} -- the whole cast of it. No one
          else from this story appears, speaks, or acts here. A minor background figure for texture is fine, but
          never gets a name, not even once: refer to them by role or brief description. A figure who needs to
          recur isn't incidental, so leave them out.
        - Knowledge: a character only acts on what they themselves have witnessed or been told so far (see STORY
          SO FAR and WHAT CHANGED above), plus any hidden truth marked as known to them. Nobody states, hints at,
          or acts on a hidden truth they aren't listed for, unless this chapter's beat reveals it.
        - The beat above is what actually happens here, not a mood to gesture at: the events occur in the order
          given, the goal and obstacle drive the chapter, and it ends on the moment named. Find your own scene
          detail, dialogue, and pacing to get there, but don't skip, defer, soften, or substitute the event itself.
          Dramatize every listed character shift as a visible moment or choice, not implied consistency. If no
          shifts are listed, don't invent an arc milestone of your own.
        - End the chapter exactly on the moment named in the beat's stopping point, and stop there: no line of
          reflection, summary, or reassurance after it, and don't resolve it early or soften it just because the
          chapter has run long enough. If that moment is a question, threat, reversal, or choice left open (true
          for every chapter but the last), the reader should want to know what happens next, not feel the matter
          is closed. Only in the final chapter, where the beat lands the story instead, should it read as settled.

        CRAFT:
        - Exemplars are rhythm and register only -- never reproduce or closely paraphrase
          a sentence, clause, or distinctive phrase from them. Write the way the narrator sees, use its signature
          moves when a moment calls for them, and never do anything on the off-limits list.
        - A character's tell, look and manner are tendencies, not props to produce on cue: don't re-describe
          anyone's appearance or voice just because they're in a scene. Show a tell once, in one sentence, when
          pressure truly builds, then leave it alone for the rest of the chapter -- this matters most for a vivid
          repeated motion, which is easy to reach for again. Let people under pressure also do things the portrait
          never mentions.
        - Begin with someone doing or saying something, and don't open the way the previous chapter opened. A catchphrase
          or gesture from the cards is used at most once per chapter.
        - The places, things and groups listed are the tracked ones. A minor passing thing (a cup, a doorway, a
          stray dog) may be invented in the scene, provided it stays minor, is never named as recurring, and carries
          no plot. Let the world's pressure and what is unspoken shape what people do and avoid, rather than
          touching every item listed.
        - Once a rule, mechanism, or detail has been established in an earlier chapter, treat it as understood
          and don't re-explain it.
        - Vary physical tics and transitions rather than defaulting to a recurring gesture.

        Write the chapter in {language}."""


EXTRACT_STATE_UPDATE_PROMPT = """Read the chapter below and extract what changed in the story state.
        Respond with ONLY valid JSON matching this schema, no fences, no preamble.
        Ensure the JSON is strictly valid — no trailing commas, no comments, no unescaped quotes.

        SCHEMA:
        {schema}

        KNOWN CHARACTERS (already have cards. Do NOT list them in unintroduced_characters, even
        under a nickname or description):
        {known_characters}

        EXISTING OBJECTS (use these ids exactly in object_moves and object_updates):
        {known_objects}

        EXISTING LOCATIONS (use these ids exactly for new_location in object_moves and in location_updates):
        {known_locations}

        EXISTING GROUPS (use these ids exactly in group_updates):
        {known_groups}

        Rules for filling the schema:
        - Use ids exactly as listed above. Never invent an id.
        - Write every text value (descriptions) in {language}. Ids and JSON keys stay exactly as given.
        - location_updates, object_updates, group_updates: only for something this chapter physically or
          materially changed (a place damaged, rebuilt, emptied or taken over; an object broken, opened, emptied or
          used up; a group that split, grew, lost its leader or changed what it wants). Write the new description
          of the thing as it is now, with the change folded in and its other facts kept, in one or two sentences.
          Keep the register of the existing description (what the thing does to people, why they want it or fear it):
          fold the change into that, never rewrite it as a plain inventory line.
          If nothing about it changed, do not list it. Do not reword a description that is still true.
        - object_moves: only for objects whose owner or location actually changed this chapter.
          For new_owner and new_location, use null for no change and "none" to clear the value.
        - unintroduced_characters: only a character who is BOTH (a) not in the KNOWN CHARACTERS list,
          AND (b) significant enough that they will likely recur or matter to the plot going forward.
          Do NOT include minor one-off characters (background figures, unnamed passersby, brief
          mentions with no other detail) even if named in passing. When in doubt, ask: will this
          person plausibly appear again? If no, omit them.

        Only report things that actually changed or were newly introduced in THIS chapter —
        don't restate existing state. If nothing changed in a category, use an empty list.

        CHAPTER {chapter_num} TEXT:
        {chapter_text}"""


EXTRACT_STATE_UPDATE_RETRY_SUFFIX = """

Previous attempt failed: {error}
Fix and respond with ONLY corrected JSON."""


JSON_RULES = (
    "Reply with one JSON object that matches the schema below, and nothing else: no commentary, "
    "no code fences, no markdown asterisks. Include every field in the schema. Use plain text in every field."
)


# What the author wants to do with the example chapter. Any number can be ticked at once, so the prompt says all of them and
# then says what each means for the card being written.
CHAPTER_USES = (
    "sequel",
    "parallel",
)  # what a pasted example chapter is for; none: the cards describe its own story


USE_MEANING = {
    "sequel": "CONTINUE AFTER IT: the story carries on after this chapter. Same world and characters, and what happens next "
    "builds on everything this chapter established and changed.",
    "parallel": "NEW STORY IN THE SAME WORLD: a different story in the same world, running alongside this one. Same world, "
    "rules and writing style; different events and mostly different people. It does not retell this chapter.",
}


USE_FOR_CARD = {
    "style": {
        "sequel": "the writing style stays the example's own",
        "parallel": "the writing style stays the example's own",
    },
    "characters": {
        "sequel": "the example's characters stay who the chapter shows them to be, written as lasting traits and not as what happens to them in it; add a new person only when the continuation needs one",
        "parallel": "the leads are new people who belong in this world; people from the example may appear but do not lead",
    },
    "world": {
        "sequel": "every fact and rule the example states stays true, and what the chapter changed stays changed; add what the continuation needs",
        "parallel": "every fact and rule the example states about the world stays true; add the places, groups and hidden truths the new story needs",
    },
    "outline": {
        "sequel": "chapter 1 begins after the last moment of the example chapter",
        "parallel": "the chapters are the new story's own events, not a retelling of the example",
    },
}


def chapter_source(req) -> str:
    use = getattr(req, "chapter_use", "")
    uses = [use] if use in CHAPTER_USES else []
    body = f"<chapter>\n{req.chapter.strip()}\n</chapter>"
    overrule = (
        "The example is a floor, not a ceiling or a lid: the author's notes below may add things the example "
        "does not show (more characters, more locations, more rules, more hidden truths, a bigger cast than "
        "the example's own), leave out things the example shows that the notes don't want, or change anything "
        "the example establishes. This applies to HOW MANY of something there should be just as much as to "
        "what they are like. Wherever the notes and the example disagree, including on counts, the notes win."
    )
    if not uses:
        return (
            "SOURCE CHAPTER: one chapter from a story. Treat it as evidence about the whole story and "
            "infer what it does not say. " + overrule + "\n\n" + body
        )
    stage = USE_FOR_CARD.get(getattr(req, "stage", ""), {})
    return (
        "EXAMPLE CHAPTER: one chapter from an existing story, given as the starting point for a NEW story. The author "
        "wants the new story to be this:\n"
        + "\n".join(f"- {USE_MEANING[u]}" for u in uses)
        + (
            "\n\nFor this card that means:\n"
            + "\n".join(f"- {stage[u]}" for u in uses if u in stage)
            if stage
            else ""
        )
        + "\n\n"
        + overrule
        + "\n\n"
        + body
    )


def source_block(req) -> str:
    """This card's own notes (and the example chapter, when it is switched on for this card), plus the card's current
    content when this is a revision. Other cards' notes are never sent. Reading order mirrors the authority order:
    example (foundation) -> notes (fine-tuner, wins on any disagreement, including counts) -> current card (what
    exists now, to be patched rather than replaced -- see feedback_block)."""
    parts = []
    if req.mode == "chapter" and req.chapter.strip():
        parts.append(chapter_source(req))
    if req.notes.strip():
        parts.append(
            "AUTHOR DIRECTION: the author's rough notes for this card. These fine-tune and can override "
            "anything above, including how many of something there should be, not just what they are like. "
            f"Fill in whatever both leave out with fitting choices.\n\n<notes>\n{req.notes.strip()}\n</notes>"
        )
    current = current_card_block(req)
    if current:
        parts.append(current)
    return "\n\n".join(parts)


def current_card_block(req) -> str:
    """The card as it stands right now, shown only when this is a revision (a change request over an existing card).
    Without this, a 'regenerate with a note' request has no way to know what it is changing and silently writes a
    brand-new card from the example/notes alone -- this gives the model something concrete to keep or patch."""
    current = getattr(req, "current", None)
    if not getattr(req, "feedback", None) or not current:
        return ""
    return (
        "CURRENT CARD: what this card already contains, before the change below is applied. Keep every part this "
        "change doesn't touch exactly as it is -- this is a patch, not a rewrite.\n\n<current_card>\n"
        + json.dumps(current, ensure_ascii=False)
        + "\n</current_card>"
    )


def feedback_block(feedback, has_current=False) -> str:
    if not feedback:
        return ""
    if has_current:
        return (
            f"\nThe author read the CURRENT CARD above and asked for this change: {feedback}\n"
            "This is an edit, not a fresh draft: change only what the request above requires, and keep every "
            "other field exactly as the CURRENT CARD shows it unless the change necessarily affects it.\n"
        )
    return (
        f"\nThe author asked for this change: {feedback}\n"
        "Write a genuinely different version that applies the change.\n"
    )


FIDELITY = (
    "FIDELITY: Copy every fact the source states exactly as stated: who did what to whom, reasons, names, "
    "numbers, how things work. Never change, soften, reverse or contradict one. Invent only what the source "
    "leaves open, and keep invented details small."
)


def language_rule(code) -> str:
    lang = config.LANGUAGES.get(code) or config.LANGUAGES["en"]
    return (
        f"LANGUAGE: Write every text value in {lang['name']}, whatever language the source is written in. "
        "JSON keys and fixed option values stay exactly as the schema gives them. Use that language's usual punctuation."
    )


def _language(req) -> dict:
    return (
        config.LANGUAGES.get(getattr(req, "language", "en")) or config.LANGUAGES["en"]
    )


def language_head(req) -> str:
    """Opens a card prompt for any language but English. The card is read in that language, so it is written in it, and the
    schema and instructions that follow are English, which is why this goes first and is repeated after the schema."""
    if _language(req) is config.LANGUAGES["en"]:
        return ""
    name = _language(req)["name"]
    return (
        f"LANGUAGE (this overrides everything else below): write every text value of this card in {name}: every rule, "
        f"description, name for a habit and every example passage. The author's notes, any example chapter and these "
        f"instructions may be in another language; that never changes the language the card is written in. JSON keys and "
        f"fixed option values stay exactly as the schema gives them.\n\n"
    )


def tail(req, schema_cls) -> str:
    end = (
        ""
        if _language(req) is config.LANGUAGES["en"]
        else f"\n\nREMINDER: write every text value in {_language(req)['name']}."
    )
    has_current = bool(getattr(req, "feedback", None) and getattr(req, "current", None))
    return (
        f"\n{FIDELITY}\n{feedback_block(req.feedback, has_current)}\n{language_rule(getattr(req, 'language', 'en'))}\n{JSON_RULES}"
        f"\n\nSCHEMA:\n{json.dumps(schema_cls.model_json_schema())}{end}"
    )


# ---------------------------------------------------------------- STYLE
def _anchor_lines() -> str:
    """The reference points for each design field, one line per field. They show the range, they are not a menu."""
    return "\n".join(f"  {k}: {', '.join(v)}" for k, v in DESIGN_ANCHORS.items())


def style_prompt(req) -> str:
    if req.mode == "chapter":
        task = (
            "Work out how this chapter is actually written and fill in each design field from what the text does: what the "
            "narrator notices and ignores, its attitude, how much language each moment gets, how plain or ornate the "
            "words are, the figures of speech, how the sentences move, how far the narration goes inside the "
            "main character, the humor, how speech is written down, and how time is handled. Infer the point of view and "
            "tense from the text."
        )
    else:
        task = (
            "Design the narration from the genre, tone and feel the author describes, and from anything they say about how it "
            "should read: brief or lavish, plain or ornate words, what the narrator pays attention "
            "to. Where the notes say nothing about a field, choose what best fits the genre, and choose with character: a "
            "narrator a reader would recognise, not a safe average."
        )
    return (
        "You are designing a narration style card for a story-writing engine. The same card is reused for every chapter of "
        "one story, so it says HOW the story is told and never WHAT happens in it. The style is designed, not just "
        "labelled: each choice about how the narrator perceives the world and builds its prose is made on purpose, and "
        "the card holds them together as one narrator.\n\n"
        f"{source_block(req)}\n\nTASK: {task}\nRULES:\n"
        "- The card contains no character names, place names, plot events, or nouns that belong only to this story. "
        "That includes the exemplars.\n"
        "- Five fields are dials: economy, diction, figurative, interiority and humor. Each is `{level, note}`, where "
        "`level` is a whole number from 1 to 5 and 3 is the middle. Choose the level whose description fits the story, and "
        "use `note` only to bend it (for example the kind of humor). Here is what every level means:\n"
        f"{ladders_for_prompt()}\n"
        "- `lens`, `stance`, `cadence`, `dialogue_manner` and `time_handling` each state one choice in a short phrase of "
        "plain words. These reference points show the range of each; they are not a menu, so combine them or use your own "
        "words when the description calls for it:\n"
        f"{_anchor_lines()}\n"
        "- The author's choices are fixed. When the notes ask for something (clipped sentences, fancy words, plain words, "
        "no metaphor), the matching field says exactly that (the level that describes it), and `narrator` and the "
        "exemplars show it. When a CURRENT CARD is shown, every level and phrase in it is the author's choice: keep it. "
        "Never soften, tidy or tone down a choice the author made, plain words included.\n"
        "- `narrator` is written from the levels you chose: it carries each one's description in your own words, without "
        "quoting it and without contradicting it.\n"
        "- The fields agree with one another. When the author's choices pull against each other (lavish imagery in clipped "
        "sentences), say in `narrator` how they fit together instead of dropping one.\n"
        "- `narrator` is the heart of the card, and the one description of the narrator the writer reads in full. Write it as "
        "a lens: what this narrator perceives, what it ignores, what it makes of what it sees, and how that sounds on "
        "the page. It describes a way of seeing, not formulas: no sentence-length limits, ratios, counts or checklists. "
        "To show the difference, a mechanical card says 'alternate long and short sentences; never open on the weather', "
        "while a lens says 'the narrator is cynical and transactional, grounded in physical objects, and never explains "
        "what a character feels, only what they touch, grip or ignore'; another lens says 'the narrator is tactile and "
        "superstitious, and every object carries the weight of old bargains, bloodlines or hidden decay'. Write a lens "
        "for this story's own style in that spirit, in your own words.\n"
        "- Do not add a sentence-length limit, a dialogue ratio or any other number unless the author gave one.\n"
        "- `signature_moves` are three to five recurring devices a reader would recognise, each a thing the narrator does "
        "(not a rule and not a restatement of a design field). Each one holds for any story in this style.\n"
        + (
            "- `off_limits` names what this narrator conspicuously never does, up to four items, each named plainly. Leave "
            "it empty if nothing stands out.\n"
            if req.mode == "chapter"
            else "- `off_limits` holds everything the author said to avoid, each named plainly, and nothing else. Leave it "
            "empty if the author named nothing. Do not pad it with generic writing advice.\n"
        )
        + "- The exemplars are two or three short passages (two to four sentences each) about ordinary everyday "
        "situations in a different part of life from the story. They use none of the story's nouns, jobs, objects "
        "or settings. They carry the whole design: the same lens, stance, economy, kind of words, "
        "figures of speech, humor and handling of the character's inner life, so a passage in plain description "
        "is not enough. They obey `signature_moves` and `off_limits`, and each shows something different.\n"
        + "- Do not copy wording from these instructions.\n"
        + tail(req, StyleCard)
    )


# ---------------------------------------------------------------- CHARACTERS
def _style_facts(style: dict, keys) -> str:
    """The listed design fields of a style card as 'name: value' lines, skipping blanks. A dial is sent as the description
    of its level (never the number)."""
    out = []
    for k in keys:
        v = style.get(k)
        if k in DIAL_FIELDS and isinstance(v, dict):
            v = ladder_text(k, Dial(**v))
        if str(v or "").strip():
            out.append(f"- {k.replace('_', ' ')}: {v}")
    return "\n".join(out)


CARD_RULES = (
    "- Use what the source says about who each person is. Invent the missing details sparingly and concretely.\n"
    "- The test for every sentence: would it still be true if this person woke up in a different genre and setting, "
    "say a noir, a space heist or a dinner party? Be specific about the person and silent about the story: no plot "
    "events, no places, objects or organizations, no other character's name, nothing that happens to them here. Where the "
    "source shows a person in one situation, write the lasting tendency behind what they do there, not the situation.\n"
    "- When the author states a trait outright (a habit, a look, a past, a way of speaking), keep it as written. What the "
    "author describes as happening in the story is plot and stays out of the card.\n"
    "- Portable does not mean generic. Skip labels and archetypes (the cynic, the loyal soldier) and give each person "
    "the particular, slightly unexpected shape that makes them one person: an odd loyalty, a kindness they hide, a rule "
    "nobody asked them to keep.\n"
    "- Give everyone a soft spot, however well hidden. A cast of nothing but armor has no way for anyone to reach anyone.\n"
    "- Every field is one or two full sentences of prose about the person: no lists, no labels, no fragments. The fields "
    "are read one after another as a single description, so each must read naturally after the one before it: after "
    "`role`, refer to the person with a pronoun, not their name.\n"
    "- `role` completes the sentence \"<name> is ...\": a phrase about the kind of person they are, never a bare title.\n"
    "- `tell` and `presence` are things a reader could watch a body do or see, never labels. `tell` names a kind of "
    "motion and a kind of thing, never one named object, so that the writer can use whatever the scene holds.\n"
    "- `blind_spot` is one specific contradiction between how the person sees themselves and what they do (for example: "
    "calls herself easygoing, yet redoes everyone else's work). A nervous tic is not a blind spot.\n"
    "- The lines in `voice` are new, unique to this person, and give away no plot.\n"
    "- Story-bound against portable, shown in other genres (never copy their wording). want: not 'wants to find out who "
    "took the ledger' but 'wants to be the one everyone needs and dreads being the one nobody calls'. wound: not 'was "
    "ruined by the Ashgrove Guild' but 'was left behind by the one person who promised to return, and learned not to wait "
    "on anyone'. armor: not 'is suspicious of the forged signature' but 'treats every offer as a trap until it is proven otherwise, and answers kindness with a question'. with_people: not 'learned the secret from the informant' but 'keeps count of what each person leaves unsaid, and lets a silence run on until the other one fills it'. tell: not 'turns a signet ring' but 'when tension rises, the hands go looking for something to peel, "
    "fray or turn over, whatever the room holds'. limits: not 'will not betray the captain' but 'will not lie to someone "
    "who depends on the truth, unless the lie is all that keeps someone they love alive'.\n"
)

CAST_RULES = (
    "- Write the cast as foils when there is more than one person: each handles the same pressure differently from "
    "someone else (one withholds, another overshares; one flees, another stands and fights), so the cast creates friction "
    "without anyone being named in anyone else's card.\n"
    "- Compare the characters as you write: no two share a want, a wound, a stance, a tell, a way with people, a limit, a blind spot or a manner of speaking.\n"
    "- Write every character's fields in different words and different sentence shapes. No phrase of four or more "
    "words may appear in the same field of two characters, and no two fields may open the same way.\n"
)


def _cast_narrator(req) -> str:
    style = req.cards.get("style") or {}
    facts = _style_facts(style, ("diction", "dialogue_manner", "humor"))
    narrator = (
        (
            f"\nTHE STORY'S NARRATION (fixed; the cast speaks inside this story):\nNarrator: {style['narrator']}\n"
            + (f"{facts}\n" if facts else "")
            + "Each character's voice must sound different from the narrator's, while their words "
            "stay within the story's diction: if it is plain, no one talks in obscure or flowery words unless their "
            "background gives a reason.\n"
        )
        if style.get("narrator")
        else ""
    )
    return narrator


def characters_prompt(req) -> str:
    narrator = _cast_narrator(req)
    return (
        "You are writing the character cards for a story-writing engine. Each card is a portrait of one person that has to "
        "hold in any story: it says who the person is, never what happens to them. The author reviews the cards, and a card "
        "may later be taken out of this story and used in a completely different one.\n\n"
        f"{source_block(req)}\n{narrator}\n"
        f"TASK: Write the whole cast together, one card per main character the source describes (one card is fine if the "
        f"source describes one person), at most {MAX_CHARACTERS}. If the source has more people than that, keep the "
        f"{MAX_CHARACTERS} who matter most to the plot.\n"
        "RULES:\n"
        + CARD_RULES
        + CAST_RULES
        + tail(req, CastDraft)
    )


def portrait_paragraph(c) -> str:
    """One card as a paragraph, the fields read one after another: how the cast is shown to a model that is not writing it."""
    return f"{c['name']}. " + " ".join(
        str(c.get(f, "")).strip() for f in PORTRAIT_FIELDS if str(c.get(f, "")).strip()
    )


def character_prompt(req, cast, target) -> str:
    """Write one person again, with the rest of the cast shown so that the new card differs from every one of them."""
    others = [c for c in cast if c["id"] != target["id"]]
    around = (
        "THE REST OF THE CAST (already written and fixed; they are here only so that this person differs from every one of "
        "them in want, wound, stance, tell, way with people, limits, blind spot and voice, and never names them):\n\n"
        + "\n\n".join(portrait_paragraph(c) for c in others)
        + "\n\n"
        if others
        else ""
    )
    return (
        "You are rewriting one character card for a story-writing engine. A card is a portrait of one person that has to "
        "hold in any story: it says who the person is, never what happens to them. The author reviews the card, and it may "
        "later be taken out of this story and used in a completely different one.\n\n"
        f"{source_block(req)}\n{_cast_narrator(req)}\n{around}"
        f"TASK: Write the card for one person only: {target['name']}. Keep the name exactly "
        f"(unless the author's change asks for another).\n"
        "RULES:\n"
        + CARD_RULES
        + "- This is one person among others: give them a different want, wound, stance, tell, way with people, limit, "
        "blind spot and manner of speaking from everyone listed above, and phrase every field in different words.\n"
        + tail(req, CharacterDraft)
    )


# ---------------------------------------------------------------- WORLD
def world_cast_lines(cast) -> str:
    """The cast as the world card sees it: name, role, want and armor, so the world's pressure can rub against what each
    person wants and how they defend themselves. (The outline's cast_lines stays name and role only.)"""

    def one(c):
        def sent(f):
            t = str(c.get(f, "")).strip()
            return t if not t or t[-1] in ".!?" else t + "."

        role = str(c.get("role", "")).strip().rstrip(".")
        head = f"- {c['name']} is {role}." if role else f"- {c['name']}."
        return " ".join(x for x in (head, sent("want"), sent("armor")) if x)

    return "\n".join(one(c) for c in cast)


WORLD_RULES = (
    "- Keep every specific the author gave exactly as written. Invent only what is missing, and spend that invention on "
    "cost, price and secrets rather than scenery.\n"
    "- The test for every entry: does it create a choice, a cost or a feeling for someone? If not, leave it out. A world "
    "is not an inventory; do not list things just because the source mentions them.\n"
    "- `setting` is one short paragraph: where and when, and what an ordinary day is like for the people there. It may "
    "carry one past event that people still live under. Add no era, country or scale the source does not state.\n"
    "- `pressure` is one or two sentences on what living here costs: what is scarce, forbidden or owed, and who feels it. "
    "Let it rub against what the cast want and how they defend themselves, without naming any one person and without "
    "touching anyone's wound.\n"
    "- `rules` are short statements, each a mechanic or custom plus what it makes people do or give up. A rule with no "
    "price attached is not worth stating. Never tell the writer how to write or what tone to use.\n"
    "- Describe customs and texture concretely, but without praising them or explaining them to an outsider.\n"
    "- A location says what the place does to people: who belongs there and who does not, what is done or hidden there. "
    "A sensory detail is welcome only if it carries that. A group is described by how it is felt in daily life, then "
    "what it wants. An object is described by why people want it, fear it or have paid for it.\n"
    "- An object's `owner` is the name of a cast member or null. Its `location` is the exact name of one of the "
    "locations you write, or null when the source does not say where it is.\n"
    "- A hidden truth is a true fact that has not yet appeared on the page and steers the story from behind the scenes. "
    "`stake` says who is guarding it and what exposure would cost them or others. `known_by` lists the names of the cast "
    "members the fact is about or who did the thing, unless the source says nobody knows it, in which case it is empty. "
    "Write the truths last, so they can lean on everything above.\n"
    "- Aim for about {rules} rules, {locations} places, {objects} objects, {groups} groups and {truths} hidden truths. "
    "Anything beyond that is left to the scene to invent. Use every place the source says a scene happens in, folding "
    "minor ones into a larger place rather than leaving a scene without a setting.\n"
    "- Shown in other genres (never copy their wording). rule: not 'The tithe is paid at harvest' but 'The tithe is "
    "paid at harvest in grain, so every family chooses each year which child goes hungry.' location: not 'a dim room with "
    "a low ceiling and the smell of tallow' but 'the counting-house, where the ones who owe go in by the side door and "
    "nobody asks who came out with less than they brought.' stake: not 'the ship is haunted' but 'the captain has kept "
    "the logbook locked since the first death, and if the crew read it they would sail home and he would hang.'\n"
).format(
    rules="{}-{}".format(*WORLD_TARGETS["rules"]),
    locations="{}-{}".format(*WORLD_TARGETS["locations"]),
    objects="{}-{}".format(*WORLD_TARGETS["objects"]),
    groups="{}-{}".format(*WORLD_TARGETS["groups"]),
    truths="{}-{}".format(*WORLD_TARGETS["hidden_truths"]),
)


def world_prompt(req, cast) -> str:
    return (
        "You are writing the world card for a story-writing engine. The card is read by the chapter writer as a short page "
        "about the place, so write each entry as plain prose about what it costs and means to people.\n\n"
        f"{source_block(req)}\n\nTHE CAST (write people by these names exactly; they are here so that the world can press "
        f"on what they want, and the card never explains their wounds):\n{world_cast_lines(cast)}\n\n"
        "TASK: Write the world the story happens in.\nRULES:\n"
        + WORLD_RULES
        + (
            "- Read the chapter for facts that some characters know and others do not, or that the story keeps back "
            "for later. List each as a hidden truth, with its `stake` and with `known_by` the people who know it. If "
            "there are none, leave the list empty.\n"
            if req.mode == "chapter"
            else ""
        )
        + tail(req, WorldDraft)
    )


# ---------------------------------------------------------------- OUTLINE
def outline_prompt(req, cast, world, want) -> str:
    places = "\n".join(f"- {l['name']}: {l['description']}" for l in world["locations"])
    truths = (
        "\n".join(
            f"- {t['id']}: {t['fact']}"
            + (f" At stake: {t['stake'].strip()}" if str(t.get("stake", "")).strip() else "")
            for t in world.get("hidden_truths", [])
        )
        or "(none)"
    )
    rules = "\n".join(f"- {r}" for r in world["rules"])
    names = "\n".join(f"- {c['name']}: {c.get('role', '')}" for c in cast)
    groups = "\n".join(
        f"- {g['name']}: {g.get('description', '')}"
        + (f" Wants: {g['wants']}" if g.get("wants") else "")
        for g in world.get("groups", [])
    )
    group_block = (
        (
            "GROUPS (background collectives; they cannot be listed in `present`, so they appear only inside "
            f"the events text, as unnamed crowds or officials):\n{groups}\n\n"
        )
        if groups
        else ""
    )
    pressure_block = (
        f"WHAT LIVING HERE COSTS: {world['pressure'].strip()}\n\n"
        if str(world.get("pressure", "")).strip()
        else ""
    )
    stage_block = "\n".join(
        f"{k}. {name}: {text}" for k, (name, text) in STORY_STAGES.items()
    )
    st = req.cards.get("style") or {}
    mood = _style_facts(st, ("stance", "humor", "time_handling", "interiority"))
    style_block = (
        (
            f"THE STORY'S NARRATION STYLE (the outline must suit this register):\nLabel: {st.get('label', '')}\n"
            f"Narrator: {st.get('narrator', '')}\n" + (f"{mood}\n" if mood else "") + "\n"
        )
        if st
        else ""
    )
    if want:
        count_rule = (
            f"The story has exactly {want} chapters: set `chapter_count` to {want}. If the author describes more or "
            "fewer sections than that, fit them into the chapters in order. "
        )
        stage_rule = (
            "- "
            + " ".join(l.strip() for l in stage_lines_for(0, spread_stages(want)[0]))
            + " Build chapter 1 to do all of it.\n"
        )
    else:
        count_rule = (
            "Decide how many chapters the whole story has and set `chapter_count`: exactly the number the author "
            "says, else one chapter for each chapter or section they describe (never splitting one of theirs into "
            "two); if they describe none, plan five to eight. "
        )
        stage_rule = (
            "- Chapter 1 is the opening of the story and covers the stages it is given: Setup only when the story "
            "has six or more chapters, Setup and Spark with three to five chapters, Setup, Spark and Friction with "
            "two, all six with a single chapter. Build chapter 1 to do all of that.\n"
        )
    return (
        "You are writing the plot outline for a story-writing engine.\n\n"
        f"{source_block(req)}\n\n{style_block}CHARACTERS (write names exactly like this):\n{names}\n\n"
        f"LOCATIONS (write names exactly like this):\n{places}\n\n{pressure_block}HOW THINGS WORK HERE:\n{rules}\n\n{group_block}"
        f"HIDDEN TRUTHS (refer to them by id in `reveals`):\n{truths}\n\n"
        f"THE STORY'S SIX STAGES (a pacing guide for how the whole story escalates. It is NOT a list of chapters: its length "
        f"says nothing about how many chapters to write):\n{stage_block}\n\n"
        f"TASK: Set up the story: its premise, main character, theme, the broad ending it is heading for, the character arcs, "
        f"how many chapters it has (at most {MAX_CHAPTERS}), and the beat of chapter 1 ONLY. "
        + count_rule
        + "The beats of the later chapters are written one at a time after each chapter is finished, so do not plan or "
        "mention them: `chapter_beats` has exactly one item.\n"
        "\nRULES:\n"
        + stage_rule
        + "- Stakes come from the first two stages: by the end of the stage 2 chapter the reader knows what the "
        "point-of-view character wants or could lose, and in stage 3 it gets worse. `goal` and `obstacle` must be "
        "concrete enough to show that.\n"
        "- Include every beat the author describes for chapter 1, in order, through to the last thing that happens "
        "in it, and use only the people the author places in that chapter for `present`.\n"
        "- Events are plain actions in order, one sentence each, with nothing explained or summarised.\n"
        "- `ends_on` is the situation the chapter stops at, in a few words, not a quoted line (if the author gives a "
        "closing line, describe what it does instead). It must be true right after the chapter's last event: it may "
        "not restate an event that already happened in the chapter or ask for something that only happens later. It "
        "must be a hook, not a landing: a question, a threat, a reversal, or a choice still open, never a moment that "
        "reads as settled or safe to stop on.\n"
        "- Open chapter 1 already in motion: someone doing or wanting something, a choice being made, an exchange "
        "underway. Never spend the opening establishing the setting, routine, or backstory before anything happens; "
        "the stage's own baseline comes through in what the character does, not in description first. Do not jump "
        "ahead to the Spark's disruption unless chapter 1's stage already includes it.\n"
        "- Use `reveals` only for a hidden truth that becomes known on the page in chapter 1 to everyone present. Most "
        "stories reveal nothing in the first chapter; leave it empty unless one clearly belongs there.\n"
        "- A plant is a specific object, line or action in chapter 1 that a LATER chapter may use. Leave it empty rather "
        "than writing general observations about a character.\n"
        "- Give chapter 1 a `tone`: one sentence on that chapter's mood as the narration style defines it, and "
        "where it turns, tightens or is undercut.\n"
        "- Show change through what happens on the page. An arc, a shift or an ending may name the change, but it also "
        "says the concrete thing the person does or says that shows it. For example: 'Mara comes to trust her brother: "
        "she hands him the keys.'\n"
        "- `goal` is what the person wants plus, where it applies, what they are holding back. `obstacle` is something "
        "specific the characters run into in the scene (a person, object, rule or event), not only a feeling.\n"
        "- `ending` is the broad destination, a concrete situation: what has been done or said and what is still open. It "
        "is not only a summary of what everyone now understands, and it does not fix the events on the way there.\n"
        "- `arcs` say where each main person ends up. They are destinations, not a schedule of chapters.\n"
        "- `leave_open` holds only what the author says must stay unresolved or unexplained. If they said nothing, "
        "leave it empty. Never invent a new central question.\n"
        "- `protagonist` is the story's ONE main character, by exact name from the list. The whole story is told from "
        "this one person's side, in every chapter, so they are in every chapter's `present` and no chapter is told "
        "from anyone else's point of view. If the author names the main character, use them; otherwise choose the "
        "person the story follows most closely.\n"
        "- `present`, `shifts` and `arcs` use only the listed characters. Anyone else the story needs appears "
        "only inside the events text.\n" + tail(req, OutlineDraft)
    )


# ---------------------------------------------------------------- WORLD
def cast_lines(cast) -> str:
    return "\n".join(f"- {c['name']}: {c.get('role', '')}" for c in cast)


# ---------------------------------------------------------------- THE NEXT BEAT
# A beat is written only when the chapter before it is finished, so it can follow what really happened. Nothing past the chapter
# being written exists: later beats are not planned, stored or shown to the writer.
BEAT_TAIL_CHARS = 1500  # how much of the chapter just written the planner reads (the ending is what matters). The
# chapter WRITER is never shown any of the previous chapter's prose at all (only the facts
# of what changed, in WHAT THE LAST CHAPTER CHANGED): chapters are not guaranteed to be
# contiguous, and a quoted passage of prose in the prompt was found to get echoed back
# verbatim as the new chapter's own opening despite being told not to reuse it — a planner
# reading a tail to produce structured JSON doesn't have that failure mode, so it keeps one.


def next_beat_prompt(story, n, summaries, prev_text, language="en"):
    """The planner's prompt for chapter n's beat. `story` is as it stands after chapter n-1: updated cards, beats up to n-1."""
    plot, w, total = story.plot, story.world, story.plot.total_chapters
    name = story.name_of
    here = {l.id: l.name for l in w.locations}
    chars = "\n".join(
        f"- {c.name}: {c.role.rstrip('.')}. {c.want.rstrip('.')}. {c.blind_spot.rstrip('.')}. {c.limits.rstrip('.')}."
        for c in story.characters
    )
    places = "\n".join(f"- {l.name}: {l.description}" for l in w.locations)
    rules = "\n".join(f"- {r}" for r in w.rules) or "(none)"
    cast_ids = {
        c.id for c in story.characters
    }  # only these people exist for this chapter
    objs = (
        "\n".join(
            f"- {o.name}"
            + (
                (
                    f", held by {name(o.owner)}"
                    if o.owner in cast_ids
                    else ", held by someone outside this cast"
                )
                if o.owner
                else ""
            )
            + (f", at {here.get(o.location, o.location)}" if o.location else "")
            for o in w.objects
        )
        or "(none)"
    )
    groups = "\n".join(f"- {g.name}: {g.description}" for g in w.groups)
    left = story.unrevealed_truths(n - 1)
    done = [t for t in w.hidden_truths if t not in left]
    know = lambda t: (
        ", ".join(name(c) for c in t.known_by if c in cast_ids) or "no one in this cast"
    )
    truths = (
        "\n".join(
            f"- {t.id}: {t.fact} (known to: {know(t)})"
            + (f" At stake: {t.stake.strip()}" if t.stake.strip() else "")
            for t in left
        )
        or "(none left)"
    )
    revealed = "\n".join(f"- {t.fact}" for t in done) or "(none yet)"
    plants = story.open_plants(n - 1)
    prev = story.beat_for(n - 1) if n > 1 else None
    stage = spread_stages(total)[min(n, total) - 1]
    stage_text = "\n".join(stage_lines_for(prev.stage if prev else 0, stage))
    stories = (
        "\n".join(f"Chapter {i + 1}: {t}" for i, t in enumerate(summaries))
        or "(no earlier chapters)"
    )
    tail_text = prev_text.strip()[-BEAT_TAIL_CHARS:] if prev_text.strip() else "(none)"
    st = story.style
    mood = _style_facts(st.model_dump(), ("stance", "humor", "time_handling", "interiority"))
    left_n = total - n + 1
    past = [b for b in plot.chapter_beats if b.chapter_num < n]
    ledger = (
        "\n".join(
            f"- Chapter {b.chapter_num}: {b.goal} At {here.get(b.location, b.location)}, with "
            f"{', '.join(name(c) for c in b.present)}."
            + (f" What changed: {b.turn}" if b.turn else "")
            + f" Ended on: {b.ends_on}"
            for b in past
        )
        or "(none)"
    )
    places_left, people_left = story.least_used(n - 1)
    objects_left, groups_left = story.least_used_world(n - 1)
    fresh = (
        "Places the story has been to least: "
        + ", ".join(f"{a} ({k}×)" for a, k in places_left)
        + "\n"
        + (
            "People who have been on the page least: "
            + ", ".join(f"{a} ({k}×)" for a, k in people_left)
            + "\n"
            if people_left
            else ""
        )
        + (
            "Objects the story has made the least use of: "
            + ", ".join(f"{a} ({k}×)" for a, k in objects_left)
            + "\n"
            if objects_left
            else ""
        )
        + (
            "Groups the story has made the least use of: "
            + ", ".join(f"{a} ({k}×)" for a, k in groups_left)
            + "\n"
            if groups_left
            else ""
        )
    )
    return (
        "You are planning the next chapter of a story that is written one chapter at a time. Only the beat of the next "
        f"chapter is needed now: chapter {n} of {total}. Nothing after it has been planned, so do not plan it.\n\n"
        f"THE STORY SO FAR (the premise, theme, ending, arcs and the list of what stays open can be revised: see REVISING)\nPremise: {plot.premise}\nMain character: {name(plot.protagonist)}\n"
        f"Theme (steers the plot; never stated aloud): {plot.theme}\n"
        f"Where the story is heading (a broad destination, not a schedule; change it if events have moved the story elsewhere): {plot.ending}\n"
        + (
            "Never resolve or explain: " + "; ".join(plot.leave_open) + "\n"
            if plot.leave_open
            else ""
        )
        + "Where each person ends up: "
        + "; ".join(f"{name(a.character)}: {a.end}" for a in plot.arcs)
        + "\n"
        f"Narration style: {st.label}. {st.narrator}\n"
        + (f"{mood}\n" if mood else "")
        + "\n"
        f"THE CARDS NOW (after chapter {n - 1}; this is the truth of the story at this point)\n"
        f"PEOPLE:\n{chars}\n\nSETTING: {w.setting}\n"
        + (f"WHAT LIVING HERE COSTS: {w.pressure}\n" if w.pressure.strip() else "")
        + f"HOW THINGS WORK HERE (each carries a price; reach for one as an obstacle or a "
        f"stake when it fits this chapter):\n{rules}\n\nPLACES (write names exactly like this):\n{places}\n"
        f"OBJECTS:\n{objs}\n"
        + (
            f"GROUPS (background collectives; they appear only inside the events text):\n{groups}\n"
            if groups
            else ""
        )
        + f"HIDDEN TRUTHS ALREADY REVEALED (part of what happened):\n{revealed}\n\n"
        f"WHAT HAS HAPPENED\n{stories}\n\nThe last chapter ended like this (the ending only):\n{tail_text}\n"
        + (f"It stopped at: {prev.ends_on}\n" if prev else "")
        + f"\nALREADY USED (the earlier chapters in brief; this chapter must not repeat any of them):\n{ledger}\n\n"
        f"FRESH MATERIAL (use it when the story allows; a new place, an object or group barely touched so far, or a person "
        f"who has been away is the easiest way to make a chapter different):\n{fresh}"
        f"\nTHIS CHAPTER: chapter {n} of {total}\n{stage_text}\n"
        f"Chapters left, counting this one: {left_n}.\n\n"
        f"CHOOSE FROM WHAT IS STILL AVAILABLE\nHidden truths not yet revealed (put an id in `reveals` only if that truth becomes "
        f"known on the page in this chapter, to everyone present; most chapters reveal one or none; a truth once revealed cannot be "
        f"chosen again; try to reveal them over the chapters that are left, at a pace the story can carry, but a story does not "
        f"have to reveal every one):\n{truths}\n"
        + (
            "Plants not yet paid off (to use one in this chapter, copy its wording exactly into `pays_off`; a plant once paid off "
            "cannot be chosen again; use what the story calls for and leave the rest):\n"
            + "\n".join(f"- {p}" for p in plants)
            + "\n"
            if plants
            else "Plants not yet paid off: (none)\n"
        )
        + "\nRULES:\n"
        "- Follow from where the last chapter really ended and from the cards as they are now. Respond to what actually "
        "happened; do not return to any earlier idea of the plot.\n"
        "- Each event happens once. Never repeat an earlier chapter's event, scene, argument or confession, and do not replay "
        "an earlier chapter with different wording. The story must move forward: something is different when this chapter ends.\n"
        "- Before settling on the obstacle and events, check FRESH MATERIAL, WHAT LIVING HERE COSTS and HOW THINGS WORK HERE for "
        "something the story has barely used: a cost someone has not yet had to pay, a rule's price, a secret's stake, an "
        "object or a group. Reach for one of these instead of returning to the same two or three details the last few "
        "chapters leaned on, whenever it genuinely fits the chapter; do not force one in where it does not.\n"
        "- `turn` says what changed. A chapter whose `turn` could be written about an earlier chapter is the wrong chapter.\n"
        "- Make this chapter do what its story stage asks, and move the story toward its destination without rushing it.\n"
        "- `goal` is what the main character wants plus, where it applies, what they are holding back. `obstacle` is something "
        "specific the characters run into in the scene (a person, object, rule or event), not only a feeling.\n"
        "- Events are plain actions in order, one sentence each, with nothing explained or summarised.\n"
        "- `ends_on` is the situation the chapter stops at, in a few words, not a quoted line. It must be true right after the "
        "chapter's last event. Unless this is the last chapter, it must be a hook: a question, a threat, a reversal, or a "
        "choice still open, never a moment that reads as settled or safe to stop on. In the last chapter, land the story "
        "instead: end on the broad destination, not a cliffhanger.\n"
        "- A new plant is a specific object, line or action in this chapter that a LATER chapter may use. Leave `plants` empty "
        "rather than writing general observations, and write none in the last chapter.\n"
        "- `tone` is one sentence on how this chapter reads, as the narration style defines it.\n"
        f"- The people listed under PEOPLE are the whole cast of this chapter. `present` and `shifts` use only them, the main "
        f"character is always present, at most {MAX_CAST} are present, and no one else in the story is named or involved, "
        "not even in the events. `location` is a place from the list.\n"
        + (
            f"- THIS IS THE LAST CHAPTER: a character's ending above can only be shown if they are in `present` here — anyone "
            f"left out is excluded from the chapter entirely and their ending cannot happen on the page. Put every person "
            f'whose ending under "Where each person ends up" is not already true in `present` (up to {MAX_CAST}), and write '
            f"events that actually land each of their endings in action, not by having someone else report it secondhand. "
            f"Only leave someone out if the cast limit forces a choice or their ending has already happened on the page in an "
            f"earlier chapter.\n"
            if n == total
            else ""
        )
        + "\nREVISING (optional): you may also correct the story's setup when the chapter just written really changed it: "
        "`revised_premise`, `revised_theme`, `revised_ending`, `revised_arcs` (all of them), `revised_leave_open` (the full list) "
        "and `closed_leave_open` (items now settled), with `why_revised`. Do it only when events call for it, keep the rest empty, and "
        "keep the ending a broad destination, not a schedule. A story is allowed to end up somewhere other than where it started "
        "heading.\n" + f"{language_rule(language)}\n" + JSON_RULES
    )
