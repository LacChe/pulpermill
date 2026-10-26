"""Did the model write in the language it was asked for? A small check on scripts and common words; a short text passes.
Returns a plain sentence saying what is wrong, or None. Names and a few foreign words do not trip it."""
import re
from collections.abc import Iterable

HAN = r"㐀-鿿"
KANA = r"぀-ヿ"
HANGUL = r"가-힯ᄀ-ᇿ"
LATIN = r"A-Za-zÀ-ɏ"

# The commonest function words of each Latin-script language. Words shared by several are left out.
STOPWORDS = {
    "en": "the and was were with that this his her they for had not from but have she you him said what there their".split(),
    "fr": "le la les des une est que qui dans pour pas sur avec elle il ils nous vous était être mais cette".split(),
    "de": "der die das und ist nicht ein eine mit sich auf dem den von zu war er sie es auch aber wie".split(),
    "es": "el la los las una que del con por para como pero más fue era sus este esta ella él se su".split(),
}
_SETS = {code: set(words) for code, words in STOPWORDS.items()}
SCRIPT_SHARE = 0.6        # at least this share of the letters must be in the language's script
MIN_LETTERS = 40          # below this there is too little to judge
MIN_WORDS = 25
MARGIN = 2.0              # another language's function words must outnumber the right one's by this much


def _count(pattern: str, text: str) -> int:
    return len(re.findall(f"[{pattern}]", text))


def check(text: str, language: str) -> str | None:
    letters = _count(HAN + KANA + HANGUL + LATIN + r"Ѐ-ӿ", text)
    if letters < MIN_LETTERS:
        return None
    han, kana, hangul = _count(HAN, text), _count(KANA, text), _count(HANGUL, text)
    latin = _count(LATIN, text)
    if language.startswith("zh"):
        return None if han / letters >= SCRIPT_SHARE else "the text is not written in Chinese"
    if language == "ja":
        return None if (han + kana) / letters >= SCRIPT_SHARE and kana / letters >= 0.05 else "the text is not written in Japanese"
    if language == "ko":
        return None if hangul / letters >= SCRIPT_SHARE else "the text is not written in Korean"
    if language not in STOPWORDS:
        return None                      # a language this check does not know: leave it to the reader
    if latin / letters < 0.85:
        return f"the text is not mostly in the Latin script that {language} uses"
    words = re.findall(f"[{LATIN}]+", text.lower())
    if len(words) < MIN_WORDS:
        return None
    hits = {code: sum(1 for w in words if w in found) for code, found in _SETS.items()}
    other, most = max(((c, n) for c, n in hits.items() if c != language), key=lambda p: p[1])
    if most >= 5 and most > MARGIN * max(hits[language], 1):
        return f"the text looks like {other}, not {language}"
    return None


def strings_in(value, min_words: int = 6) -> Iterable[str]:
    """The free-written sentences in a JSON reply (not the short names and picks), so they can be checked."""
    if isinstance(value, str):
        if len(value.split()) >= min_words or len(value) >= 40:
            yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings_in(v, min_words)
    elif isinstance(value, list):
        for v in value:
            yield from strings_in(v, min_words)


def check_value(value, language: str) -> str | None:
    """`check` over a parsed reply's longer strings, joined (a sentence at a time is too little to judge)."""
    return check("\n".join(strings_in(value)), language)
