"""Loads the wording files and the length limits. Cached, read-only."""
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
def _base_limits() -> dict:
    return _load(HERE / "limits.yaml")


# The renderers read caps as limits()[section][key]. The cap itself lives on the schema field (spec(..., cap=N)); this table says
# which field each (section, key) comes from: "field" or "list.item_field", and for a list whose items are one box, "list".
_FIELD_CAPS = {
    "characters": {"sketch": "sketch", "fear": "fear", "flaw": "flaw", "competence": "competence", "vulnerability": "vulnerability",
                   "speech": "speech", "history": "history", "want_item": "wants", "value_item": "values",
                   "behavior_state": "behaviors.state", "behavior_tendency": "behaviors.tendency"},
    "world": {"name": "name", "era_and_technology": "era_and_technology", "everyday_life": "everyday_life", "history": "history",
              "place_description": "places.description", "place_effect": "places.effect", "object_description": "objects.description",
              "object_significance": "objects.significance", "power_nature": "powers.nature", "power_hold": "powers.hold",
              "power_felt": "powers.felt", "rule_statement": "rules.statement", "rule_cost": "rules.cost",
              "rule_when_broken": "rules.when_broken", "term_meaning": "terms.meaning"},
    "entanglements": {"bond": "ties.bond", "edge": "ties.edge"},
    "setup": {"normal": "normal", "disruption": "disruption"},
    "events": {"happened": "entries.happened", "changed": "entries.changed"},
}
_CARD_OF = {"events": "summary_events"}


def _schema_cap(card: str, path: str) -> int | None:
    from ..schema import CARDS
    from typing import get_args
    model = CARDS[card][0]
    first, _, inner = path.partition(".")
    f = model.model_fields[first]
    if inner:
        f = get_args(f.annotation)[0].model_fields[inner]
    return (f.json_schema_extra or {}).get("cap")


@lru_cache(maxsize=None)
def _built_limits() -> dict:
    out = copy.deepcopy(_base_limits())
    for section, keys in _FIELD_CAPS.items():
        for key, path in keys.items():
            cap = _schema_cap(_CARD_OF.get(section, section), path)
            if cap is None:
                raise KeyError(f"the schema field for limits {section}.{key} ({path}) has no cap")
            out.setdefault(section, {})[key] = cap
    return out


# Counts and switches, not lengths: a squeeze leaves these as they are.
_NOT_LENGTHS = {("characters", "max_behaviors"), ("events", "full_chapters_writer"), ("events", "full_chapters_planner")}
_scale = 1.0


def limits() -> dict:
    """The length caps, read from the schema fields plus limits.yaml. Inside `squeeze(f)` every length is multiplied by f, so a very
    large story can be made to fit."""
    base = _built_limits()
    if _scale == 1.0:
        return base
    out = copy.deepcopy(base)
    for section, values in out.items():
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
