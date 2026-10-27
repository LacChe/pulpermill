"""Shared helpers for the schema tests. Imports nothing from the pipeline."""
import pathlib, string, sys, yaml
from typing import get_args

REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = REPO / "pulpermill" / "schema"
sys.path.insert(0, str(REPO))
from pulpermill.schema import CARDS
from pulpermill.schema.common import InputType

ALLOWED_INPUTS = set(get_args(InputType))
CARD_IDS = list(CARDS)

# Languages are found from the folders under text/, so a new language is linted automatically.
LANGS = sorted(p.name for p in (ROOT / "text").iterdir() if p.is_dir())

# Policy lists. Edit these deliberately when a decision changes.
UNCAPPED = {("entanglements", "ties"), ("entanglements", "holdings"), ("entanglements", "knowledge"),
            ("world", "places"), ("world", "objects"),
            ("outline", "beats"), ("summary_events", "entries"),
            ("summary_shifts", "shifts"), ("entanglements_history", "states")}   # exceptions to the 5-item list cap
BLOCK_CHECKS = {"required_if", "exactly_one", "fields_differ", "holding_pairs_allowed", "ref_exists",
                "includes_value", "unique_across_items", "all_or_none", "legal_shift",
                "open_plants_max", "paid_off_valid", "at_least_one", "any_filled", "disjoint_lists", "max_per_group", "not_already_landed"}   # checks a block rule may name
COMMON_KEYS = {"missing", "not_allowed", "too_many", "invalid"}

CASES = [(cid, lang) for cid in CARD_IDS for lang in LANGS]
CASE_IDS = [f"{cid}-{lang}" for cid, lang in CASES]


def load_text(cid, lang):
    return yaml.safe_load(open(ROOT / "text" / lang / f"{cid}.yaml"))


def load_common(lang):
    return yaml.safe_load(open(ROOT / "text" / lang / "common.yaml"))


def card(cid):
    """(model, groups, render order, rules, meta)"""
    return CARDS[cid]


def tokens(template):
    return {t[1] for t in string.Formatter().parse(template) if t[1]}


def _strings(ann):
    out = []
    for a in get_args(ann):
        out += [a] if isinstance(a, str) else _strings(a)
    return out


def options_of(field):
    """Allowed string values of a field, including inside Optional[Literal[...]]."""
    return _strings(field.annotation)


def is_list_field(field):
    return bool(field.json_schema_extra and field.json_schema_extra.get("repeat"))


def item_model(field):
    return get_args(field.annotation)[0]


def item_fields(field):
    return {n: sf for n, sf in item_model(field).model_fields.items() if n != "id"}


def fields_of(model):
    """Top-level fields, without the system id."""
    return {n: f for n, f in model.model_fields.items() if n != "id"}


def all_fields(model):
    """Every field, with list items flattened as 'list.field'."""
    for n, f in fields_of(model).items():
        if is_list_field(f):
            for sn, sf in item_fields(f).items():
                yield f"{n}.{sn}", sf
        else:
            yield n, f


def ref_sources():
    """Every valid reference source: a card id, or '<card>.<repeating list field>'."""
    out = set(CARDS)
    for cid, (model, *_rest) in CARDS.items():
        for n, f in fields_of(model).items():
            if is_list_field(f):
                out.add(f"{cid}.{n}")
    return out
