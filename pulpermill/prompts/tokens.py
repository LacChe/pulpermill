"""Counts Gemma 3 tokens with no outside packages (phase 5). The sandbox, CI and the Kaggle backend all need the same count, and
`tokenizers` is not always installable, so this reads the model's own `tokenizer.json` and runs the same byte-pair merges.

What Gemma's tokenizer does, as written in tokenizer.json:
  1. text is cut at the special tokens (<start_of_turn>, <end_of_turn>, ...), which are single tokens;
  2. in the rest, every space becomes "▁" and the whole run is one piece (the pre-tokenizer finds no spaces left to split at);
  3. the piece starts as single characters, a character that is not in the vocabulary becomes its UTF-8 bytes (<0xE2> ...);
  4. the pair with the lowest merge rank is merged again and again until none is left.

The files live in pulpermill/prompts/tokenizer/ (tokenizer.json, tokenizer_config.json) or in the folder named by the
PULPERMILL_TOKENIZER environment variable. `available()` says whether they are found; tests that need them skip when they are not.
"""
import heapq
import json
import os
import re
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent


def folder() -> Path:
    return Path(os.environ.get("PULPERMILL_TOKENIZER") or HERE / "tokenizer")


def available() -> bool:
    return (folder() / "tokenizer.json").exists()


class Gemma:
    def __init__(self, path: Path):
        data = json.loads((path / "tokenizer.json").read_text(encoding="utf-8"))
        model = data["model"]
        self.vocab: dict[str, int] = model["vocab"]
        self.ranks = {(a, b): i for i, (a, b) in enumerate(model["merges"])}
        self.added = {t["content"]: t["id"] for t in data["added_tokens"]}
        self.bos = self.added["<bos>"]
        self.unk = self.added["<unk>"]
        names = sorted(self.added, key=len, reverse=True)
        self._split = re.compile("(" + "|".join(re.escape(n) for n in names) + ")")
        self._cache: dict[str, list[int]] = {}

    def _bytes(self, ch: str) -> list[int]:
        return [self.vocab.get(f"<0x{b:02X}>", self.unk) for b in ch.encode("utf-8")]

    def _piece(self, text: str) -> list[int]:
        """Byte-pair merges over one piece. A heap of candidate pairs and a linked list keep long runs fast."""
        syms = list(text)
        n = len(syms)
        if n == 0:
            return []
        prev, nxt = list(range(-1, n - 1)), list(range(1, n + 1))
        nxt[-1] = -1
        alive = [True] * n
        heap: list[tuple[int, int, str, str]] = []

        def push(i):
            j = nxt[i]
            if j != -1:
                r = self.ranks.get((syms[i], syms[j]))
                if r is not None:
                    heapq.heappush(heap, (r, i, syms[i], syms[j]))

        for i in range(n):
            push(i)
        while heap:
            r, i, a, b = heapq.heappop(heap)
            j = nxt[i]
            if not alive[i] or j == -1 or not alive[j] or syms[i] != a or syms[j] != b:
                continue
            syms[i] = a + b
            alive[j] = False
            nxt[i] = nxt[j]
            if nxt[j] != -1:
                prev[nxt[j]] = i
            push(i)
            if prev[i] != -1:
                push(prev[i])
        ids, i = [], 0
        while i != -1:
            s = syms[i]
            if s in self.vocab:
                ids.append(self.vocab[s])
            else:
                for ch in s:
                    ids.extend([self.vocab[ch]] if ch in self.vocab else self._bytes(ch))
            i = nxt[i]
        return ids

    def encode(self, text: str, bos: bool = False) -> list[int]:
        ids = [self.bos] if bos else []
        for part in self._split.split(text):
            if not part:
                continue
            if part in self.added:
                ids.append(self.added[part])
                continue
            piece = part.replace(" ", "▁")
            if piece not in self._cache:
                self._cache[piece] = self._piece(piece)
            ids.extend(self._cache[piece])
        return ids

    def count(self, text: str) -> int:
        return len(self.encode(text))


@lru_cache(maxsize=1)
def gemma() -> Gemma:
    if not available():
        raise FileNotFoundError(f"Gemma tokenizer files not found in {folder()} (set PULPERMILL_TOKENIZER)")
    return Gemma(folder())


def count(text: str) -> int:
    return gemma().count(text)


def chat_text(user_text: str) -> str:
    """The exact text Gemma's chat template builds for one user turn, with the model's turn opened. The text is trimmed the way the
    template trims it. The <bos> is added by `chat_tokens`."""
    return f"<start_of_turn>user\n{user_text.strip()}<end_of_turn>\n<start_of_turn>model\n"


def chat_tokens(user_text: str) -> int:
    """Tokens the model sees for one prompt: <bos> + the chat template."""
    return len(gemma().encode(chat_text(user_text), bos=True))
