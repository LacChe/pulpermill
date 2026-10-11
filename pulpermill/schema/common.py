from __future__ import annotations

import logging
import re
from pydantic import AfterValidator, BaseModel, BeforeValidator
from pydantic.json_schema import SkipJsonSchema
from typing import Annotated, Optional



class Msg(str):
    """A message in English that also remembers its template and parameters, so the page can show it in another language.
    Everywhere else (logging, joins, tests) it is an ordinary string. Build one with M("template with {slots}", slot=value)."""
    template: str
    params: dict
    at: tuple = ()

    def __new__(cls, template: str, **params):
        obj = super().__new__(cls, template.format(**{k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in params.items()}))
        obj.template, obj.params, obj.at = template, params, []
        return obj

    def on(self, path: str, item=None, value=None, mode: str = "is"):
        """Say which field this message is about, so the page can outline it until it is fixed. `path` is the field's dotted
        path ("characters.role"), `item` the id (or chapter number) of the list item it sits in, `value` what is wrong with
        it. mode "is": the field is flagged while it still holds `value` (or, for a list, still contains it); mode
        "lacks": it is flagged while a list does not contain `value`."""
        self.at.append({"path": path, "item": None if item is None else str(item), "value": value, "mode": mode})
        return self


M = Msg


def to_json(x):
    """Plain JSON for the page: a message becomes {"s": English text, "t": template, "p": params}; containers are walked."""
    if isinstance(x, Msg):
        out = {"s": str(x), "t": x.template, "p": {k: to_json(v) for k, v in x.params.items()}}
        if x.at:
            out["at"] = list(x.at)
        return out
    if isinstance(x, dict):
        return {k: to_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_json(v) for v in x]
    return x


_CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"          # Han characters: written without spaces, so counted one by one
_CJK_RE = re.compile(f"[{_CJK}]")
_WORD_RE = re.compile(f"[^\\W_{_CJK}]+(?:['\u2019-][^\\W_{_CJK}]+)*")


def count_units(text: str) -> int:
    """Length of a text for the word target: words in space-separated scripts plus one per Han character."""
    return len(_CJK_RE.findall(text)) + len(_WORD_RE.findall(text))


def est_words(text: str) -> float:
    """Rough number of English-word equivalents (two Han characters count as about one word); for 'is this long enough' checks."""
    return len(_WORD_RE.findall(text)) + len(_CJK_RE.findall(text)) / 2


def squash(text: str) -> str:
    """Lower-case letters and digits only, so a quoted line is found in a text whatever the spacing or punctuation."""
    return re.sub(r"[\W_]+", "", text.lower())


def similar(a: str, b: str, threshold: Optional[float] = None) -> bool:
    """Do two long free-text entries say nearly the same thing? Overlap of character pairs, so it works for any script."""
    x, y = squash(a), squash(b)
    if min(len(x), len(y)) < DUPLICATE_MIN_CHARS:
        return False
    A, B = {x[i:i + 2] for i in range(len(x) - 1)}, {y[i:i + 2] for i in range(len(y) - 1)}
    return len(A & B) / len(A | B) >= (DUPLICATE_SIMILARITY if threshold is None else threshold)


RECENT_N = 5
DUPLICATE_SIMILARITY = 0.45     # a new "lasting change" or "detail" this alike to one already on any character is dropped
SAME_CHARACTER_SIMILARITY = 0.3   # against the same character's own current entries the bar is lower: the same arc, said again, is not news
MAX_HABITS = 5                   # habits on a card; a new one pushes the oldest out
DUPLICATE_MIN_CHARS = 24        # ...but only for entries this long (letters and digits); short ones differ by a word and mean different things
MAX_CHARACTERS = 6      # people one cast generation writes; a project can hold any number
MAX_CAST = 6            # people a single chapter can be written about (the main character included)
MAX_CHAPTERS = 10       # chapters in a generated outline
MAX_CHAPTER_NUM = 20    # hard ceiling when LOADING an outline, so longer hand-written ones still load
logger = logging.getLogger("pulpmill")


def _keep_recent(v: list[str]) -> list[str]:
    return v[-RECENT_N:]


Recent = Annotated[list[str], AfterValidator(_keep_recent)]


def push_recent(items: list[str], new: str) -> list[str]:
    """Append and trim to the most recent RECENT_N. Use this, not list.append."""
    return (items + [new])[-RECENT_N:]


