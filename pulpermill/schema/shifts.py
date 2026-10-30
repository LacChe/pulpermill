"""Shifts record: what changed for one card in one chapter, kept as a sparse copy of that card (P0 A1 to A3, A13, A14).
Hidden from the user and never edited by hand (a chapter is regenerated instead). One entry per card that appeared in a
chapter (the Characters in its cast, the World, the Entanglements), found through the chapter's beat; regenerating a
chapter drops its entries and every later one.

The cards themselves are locked once the story starts, so shifts are what change them. The page computes the effective
state (base card plus the shifts of earlier chapters) and sends it in every request; the overlay is written once, in the
page (P0 A6), and tested against tests/shared/overlay-vectors.json. This module only defines the shape of an entry, checks a
patch (validate_patch) and says which fields may be shifted (shiftable_fields). It never applies a patch.

A patch is a partial card in the card's own field keys:
  scalar field   holds its new value
  list field     holds a list of operations:
                   {"op": "add", "id": <new item id>, "values": {every field of the new item}}
                   {"op": "replace", "id": <existing item id>, "values": {only the fields that changed}}
                   {"op": "remove", "id": <existing item id>}
Fixed fields (name, age, sex, appearance) never appear. An item's identity fields (a tie's two ends, a holding's holdee)
are set by an add and never by a replace. Link values are ids in the stored form. Everything is derived from the card
schemas, so a field added to a card later is shiftable with no change here."""
from typing import Any, Literal, NamedTuple
from pydantic import TypeAdapter, ValidationError
from .common import spec, Rule, Item

# One entry per card that appeared in the chapter: up to 5 cast characters, the World and the Entanglements (P0 A14).
MAX_SHIFTS_PER_CHAPTER = 7

CARD = {
    "id": "shifts",
    "type": "record",
    "reads": ["chapter_text", "characters", "world", "entanglements"],
    "portable": False,
    "between_chapters": "per_chapter",
    "hidden": True,
    "sent_to_model": True,
}
GROUPS = [{"id": "entries", "collapsed": False}]
RENDER_ORDER = [["entries"]]

# The cards whose fields can be shifted. Anything else on a card list (Style, Setup, Outline) is not.
ShiftCard = Literal["characters", "world", "entanglements"]
SHIFT_CARDS = ["characters", "world", "entanglements"]


class ShiftEntry(Item):
    """What changed for one card in one chapter."""
    beat: str = spec("select", None, "note", ref=["outline.beats"], filled_by="code")                  # the chapter; its number lives on the beat
    card: ShiftCard = spec("select", None, "note", filled_by="extractor")
    target: str | None = spec("select", None, "note", required=False, ref=["characters"], filled_by="extractor")   # the character id when card is "characters"; empty otherwise
    patch: dict[str, Any] = spec(None, None, "patch", filled_by="extractor")                           # a partial card, see the module note


class Shifts(Item):
    entries: list[ShiftEntry] = spec(None, "entries", "pairs", repeat=True, uncapped=True)       # at most MAX_SHIFTS_PER_CHAPTER per beat (a rule), none per story


RULES = [
    Rule(id="shift_unique", severity="block", fields=["entries"],
         when="two entries are for the same chapter (the same beat), card and target",
         check="unique_across_items", params={"fields": ["beat", "card", "target"]}),
    Rule(id="shifts_per_chapter_max", severity="block", fields=["entries"],
         when=f"more than {MAX_SHIFTS_PER_CHAPTER} entries are recorded for one chapter (up to 5 characters, the world and the entanglements)",
         check="max_per_group", params={"group_by": "beat", "max": MAX_SHIFTS_PER_CHAPTER}),
    Rule(id="shift_target_in_cast", severity="block", fields=["entries"],
         when="a Characters entry names a character who is not in that chapter's cast, or has no character, or another card's entry names one",
         check="target_in_cast", params={"field": "target", "when": {"card": "characters"}, "cast": "cast"}, context=["beat_casts"]),
    Rule(id="shift_patch_valid", severity="block", fields=["entries"],
         when="a patch is not valid for its card (an unknown or fixed field, a wrong type or option, a bad operation, an identity field changed); "
              "validate_patch in shifts.py does the checking",
         check="patch_valid", params={"field": "patch", "card_field": "card"}),
    Rule(id="shift_link_broken", severity="block", fields=["entries"],
         when="a beat, a target, or a link inside a patch points at something that does not exist",
         check="ref_exists", params={"inside": "patch"}, context=["beat_ids", "character_ids", "world_item_ids"]),
    Rule(id="shift_patch_not_empty", severity="block", fields=["entries"],
         when="a patch holds nothing",
         check="not_empty", params={"field": "patch"}),
    Rule(id="shift_is_a_change", severity="warn", fields=["entries"],
         when="an entry records a standing trait instead of something that changed this chapter",
         needs_model=True),
]


