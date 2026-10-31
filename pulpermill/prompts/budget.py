"""Token budgets, generic: `measure` says how many tokens a prompt takes, what it may take, and what is left; `fit` finds the fullest
squeeze at which every prompt of a call fits. Nothing here knows what a prompt is for: the caller says how much room its reply needs
(a step's `max_output`). The backend answers `too_long` (413) before it spends any time on a call that cannot fit."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, NamedTuple

import yaml

from . import tokens

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def budgets() -> dict:
    return yaml.safe_load((HERE / "budgets.yaml").read_text(encoding="utf-8"))


class Sized(NamedTuple):
    """A prompt to be measured: a name for messages, the text of its one user turn, and the room its reply needs."""
    name: str
    text: str
    max_output: int


@dataclass(frozen=True)
class Measure:
    name: str
    tokens: int          # the prompt as the model sees it: <bos> + the chat template
    limit: int           # n_ctx - the reply's room - margin
    max_output: int

    @property
    def headroom(self) -> int:
        return self.limit - self.tokens

    @property
    def ok(self) -> bool:
        return self.headroom >= 0


def input_limit(max_output: int) -> int:
    b = budgets()
    return b["n_ctx"] - max_output - b["margin"]


def measure(item: Sized) -> Measure:
    return Measure(item.name, tokens.chat_tokens(item.text), input_limit(item.max_output), item.max_output)


class PromptTooLong(Exception):
    """The backend answers this with the `too_long` error (413)."""

    def __init__(self, m: Measure):
        super().__init__(f"{m.name}: {m.tokens} tokens, {m.limit} allowed")
        self.measure = m


def check(item: Sized, measurer: Callable[[Sized], Measure] = measure) -> Measure:
    m = measurer(item)
    if not m.ok:
        raise PromptTooLong(m)
    return m


# How far the length caps are squeezed, in order, when a prompt does not fit. 1.0 is as written.
SQUEEZES = (1.0, 0.85, 0.7, 0.55, 0.4, 0.3)


def fit(build: Callable[[float], "Sized | list[Sized]"], squeezes=SQUEEZES, measurer: Callable[[Sized], Measure] = measure):
    """`build(factor)` makes one Sized (or a list). Returns (made, factor, measures) for the first squeeze at which every prompt fits, so
    the fullest prompt that fits is sent. If none fits it raises PromptTooLong for the last try."""
    last = None
    for factor in squeezes:
        made = build(factor)
        items = made if isinstance(made, list) else [made]
        measures = [measurer(p) for p in items]
        bad = [m for m in measures if not m.ok]
        if not bad:
            return made, factor, measures
        last = bad[0]
    raise PromptTooLong(last)
