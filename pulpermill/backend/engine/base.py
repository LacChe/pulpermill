"""The one thing every pipeline depends on. The real engine (llama.cpp) and the fake one both fit it."""
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable

from ..errors import Cancelled


class CancelFlag:
    """Set when the writer presses Stop. An engine looks at it between tokens and raises Cancelled."""

    def __init__(self):
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise Cancelled()


class Engine(ABC):
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Tokens in `text`, so too_long can be answered before any inference."""

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int, *, constraint: dict[str, Any] | None = None,
                 on_token: Callable[[str], None] | None = None, cancel: CancelFlag | None = None,
                 params: Any = None) -> str:
        """Run inference and return the text. `constraint` is a JSON Schema the output must follow. The cancel flag is
        checked between tokens (and before prefill starts); a cancelled run raises Cancelled. `params` is a Sampling."""

    @abstractmethod
    def info(self) -> dict[str, Any]:
        """{"model": str, "n_ctx": int, "free_vram_mb": int | None}"""