# ---------------------------------------------------------------- reading the card schemas
def _card_model(card_id: str):
    from . import CARDS                      # imported here because the registry imports this module
    if card_id not in SHIFT_CARDS:
        raise KeyError(card_id)
    return CARDS[card_id][0]


def _meta(field) -> dict:
    return field.json_schema_extra or {}


def _options(annotation) -> list[str]:
    """Allowed string values of a field, including inside Optional[Literal[...]]."""
    from typing import get_args
    out: list[str] = []
    for a in get_args(annotation):
        out += [a] if isinstance(a, str) else _options(a)
    return out


def _is_list(field) -> bool:
    return bool(_meta(field).get("repeat"))


def _item_model(field):
    from typing import get_args
    return get_args(field.annotation)[0]


def _shiftable(model) -> dict:
    """The top-level fields of a card that a shift may carry: every field that is not fixed."""
    return {n: f for n, f in model.model_fields.items() if n != "id" and not _meta(f).get("fixed")}


def _item_fields(field) -> dict:
    return {n: f for n, f in _item_model(field).model_fields.items() if n != "id"}


def _is_identity(item_field) -> bool:
    meta = _meta(item_field)
    return bool(meta.get("identity") or meta.get("fixed"))


def shiftable_fields(card_id: str) -> list[dict]:
    """Every shiftable field of a card, in declaration order, for prompt design and the backend's grammar.

    Each entry: {"key", "type": "scalar" | "list", "options": [...] | None}. A list also has
      "item_fields"     keys a `replace` may change,
      "identity_fields" keys only an `add` may set (they say which item it is),
      "item_options"    {key: allowed options} for item fields that have a fixed set of choices.
    Everything comes from the card's schema: a field added to a card later shows up here with no other change.
    An unknown card (or one that cannot be shifted) returns an empty list."""
    try:
        model = _card_model(card_id)
    except KeyError:
        return []
    out = []
    for key, f in _shiftable(model).items():
        if _is_list(f):
            items = _item_fields(f)
            out.append({
                "key": key, "type": "list", "options": None,
                "item_fields": [n for n, sf in items.items() if not _is_identity(sf)],
                "identity_fields": [n for n, sf in items.items() if _is_identity(sf)],
                "item_options": {n: _options(sf.annotation) for n, sf in items.items() if _options(sf.annotation)},
            })
        else:
            out.append({"key": key, "type": "scalar", "options": _options(f.annotation) or None})
    return out


# ---------------------------------------------------------------- validating a patch
class PatchProblem(NamedTuple):
    code: str       # short, stable: what is wrong
    field: str      # the field key, or "list.item_field" inside a list item; empty when it is the patch as a whole
    message: str    # for a person


OPS = ("add", "replace", "remove")


