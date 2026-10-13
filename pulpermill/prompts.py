"""All the text sent to the model: the chapter templates, and the builders for every card prompt and for the next-beat planner. Builders only assemble strings from the data they are given; sending and checking is done in stages.py and chapter.py."""

import json

from . import config
from .schema import (
    CastDraft, MAX_CAST, MAX_CHAPTERS, MAX_CHARACTERS, OutlineDraft, STORY_STAGES, StyleCard, WorldDraft,
    spread_stages, stage_lines_for
)


SUMMARIZE_CHAPTER_PROMPT = """Read the chapter text below and write a summary of it: 3-5 sentences of
        plain prose covering key plot events, revelations, and character actions. Also state who learns
        or is told what, and any object that changes hands. Focus on facts that matter for continuity
        — do not include stylistic commentary. Do NOT use markdown bold, headers, asterisks, or any
        formatting, and do not add a label or preamble: begin directly with the summary. Refer to every
        person by name. Never write "I" or "we": the chapter is narrated by {narrator}, so use that name.

        CHAPTER {chapter_num} TEXT:
        {chapter_text}

        Write the summary in {language}, with that language's usual punctuation."""


GENERATE_CHAPTER_PROMPT = """LANGUAGE (this overrides everything else below): write the whole chapter, narration and dialogue, in
        {language}. The cards, notes, earlier chapters and these instructions may be written in other languages;
        that never changes the language you write in.

        Write chapter {chapter_num}, ~{target_words} {unit}, prose only, no meta-commentary.
        Do not include a chapter title, heading, or number at the top — begin directly with the prose.
        Stay strictly consistent with the cards below and do not contradict facts. Stay close to the
        word target: neither wrap up early nor run substantially long.

        CAST CONSTRAINT: The only named, recurring characters are: {named_cast}. They are the whole cast of this chapter:
        no other character of this story appears, speaks or acts in it.
        Introduce no other named or significant characters (anyone who could recur or matter to the
        plot). Minor background figures for texture are allowed, but they never get a proper name, not
        even a first name or a nickname used once: refer to them by role or brief description,
        consistently, in narration and in dialogue. A figure who needs to recur is not incidental, so
        leave them out.

        KNOWLEDGE CONSTRAINT: A character may only act on, reference, or react to what they have
        witnessed or been told in the story so far (see STORY SO FAR and WHAT THE LAST CHAPTER
        CHANGED), plus any hidden truth marked as known by them. No character may state, hint at, or
        act on a hidden truth they are not listed for, unless this chapter's beat says it is revealed here.

        PLOT CONSTRAINT: This chapter MUST accomplish the beat given at the very end of this prompt
        (THIS CHAPTER'S BEAT). It is what must actually happen, not a suggestion or mood. The events
        occur in the order given, the goal and obstacle drive the chapter, and it ends on the moment
        named. You may write original scene detail, dialogue, and pacing to get there, but do not
        skip, defer, soften, or substitute any event. Dramatize every listed character shift as a
        visible moment or choice, shown in action or dialogue, not merely implied by a character
        acting consistently. If no shifts are listed, do not invent an arc milestone.

        LAST LINES: end the chapter exactly on the moment named in ends_on, and stop there — do not add
        a line of reflection, summary, or reassurance after it, and do not resolve it early or soften it
        just because the chapter has run long enough. If ends_on is a question, threat, reversal, or
        choice left open (true for every chapter but the last), the reader should want to know what
        happens next, not feel the matter is closed. Only in the final chapter, where the beat lands the
        story instead, should the ending read as settled.

        THE CARDS (story, style, characters, world):
        {context}

        HOW TO READ THE CARDS: Each section says what its fields are for. Write each character as
        their current state says they are now, never contradict the world's rules, and follow the
        beat's Narration line for person and tense. The lists of looks, habits, sample lines, exemplars, chapter shapes, places,
        objects and groups are a selection made for this chapter, not everything on the cards. If an ENDING
        section appears, this is the final chapter: land it.

        STORY SO FAR (summary of earlier chapters):
        {prior_summary_block}

        PROSE CONSTRAINTS:
        - Exemplars and sample lines show rhythm, register, and voice only. Never reproduce or closely
          paraphrase a sentence, clause, or distinctive phrase from them. Follow the prose habits, and
          never do anything on the never-do list.
        - Looks and habits are reference facts: do not re-describe a character's appearance, voice, or
          mannerisms just because they appear in a scene. A look or habit given for this chapter is used
          AT MOST ONCE, in one sentence, when a moment truly calls for it (a habit when the character is
          nervous, lying or avoiding something; a look when it is changing or newly relevant, such as an
          injury, a prop being used, a reaction). Once it has been shown, do not return to it, repeat the
          gesture, or mention it again anywhere else in the chapter, even in passing: this applies most of
          all to a vivid signature object or tic (a coin, a pen, a drink) that is easy to reach for again —
          once it has done its one moment of work, leave it alone for the rest of the chapter.
        - If the style section gives a chapter shape, open and close the chapter as it says. Without one, begin with
          someone doing or saying something and do not open the way the previous chapter opened. Either way, never
          open on a smell, the weather or the light. A catchphrase or gesture from the cards is used at
          most once per chapter.
        - Once a rule, mechanism, or detail has been established in an earlier chapter, treat it as
          understood and do not re-explain it.
        - Do not narrate that a moment is significant, tense, or emotional: dramatize it through
          action, dialogue, and concrete sensory detail and trust the reader to feel it. Watch for
          stock phrasing that announces weight rather than earning it (e.g. "exhaled sharply through
          his/her nose," "carrying the weight of," "beyond simple words," "without a word"); these
          illustrate the pattern and are not an exhaustive list. Vary physical tics and transitions
          rather than defaulting to a recurring gesture.

        WHAT THE LAST CHAPTER CHANGED (plain facts, already true as this chapter opens; treat every one
        of them as settled and already known to the characters who were there — do not re-establish,
        re-explain, or have a character rediscover any of them):
        {changes_block}

        THIS CHAPTER'S BEAT (open the chapter at the Location and When given here; chapters are not
        necessarily back to back, so do not assume this one picks up right where the last one left off):
        {beat_block}
        {note_block}
        Write the chapter in {language}."""


