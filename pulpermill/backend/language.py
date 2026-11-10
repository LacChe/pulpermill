"""Did the model write in the language it was asked for? A small check on scripts and common words; a short text passes.
Returns a plain sentence saying what is wrong, or None. Names and a few foreign words do not trip it, but a whole passage in another
language does: Chinese needs most of its letters to be Han (capitalised Latin words, which are names, are left out of the count) and no
run of six or more Latin words, and a Latin-script language may have only a sprinkle of Han, kana or Hangul."""
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
SCRIPT_SHARE = 0.6        # at least this share of the letters must be in the language's script (Japanese and Korean)
ZH_HAN_SHARE = 0.8        # Chinese: at least this share of the letters, not counting the capitalised Latin words (names), must be Han
LATIN_RUN = 6             # Chinese: this many Latin words in a row, at least four of them lower case, are a passage in another language
CJK_IN_LATIN = 0.05       # a Latin-script language: at most this share of the letters may be Han, kana or Hangul
STRING_MIN_HAN = 15       # a reply string with this many Han characters is long enough to read, though Chinese has no spaces
MIN_LETTERS = 40          # below this there is too little to judge
MIN_WORDS = 25
MARGIN = 2.0              # another language's function words must outnumber the right one's by this much


def _count(pattern: str, text: str) -> int:
    return len(re.findall(f"[{pattern}]", text))


# Latin words one after another, with only spaces and plain punctuation between them: a stretch of English, French and the like.
_LATIN_RUN = re.compile(rf"(?:[{LATIN}]+[ \t'’\-,.;:!?\"“”]+){{{LATIN_RUN - 1},}}[{LATIN}]+")
_LATIN_WORD = re.compile(f"[{LATIN}]+")


def _foreign_passage(text: str) -> bool:
    """A run of Latin words that reads as a passage: a list of names (all capitalised) is not one."""
    for run in _LATIN_RUN.finditer(text):
        if sum(1 for word in _LATIN_WORD.findall(run.group()) if word[0].islower()) >= 4:
            return True
    return False


def _chinese_problem(text: str, han: int, letters: int) -> str | None:
    other = letters - han - sum(len(w) for w in _LATIN_WORD.findall(text) if w[0].isupper())      # names do not count against it
    if han / max(han + other, 1) < ZH_HAN_SHARE:
        return "the text is not written in Chinese"
    if _foreign_passage(text):
        return "the text has a passage that is not written in Chinese"
    return None


def check(text: str, language: str) -> str | None:
    letters = _count(HAN + KANA + HANGUL + LATIN + r"Ѐ-ӿ", text)
    if letters < MIN_LETTERS:
        return None
    han, kana, hangul = _count(HAN, text), _count(KANA, text), _count(HANGUL, text)
    latin = _count(LATIN, text)
    if language.startswith("zh"):
        return _chinese_problem(text, han, letters)
    if language == "ja":
        return None if (han + kana) / letters >= SCRIPT_SHARE and kana / letters >= 0.05 else "the text is not written in Japanese"
    if language == "ko":
        return None if hangul / letters >= SCRIPT_SHARE else "the text is not written in Korean"
    if language not in STOPWORDS:
        return None                      # a language this check does not know: leave it to the reader
    if (han + kana + hangul) / letters > CJK_IN_LATIN:
        return f"the text has Chinese, Japanese or Korean characters in it, which {language} does not use"
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
        if len(value.split()) >= min_words or len(value) >= 40 or _count(HAN, value) >= STRING_MIN_HAN:
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