# ---------------------------------------------------------------------------
# USE COUNTS AND ROTATING LISTS
# Each chapter the writer is handed only SOME of the items in the lists below, the least-used ones, and each item it was
# handed is counted. Every detail gets its turn and none wears out, and the choice is made in code, not left to the model.
# Path -> how many items. For the world's places, objects and groups the number is on top of the ones the chapter itself
# needs (its own place, anything its beat names, whatever its characters hold). A list not named here (rules, never-do
# lists, hidden truths, the outline's lists) always goes to the writer whole and is not counted.
# ---------------------------------------------------------------------------

POOLS = {
    "style.exemplars": 1,
    "style.chapter_shapes": 1,
    "characters.look": 1,
    "characters.habits": 1,
    "characters.sample_lines": 1,
    "world.locations": 2,
    "world.objects": 2,
    "world.groups": 1,
}

# {list field: {item key: times handed to the writer}}. The key is the item's text, or its id for places, objects and groups.
# It is code-owned live state: it is never part of the schema the model writes.
def _lenient_uses(v):
    """A count that is not a number is dropped rather than failing the whole card: this is bookkeeping, not content."""
    out: dict[str, dict[str, int]] = {}
    for field, row in (v.items() if isinstance(v, dict) else ()):
        if isinstance(row, dict):
            kept = {}
            for k, n in row.items():
                try:
                    kept[str(k)] = int(n)
                except (TypeError, ValueError):
                    pass                              # a count that is not a number is skipped
            out[str(field)] = kept
    return out


UsesMap = SkipJsonSchema[Annotated[dict[str, dict[str, int]], BeforeValidator(_lenient_uses)]]


def _pooled(card: str, fields: dict[str, list[str]]) -> dict[str, list[str]]:
    return {f: keys for f, keys in fields.items() if f"{card}.{f}" in POOLS}


def clean_uses(uses, live: dict[str, list[str]]) -> dict[str, dict[str, int]]:
    """Keep the counts of items that still exist. Zero counts are left out, and an item whose text was changed starts again."""
    out: dict[str, dict[str, int]] = {}
    for field, keys in live.items():
        have = uses.get(field) if isinstance(uses, dict) else None
        have = have if isinstance(have, dict) else {}
        row = {}
        for k in keys:
            try:
                n = int(have.get(k, 0))
            except (TypeError, ValueError):
                n = 0
            if n > 0:
                row[k] = n
        if row:
            out[field] = row
    return out


def _shown(items: list, chosen: Optional[list[str]], key=lambda x: x) -> list:
    """The items the writer sees: all of them when the list is not rotating (chosen is None), else the chosen ones."""
    return list(items) if chosen is None else [x for x in items if key(x) in set(chosen)]


def pick_least_used(keys: list[str], used: dict[str, int], k: int, required=()) -> list[str]:
    """The required items, plus the k least-used of the rest (ties keep the card's order). Returned in card order."""
    keys = list(dict.fromkeys(keys))
    req = set(required)
    rest = sorted((x for x in keys if x not in req), key=lambda x: used.get(x, 0))      # sorted() is stable
    chosen = req | set(rest[:max(k, 0)])
    return [x for x in keys if x in chosen]


def _beat_seq(text: str) -> list[str]:
    return _tokens(text.lower().replace("\u2019s", "").replace("'s", ""))


def _mentions(seq: list[str], name: str) -> bool:
    """True when the name's words (titles and articles left out) come one after another in the token list."""
    want = _name_tokens(name)
    n = len(want)
    return n > 0 and any(seq[i:i + n] == want for i in range(len(seq) - n + 1))


def slugify(name: str) -> str:
    return re.sub(r"[\W_]+", "_", name.lower()).strip("_") or "x"


def unique_ids(names: list[str], prefix: str = "") -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        base = prefix + slugify(n)
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return out


# ---------------------------------------------------------------------------
# Reference resolution. The model writes people, places and things by NAME; code turns what it wrote into the real id.
# A spelling difference ("Queen Ann" for "Princess Ann", "Old Inn" for "The Old Inn") therefore never costs a regeneration.
# ---------------------------------------------------------------------------

_TITLES = {
    "the", "a", "an", "mr", "mrs", "ms", "miss", "mx", "dr", "doctor", "prof", "professor", "sir", "dame", "lord", "lady",
    "king", "queen", "prince", "princess", "duke", "duchess", "earl", "count", "countess", "baron", "baroness",
    "emperor", "empress", "master", "mistress", "madam", "madame", "captain", "capt", "general", "colonel", "major",
    "sergeant", "lieutenant", "admiral", "commander", "judge", "father", "mother", "brother", "sister", "saint", "st",
    "uncle", "aunt", "old", "young", "little", "big", "grand", "great",
}