EXTRACT_STATE_UPDATE_PROMPT = """Read the chapter below and extract what changed in the story state.
        Respond with ONLY valid JSON matching this schema, no fences, no preamble.
        Ensure the JSON is strictly valid — no trailing commas, no comments, no unescaped quotes.

        SCHEMA:
        {schema}

        KNOWN CHARACTERS (already have cards, shown here with their card and current state. Track
        them via character_updates, and do NOT list them in unintroduced_characters even under a
        nickname or description):
        {known_characters}

        EXISTING OBJECTS (use these ids exactly in object_moves and object_updates):
        {known_objects}

        EXISTING LOCATIONS (use these ids exactly for new_location in object_moves and in location_updates):
        {known_locations}

        EXISTING GROUPS (use these ids exactly in group_updates):
        {known_groups}

        Rules for filling the schema:
        - Use ids exactly as listed above. Never invent an id.
        - character_updates: include an entry for every KNOWN character who appears or acts in this
          chapter, with their condition (emotional and physical, at the end of the chapter). Compare
          against each character's card and current state above before filling anything else, and leave
          every other field empty unless the chapter clearly calls for it. Never put object or location ids
          in a character update.
        - "change": a turning point, not a mood. It must be a different kind of shift from every line in any
          character's current state: if it could be written as a rewording of one of them, or says the same
          arc again with a new detail, leave it empty. One short sentence. Most characters have no change in
          most chapters, and a chapter with none is normal.
        - "detail": only a durable fact the chapter newly established about them that is NOT already on their
          card or in their current state.
        - "want": only if this chapter settled or reversed what they want: they got it, lost it for good, gave it
          up, or found something bigger to want. Write what they want now, as one sentence in the same form as the
          want on their card. A setback or a doubt is not enough.
        - "blind_spot": only if this chapter made them see through their blind spot (they admitted it, or acted
          against it and meant it) or gave them a new one. Write their blind spot as it now stands, in the same form
          as the one on their card. A passing moment of doubt that they then fall back from is not enough.
        - "new_habit": a repeated behavior the chapter showed as a pattern (it happens more than once, or is plainly
          how they now act), not a one-off action, and not already among their habits. "dropped_habit": a habit from
          their card, copied exactly, that they have clearly given up or can no longer keep.
        - Write every text value (condition, change, detail, want, blind spot, habits,
          descriptions) in {language}. Ids and JSON keys stay exactly as given.
        - Every entry is about that one character only. Never copy or reword another character's entry, or an
          entry already listed in a current state: if it is not new and specific, leave it empty.
        - location_updates, object_updates, group_updates: only for something this chapter physically or
          materially changed (a place damaged, rebuilt, emptied or taken over; an object broken, opened, emptied or
          used up; a group that split, grew, lost its leader or changed what it wants). Write the new description
          of the thing as it is now, with the change folded in and its other facts kept, in one or two sentences.
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


JSON_RULES = ("Reply with one JSON object that matches the schema below, and nothing else: no commentary, "
              "no code fences, no markdown asterisks. Include every field in the schema. Use plain text in every field.")


# What the author wants to do with the example chapter. Any number can be ticked at once, so the prompt says all of them and
# then says what each means for the card being written.
CHAPTER_USES = ("sequel", "parallel")      # what a pasted example chapter is for; none: the cards describe its own story


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
        "sequel": "the example's characters stay as the chapter shows them; add a new person only when the continuation needs one",
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
    if not uses:
        return ("SOURCE CHAPTER: one chapter from a story. Treat it as evidence about the whole story and "
                "infer what it does not say. The author direction, if any, wins where the two disagree.\n\n" + body)
    stage = USE_FOR_CARD.get(getattr(req, "stage", ""), {})
    return ("EXAMPLE CHAPTER: one chapter from an existing story, given as the starting point for a NEW story. The author "
            "wants the new story to be this:\n"
            + "\n".join(f"- {USE_MEANING[u]}" for u in uses)
            + ("\n\nFor this card that means:\n" + "\n".join(f"- {stage[u]}" for u in uses if u in stage) if stage else "")
            + "\n\nWhere the author direction says which way to take it, follow it; where it does not, choose a direction that "
              "the chapter hints at but does not develop. The author direction wins wherever it disagrees with the chapter.\n\n" + body)


def source_block(req) -> str:
    """Only this card's own notes (and the example chapter, when it is switched on for this card). Other cards' notes are never sent."""
    parts = []
    if req.mode == "chapter" and req.chapter.strip():
        parts.append(chapter_source(req))
    if req.notes.strip():
        parts.append("AUTHOR DIRECTION: the author's rough notes for this card. Fill in whatever they leave out "
                     f"with fitting choices.\n\n<notes>\n{req.notes.strip()}\n</notes>")
    return "\n\n".join(parts)


def feedback_block(feedback) -> str:
    if not feedback:
        return ""
    return (f"\nThe author asked for this change: {feedback}\n"
            "Write a genuinely different version that applies the change.\n")


FIDELITY = ("FIDELITY: Copy every fact the source states exactly as stated: who did what to whom, reasons, names, "
            "numbers, how things work. Never change, soften, reverse or contradict one. Invent only what the source "
            "leaves open, and keep invented details small.")


def language_rule(code) -> str:
    lang = config.LANGUAGES.get(code) or config.LANGUAGES["en"]
    return (f"LANGUAGE: Write every text value in {lang['name']}, whatever language the source is written in. "
            "JSON keys and fixed option values stay exactly as the schema gives them. Use that language's usual punctuation.")


def _language(req) -> dict:
    return config.LANGUAGES.get(getattr(req, "language", "en")) or config.LANGUAGES["en"]


def language_head(req) -> str:
    """Opens a card prompt for any language but English. The card is read in that language, so it is written in it, and the
    schema and instructions that follow are English, which is why this goes first and is repeated after the schema."""
    if _language(req) is config.LANGUAGES["en"]:
        return ""
    name = _language(req)["name"]
    return (f"LANGUAGE (this overrides everything else below): write every text value of this card in {name}: every rule, "
            f"description, name for a habit and every example passage. The author's notes, any example chapter and these "
            f"instructions may be in another language; that never changes the language the card is written in. JSON keys and "
            f"fixed option values stay exactly as the schema gives them.\n\n")


def tail(req, schema_cls) -> str:
    end = "" if _language(req) is config.LANGUAGES["en"] else f"\n\nREMINDER: write every text value in {_language(req)['name']}."
    return (f"\n{FIDELITY}\n{feedback_block(req.feedback)}\n{language_rule(getattr(req, 'language', 'en'))}\n{JSON_RULES}"
            f"\n\nSCHEMA:\n{json.dumps(schema_cls.model_json_schema())}{end}")


# ---------------------------------------------------------------- STYLE
def style_prompt(req) -> str:
    if req.mode == "chapter":
        task = ("Describe how this chapter is actually written: the narrator's voice, sentence rhythm, how "
                "dialogue is handled, how any humor, tension or emotion is handled, and what the writing avoids. "
                "Infer the point of view and tense from the text.")
    else:
        task = ("Base the style on the genre, tone and feel the author describes. Where the notes say nothing "
                "about it, choose the style that best fits.")
    return (
        "You are writing a narration style card for a story-writing engine. The same card is reused for every "
        "chapter of one story, so it says HOW the story is told and never WHAT happens in it.\n\n"
        f"{source_block(req)}\n\nTASK: {task}\nRULES:\n"
        "- The card contains no character names, place names, plot events, or nouns that belong only to this story. "
        "That includes the exemplars.\n"
        "- Every rule is concrete enough that a reader could check it on the page.\n"
        "- Write rules as things to do. Do not add a sentence-length limit, a dialogue ratio or any other number "
        "unless the author gave one.\n"
        "- Before writing, work out what makes this narrator recognisable and put each point on the card: "
        "(a) the narrator's attitude toward events and what they tend to notice or make of things (humor, irony, awe, menace, tenderness, or none); (b) whether the narrator comments "
        "on events or stays silent, and how; (c) sentence rhythm, including any contrast between long and short; "
        "(d) how much of a chapter is dialogue and how it is tagged; (e) how an emotional moment is handled; "
        "(f) how chapters open and close, described as the narrator's moves and never as plot. Put them in `voice`, "
        "`prose_habits` and `avoid`; chapter shapes have their own rule below.\n"
        "- Describe only what the source does. If it has no inner monologue, do not ask for any. Never turn a missing "
        "quality into its opposite.\n"
        + ("- The avoid list names what this narrator conspicuously never does, up to six items, each named plainly.\n"
           if req.mode == "chapter" else
           "- The avoid list holds everything the author said to avoid, each named plainly, and nothing else except "
           "at most two habits the author's description clearly implies. Do not pad it with generic writing advice.\n") +
        "- The exemplars are two or three short passages (two to four sentences each) about ordinary everyday "
        "situations in a different part of life from the story. They use none of the story's nouns, jobs, objects "
        "or settings. They must reproduce points (a) to (e): the same "
        "attitude, the same rhythm, the same handling of feeling. Plain description in the right tense is not enough. "
        "They obey every prose habit and avoid item on the card, and each shows something different.\n"
        + ("- `chapter_shapes` holds up to four chapter shapes the source uses. Each is one short instruction covering how "
           "a chapter opens, how it closes and the balance of dialogue and narration, and the shapes differ clearly from one "
           "another. Structure only, never plot. Leave it empty if the source shows no clear shapes.\n"
           if req.mode == "chapter" else
           "- `chapter_shapes` holds 2-4 distinct chapter shapes, each one short instruction covering how a chapter opens, "
           "how it closes and the balance of dialogue and narration. Use what the author described; invent the rest so "
           "there are at least two, choosing shapes that fit the genre and tone and that differ clearly from one another "
           "(for example: one opens on dialogue and closes quiet, another opens on action and closes on a question). "
           "Structure only, never plot, and never contradict a shape the author gave.\n") +
        "- Do not copy wording from these instructions.\n" + tail(req, StyleCard))



# ---------------------------------------------------------------- CHARACTERS
def characters_prompt(req) -> str:
    style = req.cards.get("style") or {}
    narrator = (f"\nFor contrast, the narrator's voice is: {style['voice']}\n"
                "Each character's voice must sound different from the narrator's.\n") if style.get("voice") else ""
    return (
        "You are writing the character cards for a story-writing engine.\n\n"
        f"{source_block(req)}\n{narrator}\n"
        f"TASK: Write the whole cast together, one card per main character the source describes, at most {MAX_CHARACTERS}. "
        f"If the source has more people than that, keep the {MAX_CHARACTERS} who matter most to the plot.\n"
        "RULES:\n"
        "- Use what the source says. Invent the missing details sparingly and concretely.\n"
        "- Compare the characters as you write: no two share a want, a blind spot, a habit or a manner of speaking.\n"
        "- Write every character's fields in different words and different sentence shapes. No phrase of four or more "
        "words may appear in the same field of two characters, and no two fields may open the same way.\n"
        "- `role` says in a few words what this person is and does in this story, using the source's own words for "
        "their job or place. Never use a title that belongs to a different character, even a minor one, and never "
        "a single bare word.\n"
        "- `sample_lines` are new lines this person might say in situations outside the story. Each is unique to "
        "this person, quotes nothing from the source, and gives away no plot.\n"
        "- `blind_spot` says how the person sees themselves and the specific thing they do that contradicts it "
        "(for example: calls herself easygoing, yet redoes everyone else's work). A nervous tic is not a blind spot.\n"
        "- Looks and habits are things a reader could watch a person do, never labels.\n"
        "- Each `toward` entry names another character in this cast exactly as that character's `name` is written, "
        "and is written from this character's side only. Add an entry for every other main character they have a stake in.\n"
        "- Mention no places or objects by id.\n" + tail(req, CastDraft))



# ---------------------------------------------------------------- WORLD
def world_prompt(req, cast) -> str:
    return (
        "You are writing the world card for a story-writing engine.\n\n"
        f"{source_block(req)}\n\nTHE CAST (write people by these names exactly):\n{cast_lines(cast)}\n\n"
        "TASK: Write the world the story happens in.\nRULES:\n"
        "- The setting is one paragraph of the place and occasion the source describes. Add no era, country, scale "
        "or popularity the source does not state, and never explain or praise the world's customs.\n"
        "- Write one rule for every mechanic the source describes, each as a separate settled fact. Never tell the "
        "writer how to write or what tone to use.\n"
        "- A hidden truth is a true fact that has not yet appeared on the page and steers the story from behind "
        "the scenes. `known_by` lists the names of the cast members the fact is about or who did the thing, unless the "
        "source says nobody knows it, in which case it is empty.\n"
        + ("- Read the chapter for facts that some characters know and others do not, or that the story keeps back "
           "for later. List each as a hidden truth, with `known_by` the people who know it. If there are none, leave "
           "the list empty.\n" if req.mode == "chapter" else "") +
        "- An object's `owner` is the name of a cast member or null. Its `location` is the exact name of one of "
        "the locations you write, or null when the source does not say where it is.\n"
        "- Write a location for every place the source names or says a scene happens in, without merging or skipping "
        "any. Include only the objects and groups that matter to the plot.\n"
        + tail(req, WorldDraft))



# ---------------------------------------------------------------- OUTLINE
def outline_prompt(req, cast, world, want) -> str:
    places = "\n".join(f"- {l['name']}: {l['description']}" for l in world["locations"])
    truths = "\n".join(f"- {t['id']}: {t['fact']}" for t in world.get("hidden_truths", [])) or "(none)"
    rules = "\n".join(f"- {r}" for r in world["rules"])
    names = "\n".join(f"- {c['name']}: {c.get('role', '')}" for c in cast)
    groups = "\n".join(f"- {g['name']}: {g.get('description', '')}" + (f" Wants: {g['wants']}" if g.get("wants") else "")
                       for g in world.get("groups", []))
    group_block = ("GROUPS (background collectives; they cannot be listed in `present`, so they appear only inside "
                   f"the events text, as unnamed crowds or officials):\n{groups}\n\n") if groups else ""
    stage_block = "\n".join(f"{k}. {name}: {text}" for k, (name, text) in STORY_STAGES.items())
    st = req.cards.get("style") or {}
    style_block = (f"THE STORY'S NARRATION STYLE (the outline must suit this register):\nLabel: {st.get('label', '')}\n"
                   f"Voice: {st.get('voice', '')}\n\n") if st else ""
    if want:
        count_rule = (f"The story has exactly {want} chapters: set `chapter_count` to {want}. If the author describes more or "
                      "fewer sections than that, fit them into the chapters in order. ")
        stage_rule = ("- " + " ".join(l.strip() for l in stage_lines_for(0, spread_stages(want)[0])) + " Build chapter 1 to do all of it.\n")
    else:
        count_rule = ("Decide how many chapters the whole story has and set `chapter_count`: exactly the number the author "
                      "says, else one chapter for each chapter or section they describe (never splitting one of theirs into "
                      "two); if they describe none, plan five to eight. ")
        stage_rule = ("- Chapter 1 is the opening of the story and covers the stages it is given: Setup only when the story "
                      "has six or more chapters, Setup and Spark with three to five chapters, Setup, Spark and Friction with "
                      "two, all six with a single chapter. Build chapter 1 to do all of that.\n")
    return (
        "You are writing the plot outline for a story-writing engine.\n\n"
        f"{source_block(req)}\n\n{style_block}CHARACTERS (write names exactly like this):\n{names}\n\n"
        f"LOCATIONS (write names exactly like this):\n{places}\n\nHOW THE WORLD WORKS:\n{rules}\n\n{group_block}"
        f"HIDDEN TRUTHS (refer to them by id in `reveals`):\n{truths}\n\n"
        f"THE STORY'S SIX STAGES (a pacing guide for how the whole story escalates. It is NOT a list of chapters: its length "
        f"says nothing about how many chapters to write):\n{stage_block}\n\n"
        f"TASK: Set up the story: its premise, main character, theme, the broad ending it is heading for, the character arcs, "
        f"how many chapters it has (at most {MAX_CHAPTERS}), and the beat of chapter 1 ONLY. " + count_rule +
        "The beats of the later chapters are written one at a time after each chapter is finished, so do not plan or "
        "mention them: `chapter_beats` has exactly one item.\n"
        "\nRULES:\n" + stage_rule +
        "- Stakes come from the first two stages: by the end of the stage 2 chapter the reader knows what the "
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
        "only inside the events text.\n"
        + tail(req, OutlineDraft))


# ---------------------------------------------------------------- WORLD
def cast_lines(cast) -> str:
    return "\n".join(f"- {c['name']}: {c.get('role', '')}" for c in cast)


# ---------------------------------------------------------------- THE NEXT BEAT
# A beat is written only when the chapter before it is finished, so it can follow what really happened. Nothing past the chapter
# being written exists: later beats are not planned, stored or shown to the writer.
BEAT_TAIL_CHARS = 1500            # how much of the chapter just written the planner reads (the ending is what matters). The
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
        f"- {c.name}: {c.role}. Wants: {c.want}. Blind spot: {c.blind_spot}."
        + (f" Now: {c.wrap.condition}" if c.wrap.condition else "")
        + (f" Lately: {'; '.join(c.wrap.recent_changes)}" if c.wrap.recent_changes else "") for c in story.characters)
    places = "\n".join(f"- {l.name}: {l.description}" for l in w.locations)
    rules = "\n".join(f"- {r}" for r in w.rules) or "(none)"
    cast_ids = {c.id for c in story.characters}                          # only these people exist for this chapter
    objs = "\n".join(f"- {o.name}" + ((f", held by {name(o.owner)}" if o.owner in cast_ids else ", held by someone outside this cast") if o.owner else "")
                     + (f", at {here.get(o.location, o.location)}" if o.location else "") for o in w.objects) or "(none)"
    groups = "\n".join(f"- {g.name}: {g.description}" for g in w.groups)
    left = story.unrevealed_truths(n - 1)
    done = [t for t in w.hidden_truths if t not in left]
    know = lambda t: ", ".join(name(c) for c in t.known_by if c in cast_ids) or "no one in this cast"
    truths = "\n".join(f"- {t.id}: {t.fact} (known to: {know(t)})" for t in left) or "(none left)"
    revealed = "\n".join(f"- {t.fact}" for t in done) or "(none yet)"
    plants = story.open_plants(n - 1)
    prev = story.beat_for(n - 1) if n > 1 else None
    stage = spread_stages(total)[min(n, total) - 1]
    stage_text = "\n".join(stage_lines_for(prev.stage if prev else 0, stage))
    stories = "\n".join(f"Chapter {i + 1}: {t}" for i, t in enumerate(summaries)) or "(no earlier chapters)"
    tail_text = prev_text.strip()[-BEAT_TAIL_CHARS:] if prev_text.strip() else "(none)"
    st = story.style
    left_n = total - n + 1
    past = [b for b in plot.chapter_beats if b.chapter_num < n]
    ledger = "\n".join(f"- Chapter {b.chapter_num}: {b.goal} At {here.get(b.location, b.location)}, with "
                       f"{', '.join(name(c) for c in b.present)}." + (f" What changed: {b.turn}" if b.turn else "")
                       + f" Ended on: {b.ends_on}" for b in past) or "(none)"
    places_left, people_left = story.least_used(n - 1)
    objects_left, groups_left = story.least_used_world(n - 1)
    fresh = ("Places the story has been to least: " + ", ".join(f"{a} ({k}×)" for a, k in places_left) + "\n"
             + ("People who have been on the page least: " + ", ".join(f"{a} ({k}×)" for a, k in people_left) + "\n" if people_left else "")
             + ("Objects the story has made the least use of: " + ", ".join(f"{a} ({k}×)" for a, k in objects_left) + "\n" if objects_left else "")
             + ("Groups the story has made the least use of: " + ", ".join(f"{a} ({k}×)" for a, k in groups_left) + "\n" if groups_left else ""))
    return (
        "You are planning the next chapter of a story that is written one chapter at a time. Only the beat of the next "
        f"chapter is needed now: chapter {n} of {total}. Nothing after it has been planned, so do not plan it.\n\n"
        f"THE STORY SO FAR (the premise, theme, ending, arcs and the list of what stays open can be revised: see REVISING)\nPremise: {plot.premise}\nMain character: {name(plot.protagonist)}\n"
        f"Theme (steers the plot; never stated aloud): {plot.theme}\n"
        f"Where the story is heading (a broad destination, not a schedule; change it if events have moved the story elsewhere): {plot.ending}\n"
        + ("Never resolve or explain: " + "; ".join(plot.leave_open) + "\n" if plot.leave_open else "")
        + "Where each person ends up: " + "; ".join(f"{name(a.character)}: {a.end}" for a in plot.arcs) + "\n"
        f"Narration style: {st.label}. {st.voice}\n\n"
        f"THE CARDS NOW (after chapter {n - 1}; this is the truth of the story at this point)\n"
        f"PEOPLE:\n{chars}\n\nSETTING: {w.setting}\nHOW THE WORLD WORKS (permanent facts; reach for one as an obstacle or a "
        f"stake when it fits this chapter):\n{rules}\n\nPLACES (write names exactly like this):\n{places}\n"
        f"OBJECTS:\n{objs}\n" + (f"GROUPS (background collectives; they appear only inside the events text):\n{groups}\n" if groups else "")
        + f"HIDDEN TRUTHS ALREADY REVEALED (part of what happened):\n{revealed}\n\n"
        f"WHAT HAS HAPPENED\n{stories}\n\nThe last chapter ended like this (the ending only):\n{tail_text}\n"
        + (f"It stopped at: {prev.ends_on}\n" if prev else "") +
        f"\nALREADY USED (the earlier chapters in brief; this chapter must not repeat any of them):\n{ledger}\n\n"
        f"FRESH MATERIAL (use it when the story allows; a new place, an object or group barely touched so far, or a person "
        f"who has been away is the easiest way to make a chapter different):\n{fresh}"
        f"\nTHIS CHAPTER: chapter {n} of {total}\n{stage_text}\n"
        f"Chapters left, counting this one: {left_n}.\n\n"
        f"CHOOSE FROM WHAT IS STILL AVAILABLE\nHidden truths not yet revealed (put an id in `reveals` only if that truth becomes "
        f"known on the page in this chapter, to everyone present; most chapters reveal one or none; a truth once revealed cannot be "
        f"chosen again; try to reveal them over the chapters that are left, at a pace the story can carry, but a story does not "
        f"have to reveal every one):\n{truths}\n"
        + ("Plants not yet paid off (to use one in this chapter, copy its wording exactly into `pays_off`; a plant once paid off "
           "cannot be chosen again; use what the story calls for and leave the rest):\n" + "\n".join(f"- {p}" for p in plants) + "\n"
           if plants else "Plants not yet paid off: (none)\n")
        + "\nRULES:\n"
        "- Follow from where the last chapter really ended and from the cards as they are now. Respond to what actually "
        "happened; do not return to any earlier idea of the plot.\n"
        "- Each event happens once. Never repeat an earlier chapter's event, scene, argument or confession, and do not replay "
        "an earlier chapter with different wording. The story must move forward: something is different when this chapter ends.\n"
        "- Before settling on the obstacle and events, check FRESH MATERIAL and HOW THE WORLD WORKS for something the story "
        "has barely used: an object, a group or a world rule the cards already give you. Reach for one of these instead of "
        "returning to the same two or three details the last few chapters leaned on, whenever it genuinely fits the chapter; "
        "do not force one in where it does not.\n"
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
        + (f"- THIS IS THE LAST CHAPTER: a character's ending above can only be shown if they are in `present` here — anyone "
           f"left out is excluded from the chapter entirely and their ending cannot happen on the page. Put every person "
           f"whose ending under \"Where each person ends up\" is not already true in `present` (up to {MAX_CAST}), and write "
           f"events that actually land each of their endings in action, not by having someone else report it secondhand. "
           f"Only leave someone out if the cast limit forces a choice or their ending has already happened on the page in an "
           f"earlier chapter.\n" if n == total else "")
        + "\nREVISING (optional): you may also correct the story's setup when the chapter just written really changed it: "
        "`revised_premise`, `revised_theme`, `revised_ending`, `revised_arcs` (all of them), `revised_leave_open` (the full list) "
        "and `closed_leave_open` (items now settled), with `why_revised`. Do it only when events call for it, keep the rest empty, and "
        "keep the ending a broad destination, not a schedule. A story is allowed to end up somewhere other than where it started "
        "heading.\n"
        + f"{language_rule(language)}\n" + JSON_RULES)
