"""The shape of each reply, as JSON Schema, for constrained decoding. The backend gives these to the model server so the
reply is valid JSON in the contract's shape. Where the request already lists the allowed words (the places, the open plants,
the cast's names), they are the enum, so the model cannot answer a word the page will not match.

Shape is forced here; content is checked afterwards by the page. Only the JSON Schema keywords llama.cpp's grammar builder
understands are used: type, enum, const, items, properties, required, anyOf, minItems, maxItems, additionalProperties."""
from copy import deepcopy
from typing import Any

from ..schema import CARDS

KEEP = ("type", "enum", "const", "items", "properties", "required", "anyOf", "minItems", "maxItems", "additionalProperties")
SHIFT_FIELDS = ("believes", "fears", "wants", "refuses", "decided")
STATUSES = ["knows", "suspects", "misled"]

Schema = dict[str, Any]


# ---- Small shapes ---------------------------------------------------------------------------------------------------

def text() -> Schema:
    return {"type": "string"}


def maybe(schema: Schema) -> Schema:
    return {"anyOf": [schema, {"type": "null"}]}


def one_of(names: list[str]) -> Schema:
    """One of these exact words (a plain string when the list is empty, so nothing can be forced wrongly)."""
    names = _unique(names)
    return {"type": "string", "enum": names} if names else text()


def list_of(names: list[str], limit: int | None = None) -> Schema:
    """A list of these exact words. An empty list of words allows only an empty list."""
    names = _unique(names)
    if not names:
        return {"type": "array", "items": text(), "maxItems": 0}
    out: Schema = {"type": "array", "items": {"type": "string", "enum": names}}
    if limit:
        out["maxItems"] = limit
    return out


def obj(properties: dict[str, Schema], required: list[str] | None = None) -> Schema:
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required, "additionalProperties": False}


def _unique(names: list[Any]) -> list[str]:
    seen: dict[str, None] = {}
    for n in names:
        n = str(n or "").strip()
        if n:
            seen.setdefault(n, None)
    return list(seen)


def names_of(items: list[dict] | None, key: str = "name") -> list[str]:
    return _unique([i.get(key) for i in items or []])


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


def field_extras(card_id: str, field: str | None = None) -> dict[str, dict]:
    """The extras of a card's fields (or of the item fields of a list field), by key: ref, filled_by, fixed, and so on."""
    node = card_model_schema(card_id)
    if field:
        node = node["properties"][field].get("items", {})
    return {k: {x: y for x, y in v.items() if x not in ("type", "title", "enum", "items", "anyOf", "properties")}
            for k, v in node.get("properties", {}).items()}


def _with_enum(node: Schema, names: list[str]) -> Schema:
    if "anyOf" in node:
        return {**node, "anyOf": [b if b.get("type") == "null" else _with_enum(b, names) for b in node["anyOf"]]}
    if node.get("type") == "array":
        return {**node, "items": {**node.get("items", text()), "enum": names}}
    if node.get("type") == "string":
        return {**node, "enum": names}
    return node


def _clean(node: Any, refs: dict | None, drop_fixed: bool, item_ids: bool, top: bool) -> Any:
    if isinstance(node, list):
        return [_clean(v, refs, drop_fixed, item_ids, False) for v in node]
    if not isinstance(node, dict):
        return node
    out: Schema = {}
    for key in KEEP:
        if key not in node:
            continue
        value = node[key]
        if key == "properties":
            props = {}
            for name, spec in value.items():
                if name == "id" and (top or not item_ids):
                    continue
                if drop_fixed and spec.get("fixed"):
                    continue
                child = _clean(spec, refs, drop_fixed, item_ids, False)
                sources = spec.get("ref")
                if refs and sources:
                    names = _unique([n for source in sources for n in refs.get(source, [])])
                    if names:
                        child = _with_enum(child, names)
                props[name] = child
            out["properties"] = props
            out["required"] = []                       # empty means no answer: every field is optional
            out["additionalProperties"] = False
        elif key == "required":
            continue
        elif key == "additionalProperties":
            continue
        else:
            out[key] = _clean(value, refs, drop_fixed, item_ids, False)
    return out


def card_schema(card_id: str, *, refs: dict[str, list[str]] | None = None, drop_fixed: bool = False,
                item_ids: bool = False) -> Schema:
    """The reply shape for a card: every field optional, ids left out (the page makes them), and each link field limited to
    the names in `refs` (keyed by reference source, such as "characters" or "world.places"). `item_ids` keeps an optional
    `id` on list items, for the end-of-story update, where an existing item must carry the id it was sent."""
    return _clean(card_model_schema(card_id), refs, drop_fixed, item_ids, True)


def link_names(related: dict) -> dict[str, list[str]]:
    """The names a card may link to, by reference source, from the cards a request carries."""
    world = related.get("world") or {}
    characters = related.get("characters") or []
    if isinstance(characters, dict):
        characters = [characters]
    return {
        "characters": names_of(characters),
        "world.places": names_of(world.get("places")),
        "world.objects": names_of(world.get("objects")),
        "world.powers": names_of(world.get("powers")),
        "world.rules": names_of(world.get("rules"), "statement"),
    }


def fill_schema(req: dict) -> Schema:
    return card_schema(req["card"], refs=link_names(req.get("related") or {}))


