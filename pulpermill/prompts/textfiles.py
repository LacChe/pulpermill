"""Loads the wording and the limits. Cached, read-only."""
import copy
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
SCHEMA_TEXT = HERE.parent / "schema" / "text"
PROMPT_TEXT = HERE / "text"


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache(maxsize=None)
def schema_text(card: str, lang: str = "en") -> dict:
    """A card's text file from the schema (expansions, lead-ins, item templates)."""
    return _load(SCHEMA_TEXT / lang / f"{card}.yaml")


@lru_cache(maxsize=None)
def prompt_text(name: str, lang: str = "en") -> dict:
    """One of this package's own wording files (style_directives, frames)."""
    return _load(PROMPT_TEXT / lang / f"{name}.yaml")


@lru_cache(maxsize=None)
def template(name: str, lang: str = "en") -> dict:
    """One prompt template file (templates/en/<name>.yaml). Its `version` is recorded with every evaluation result."""
    return _load(HERE / "templates" / lang / f"{name}.yaml")


@lru_cache(maxsize=None)
def _base_limits() -> dict:
    return _load(HERE / "limits.yaml")


# Counts and switches, not lengths: a squeeze (phase 5) leaves these as they are.
_NOT_LENGTHS = {("characters", "max_behaviors"), ("events", "full_chapters_writer"), ("events", "full_chapters_planner")}
_scale = 1.0


def limits() -> dict:
    """The length caps. Inside `squeeze(f)` every length is multiplied by f, so a very large story can be made to fit."""
    base = _base_limits()
    if _scale == 1.0:
        return base
    out = copy.deepcopy(base)
    for section, values in out.items():
        if section == "chapter":
            continue
        for key, value in values.items():
            if isinstance(value, int) and (section, key) not in _NOT_LENGTHS:
                values[key] = max(40, int(value * _scale))
    return out


@contextmanager
def squeeze(factor: float):
    """Every length cap in limits.yaml, times `factor`, for the code inside the block."""
    global _scale
    before, _scale = _scale, factor
    try:
        yield
    finally:
        _scale = before


def field(card: str, key: str) -> dict:
    return schema_text(card)["fields"][key]


def option_expand(card: str, key: str, value: str, item_field: str | None = None) -> str:
    """The expansion of one option. `item_field` is for a choice inside a list item (a rule's status)."""
    spec = field(card, key)
    if item_field:
        spec = spec["item_fields"][item_field]
    return spec["options"][value]["expand"]
