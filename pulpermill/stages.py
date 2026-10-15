"""The card stages: each takes the page's request and returns (card, warnings). Prompt text lives in prompts.py; this module sends it, checks the language and finishes the card with the schema's finalize_* functions."""

import re

from . import config, generation, prompts
from .prompts import _language, language_head, style_prompt
from .schema import (
    CastDraft,
    M,
    MAX_CHARACTERS,
    NextBeatD,
    OutlineDraft,
    PORTRAIT_FIELDS,
    StateUpdate,
    StyleCard,
    WorldBible,
    WorldDraft,
    _CJK,
    chapter_count_in,
    check_characters,
    check_outline,
    check_world,
    finalize_cast,
    finalize_outline,
    finalize_world,
)


class NotBuilt(Exception):
    pass


# Ordinary words that can look like names when capitalised (guess_names). English only; separate from the schema's word lists.
NOT_NAMES = {
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
}


def guess_names(text: str) -> list:
    """Name-like words: capitalised mid-sentence somewhere, and never seen in lower case anywhere in the input.
    (Capitals after a comma in dialogue, like 'said, "But', are ordinary words and appear lower-case elsewhere.)"""
    words = re.findall(r"[A-Za-z']+", text)
    lower = {w for w in words if w.islower()}
    mid = set()
    for sent in re.split(r"[.!?\n]+", text):
        for w in re.findall(r"[A-Za-z']+", sent)[1:]:
            if w[:1].isupper() and len(w) > 2:
                mid.add(w.lower())
    return sorted(w for w in mid if w not in lower and w not in NOT_NAMES)


def check_card_language(card, req) -> None:
    """Fail (so the model is asked again) when a card's text is in the wrong script for the chosen language. Ids and fixed
    options are left out; a card too short to judge passes."""
    lang = _language(req)
    texts: list[str] = []

    def walk(v, key=""):
        if isinstance(v, dict):
            for k, x in v.items():
                if k != "id":
                    walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str) and not re.fullmatch(r"[a-z0-9_]+", v):
            texts.append(v)

    walk(card)
    blob = " ".join(texts)
    han, latin = len(re.findall(f"[{_CJK}]", blob)), len(re.findall("[A-Za-z]", blob))
    if han + latin < 40:
        return
    share = han / (han + latin)
    if share < 0.5 if lang.get("cjk") else share > 0.3:
        raise ValueError(
            M(
                "the card text is not written in {language}. Rewrite every text value of the card in {language}, "
                "keeping the JSON keys and fixed option values as they are",
                language=lang["name"],
            )
        )


def lang_post(req, post=None):
    """The check for the chosen language, then the stage's own post step."""

    def run(d):
        check_card_language(d.model_dump(mode="json"), req)
        return post(d) if post else d

    return run


def run_style(req):
    card = generation.structured_call(
        language_head(req) + style_prompt(req),
        StyleCard,
        max_tokens=config.MAX_TOKENS["style"],
        temperature=config.TEMPS["style"],
        min_tokens=config.MIN_TOKENS["style"],
        post=lang_post(req),
    )
    blob = card.model_dump_json().lower()
    src = req.notes + "\n" + (req.chapter if req.mode == "chapter" else "")
    warnings = [
        M(
            "the style uses '{word}', a name-like word from your input; style should not name story details",
            word=n,
        )
        for n in guess_names(src)
        if re.search(rf"\b{re.escape(n)}\b", blob)
    ]
    return card.model_dump(mode="json"), warnings


# ---------------------------------------------------------------- CHARACTERS
def cast_post(d):
    if len(d.characters) > MAX_CHARACTERS:
        raise ValueError(
            M(
                "too many characters ({n}); write at most {max}, keeping the ones who matter most",
                n=len(d.characters),
                max=MAX_CHARACTERS,
            )
        )
    return finalize_cast(d)


