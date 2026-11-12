"""The one place that knows about the calls the page named: which are running, which have finished, and what each one is for.

A call that carries a `job_id` is an entry here. It keeps going if the connection drops, and its outcome stays until the page
fetches it (call `job`). Each entry also carries the page's own labels, the project it belongs to and a short `tag`, so a page that
was reloaded can ask `status` and learn what is running, and whether it is for the project now open. The backend only stores and
repeats the labels; it never reads them.

Memory only: a restart forgets everything. At most `keep` finished entries are kept; a running one is never dropped."""
import threading
import time
from typing import Any

from .engine.base import CancelFlag


class Entry:
    """One named call: its id, call name, labels, and (once it ends) its outcome."""

    def __init__(self, job_id: str, call: str, cancel: CancelFlag, project: dict | None = None, tag: str | None = None):
        self.id, self.call, self.cancel = job_id, call, cancel
        self.project, self.tag = project, tag
        self.outcome: tuple[str, Any] | None = None       # ("ok", reply) or ("fail", (kind, detail)); None while running
        self.started_at = time.time()
        self.finished_at: float | None = None

    def info(self) -> dict:
        """The entry as `status` lists it. Never the reply itself: that is fetched by id with call `job`."""
        state = "running" if self.outcome is None else ("done" if self.outcome[0] == "ok" else "failed")
        body: dict = {"job_id": self.id, "call": self.call, "state": state}
        if self.project:
            body["project"] = self.project
        if self.tag:
            body["tag"] = self.tag
        if state == "failed":
            body["error"] = self.outcome[1][0]
        return body


class CallRegistry:
    def __init__(self, keep: int = 30):
        self._lock = threading.Lock()
        self._entries: dict[str, Entry] = {}
        self.keep = keep

    def get(self, job_id: str) -> Entry | None:
        with self._lock:
            return self._entries.get(job_id)

    def add(self, entry: Entry) -> None:
        with self._lock:
            self._entries[entry.id] = entry

    def finish(self, entry: Entry, outcome: tuple[str, Any]) -> None:
        with self._lock:
            entry.outcome = outcome
            entry.finished_at = time.time()
            finished = sorted((e for e in self._entries.values() if e.outcome is not None), key=lambda e: e.finished_at)
            for old in finished[: max(len(finished) - self.keep, 0)]:
                del self._entries[old.id]

    def listing(self) -> list[dict]:
        """Running calls first, then finished ones, oldest first."""
        with self._lock:
            entries = list(self._entries.values())
        running = [e for e in entries if e.outcome is None]
        done = sorted((e for e in entries if e.outcome is not None), key=lambda e: e.finished_at)
        return [e.info() for e in running + done]
