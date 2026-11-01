"""Small helpers shared by the call modules: wording files, a handle label, a clipping helper, and the stub's flow as the fallback."""
import hashlib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

TEXT = Path(__file__).resolve().parent / "text"


@lru_cache(maxsize=None)
def load_text(call: str, lang: str = "en") -> dict:
    """The wording file `text/<lang>/<call>.yaml` as a dict (an empty or comment-only file is an empty dict). Cached, read-only."""
    with open(TEXT / lang / f"{call}.yaml", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def text_digest(call: str, lang: str = "en") -> str:
    """Six hex characters of the wording file's content, or "" when the file holds no wording. Read fresh, so it follows every edit."""
    raw = (TEXT / lang / f"{call}.yaml").read_text(encoding="utf-8")
    if not any(line.strip() and not line.lstrip().startswith("#") for line in raw.splitlines()):
        return ""
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]


def labelled(scope: Any, key: str, item_id: str, text: str) -> str:
    """One list item shown with its handle, `wants.1: text`, so the model can point at it. `scope` is a kit.handles scope."""
    return f"{scope.of(key, item_id)}: {text}"


def clip(text: str, factor: float, floor: int = 40) -> str:
    """The text cut to `factor` of its length (never below `floor` characters), at a sentence end when one falls in the kept
    second half, else at a word end. Factor 1.0 or more returns the text as it is."""
    if factor >= 1.0 or len(text) <= floor:
        return text
    limit = max(int(len(text) * factor), floor)
    if limit >= len(text):
        return text
    kept = text[:limit]
    ends = [m.end() for m in re.finditer(r"[.!?。！？](?=\s|$)", kept)]
    if ends and ends[-1] >= limit // 2:
        return kept[: ends[-1]].rstrip()
    return kept.rsplit(None, 1)[0] if " " in kept.strip() else kept


def stub_flow(call: str, request: dict, kit: Any):
    """The stub prompter's flow for `call`: what a call module returns until its own wording is written."""
    from ..stub.stub import StubPrompter
    return StubPrompter().flow(call, request, kit)
