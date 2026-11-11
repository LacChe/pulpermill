"""JSON grammars for constrained decoding, made from the card schema and the request, never from prompt text. The same schema is
what a free-written reply is checked against (shape.py). Only the keywords llama.cpp's grammar builder understands are used: type,
enum, const, items, properties, required, anyOf, minItems, maxItems, additionalProperties.

Three grammars come ready made, because they follow from the cards alone: a card fill (`fill`), the planner's fields of a beat
(`plan_beat`), the shifts of a chapter (`shifts`, the new edge of ties) and the shifts at the end of the story (`finish`, one patch per person). The shape of any other reply (a
judge's answer, an extractor's) is the prompter's, built from the small pieces at the top. Link fields are limited to the names the
request sent (the `ref` of the field says which names); where a request sent none, a link is plain text."""
import json
import re
from copy import deepcopy
from typing import Any

from pulpermill.schema import CARDS
from pulpermill.schema.common import MAX_ITEMS
from pulpermill.schema.shifts import CHAPTER_SHIFT_CARDS, MAX_SHIFTS_PER_CHAPTER, shiftable_fields

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


# ---- Free text in the story's script ---------------------------------------------------------------------------------

# A Chinese story's free-text strings may hold only Han characters, CJK and full-width punctuation, digits, a space and a little plain
# punctuation (no quote or backslash, which would break the JSON string), so the model cannot drift into English. The one allowance for
# Latin letters is a name that is in the request's own text (note, example chapter, values, related cards), spelled as it is there.
# Written as \\u escapes: the grammar builder passes them through into a GBNF character class.
_ZH_CLASS = ("0-9 ,.!?;:()'\\-"                        # digits, space, a little plain punctuation
             "\\u3400-\\u4dbf\\u4e00-\\u9fff"        # Han (extension A and the main block)
             "\\u3000-\\u303f\\uff00-\\uffef"          # CJK punctuation, full-width forms
             "\\u2014\\u2018-\\u201f\\u2026\\u00b7")  # dash, curly quotes, ellipsis, middle dot
_NAME_RUN = re.compile(r"[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*)*")
MAX_LATIN_NAMES = 60


def latin_names(request: dict) -> list[str]:
    """Latin-script names in the writer's own text of this request: each run of capitalised words, and each word alone, longest first."""
    blob = json.dumps({k: request.get(k) for k in ("note", "example_chapter", "values", "related")}, ensure_ascii=False)
    found: dict[str, None] = {}
    for run in _NAME_RUN.findall(blob):
        found.setdefault(run, None)
        for word in run.split():
            found.setdefault(word, None)
    return sorted(found, key=lambda n: (-len(n), n))[:MAX_LATIN_NAMES]


def script_pattern(request: dict) -> str | None:
    """The regex for a free-text string in the story's language, or None where the language has no rule here (only Chinese does)."""
    if not str(request.get("language") or "").lower().startswith("zh"):
        return None
    names = latin_names(request)
    return "^([" + _ZH_CLASS + "]" + "".join("|" + n for n in names) + ")+$"


def in_script(node: Any, pattern: str) -> Any:
    """The schema with `pattern` on every free-text string: a string with no `enum` or `const` (those are fixed words, the answer words and
    the names of links, and stay as they are)."""
    if isinstance(node, list):
        return [in_script(v, pattern) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: in_script(v, pattern) for k, v in node.items()}
    if out.get("type") == "string" and "enum" not in out and "const" not in out:
        out["pattern"] = pattern
    return out


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
    the related cards; in a Chinese story the free-text strings are limited to Han text (`script_pattern`). A list may be empty."""
    related = request.get("related") or {}
    people = related.get("characters") or []
    people = [people] if isinstance(people, dict) else people
    refs = link_names([p.get(cards.label_key("characters")) for p in people if isinstance(p, dict)], related.get("world"))
    schema = _clean(card_model_schema(request["card"]), refs, False, item_required=True)
    schema["required"] = list(schema["properties"])
    pattern = script_pattern(request)
    if pattern:
        schema = in_script(schema, pattern)      # a Chinese story's free text can be written only in its own script (see script_pattern)
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


def edge_patch(scope, refs: dict) -> Schema:
    """What a chapter's patch of the Entanglements may hold: `replace` operations on the ties this scope sent, each with a new `edge` and, when the chapter
    changed what the two are to each other, a new `bond`. A tie's ends and the holdings do not change in a chapter."""
    ids = scope.handles("ties")
    op = obj({"op": {"const": "replace"}, "id": one_of(ids), "values": obj(_item_props("entanglements", "ties", ["edge", "bond"], refs), ["edge"])})
    return obj({"ties": {"type": "array", "items": op, "minItems": 1, "maxItems": MAX_ITEMS}})


def shifts(request: dict, handles: Handles) -> Schema:
    """The `shifts` list of a chapter: at most one entry, for the Entanglements (`CHAPTER_SHIFT_CARDS`), replacing the edge of ties, as the
    contract's ShiftOut with an item named by its handle. With no tie sent there is nothing to shift and the list is empty."""
    refs = link_names([s.label for s in handles.of_card("characters")], request.get("world"))
    variants = [obj({"card": {"const": scope.card}, "patch": edge_patch(scope, refs)})
                for scope in handles.scopes if scope.card in CHAPTER_SHIFT_CARDS and scope.handles("ties")]
    if not variants:
        return {"type": "array", "items": text(), "maxItems": 0}
    return {"type": "array", "items": variants[0], "maxItems": 1}


def finish(request: dict, handles: Handles) -> Schema:
    """The `shifts` list at the end of the story: at most one entry per character, each for the Characters card, as the contract's ShiftOut with
    the character named by label and a list item by its handle. Every shiftable field of the card may be in the patch (`patch`). Which person an
    entry is for is part of its shape, so one person's patch can only point at that person's own items; that there is one entry per person is
    checked by `assemble.finish_shifts`, which a grammar cannot say."""
    refs = link_names([s.label for s in handles.of_card("characters")], None)
    variants = [obj({"card": {"const": "characters"}, "target": {"const": scope.label}, "patch": patch("characters", scope, refs)})
                for scope in handles.of_card("characters")]
    if not variants:
        return {"type": "array", "items": text(), "maxItems": 0}
    return {"type": "array", "items": variants[0] if len(variants) == 1 else {"anyOf": variants}, "maxItems": len(variants)}