def story_words_in_cards(cards, req) -> list:
    """Name-like words from the author's input (a place, an object, a person outside the cast) that a card has used. A card
    should hold up in any story, so these are story details that leaked in. The cast's own names are expected and left out."""
    src = req.notes + "\n" + (req.chapter if req.mode == "chapter" else "")
    own = {w.lower() for c in cards for w in re.findall(r"[A-Za-z']+", c.name)}
    names = [n for n in guess_names(src) if n not in own]
    out = []
    for c in cards:
        for n in names:
            for field in PORTRAIT_FIELDS:
                value = getattr(c, field)
                if re.search(rf"\b{re.escape(n)}\b", value.lower()):
                    out.append(
                        M(
                            "{name}: {field} uses '{word}', a name-like word from your input; a card should not name story details",
                            name=c.name,
                            field=field,
                            word=n,
                        ).on(f"characters.{field}", c.id, value)
                    )
                    break  # one note for each word, however many fields use it
    return out


def cast_tweak(schema):
    """The cast card's schema as the model is asked for it: at most MAX_CHARACTERS people."""
    schema["properties"]["characters"].update(maxItems=MAX_CHARACTERS)


def run_characters(req):
    prompt = prompts.characters_prompt(req)
    cards = generation.structured_call(
        language_head(req) + prompt,
        CastDraft,
        max_tokens=config.MAX_TOKENS["characters"],
        temperature=config.TEMPS["characters"],
        min_tokens=config.MIN_TOKENS["characters"],
        post=lang_post(req, cast_post),
        tweak=cast_tweak,
    )
    return [c.model_dump(mode="json") for c in cards], story_words_in_cards(
        cards, req
    ) + check_characters(cards, set())


def run_world(req):
    cast = req.cards.get("characters")
    if not cast:
        raise ValueError(M("generate the characters first"))
    cast_ids = {c["id"] for c in cast}
    prompt = prompts.world_prompt(req, cast)
    notes: list = []

    def post(d):
        notes.clear()
        return finalize_world(d, cast_ids, cast, notes)

    world = generation.structured_call(
        language_head(req) + prompt,
        WorldDraft,
        max_tokens=config.MAX_TOKENS["world"],
        temperature=config.TEMPS["world"],
        min_tokens=config.MIN_TOKENS["world"],
        post=lang_post(req, post),
    )
    return world.model_dump(mode="json"), notes + check_world(world, cast_ids)


# ---------------------------------------------------------------- OUTLINE
def run_outline(req):
    cast, world = req.cards.get("characters"), req.cards.get("world")
    if not cast or not world:
        raise ValueError(M("generate the characters and the world first"))
    want = req.chapters or chapter_count_in(
        req.notes
    )  # the author's stated chapter count, if any: used as given, in code
    prompt = prompts.outline_prompt(req, cast, world, want)
    res = generation.structured_call(
        language_head(req) + prompt,
        OutlineDraft,
        max_tokens=config.MAX_TOKENS["outline"],
        temperature=config.TEMPS["outline"],
        min_tokens=config.MIN_TOKENS["outline"],
        post=lang_post(req, lambda d: finalize_outline(d, cast, world, want)),
    )
    bible = WorldBible.model_validate(
        {**world, "locations": world["locations"] + res.new_locations}
    )
    warnings = res.notes + check_outline(res.plot, {c["id"] for c in cast}, bible)
    return (
        res.plot.model_dump(mode="json"),
        warnings,
        {"world_additions": res.new_locations},
    )


STAGES = {
    "style": run_style,
    "characters": run_characters,
    "world": run_world,
    "outline": run_outline,
}

# Every schema the model is asked to write as JSON, with the tweak structured_call applies to it: the startup grammar check builds a grammar from each.
GRAMMAR_CHECKS = [
    (StyleCard, None),
    (CastDraft, cast_tweak),
    (WorldDraft, None),
    (OutlineDraft, None),
    (NextBeatD, None),
    (StateUpdate, None),
]
