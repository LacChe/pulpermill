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

def s_plain(value: Any) -> str:
    return str(value or "").strip()


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
    return _exclusive(_clean(card_model_schema(card_id), refs, drop_fixed, item_ids, True), card_id)


def _exclusive(schema: Schema, card_id: str) -> Schema:
    """An either-or pair (a rule `exactly_one` over two fields of a list item) becomes two shapes the model must pick between:
    one with only the first field (required) and one with only the second (required). The grammar then cannot produce both
    or neither, which the card's rule would otherwise block afterwards."""
    for rule in CARDS[card_id][3]:
        if rule.check != "exactly_one":
            continue
        for list_field in rule.fields:
            node = (schema.get("properties") or {}).get(list_field)
            item = (node or {}).get("items")
            if not item or "properties" not in item:
                continue
            keys = [k for k in rule.params["fields"] if k in item["properties"]]
            if len(keys) != 2:
                continue
            variants = []
            for key in keys:
                other = [k for k in keys if k != key]
                variants.append({**item, "properties": {n: v for n, v in item["properties"].items() if n not in other},
                                 "required": [key]})
            node["items"] = {"anyOf": variants}
    return schema


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
        "collision_goal": text(),
        "shift": {"type": "string", "enum": shifts},
        "ends_on": text(),
    }
    required = list(props)
    # Reveal, payoff and plant are always answered. Left optional, the model skipped them even when its own thinking had
    # chosen one ("pay off the open plant"), so the beat came out empty. An empty answer is the way to say "none".
    if reveals:
        props["reveal_rule"] = {"type": "string", "enum": [*reveals, ""]}
        required.append("reveal_rule")
    if plants:
        props["payoff"] = list_of(plants, 2)
        required.append("payoff")
    props["plant"] = maybe(text())      # null says "no plant". Left a plain string, the model wrote "none" and the page took it for a plant.
    required.append("plant")
    return obj(props, required)


# ---- The extractors -------------------------------------------------------------------------------------------------

def behavior_states(cast: list[dict]) -> list[str]:
    return _unique([b.get("state") for p in cast or [] for b in p.get("behaviors") or []])


def events_schema(req: dict) -> Schema:
    world = req.get("world") or {}
    # `planted` may only confirm the plant the beat planned, in the beat's own words. Left free, the model copied the
    # open plants list back as if every chapter had planted it again.
    planned = s_plain((req.get("beat") or {}).get("plant"))
    planted = maybe(one_of([planned])) if planned else {"type": "null"}
    return obj({
        "happened": text(), "changed": text(), "planted": planted,
        "paid_off": list_of(names_of(req.get("open_plants"), "text"), 2),
        "reveals_landed": list_of(names_of(req.get("available_reveals"), "statement"), 5),
        "behaviors_seen": list_of(behavior_states(req.get("cast")), 5),
        "things_seen": list_of(names_of(world.get("objects")), 5),
        # How the chapter left the goal it began with. Always answered: an empty answer would leave the next plan with nothing to stand on.
        "goal_change": {"type": "string", "enum": ["achieved", "redefined", "abandoned"]},
        "goal_now": text(),
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
        # The value is the person who now knows, suspects or is misled about it; the page moves them between the item's lists.
        "knowledge": lambda: change("knowledge", ["knows", "suspects", "misled"], one_of(people)),
        "pressures": lambda: change("pressures", ["what", "next_move", "bears_on"],
                                    {"anyOf": [text(), {"type": "array", "items": {"type": "string", "enum": people} if people else text()}]}),
    }
    options = [make() for section, make in kinds.items() if by_section.get(section)]
    if by_section.get("pressures"):
        # A pressure whose next move has happened on the page is resolved; the page then passes over it when it picks the spotlight.
        options.append(change("pressures", ["status"], {"type": "string", "enum": ["resolved"]}))
    if by_section.get("knowledge"):
        # What a misled person believes can move too (a new false belief, or none once they learn the truth).
        options.append(change("knowledge", ["belief"], text()))
    changes = ({"type": "array", "items": {"anyOf": options} if len(options) > 1 else options[0]}
               if options else {"type": "array", "items": text(), "maxItems": 0})
    shift = obj({"character": one_of(cast), **{k: text() for k in SHIFT_FIELDS}}, ["character"])
    rules = names_of((req.get("world") or {}).get("rules"), "statement")
    # `belief` is what a misled person wrongly believes instead; null for anyone who knows or suspects the truth.
    about_rule = obj({"person": one_of(people), "status": {"type": "string", "enum": STATUSES}, "rule": one_of(rules), "belief": maybe(text())})
    about_fact = obj({"person": one_of(people), "status": {"type": "string", "enum": STATUSES}, "fact": text(), "belief": maybe(text())})
    # A person who joins something that already has a line points at that line by its handle; only a new thing is written out.
    about_entry = obj({"person": one_of(people), "status": {"type": "string", "enum": STATUSES}, "entry": one_of(by_section.get("knowledge") or []), "belief": maybe(text())})
    shapes = [*([about_entry] if by_section.get("knowledge") else []), *([about_rule] if rules else []), about_fact]
    new = {"anyOf": shapes} if len(shapes) > 1 else shapes[0]
    # Which knowledge, ties and holdings the chapter actually showed (never one it only named): this is what use counts are made of,
    # so the least-shown are the ones carried into later requests. A pressure is not listed: the spotlight is its use.
    showable = [h for h, info in handles.items() if info["section"] != "pressures"]
    return obj({"shifts": {"type": "array", "items": shift, "maxItems": 5},
                "changes": changes,
                "new_knowledge": {"type": "array", "items": new, "maxItems": 8},
                "shown": list_of(showable, len(showable))})


# ---- The rest -------------------------------------------------------------------------------------------------------

def judge_schema(handles: list[str]) -> Schema:
    """One check per item, each saying outright whether it keeps the rule. The model sees only the key names (the grammar
    forces them), so they say what is asked: a list named "hits" was read as "the items that match the question". The
    handle names the field too ("behaviors.2"), so a check is only two keys: fewer tokens to write, and the reply is
    exactly one check per item."""
    check = obj({"item": one_of(handles), "keeps_the_rule": {"type": "boolean"}})
    items: Schema = {"type": "array", "items": check}
    if handles:
        items.update({"minItems": len(handles), "maxItems": len(handles)})
    return obj({"checks": items})


def style_fit_schema() -> Schema:
    return obj({"fits": {"type": "boolean"}, "message": text()})


def offstage_schema() -> Schema:
    return obj({"did": text(), "reach": text()})