def _value_problem(field, key: str, value: Any, where: str = "") -> PatchProblem | None:
    """Type and option check for one value, scalar or inside an item. None when it is fine."""
    options = _options(field.annotation)
    if options:
        if not isinstance(value, str):
            return PatchProblem("bad_type", key, f"{where}{key} must be text, one of: {', '.join(options)}.")
        if value not in options:
            return PatchProblem("bad_option", key, f"{where}{key} must be one of: {', '.join(options)} (got {value!r}).")
        return None
    try:
        TypeAdapter(field.annotation).validate_python(value, strict=True)
    except ValidationError:
        return PatchProblem("bad_type", key, f"{where}{key} has the wrong type (got {type(value).__name__}).")
    return None


def _operation_problems(key: str, f, index: int, op: Any) -> list[PatchProblem]:
    where = f"Operation {index + 1} of {key}: "
    if not isinstance(op, dict):
        return [PatchProblem("bad_operation", key, f"{where}must be an object with an op and an id.")]
    kind = op.get("op")
    if kind not in OPS:
        return [PatchProblem("bad_operation", key, f"{where}op must be one of: {', '.join(OPS)}.")]
    problems: list[PatchProblem] = []
    allowed = {"op", "id"} if kind == "remove" else {"op", "id", "values"}
    extra = sorted(set(op) - allowed)
    if extra:
        problems.append(PatchProblem("bad_operation", key, f"{where}{kind} does not take: {', '.join(extra)}."))
    if not isinstance(op.get("id"), str) or not op["id"].strip():
        problems.append(PatchProblem("missing_id", key, f"{where}{kind} needs the id of the item."))
    if kind == "remove":
        return problems

    values = op.get("values")
    if not isinstance(values, dict):
        return problems + [PatchProblem("bad_operation", key, f"{where}{kind} needs values, an object of the item's fields.")]
    items = _item_fields(f)
    if kind == "replace" and not values:
        problems.append(PatchProblem("empty_values", key, f"{where}replace holds no values, so it changes nothing."))
    for name, value in values.items():
        path = f"{key}.{name}"
        if name not in items:
            problems.append(PatchProblem("unknown_item_field", path, f"{where}{name} is not a field of an item in {key}."))
        elif kind == "replace" and _is_identity(items[name]):
            problems.append(PatchProblem("identity_field", path, f"{where}{name} says which item this is and cannot be changed."))
        elif (p := _value_problem(items[name], path, value, where)):
            problems.append(p)
    if kind == "add":
        for name, sf in items.items():
            if sf.is_required() and name not in values:
                problems.append(PatchProblem("missing_value", f"{key}.{name}", f"{where}add needs a value for {name}."))
    return problems


def validate_patch(card_id: str, patch: Any) -> list[PatchProblem]:
    """Problems with a patch for one card; an empty list means it is valid. Checks the shape only: it does not apply the
    patch, and it does not look for the ids it names (an id that no longer exists is the overlay's business, and links
    are checked against the project by the shift_link_broken rule)."""
    try:
        model = _card_model(card_id)
    except KeyError:
        return [PatchProblem("unknown_card", "", f"{card_id!r} is not a card that can be shifted ({', '.join(SHIFT_CARDS)}).")]
    if not isinstance(patch, dict):
        return [PatchProblem("bad_type", "", "A patch must be an object of field keys.")]
    if not patch:
        return [PatchProblem("empty_patch", "", "The patch holds nothing.")]

    fields = model.model_fields
    allowed = _shiftable(model)
    problems: list[PatchProblem] = []
    for key, value in patch.items():
        if key == "id" or key not in fields:
            problems.append(PatchProblem("unknown_field", str(key), f"{key} is not a field of {card_id}."))
            continue
        if key not in allowed:
            problems.append(PatchProblem("fixed_field", key, f"{key} is fixed and never changes."))
            continue
        f = allowed[key]
        if not _is_list(f):
            if (p := _value_problem(f, key, value)):
                problems.append(p)
            continue
        if not isinstance(value, list):
            problems.append(PatchProblem("bad_type", key, f"{key} must be a list of operations."))
        elif not value:
            problems.append(PatchProblem("empty_list", key, f"{key} holds no operations."))
        else:
            for i, op in enumerate(value):
                problems += _operation_problems(key, f, i, op)
    return problems
