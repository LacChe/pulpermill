"""A deterministic engine for tests and for running the page with no GPU. It makes up words, sleeps between them if told
to, checks the cancel flag like the real one, and can be told to fail. `active` is True exactly while inference runs,
so a test can check that the server reports idle only after inference has really ended."""
import threading
import time
from typing import Any, Callable

from ..errors import Cancelled
from .base import CancelFlag, Engine


class FakeEngine(Engine):
    def __init__(self, *, seconds_per_token: float = 0.0, tokens_per_call: int = 5, n_ctx: int = 12288):
        self.seconds_per_token = seconds_per_token
        self.tokens_per_call = tokens_per_call     # how many words a canned pipeline's call makes
        self.n_ctx = n_ctx
        self.active = False                        # True while generate is running
        self.calls = 0                             # generate calls started
        self.finished = 0                          # generate calls that ended, by any path
        self.cancelled_calls = 0
        self.prompts: list[str] = []
        self._failures: list[BaseException] = []
        self._lock = threading.Lock()

    def fail_next(self, *errors: BaseException) -> None:
        """The next generate calls raise these, in order, then it behaves again."""
        with self._lock:
            self._failures.extend(errors)

    def count_tokens(self, text: str) -> int:
        return len(text.split())                   # one word, one token: only for tests

    def generate(self, prompt: str, max_tokens: int, *, constraint: dict[str, Any] | None = None,
                 on_token: Callable[[str], None] | None = None, cancel: CancelFlag | None = None,
                 params: Any = None) -> str:
        with self._lock:
            self.calls += 1
            self.active = True
            self.prompts.append(prompt)
            failure = self._failures.pop(0) if self._failures else None
        try:
            if cancel:
                cancel.raise_if_cancelled()
            if failure:
                raise failure
            made = []
            for i in range(min(max_tokens, self.tokens_per_call)):
                if self.seconds_per_token:
                    time.sleep(self.seconds_per_token)
                if cancel:
                    cancel.raise_if_cancelled()
                word = f"word{i + 1}"
                made.append(word)
                if on_token:
                    on_token(word)
            return " ".join(made)
        except Cancelled:
            with self._lock:
                self.cancelled_calls += 1
            raise
        finally:
            with self._lock:
                self.active = False
                self.finished += 1

    def info(self) -> dict[str, Any]:
        return {"model": "fake", "n_ctx": self.n_ctx, "free_vram_mb": None}