# ---- The planner ----------------------------------------------------------------------------------------------------

def beat_schema(req: dict) -> Schema:
    """The beat the planner fills. The cast, chapter, spotlight, offstage move and plan hash are not the planner's."""
    cast = names_of(req.get("cast"))
    places = names_of((req.get("world") or {}).get("places"))
    reveals = names_of(req.get("available_reveals"), "statement")
    plants = names_of(req.get("open_plants"), "text")
    shifts = list(req.get("legal_shifts") or []) or ["harder", "easier"]
    first = int(req.get("chapter") or 1) == 1
    props: dict[str, Schema] = {
        "where": one_of(places),
        "when_time": text(),
        **({} if first else {"when_gap": text()}),
        "collision_goal": text(), "collision_block": text(),
        "choice_a": text(), "choice_b": text(),
        "turn": text(),
        "shift": {"type": "string", "enum": shifts},
        "ends_on": text(),
    }
    required = list(props)
    if reveals:
        props["reveal_rule"] = {"type": "string", "enum": reveals}
        props["reveal_learners"] = list_of(cast)
    if plants:
        props["payoff"] = list_of(plants, 2)
    props["plant"] = text()
    if req.get("goal"):
        props["goal_change"] = {"type": "string", "enum": ["achieved", "redefined", "abandoned"]}
        props["goal_now"] = text()
    return obj(props, required)


# ---- The extractors -------------------------------------------------------------------------------------------------

def behavior_states(cast: list[dict]) -> list[str]:
    return _unique([b.get("state") for p in cast or [] for b in p.get("behaviors") or []])


def events_schema(req: dict) -> Schema:
    world = req.get("world") or {}
    return obj({
        "happened": text(), "changed": text(), "planted": maybe(text()),
        "paid_off": list_of(names_of(req.get("open_plants"), "text"), 2),
        "reveals_landed": list_of(names_of(req.get("available_reveals"), "statement"), 5),
        "behaviors_seen": list_of(behavior_states(req.get("cast")), 5),
        "things_seen": list_of(names_of(world.get("objects")), 5),
        "goal_landed": {"type": "boolean"},
    })


def entanglement_handles(entanglements: dict) -> dict[str, dict]:
    """A short handle for every live item, so the model points at an item without ever seeing an id: T1, H1, K1, P1."""
    letters = {"ties": "T", "holdings": "H", "knowledge": "K", "pressures": "P"}
    out: dict[str, dict] = {}
    for section, letter in letters.items():
        for n, item in enumerate(entanglements.get(section) or [], 1):
            out[f"{letter}{n}"] = {"section": section, "id": item.get("id")}
    return out


def shifts_schema(req: dict, handles: dict[str, dict]) -> Schema:
    cast = names_of(req.get("cast"))
    world = req.get("world") or {}
    groups = names_of(world.get("powers"))
    holders = _unique(cast + groups + names_of(world.get("places")))
    people = _unique(cast + groups)
    by_section: dict[str, list[str]] = {}
    for handle, info in handles.items():
        by_section.setdefault(info["section"], []).append(handle)

    def change(section: str, fields: list[str], value: Schema) -> Schema:
        return obj({"section": {"const": section}, "item": {"type": "string", "enum": by_section[section]},
                    "field": {"type": "string", "enum": fields}, "value": value})

    kinds = {
        "ties": lambda: change("ties", ["bond", "edge"], text()),
        "holdings": lambda: change("holdings", ["held_by"], one_of(holders)),
        "knowledge": lambda: change("knowledge", ["status"], {"type": "string", "enum": STATUSES}),
        "pressures": lambda: change("pressures", ["what", "next_move", "bears_on"],
                                    {"anyOf": [text(), {"type": "array", "items": {"type": "string", "enum": people} if people else text()}]}),
    }
    options = [make() for section, make in kinds.items() if by_section.get(section)]
    changes = ({"type": "array", "items": {"anyOf": options} if len(options) > 1 else options[0]}
               if options else {"type": "array", "items": text(), "maxItems": 0})
    shift = obj({"character": one_of(cast), **{k: text() for k in SHIFT_FIELDS}}, ["character"])
    new = obj({"person": one_of(people), "status": {"type": "string", "enum": STATUSES},
               "rule": maybe(one_of(names_of((req.get("world") or {}).get("rules"), "statement"))), "fact": maybe(text())})
    return obj({"shifts": {"type": "array", "items": shift, "maxItems": 5},
                "changes": changes,
                "new_knowledge": {"type": "array", "items": new, "maxItems": 3}})


# ---- The rest -------------------------------------------------------------------------------------------------------

def judge_schema(fields: list[str], handles: list[str]) -> Schema:
    """One check per item, each saying outright whether it keeps the rule. The model sees only the key names (the grammar
    forces them), so they say what is asked: a list named "hits" was read as "the items that match the question"."""
    check = obj({"field": one_of(fields), "item": maybe(one_of(handles)) if handles else maybe(text()),
                 "keeps_the_rule": {"type": "boolean"}})
    return obj({"checks": {"type": "array", "items": check}})


def style_fit_schema() -> Schema:
    return obj({"fits": {"type": "boolean"}, "message": text()})


def offstage_schema() -> Schema:
    return obj({"did": text(), "reach": text()})
