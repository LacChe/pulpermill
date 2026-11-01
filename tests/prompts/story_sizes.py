"""The cases the budget tests measure: the Salt Coast sample story (the new request shape, see fixtures/) and bigger and bigger versions of it.
`render_story` is a generic prompt made with the card renderers alone; it is what the budget tests fit."""
import copy

from pulpermill.prompts import budget, render, textfiles as tx
from pulpermill.schema.common import MAX_ITEMS
from test_render import generate_request

PROSE = [
    "The harbour board had changed the dock rules again, and nobody on the quay would say who had asked for it.",
    "She counted the coins twice, set them down in a row, and listened to the gulls complain about the weather over the east market.",
    "He talked the way a man walks across thin ice, quickly and without looking at his feet, and stopped when the silence grew too loud.",
    "Salt had eaten the paint from the shutters years ago, and the grey boards held the smell of tar, wet rope and old fish.",
    "Nobody in the room mentioned the letter, which was how everyone knew that everyone had read it before the lamps were lit.",
    "A long habit of keeping accounts had taught her that the most dangerous number in any ledger is the one nobody writes down.",
]


def prose(chars: int, offset: int = 0) -> str:
    """Plain English prose of at least `chars` characters, ending on a full stop."""
    out, i = [], offset
    while sum(len(x) + 1 for x in out) < chars:
        out.append(PROSE[i % len(PROSE)])
        i += 1
    return " ".join(out)


def chapter_text(words: int) -> str:
    text, i = [], 0
    while sum(len(x.split()) for x in text) < words:
        text.append(prose(600, i))
        i += 1
    return "\n\n".join(text)


# What the page itself bounds: the fixed facts are short, the last ending is cut to 1,500 characters (inventory, row 8).
PAGE_BOUND = {"appearance": 300, "previous_ending": 1500}
# The free-text fields the renderers cap. Choices (style options, sexes, statuses) are left as they are.
FREE_TEXT = {"sketch", "fear", "flaw", "competence", "vulnerability", "speech", "history", "text", "state", "tendency",
             "description", "effect", "significance", "nature", "hold", "felt", "statement", "cost", "when_broken",
             "meaning", "bond", "edge", "happened", "changed", "normal", "disruption", "note", "appearance",
             "previous_ending", "aim", "plan", "problem"}


def _stuff(node, counter, chars=2400, skip=("id", "language", "call", "status", "schema_version")):
    """Every multi-word text is lengthened to far past its cap, so each cap is what limits the prompt."""
    if isinstance(node, dict):
        return {k: (v if k in skip else _stuff_value(k, v, counter, chars)) for k, v in node.items()}
    if isinstance(node, list):
        return [_stuff(v, counter, chars) for v in node]
    return _stuff_value("", node, counter, chars)


def _stuff_value(key, node, counter, chars):
    if isinstance(node, (dict, list)):
        return _stuff(node, counter, chars)
    if isinstance(node, str) and key in FREE_TEXT and len(node.split()) >= 2:
        counter[0] += 1
        return prose(min(PAGE_BOUND.get(key, chars), chars), counter[0])
    return node


def _clone(items: list, size: int) -> list:
    out = list(items)
    k = 0
    while out and len(out) < size:
        item = copy.deepcopy(items[k % len(items)])
        k += 1
        if isinstance(item, dict):
            for key in ("id",):
                if isinstance(item.get(key), str):
                    item[key] = f"{item[key]}_{k}"
            for key in ("name", "term"):
                if isinstance(item.get(key), str):
                    item[key] = f"{item[key]} {chr(64 + k)}"
        out.append(item)
    return out


def inflate(req: dict, cast: int = 8, each: int = MAX_ITEMS, ties: int = 12, chapters: int = 12, chars: int = 2400) -> dict:
    """A very large story: `cast` people, the most items the schema allows (MAX_ITEMS) in every list, `ties` ties, `chapters` chapters of events, and
    every multi-word text far past its cap, so each cap is what limits the prompt."""
    req = copy.deepcopy(req)
    if isinstance(req.get("cast"), list) and req["cast"] and isinstance(req["cast"][0], dict) and "wants" in req["cast"][0]:
        req["cast"] = _clone(req["cast"], cast)
        for person in req["cast"]:
            for key in ("wants", "values", "behaviors"):
                if person.get(key):
                    person[key] = _clone(person[key], each)
    for key, value in (req.get("world") or {}).items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            req["world"][key] = _clone(value, each)
    for key in ("ties", "holdings"):
        if isinstance(req.get(key), list) and req[key]:
            req[key] = _clone(req[key], ties if key == "ties" else each)
    events = req.get("earlier_events")
    if isinstance(events, list) and events:
        base = _clone(events, chapters)
        for n, e in enumerate(base, 1):
            e["chapter"] = n
        req["earlier_events"] = base
        req["chapter"] = max(req.get("chapter", 1), chapters + 1)
        req["chapter_count"] = max(req.get("chapter_count", 1), chapters + 3)
    return _stuff(req, [0], chars)


TIERS = {
    # name: (inflate arguments, chapter words). "sample" is the Salt Coast story as it is.
    "medium": (dict(cast=5, each=3, ties=6, chapters=8, chars=200), 3000),
    "huge": (dict(cast=40, each=MAX_ITEMS, ties=60, chapters=12, chars=2400), None),     # does not fit at any squeeze: the too_long case
    "large": (dict(cast=8, each=MAX_ITEMS, ties=12, chapters=12, chars=2400), None),
}


def tier_request(name: str) -> dict:
    """The sample story, or a bigger one: "sample", "medium", "large" or "huge"."""
    if name == "sample":
        return generate_request()
    args, _ = TIERS[name]
    return inflate(generate_request(), **args)


def render_story(req: dict, factor: float = 1.0) -> budget.Sized:
    """A prompt made of what the card renderers make of a story request: the style, the cast, the world, and the ties and holdings by
    name. No story prompt, no wording of a particular call: a stand-in whose size follows the cards, to fit against the budget."""
    names = {c["id"]: c.get("name") for c in req["cast"]}
    for key in ("places", "objects", "powers"):
        names.update({i["id"]: i.get("name") for i in req["world"].get(key, [])})
    ties = [{**x, "tie_from": names.get(x["tie_from"], ""), "tie_to": names.get(x["tie_to"], "")} for x in req["ties"]]
    holdings = [{**x, "holdee": names.get(x["holdee"], ""), "held_by": names.get(x["held_by"], "")} for x in req["holdings"]]
    with tx.squeeze(factor):
        text = "\n\n".join(x for x in (render.render_style(req["style"]), render.render_cast(req["cast"]), render.render_world(req["world"]),
                                        render.render_entanglements({"ties": ties, "holdings": holdings}, list(names.values()))) if x)
    return budget.Sized("render_story", text, 1000)
