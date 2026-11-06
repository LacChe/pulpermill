"""JSON grammars for constrained decoding, made from the card schema and the request, never from prompt text. The same schema is
what a free-written reply is checked against (shape.py). Only the keywords llama.cpp's grammar builder understands are used: type,
enum, const, items, properties, required, anyOf, minItems, maxItems, additionalProperties.

Three grammars come ready made, because they follow from the cards alone: a card fill (`fill`), the planner's fields of a beat
(`plan_beat`) and the shifts of a chapter (`shifts`, a patch per card built from shiftable_fields). The shape of any other reply (a
judge's answer, an extractor's) is the prompter's, built from the small pieces at the top. Link fields are limited to the names the
request sent (the `ref` of the field says which names); where a request sent none, a link is plain text."""
from copy import deepcopy
from typing import Any

from pulpermill.schema import CARDS
from pulpermill.schema.common import MAX_ITEMS
from pulpermill.schema.shifts import MAX_SHIFTS_PER_CHAPTER, SHIFT_CARDS, shiftable_fields

from . import cards
from .handles import Handles

KEEP = ("type", "enum", "const", "items", "properties", "required", "anyOf", "minItems", "maxItems", "additionalProperties")
Schema = dict[str, Any]


# ---- Small pieces ---------------------------------------------------------------------------------------------------

def text() -> Schema:
    return {"type": "string"}


def maybe(schema: Schema) -> Schema:
    return {"anyOf": [schema, {"type": "null"}]}


def unique(names: list[Any]) -> list[str]:
    seen: dict[str, None] = {}
    for n in names:
        n = str(n or "").strip()
        if n:
            seen.setdefault(n, None)
    return list(seen)


def one_of(names: list[str]) -> Schema:
    """One of these exact words (plain text when there are none, so nothing can be forced wrongly)."""
    names = unique(names)
    return {"type": "string", "enum": names} if names else text()


def list_of(names: list[str], limit: int | None = None) -> Schema:
    """A list of these exact words. With no words it allows only an empty list."""
    names = unique(names)
    if not names:
        return {"type": "array", "items": text(), "maxItems": 0}
    out: Schema = {"type": "array", "items": {"type": "string", "enum": names}}
    if limit:
        out["maxItems"] = limit
    return out


def obj(properties: dict[str, Schema], required: list[str] | None = None) -> Schema:
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required,
            "additionalProperties": False}


# ---- Cards, from the Pydantic models --------------------------------------------------------------------------------

