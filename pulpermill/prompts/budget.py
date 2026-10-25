"""Token budgets for the prompts (phase 5). `measure` says how many tokens a prompt takes, what it may take, and what is left.
The backend uses `check` to answer `too_long` (413) before it spends any time on a prompt that cannot fit."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from . import tokens

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def budgets() -> dict:
    return yaml.safe_load((HERE / "budgets.yaml").read_text(encoding="utf-8"))


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


def key(name: str) -> str:
    """end_story_character and end_story_world share one budget."""
    return "end_story" if name.startswith("end_story") else name


def input_limit(name: str) -> int:
    b = budgets()
    return b["n_ctx"] - b["max_output"][key(name)] - b["margin"]


def measure(prompt) -> Measure:
    """`prompt` is a Prompt; its name picks the reply's room."""
    return Measure(prompt.name, tokens.chat_tokens(prompt.text), input_limit(prompt.name), budgets()["max_output"][key(prompt.name)])


def check(prompt) -> Measure:
    m = measure(prompt)
    if not m.ok:
        raise PromptTooLong(m)
    return m


class PromptTooLong(Exception):
    """The backend answers this with the `too_long` error (413)."""

    def __init__(self, m: Measure):
        super().__init__(f"{m.name}: {m.tokens} tokens, {m.limit} allowed")
        self.measure = m


# How far the length caps are squeezed, in order, when a story's prompt does not fit. 1.0 is limits.yaml as written.
SQUEEZES = (1.0, 0.85, 0.7, 0.55, 0.4, 0.3)


def fit(build, squeezes=SQUEEZES):
    """`build()` makes one Prompt (or a list of them). Returns (result, factor, measures) for the first squeeze at which every
    prompt fits, so the backend sends the fullest prompt that fits. If none fits it raises PromptTooLong for the last try, which the
    backend answers with `too_long` (413)."""
    from . import textfiles as tx
    last = None
    for factor in squeezes:
        with tx.squeeze(factor):
            made = build()
        prompts = made if isinstance(made, list) else [made]
        measures = [measure(p) for p in prompts]
        bad = [m for m in measures if not m.ok]
        if not bad:
            return made, factor, measures
        last = bad[0]
    raise PromptTooLong(last)
