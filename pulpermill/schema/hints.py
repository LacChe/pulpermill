from __future__ import annotations

import json

from .characters import CastDraft, CharacterCard
from .common import POOLS
from .outline import PlotOutline
from .style import DESIGN_ANCHORS, LADDERS, StyleCard
from .updates import StateUpdate
from .world import WorldBible, WorldDraft


# ===========================================================================
# EDITOR HINTS (so the page never keeps its own copy of the schema)
# ===========================================================================

# Fields that name something on another card (a character, a place, a hidden truth), as dotted paths without list
# positions. The page checks each of them against the cards it holds, so that when one card is regenerated it can mark
# every field on the other cards that now points at something that is gone.
REFS = {
    "world.objects.owner": "character",
    "world.objects.location": "location",
    "world.hidden_truths.known_by": "character",
    "outline.arcs.character": "character",
    "outline.chapter_beats.location": "location",
    "outline.protagonist": "character",
    "outline.chapter_beats.present": "character",
    "outline.chapter_beats.agendas.character": "character",
    "outline.relationships.a": "character",
    "outline.relationships.b": "character",
    "outline.chapter_beats.reveals": "truth",
}

# Fields that take one of a fixed set of numbered choices: path -> [[value, name], ...]. None now (the page reads SCH.choices).
CHOICES: dict[str, list] = {}

# Fields the card GENERATOR page hides (live state that starts empty). None now: a character holds no live state.
GENERATOR_HIDDEN: list[str] = []


def ui_hints() -> dict:
    """
    What a card editor needs to know, read from the models themselves:
      enums:    {card: {field: [allowed values]}}
      nullable: ["world.objects.owner", ...]  dotted paths (no list indexes) of fields that may be null,
                so an emptied text box can be saved as null
      hidden:   field names the generator page leaves out
      lists:    {dotted path: a blank item} for every list whose items are objects, so the page can add the first item to
                an empty list (it has no earlier item to copy)
    Card keys are the four the page uses: style, characters, world, outline.
    """
    roots = {
        "style": StyleCard,
        "characters": CharacterCard,
        "world": WorldBible,
        "outline": PlotOutline,
    }
    enums: dict[str, dict[str, list]] = {}
    nullable: list[str] = []
    lists: dict[str, dict] = {}

    def unwrap(node, defs):
        null = False
        if "anyOf" in node:
            rest = [o for o in node["anyOf"] if o.get("type") != "null"]
            null = len(rest) != len(node["anyOf"])
            node = rest[0] if len(rest) == 1 else node
        while "$ref" in node:
            node = defs[node["$ref"].split("/")[-1]]
        return node, null

    def blank_of(node, defs):
        """A new, empty item of the shape `node` describes: text empty, lists empty, numbers 0, a choice its first value."""
        out = {}
        for name, sub in (node.get("properties") or {}).items():
            inner, _ = unwrap(sub, defs)
            if "enum" in inner:
                out[name] = inner["enum"][0]
            elif inner.get("type") == "array":
                out[name] = []
            elif inner.get("properties"):
                out[name] = blank_of(inner, defs)
            elif inner.get("type") in ("integer", "number"):
                out[name] = 0
            else:
                out[name] = ""
        return out

    def visit(card, node, defs, path):
        node, _ = unwrap(node, defs)
        if node.get("type") == "array":
            visit(card, node.get("items", {}), defs, path)
            return
        for name, sub in (node.get("properties") or {}).items():
            inner, null = unwrap(sub, defs)
            here = path + [name]
            if null:
                nullable.append(".".join(here))
            if "enum" in inner:
                enums.setdefault(card, {})[name] = list(inner["enum"])
            if inner.get("type") == "array":
                item, _ = unwrap(inner.get("items", {}), defs)
                if item.get("properties"):
                    lists[".".join(here)] = blank_of(item, defs)
            visit(card, inner, defs, here)

    for card, cls in roots.items():
        sch = cls.model_json_schema()
        visit(card, sch, sch.get("$defs", {}), [card])
    return {
        "enums": enums,
        "nullable": sorted(set(nullable)),
        "lists": lists,
        "hidden": list(GENERATOR_HIDDEN),
        "refs": dict(REFS),
        "choices": dict(CHOICES),
        "pools": dict(POOLS),
        "anchors": {k: list(v) for k, v in DESIGN_ANCHORS.items()},
        "ladders": {k: [[n, t] for n, t in v] for k, v in LADDERS.items()},
    }


if __name__ == "__main__":
    for m in (StyleCard, CastDraft, WorldDraft, PlotOutline, StateUpdate):
        print(m.__name__, len(json.dumps(m.model_json_schema())), "chars of schema")
