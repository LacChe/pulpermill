"""The prompter interface: everything about wording, and nothing about running. The backend's runner does the mechanical work (token
fit and squeeze, the two attempts and the retry line, cancel, progress, the run log, ids); a prompter decides what to ask the model and
what shape the answer has. See README.md in this folder.

A prompter answers each model call with a Flow. A Flow hands the runner one Step at a time. Nothing here, and nothing a prompter
needs from the runner, names a story idea."""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Literal

CALLS = ("fill", "judge", "style_fit", "plan", "generate")
SAMPLING = ("prose", "thinking", "structured")        # the sampling sets the Config holds; a step names one
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,32}$")          # the contract's Progress name: it is what `status` shows


@dataclass(frozen=True)
class Step:
    """One model call.

    name        a short word for progress and the run log (letters, digits, - and _; at most 32). Steps may share a name.
    text        text(squeeze) -> the prompt, one user turn. `squeeze` is 1.0 for the fullest prompt and smaller when the runner needs
                it shorter to fit; the prompter decides what to cut. It is called again for every factor the runner tries.
    kind        "text" (free text) or "json" (a JSON value that follows `grammar`).
    max_output  the most tokens the reply may take; the runner keeps that much of the context free.
    grammar     for "json": the JSON Schema the reply must follow (constrained decoding, and the check on a free reply).
    check       optional check(value) -> None, or one plain line saying what is wrong (it is shown to the model on the retry).
                `value` is the parsed JSON, or the text for a "text" step.
    sampling    which sampling set to use: "prose", "thinking" or "structured".
    language    True when the reply is written in the story's language, so the runner checks it (a short text always passes).
    """
    name: str
    text: Callable[[float], str]
    kind: Literal["text", "json"]
    max_output: int
    grammar: dict | None = None
    check: Callable[[Any], str | None] | None = None
    sampling: str = "structured"
    language: bool = True

    def __post_init__(self):
        if not _NAME.match(self.name):
            raise ValueError(f"a step name is letters, digits, - and _ (at most 32): {self.name!r}")
        if self.kind not in ("text", "json"):
            raise ValueError(f"a step is text or json, not {self.kind!r}")
        if self.kind == "json" and not isinstance(self.grammar, dict):
            raise ValueError("a json step needs a grammar")
        if self.kind == "text" and self.grammar is not None:
            raise ValueError("a text step has no grammar")
        if self.max_output < 1:
            raise ValueError("max_output must be at least 1")
        if self.sampling not in SAMPLING:
            raise ValueError(f"sampling is one of {SAMPLING}, not {self.sampling!r}")


class Flow(ABC):
    """The steps of one call, and the reply they add up to. The runner owns the loop; the Flow owns what comes next."""

    @abstractmethod
    def next(self, results: list[Any]) -> Step | None:
        """The step to run now, given the results of the steps so far (empty for the first); None when the call is done.
        A result is the parsed JSON of a "json" step and the text of a "text" step."""

    @abstractmethod
    def reply(self, results: list[Any]) -> dict:
        """The call's reply from all the results, in the model's own references: wherever the contract's reply carries an item's id, put
        the handle the model was shown (kit.handles). The runner turns handles into ids and adds `ok`. Shapes: README.md."""

    def worst_case(self) -> list[Step]:
        """Every step this call may run, in order, each built as heavy as it can get (a step that reads an earlier reply gets a stand-in
        of that reply's largest size). The runner fits them all before the first token and answers `too_long` early when they cannot.
        The default is the first step only."""
        first = self.next([])
        return [first] if first else []

    notes: dict[str, Any] = {}      # optional: counts and short words for the run log. Never story text.


class Prompter(ABC):
    """A replaceable module chosen by name in Config. `name` is the folder's name and `version` changes whenever any wording does:
    the run log records both with every call, so prompt versions can be compared."""
    name: str
    version: str

    @abstractmethod
    def flow(self, call: str, request: dict, kit: Any) -> Flow:
        """The Flow for one request. `call` is one of CALLS; `request` is the validated request as a plain dict; `kit` is what the runner
        offers (handles, grammars): see README.md."""
