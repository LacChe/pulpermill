"""The opt-in debug capture: why a reply was refused.

Off by default (`Config.debug_path` is None). When it is set, every attempt the runner refuses appends one JSON line to that file:
the time, the call, the step, the attempt number, whether the attempt was grammar-constrained, the problem line (in full, not the
shortened one the retry line carries), the model's raw reply (cut at REPLY_CHARS, and the line says so) and the output token
count. With `Config.debug_prompts` also set, the first refused attempt of each step carries its prompt text too.
A call that succeeds writes nothing.

This file holds the writer's story text and the model's raw words, so it is the one opt-in exception to the run log's privacy rule
(runlog.py keeps no text at all). It is never sent to the page, and it must not be shared or committed.

Writing it never fails and never slows a call: any error is caught, said once on the server console, and the capture stops."""
import json
import logging
import threading
import time
from typing import Any

from .config import Config

log = logging.getLogger("pulpermill")

REPLY_CHARS = 30_000

_lock = threading.Lock()
_logs: dict[tuple[str, bool], "DebugLog"] = {}


class DebugLog:
    def __init__(self, path: str, prompts: bool = False):
        self.path = path
        self.prompts = prompts
        self.failed: str | None = None          # the error's name once writing has failed; the capture then stops
        self._lock = threading.Lock()

    def refused(self, *, call: str | None, step: str, attempt: int, constrained: bool, problem: str, reply: str | None,
                tokens: int | None, prompt: str | None = None, first_of_step: bool = False) -> None:
        """Appends one line for one refused attempt. Never raises."""
        if self.failed:
            return
        try:
            text = reply if isinstance(reply, str) else ""
            row: dict[str, Any] = {
                "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z", "call": call, "step": step, "attempt": attempt,
                "constrained": constrained, "problem": str(problem), "reply": text[:REPLY_CHARS],
                "reply_chars": len(text), "reply_cut": len(text) > REPLY_CHARS, "output_tokens": tokens,
            }
            if self.prompts and first_of_step and prompt is not None:
                row["prompt"] = prompt
            line = json.dumps(row, ensure_ascii=False) + "\n"
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception as e:      # a full disk, a bad path, anything: the call goes on
            self.failed = type(e).__name__
            log.warning("the debug file %s could not be written (%s); debug capture is off for this session", self.path, self.failed)


def for_config(config: Config) -> DebugLog | None:
    """The shared capture for this config's debug_path, or None when debugging is off. One instance per path and prompts flag,
    so the 'said once' rule holds across calls."""
    if not config.debug_path:
        return None
    key = (config.debug_path, bool(config.debug_prompts))
    with _lock:
        if key not in _logs:
            _logs[key] = DebugLog(config.debug_path, bool(config.debug_prompts))
        return _logs[key]
