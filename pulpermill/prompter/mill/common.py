"""Small helpers shared by the call modules: wording files, a handle label, a clipping helper, and the stub's flow as the fallback."""
import hashlib
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

TEXT = Path(__file__).resolve().parent / "text"


@lru_cache(maxsize=None)
def load_text(call: str, lang: str = "en") -> dict:
    """The wording file `text/<lang>/<call>.yaml` as a dict (an empty or comment-only file is an empty dict). Cached, read-only."""
    with open(TEXT / lang / f"{call}.yaml", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def text_digest(call: str, lang: str = "en") -> str:
    """Six hex characters of the wording file's content, or "" when the file holds no wording. Read fresh, so it follows every edit."""
    raw = (TEXT / lang / f"{call}.yaml").read_text(encoding="utf-8")
    if not any(line.strip() and not line.lstrip().startswith("#") for line in raw.splitlines()):
        return ""
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]


def labelled(scope: Any, key: str, item_id: str, text: str) -> str:
    """One list item shown with its handle, `wants.1: text`, so the model can point at it. `scope` is a kit.handles scope."""
    return f"{scope.of(key, item_id)}: {text}"


def clip(text: str, factor: float, floor: int = 40) -> str:
    """The text cut to `factor` of its length (never below `floor` characters), at a sentence end when one falls in the kept
    second half, else at a word end. Factor 1.0 or more returns the text as it is."""
    if factor >= 1.0 or len(text) <= floor:
        return text
    limit = max(int(len(text) * factor), floor)
    if limit >= len(text):
        return text
    kept = text[:limit]
    ends = [m.end() for m in re.finditer(r"[.!?。！？](?=\s|$)", kept)]
    if ends and ends[-1] >= limit // 2:
        return kept[: ends[-1]].rstrip()
    return kept.rsplit(None, 1)[0] if " " in kept.strip() else kept


def stub_flow(call: str, request: dict, kit: Any):
    """The stub prompter's flow for `call`: what a call module returns until its own wording is written."""
    from ..stub.stub import StubPrompter
    return StubPrompter().flow(call, request, kit)


# ---- names that belong to no card ----------------------------------------------------------------------------------------------
# One detector for fill (setup), plan and generate (write). It is a port of `strangeNames` in tools/trial_checks.mjs (read-only there):
# a capitalised word that is not at the start of a sentence and is on no card, in the narration (quoted speech cut out). Two additions,
# both to keep to design rule 5 (a person beyond the cards appears by role only): an honorific and a name ("Old Man Tiber", "Master
# Elmsworth", "Mrs Hale") counts wherever it stands, speech included. English only: a story in another language is skipped, because a
# capital letter says nothing about a name in Chinese and little in other scripts. The check prefers missing a name to refusing a good
# text: common capitalised words are let through, and a plain capitalised word in long text counts only when it comes back.

_TITLES = ("Old Man|Old Woman|Old Mother|Old Father|Master|Mistress|Mrs|Mr|Ms|Miss|Aunt|Auntie|Uncle|Captain|Councilman|Councilwoman|Councillor|"
           "Sergeant|Constable|Deacon|Deaconess|Sister|Brother|Dame|Goodwife|Goodman|Granny|Grandma|Grandpa|Mayor|Reverend|Elder|Dr|Doctor|"
           "Professor|Sir|Lady|Lord|Madam|Madame|Father|Mother")
_TITLE_NAME = re.compile(rf"\b((?:{_TITLES})\.?\s+([A-Z][a-z]+(?:[’']s)?))")
_CAPITAL = re.compile(r"(^|[.!?…:;—\n]\s*[\"“‘']?|\s)([A-Z][a-z]+(?:[’']s)?)")
# Calendar words, titles on their own, and words that open a planning label: never a person.
_COMMON = set("Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August September October "
              "November December Mr Mrs Ms Dr Sir Lady Lord God Act Chapter".split()) | {t for chunk in _TITLES.split("|") for t in chunk.split()}


def _narration(text: str) -> str:
    """The text with anything in quotation marks cut out (the port of `narration` in trial_checks.mjs)."""
    for pattern in (r"“[^”]*”", r'"[^"]*"', r"「[^」]*」", r"『[^』]*』", r"‘[^’]*’(?=[\s.,!?])"):
        text = re.sub(pattern, " ", text)
    return text


def detects_names(request: dict) -> bool:
    """Whether the detector understands the story's language: English only (a missing language means English)."""
    return str(request.get("language") or "en").lower().split("-")[0] == "en"


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def card_words(*parts: Any) -> set[str]:
    """Every capitalised word in the strings of the given parts: the names on the cards, and the names in any text the writer typed or
    approved. Words in the text count wherever they stand, so 'Hemlock' in the writer's own setup is allowed."""
    return {m.group(0) for part in parts for text in _strings(part) for m in re.finditer(r"[A-Z][a-z]+", text)}