_TITLES_ZH = (
    "国王", "女王", "王后", "王子", "公主", "皇帝", "皇后", "太子", "公爵", "侯爵", "伯爵", "男爵", "爵士", "夫人", "小姐", "先生",
    "女士", "太太", "大人", "陛下", "殿下", "阁下", "老爷", "少爷", "姑娘", "博士", "教授", "医生", "船长", "将军", "上校", "少校",
    "中尉", "队长", "老师", "师傅", "大师", "神父", "修女", "大叔", "阿姨", "叔叔", "姐姐", "哥哥",
)   # multi-character titles only: a single character such as 王 is as often a surname as a title


def _tokens(text: str) -> list[str]:
    return re.findall(f"[{_CJK}]|[^\\W_{_CJK}]+", text)


def _name_tokens(text: str) -> list[str]:
    """The words of a name with titles and articles removed ("Queen Ann" and "Princess Ann" both give ['ann'];
    "安公主" and "女王安" both give ['安']). Han characters are separate tokens, since Chinese names have no spaces."""
    text = text.lower().replace("\u2019s", "").replace("'s", "")
    stripped = text
    for t in _TITLES_ZH:
        stripped = stripped.replace(t, " ")
    kept = [t for t in _tokens(stripped) if t not in _TITLES]
    every = _tokens(text)
    return kept or [t for t in every if t not in _TITLES] or every


class Resolver:
    """
    Maps whatever the model wrote for a character, place or object (its exact name, its id, or a shortened or re-titled form
    of the name) to the real id, or None. Order: exact name or id; the same words once titles are removed; a name that
    contains, or is contained in, exactly one entry. Anything ambiguous or unknown gives None: never a guess between two.
    """

    def __init__(self, items):
        pairs = [(i["id"], i.get("name") or i["id"]) for i in items]
        self.exact: dict[str, str] = {}
        for rid, name in pairs:
            for k in (rid.strip().lower(), name.strip().lower()):
                self.exact.setdefault(k, rid)
        self.tokens = {rid: set(_name_tokens(name)) for rid, name in pairs}

    def find(self, text) -> Optional[str]:
        if not isinstance(text, str) or not text.strip():
            return None
        hit = self.exact.get(text.strip().lower())
        if hit:
            return hit
        q = set(_name_tokens(text))
        if not q:
            return None
        same = [rid for rid, t in self.tokens.items() if t == q]
        if same:
            return same[0] if len(same) == 1 else None
        near = [rid for rid, t in self.tokens.items() if t and (q <= t or t <= q)]
        if len(near) <= 1:
            return near[0] if near else None
        score = {rid: (len(q & self.tokens[rid]), -len(q ^ self.tokens[rid])) for rid in near}
        best = max(score.values())
        top = [rid for rid, sc in score.items() if sc == best]
        return top[0] if len(top) == 1 else None


# --- text helpers shared by the outline, story and check sections (they sat in the checks section; moved here so those do not import each other) ---

def _as_dicts(items) -> list[dict]:
    return [i.model_dump() if isinstance(i, BaseModel) else i for i in items]


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


# Words ignored when matching a plant to its payoff (_content_words).
_PAYOFF_STOP = {"the", "and", "but", "for", "with", "when", "then", "this", "that", "they", "she", "her", "his", "him",
         "its", "one", "two", "who", "what", "where", "after", "before", "while", "about", "into", "from", "has",
         "had", "was", "were", "are", "not", "out", "off", "all", "any", "her", "their", "them", "there", "than"}


def _content_words(text: str) -> set[str]:
    """Meaningful words with a trailing plural 's' removed, so 'pillow' and 'pillows' match."""
    words = {re.sub(r"s$", "", w) for w in _words(text) if len(w) > 2 and w not in _PAYOFF_STOP}
    for run in "".join(ch if _CJK_RE.match(ch) else " " for ch in text).split():       # Han text: overlapping pairs of characters
        words |= {run[i:i + 2] for i in range(len(run) - 1)}
    return words


def _related(a: str, b: str) -> bool:
    """A plant and a payoff match when most of the shorter one's content words appear in the other."""
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return False
    short, long_ = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    return len(short & long_) / len(short) >= 0.6
