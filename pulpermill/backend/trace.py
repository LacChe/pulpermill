"""The opt-in trace: what the model saw and said at every step, and why an attempt was refused.

Off by default (`Config.trace_path` is None). When it is set, EVERY attempt of every step appends one JSON line to that file, used or
refused, with the full prompt each time:

    {t, call, step, attempt, constrained, prompt, reply, used, problem, output_tokens, seconds}

`t` is the UTC time, `used` says whether the attempt's reply became the step's value, `problem` is the full problem line of a refused
attempt (None when used). Two optional keys: `soft`, a list of the soft problems a used attempt carried (a reply accepted with a flaw,
see `Collector`), and `fallback: true` on the line of a step whose last-resort value was used (phase 2A; `Trace.record` takes it).

This is the richer sibling of debuglog.py, which keeps only refused attempts and only the first refused prompt; the debug file works
as before. Like it, this file holds the writer's story text and the model's raw words, so it is an opt-in exception to the run log's
privacy rule (runlog.py keeps no text at all). It is never sent to the page, and it must not be shared or committed.

Writing it never fails and never slows a call: any error is caught, said once on the server console, and the trace stops.

Soft problems. A prompter says "I accepted this reply with a flaw" through the standard `logging` module (`note_soft` in the mill's
common.py logs a record on the "pulpermill" logger and puts the facts in the record's `pulpermill_soft` attribute). The prompter
imports nothing from here. While an attempt is being read, the runner opens a `capture()`; the handler below collects the records that
the same thread emits meanwhile, and they land on that attempt's line."""
import json
import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .config import Config

log = logging.getLogger("pulpermill")

SOFT_ATTRIBUTE = "pulpermill_soft"          # the record attribute a prompter's soft note travels in (a dict: call, step, what, line)

_lock = threading.RLock()        # reentrant: for_config holds it while a new Trace attaches the handler
_traces: dict[str, "Trace"] = {}


class Collector(logging.Handler):
    """Collects the soft notes a thread logs while it has a capture open. Never raises."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self._open: dict[int, list[str]] = {}
        self._guard = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            note = getattr(record, SOFT_ATTRIBUTE, None)
            if not isinstance(note, dict):
                return
            with self._guard:
                bucket = self._open.get(record.thread)
                if bucket is not None:
                    what, line = str(note.get("what") or "accepted"), " ".join(str(note.get("line") or "").split())
                    bucket.append(f"{what}: {line}")
        except Exception:
            pass

    @contextmanager
    def capture(self) -> Iterator[list[str]]:
        """The soft notes this thread logs inside the block, as lines like "accepted: <problem line>"."""
        ident, bucket = threading.get_ident(), []
        with self._guard:
            self._open[ident] = bucket
        try:
            yield bucket
        finally:
            with self._guard:
                self._open.pop(ident, None)


_collector = Collector()
_attached = False


def _attach() -> None:
    global _attached
    with _lock:
        if not _attached:
            log.addHandler(_collector)
            _attached = True


class Trace:
    def __init__(self, path: str):
        self.path = path
        self.failed: str | None = None          # the error's name once writing has failed; the trace then stops
        self._lock = threading.Lock()
        _attach()

    def capture(self):
        """Open around reading one attempt's reply; yields the list the soft notes are collected in."""
        return _collector.capture()

    def record(self, *, call: str | None, step: str, attempt: int, constrained: bool, prompt: str, reply: str | None, used: bool,
               problem: str | None, tokens: int | None, seconds: float, soft: list[str] | None = None, fallback: bool = False) -> None:
        """Appends one line for one attempt. Never raises."""
        if self.failed:
            return
        try:
            row: dict[str, Any] = {
                "t": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z", "call": call, "step": step, "attempt": attempt,
                "constrained": constrained, "prompt": prompt, "reply": reply if isinstance(reply, str) else "", "used": used,
                "problem": None if problem is None else str(problem), "output_tokens": tokens, "seconds": round(float(seconds), 3),
            }
            if soft:
                row["soft"] = list(soft)
            if fallback:
                row["fallback"] = True
            line = json.dumps(row, ensure_ascii=False) + "\n"
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception as e:      # a full disk, a bad path, anything: the call goes on
            self.failed = type(e).__name__
            log.warning("the trace file %s could not be written (%s); the trace is off for this session", self.path, self.failed)


def for_config(config: Config) -> Trace | None:
    """The shared trace for this config's trace_path, or None when tracing is off. One instance per path, so the 'said once' rule holds."""
    if not config.trace_path:
        return None
    with _lock:
        if config.trace_path not in _traces:
            _traces[config.trace_path] = Trace(config.trace_path)
        return _traces[config.trace_path]
