"""Loads the wording and the limits. Cached, read-only."""
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
def limits() -> dict:
    return _load(HERE / "limits.yaml")


def field(card: str, key: str) -> dict:
    return schema_text(card)["fields"][key]


def option_expand(card: str, key: str, value: str, item_field: str | None = None) -> str:
    """The expansion of one option. `item_field` is for a choice inside a list item (a rule's status)."""
    spec = field(card, key)
    if item_field:
        spec = spec["item_fields"][item_field]
    return spec["options"][value]["expand"]