def strange_names(text: str, known: set[str], min_count: int = 1) -> list[str]:
    """The people `text` names who are on no card: honorific names first (whole phrase, "Master Elmsworth"), then capitalised mid-sentence
    words that are not in `known` and not common words. A plain word counts when it appears at least `min_count` times."""
    found: list[str] = []
    for m in _TITLE_NAME.finditer(text):
        word = re.sub(r"[’']s$", "", m.group(2))
        if word not in known and word not in _COMMON and m.group(1) not in found:
            found.append(m.group(1))
    body = _TITLE_NAME.sub(" ", _narration(text))
    counts: dict[str, int] = {}
    for m in _CAPITAL.finditer(body):
        if m.group(1) not in (" ", "\t", "\u00a0"):          # at the start of the text or after sentence punctuation (or a line break): a sentence's first word
            continue
        word = re.sub(r"[’']s$", "", m.group(2))
        if word in known or word in _COMMON:
            continue
        counts[word] = counts.get(word, 0) + 1
    found += [w for w, n in counts.items() if n >= min_count and not any(w in phrase for phrase in found)]
    return found


def names_found(request: dict, texts: list[str], allowed: list[Any], min_count: int = 1) -> list[str]:
    """The people the `texts` name who are on no card. `allowed` is the part of the request whose own words are fine to reuse: the cards and any
    text the writer typed or approved. Empty when the story's language is not English."""
    if not detects_names(request):
        return []
    return strange_names("\n".join(t for t in texts if t), card_words(*allowed), min_count)


def _norm_words(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower().replace("’", "'").replace("'", "")).split())


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?…])[\"”’']*\s+|\n+", text.strip()) if s.strip()]


def echoes_ending(opening: str, ending: str, first: int = 2, min_words: int = 6) -> bool:
    """Whether one of the first `first` sentences of `opening` repeats a sentence of `ending`, ignoring case, punctuation and spacing: the
    same sentence, one inside the other, nearly the same (ratio 0.9), or sharing a run of 8 words (the ending may be cut mid-sentence, and
    the opening may carry on past it). A sentence of fewer than `min_words` words is never an echo: a name or a short phrase may come back."""
    from difflib import SequenceMatcher
    old = [n for n in (_norm_words(x) for x in _sentences(ending)) if len(n.split()) >= min_words]
    for sentence in _sentences(opening)[:first]:
        new = _norm_words(sentence)
        if len(new.split()) < min_words:
            continue
        for n in old:
            if new == n or new in n or n in new or SequenceMatcher(None, new, n).ratio() >= 0.9:
                return True
            a, b = new.split(), n.split()
            if SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b)).size >= 8:
                return True
    return False


# ---- Hard and soft problems ------------------------------------------------------------------------------------------------
# A hard problem (nothing to use: far over the cap, a plan that is not in the four-points shape or lacks a required part) refuses every
# attempt. A soft problem (an echoed opening, a name on no card) is a defect a person can read and fix, so the first attempt is strict,
# the retry line carries the problem to the model, and a second attempt with only soft problems is used. The runner gives each step
# two attempts (backend/runner.py MAX_ATTEMPTS, not imported: a prompter never needs the runner); a step's check runs once per reply
# that is not empty and not malformed, in order, so the second check call is the last attempt.
ATTEMPTS = 2
log = logging.getLogger("pulpermill")


class Attempts:
    """Counts the calls to one step instance's check. One is made per step instance (a new one starts again at the first attempt)."""

    def __init__(self, attempts: int = ATTEMPTS):
        self.attempts, self.calls = attempts, 0

    def tick(self) -> bool:
        """Records one check call. True when it is the last attempt, the one that accepts soft problems."""
        self.calls += 1
        return self.calls >= self.attempts


def note_soft(call: str, step: str, line: str, what: str = "accepted") -> None:
    """Says once on the server console (not the run log) that a soft problem was accepted or an echo trimmed. `line` is the problem line
    or a count, never story text."""
    one = " ".join(str(line).split())
    # The facts also travel in the record, so a trace the backend keeps can pick them up through `logging` (nothing is imported from it).
    log.warning("call=%s step=%s soft problem %s: %s", call, step, what, one, extra={"pulpermill_soft": {"call": call, "step": step, "what": what, "line": one}})


_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"”’']*\s+|\n+")
_WORD = re.compile(r"[\w'’-]+")
MIN_TRIMMED_WORDS = 400


def trim_echo(opening: str, ending: str, first: int = 2, min_words: int = MIN_TRIMMED_WORDS) -> tuple[str, int]:
    """(the text, how many sentences were dropped). Of the first `first` sentences, each one that repeats a sentence of the previous ending
    is dropped, whole sentences only; the rest is kept as it was. When what remains has fewer than `min_words` words, or nothing repeats,
    the text is returned whole."""
    pieces, start = [], 0
    for m in _SENTENCE_END.finditer(opening):
        pieces.append(opening[start:m.end()])
        start = m.end()
    if opening[start:].strip():
        pieces.append(opening[start:])
    drop = [i for i, piece in enumerate(pieces[:first]) if piece.strip() and echoes_ending(piece, ending, first=1)]
    if not drop:
        return opening, 0
    kept = "".join(piece for i, piece in enumerate(pieces) if i not in drop).lstrip()
    if len(_WORD.findall(kept)) < min_words:
        return opening, 0
    return kept, len(drop)
