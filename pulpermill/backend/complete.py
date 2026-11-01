"""`complete(text) -> str` on the in-process engine, for a trial or eval tool (the old tools/run_trials.py is at the tag pre-prompt-design; any other tool that wants to run
one prompt and read the text back). The prompt goes in as one user turn in Gemma's chat format, as in the server."""
from typing import Any, Callable

from .config import Sampling
from .engine.base import CancelFlag, Engine


def make_complete(engine: Engine, max_tokens: int = 1600, params: Sampling | None = None,
                  record: list[dict[str, Any]] | None = None) -> Callable[[str], str]:
    """`record`, when given, gets one row per call: the sampling used and what the engine says about the run (tokens, seconds)."""
    sampling = params or Sampling()

    def complete(text: str) -> str:
        out = engine.generate(text, max_tokens, cancel=CancelFlag(), params=sampling)
        if record is not None:
            record.append({"sampling": sampling.as_dict(), "run": dict(getattr(engine, "last_run", None) or {})})
        return out

    return complete