def _inline(node: Any, defs: dict) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline(deepcopy(defs[node["$ref"].split("/")[-1]]), defs)
        return {k: _inline(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline(v, defs) for v in node]
    return node


def card_model_schema(card_id: str) -> Schema:
    """The card's own JSON Schema with every reference inlined and the schema's extras (ref, fixed, kind, ...) still in it."""
    schema = CARDS[card_id][0].model_json_schema()
    return _inline(schema, schema.get("$defs", {}))


def _with_enum(node: Schema, names: list[str]) -> Schema:
    if "anyOf" in node:
        return {**node, "anyOf": [b if b.get("type") == "null" else _with_enum(b, names) for b in node["anyOf"]]}
    if node.get("type") == "array":
        return {**node, "items": {**node.get("items", text()), "enum": names}}
    if node.get("type") == "string":
        return {**node, "enum": names}
    return node


def _clean(node: Any, refs: dict | None, drop_fixed: bool, item_required: bool = False, inside_list: bool = False) -> Any:
    """A model schema node reduced to the keywords above: every field optional, ids left out (the page makes them), and each link field
    limited to the names in `refs` (keyed by reference source, such as "characters" or "world.places"). With `item_required` (the fill),
    the fields inside a list item stay required when the schema marks them required: a fill may leave a card's own field alone, but an
    item it writes is whole (`inside_list` is true for the object that is the item of a list)."""
    if isinstance(node, list):
        return [_clean(v, refs, drop_fixed, item_required, inside_list) for v in node]
    if not isinstance(node, dict):
        return node
    out: Schema = {}
    for key in KEEP:
        if key not in node or key in ("required", "additionalProperties"):
            continue
        value = node[key]
        if key == "properties":
            props = {}
            for name, spec in value.items():
                if name == "id" or (drop_fixed and spec.get("fixed")):
                    continue
                child = _clean(spec, refs, drop_fixed, item_required)
                sources = spec.get("ref")
                if refs and sources:
                    names = unique([n for source in sources for n in refs.get(source, [])])
                    if names:
                        child = _with_enum(child, names)
                props[name] = child
            kept = [k for k in node.get("required") or [] if k in props] if item_required and inside_list else []
            out["properties"], out["required"], out["additionalProperties"] = props, kept, False
        else:
            out[key] = _clean(value, refs, drop_fixed, item_required, inside_list=(key == "items"))
    return out


def _exclusive(schema: Schema, card_id: str) -> Schema:
    """An either-or pair (a rule `exactly_one` over two fields of a list item) becomes two shapes the model must pick between."""
    for rule in CARDS[card_id][3]:
        if rule.check != "exactly_one":
            continue
        for list_field in rule.fields:
            item = ((schema.get("properties") or {}).get(list_field) or {}).get("items")
            if not item or "properties" not in item:
                continue
            keys = [k for k in rule.params["fields"] if k in item["properties"]]
            if len(keys) == 2:
                schema["properties"][list_field]["items"] = {"anyOf": [
                    {**item, "properties": {n: v for n, v in item["properties"].items() if n not in [o for o in keys if o != key]},
                     "required": [r for r in item.get("required") or [] if r not in keys] + [key]}
                    for key in keys]}
    return schema


def link_names(characters: list[str], world: dict | None) -> dict[str, list[str]]:
    """The names a link may point at, by reference source: "characters", and "world.<list>" for each list of the World card."""
    out = {"characters": unique(characters)}
    for key in cards.list_fields("world"):
        lk = cards.label_key("world", key)
        out[f"world.{key}"] = unique([i.get(lk) for i in (world or {}).get(key) or [] if isinstance(i, dict)])
    return out


# ---- A card fill ----------------------------------------------------------------------------------------------------

def fill(request: dict) -> Schema:
    """The reply shape for a fill: every field of the card required (a re-fill is asked exactly as a blank card is), and the fields of every
    list item it writes required as the schema says (a tie always has both ends, a bond and an edge), no ids, links limited to the names of
    the related cards. A list may be empty."""
    related = request.get("related") or {}
    people = related.get("characters") or []
    people = [people] if isinstance(people, dict) else people
    refs = link_names([p.get(cards.label_key("characters")) for p in people if isinstance(p, dict)], related.get("world"))
    schema = _clean(card_model_schema(request["card"]), refs, False, item_required=True)
    schema["required"] = list(schema["properties"])
    return _exclusive(schema, request["card"])


# ---- The planner's fields of a beat ---------------------------------------------------------------------------------

def plan_beat(request: dict) -> Schema:
    """The beat's planner fields (the Outline fields filled by the planner), all required, links limited to the names the request sent."""
    node = card_model_schema("outline")["properties"]["beats"]["items"]
    mine = {k: v for k, v in node["properties"].items() if v.get("filled_by") == "planner"}
    refs = link_names([p.get(cards.label_key("characters")) for p in request.get("cast") or []], request.get("world"))
    cleaned = _clean({"type": "object", "properties": mine}, refs, False)
    return obj(cleaned["properties"])


# ---- Shifts ---------------------------------------------------------------------------------------------------------

def _item_props(card: str, key: str, names: list[str], refs: dict) -> Schema:
    items = card_model_schema(card)["properties"][key]["items"]["properties"]
    return _clean({"type": "object", "properties": {n: items[n] for n in names}}, refs, False)["properties"]


def patch(card: str, scope, refs: dict) -> Schema:
    """What one card's patch may hold: every shiftable field (P2), a scalar as its new value and a list as `replace` operations on the items
    this scope sent. The model may only replace: `add` and `remove` are not generated (the schema and the overlay still accept them). A list
    field the scope has no handles for has no valid operation, so it is left out."""
    model = card_model_schema(card)["properties"]
    props: dict[str, Schema] = {}
    for f in shiftable_fields(card):
        key = f["key"]
        if f["type"] == "scalar":
            props[key] = _clean({"type": "object", "properties": {key: model[key]}}, refs, False)["properties"][key]
            continue
        ids = scope.handles(key)
        if not ids:
            continue
        op = obj({"op": {"const": "replace"}, "id": one_of(ids), "values": obj(_item_props(card, key, f["item_fields"], refs), [])})
        props[key] = {"type": "array", "items": op, "minItems": 1, "maxItems": MAX_ITEMS}
    return {"type": "object", "properties": props, "required": [], "additionalProperties": False}


def _required(card: str, key: str) -> list[str]:
    from typing import get_args
    item = get_args(CARDS[card][0].model_fields[key].annotation)[0]
    return [k for k, f in item.model_fields.items() if k != "id" and f.is_required()]


def shifts(request: dict, handles: Handles) -> Schema:
    """The `shifts` list of a chapter: at most one entry per card that was sent (a character, the world, the ties and holdings), each
    `{card, target, patch}` as the contract's ShiftOut, with a character named by its label and an item by its handle."""
    people = [s.label for s in handles.of_card("characters")]
    refs = link_names(people, request.get("world"))
    variants = []
    for scope in handles.scopes:
        if scope.card not in SHIFT_CARDS:
            continue
        head: dict[str, Schema] = {"card": {"const": scope.card}}
        if scope.card == "characters":
            head["target"] = {"const": scope.label}
        variants.append(obj({**head, "patch": patch(scope.card, scope, refs)}))
    if not variants:
        return {"type": "array", "items": text(), "maxItems": 0}
    return {"type": "array", "items": {"anyOf": variants} if len(variants) > 1 else variants[0],
            "maxItems": min(len(variants), MAX_SHIFTS_PER_CHAPTER)}
