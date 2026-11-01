"""A fake engine that answers the real runner with the stub prompter's own valid scripts, so a whole story can run with no model.

The stub prompter's prompt is "Stub prompt for <step>.\\n<the request as JSON>"; this engine reads the request back out of it, asks the stub
for the script of that call and returns the text for the step being asked. Two things are made to look like a story so the page's rules
pass: each chapter's aim is different, and the write step takes a little time (so a Stop can land in the middle of it)."""
import json
import re
import time

from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.errors import Cancelled  # noqa: F401  (raised by the cancel flag)
from pulpermill.backend.kit import Kit
from pulpermill.prompter.stub import script

STEP_OF = {"plan": 0, "write": 0, "events": 1, "shifts": 2}
WORDS = ["lantern", "harbour", "ledger", "orchard", "bridge", "cellar", "furnace", "meadow", "tavern", "quarry", "signal", "market"]


class StubEngine(FakeEngine):
    def __init__(self, *, write_seconds: float = 0.6, **kw):
        super().__init__(**kw)
        self.write_seconds = write_seconds
        self._seen: dict[str, int] = {}

    def generate(self, prompt, max_tokens, *, constraint=None, on_token=None, cancel=None, params=None):
        head, _, rest = prompt.partition("\n")
        label = re.match(r"Stub prompt for (.+)\.$", head).group(1).split(" ")[0]
        request = json.loads(rest.split("\n\n")[0])
        steps = script(request["call"], request, Kit(request))
        if request["call"] in ("plan", "generate"):
            text = steps[STEP_OF[label]]
        else:   # fill, judge and style_fit: the steps of one request come in order
            key = rest
            self._seen[key] = self._seen.get(key, -1) + 1
            text = steps[self._seen[key] % len(steps)]
        if label == "plan":
            beat = json.loads(text)
            n = int(request["chapter"])
            beat["aim"] = f"{WORDS[n % len(WORDS)]} {WORDS[(n * 5) % len(WORDS)]} gathering number{n}"
            text = json.dumps(beat)
        if label == "write" and cancel:
            # A slow stretch the Stop can land in; it counts as an engine call that was cancelled, like the real engine's.
            with self._lock:
                self.calls += 1
                self.active = True
            try:
                for _ in range(int(self.write_seconds / 0.02)):
                    cancel.raise_if_cancelled()
                    time.sleep(0.02)
            except Cancelled:
                with self._lock:
                    self.cancelled_calls += 1
                raise
            finally:
                with self._lock:
                    self.active = False
                    self.finished += 1
        self.script(text)
        return super().generate(prompt, max_tokens, constraint=constraint, on_token=on_token, cancel=cancel, params=params)
