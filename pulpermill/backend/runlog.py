"""The run record: one line of JSON per model call, so a run can be read afterwards and two setups compared.

What a record holds: the call, when it started, how long it took, what came of it (ok or an error kind), the prompter's name and
version, the stages with their seconds, the squeeze factor, the flow's own counts, and every step with its token count, attempts
and the engine's own prefill and generation numbers. The first line of
a log file is the settings the run was made with (model, sampling sets, constrain mode), so a log is comparable without
the notebook beside it.

What a record never holds: the writer's text, the model's text, the token, or an error's detail. An attempt's problem line may quote
the story, so only whether it failed is kept, and a flow's notes are kept only when they are numbers or short plain words.
Counts, names, versions and seconds are all it says."""
import json
import threading
import time
from dataclasses import asdict
from typing import Any

from .config import Config


def settings_line(config: Config, prompter=None) -> dict[str, Any]:
    """The settings a log was made under. Sampling is recorded here once; change it in config.py and nowhere else."""
    return {
        "record": "settings",
        "model": asdict(config.model),
        "sampling": {"prose": config.prose.as_dict(), "prose_zh": config.prose_zh.as_dict(), "thinking": config.thinking.as_dict(), "structured": config.structured.as_dict()},
        "constrain": config.constrain,
        "prompter": {"name": getattr(prompter, "name", config.prompter), "version": getattr(prompter, "version", None)},
        "prompt_version_note": config.prompt_version_note,
    }


_PLAIN = __import__("re").compile(r"^[A-Za-z0-9_.-]{1,32}$")


def _plain_notes(notes: dict) -> dict:
    """A flow's notes, minus anything that could be story text: numbers, booleans and short plain words only."""
    return {str(k)[:32]: v for k, v in notes.items() if isinstance(v, (bool, int, float)) or (isinstance(v, str) and _PLAIN.match(v))}


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
        "prompter": notes.get("prompter"),
        "stages": [{"stage": s["stage"], "index": s["index"], "seconds": round(s["seconds"], 2)} for s in stages],
    }
    if "squeeze" in notes:
        record["squeeze"] = notes["squeeze"]
    if notes.get("flow"):
        record["notes"] = _plain_notes(notes["flow"])
    passes = notes.get("passes") or []
    record["passes"] = [{**{k: v for k, v in p.items() if k != "attempts"},
                         "attempts": [_attempt(a) for a in p.get("attempts", [])]} for p in passes]
    record["retries"] = sum(max(len(p.get("attempts", [])) - 1, 0) for p in passes)
    return record


class Stages:
    """Times each stage the pipeline names through set_stage. Wraps the server's own set_stage, which it still calls."""

    def __init__(self, inner):
        self._inner = inner
        self._current: tuple[str, int] | None = None
        self._since = 0.0
        self.done: list[dict] = []

    def __call__(self, stage: dict | None) -> None:
        """`stage` is `{name, index, of}` or None. Naming the same step again (its retry) does not start a new stage."""
        if stage is not None and self._current is not None and (stage["name"], stage["index"]) == self._current:
            self._inner(stage)
            return
        self.close()
        if stage is not None:
            self._current, self._since = (stage["name"], stage["index"]), time.monotonic()
        self._inner(stage)

    def close(self) -> None:
        if self._current is not None:
            self.done.append({"stage": self._current[0], "index": self._current[1], "seconds": time.monotonic() - self._since})
            self._current = None


class RunLog:
    """Appends records to a file (JSON lines) and keeps the last few in memory for tests and the notebook.
    Writing never raises: a full disk or a bad path must not turn a finished story into an error."""

    def __init__(self, path: str | None, config: Config, prompter=None, keep: int = 50):
        self.path = path
        self.recent: list[dict] = []
        self._keep = keep
        self._lock = threading.Lock()
        self.failed: str | None = None
        self._write(settings_line(config, prompter), remember=False)

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
