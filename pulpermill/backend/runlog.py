"""The run record: one line of JSON per model call, so a run can be read afterwards and two setups compared.

What a record holds: the call, when it started, how long it took, what came of it (ok or an error kind), the stages
with their seconds, and what the pipeline noted (squeeze factor, words per section, code flags, and every prompt pass
with its prompt version, token counts, attempts and the engine's own prefill and generation numbers). The first line of
a log file is the settings the run was made with (model, sampling sets, constrain mode), so a log is comparable without
the notebook beside it.

What a record never holds: the writer's text, the model's text, the token, or an error's detail. Code flags are kept by
id only, because a flag's detail, and an attempt's problem line, may quote the story. Counts, names, versions and seconds are all it says."""
import json
import threading
import time
from dataclasses import asdict
from typing import Any

from .config import Config


def settings_line(config: Config) -> dict[str, Any]:
    """The settings a log was made under. Sampling is recorded here once; change it in config.py and nowhere else."""
    return {
        "record": "settings",
        "model": asdict(config.model),
        "sampling": {"prose": config.prose.as_dict(), "thinking": config.thinking.as_dict(), "structured": config.structured.as_dict()},
        "constrain": config.constrain,
        "prompt_version_note": config.prompt_version_note,
    }


def _flag_ids(flags: list[str]) -> list[str]:
    return [f.split(":", 1)[0] for f in flags]


def _attempt(attempt: dict) -> dict:
    """An attempt without its problem line, which may quote what the model wrote; only whether it failed is kept."""
    kept = {k: v for k, v in attempt.items() if k != "problem"}
    kept["failed"] = "problem" in attempt
    return kept


def build(call: str, started_at: float, seconds: float, result: str, stages: list[dict], notes: dict) -> dict[str, Any]:
    """One call's record. `result` is "ok" or an error kind. `notes` is ctx.notes."""
    record: dict[str, Any] = {
        "record": "call", "call": call, "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(started_at)) + "Z",
        "seconds": round(seconds, 2), "result": result,
        "stages": [{"stage": s["stage"], "seconds": round(s["seconds"], 2)} for s in stages],
    }
    for key in ("squeeze", "words", "words_per_section"):
        if key in notes:
            record[key] = notes[key]
    if "flags" in notes:
        record["flags"] = _flag_ids(notes["flags"])
    passes = notes.get("passes") or []
    record["passes"] = [{**{k: v for k, v in p.items() if k != "attempts"},
                         "attempts": [_attempt(a) for a in p.get("attempts", [])]} for p in passes]
    record["retries"] = sum(max(len(p.get("attempts", [])) - 1, 0) for p in passes)
    return record


class Stages:
    """Times each stage the pipeline names through set_stage. Wraps the server's own set_stage, which it still calls."""

    def __init__(self, inner):
        self._inner = inner
        self._current: str | None = None
        self._since = 0.0
        self.done: list[dict] = []

    def __call__(self, stage: str | None) -> None:
        self.close()
        if stage is not None:
            self._current, self._since = stage, time.monotonic()
        self._inner(stage)

    def close(self) -> None:
        if self._current is not None:
            self.done.append({"stage": self._current, "seconds": time.monotonic() - self._since})
            self._current = None


class RunLog:
    """Appends records to a file (JSON lines) and keeps the last few in memory for tests and the notebook.
    Writing never raises: a full disk or a bad path must not turn a finished story into an error."""

    def __init__(self, path: str | None, config: Config, keep: int = 50):
        self.path = path
        self.recent: list[dict] = []
        self._keep = keep
        self._lock = threading.Lock()
        self.failed: str | None = None
        self._write(settings_line(config), remember=False)

    def add(self, record: dict) -> None:
        self._write(record, remember=True)

    def _write(self, record: dict, remember: bool) -> None:
        with self._lock:
            if remember:
                self.recent = (self.recent + [record])[-self._keep:]
            if not self.path:
                return
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError as e:
                self.failed = f"{type(e).__name__}"     # said once in the server log by the caller; never retried loudly
