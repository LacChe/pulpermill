"""The prompt cases the harness measures (phase 5): every call, built for the Salt Coast sample story and for a very large one.
Used by tools/render_prompts.py, tools/budget_report.py and the tests."""
import copy
import json
from pathlib import Path

from pulpermill.prompts import budget
from pulpermill.schema.common import MAX_ITEMS
from pulpermill.prompts import prompts as P
from test_render import generate_request, plan_request

ROOT = Path(__file__).resolve().parents[2]
VECTORS = {r["name"]: r["data"] for r in json.loads((ROOT / "web/tests/contract-vectors.json").read_text(encoding="utf-8"))["requests"]}

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
             "description", "effect", "significance", "nature", "hold", "felt", "statement", "cost", "when_broken", "truth",
             "meaning", "bond", "edge", "what", "next_move", "fact", "happened", "changed", "normal", "disruption", "goal",
             "stakes", "believes", "fears", "wants", "refuses", "decided", "planted", "did", "reach", "note", "appearance",
             "previous_ending", "turn", "problem"}


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
    for card in ("world", "entanglements"):
        for key, value in (req.get(card) or {}).items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                req[card][key] = _clone(value, ties if key == "ties" else each)
    for key in ("standing", "open_plants", "available_reveals"):
        if isinstance(req.get(key), list) and req[key]:
            req[key] = _clone(req[key], each)
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
    "large": (dict(cast=8, each=MAX_ITEMS, ties=12, chapters=12, chars=2400), None),
}


def prompts(gen: dict, plan: dict, chapter_words: int = 3000, vectors: dict | None = None, big: dict | None = None) -> dict:
    """Every prompt for one story. With `big` (inflate arguments), the vector requests (fill, judge, ...) are inflated too."""
    vec = vectors or VECTORS
    if big:
        vec = {k: inflate(v, **big) for k, v in vec.items()}
    chapter = chapter_text(chapter_words)
    roles = P.writer_plan()
    earlier = prose(6500, 3)          # a whole first section at its ceiling (about 1,500 words)
    return {
        "writer-1-open": P.writer_prompt(gen, roles, 0),
        "writer-2-close": P.writer_prompt(gen, roles, 1, earlier),
        "planner-1-think": P.planner_think_prompt(plan),
        "planner-2-beat": P.planner_beat_prompt(plan, prose(5000, 1)),
        "events": P.events_prompt(gen, chapter),
        "shifts": P.shifts_prompt(gen, chapter, {"happened": prose(1100, 2)}),
        "fill-character": P.fill_prompt(vec["the page's fill_character request"]),
        "judge-world": P.judge_prompts(vec["the page's judge_world request"])[0],
        "style-fit": P.style_fit_prompt(vec["the page's style_fit request"]),
        "offstage": P.offstage_prompt(vec["an offstage request"]),
        "end-story-character": P.end_story_prompts(vec["an end-of-story request"])[0],
    }


def tier(name: str) -> dict:
    """The prompts for one size of story: sample, medium or large."""
    if name == "sample":
        return prompts(generate_request(), plan_request())
    args, words = TIERS[name]
    words = words or budget.budgets()["chapter_words_worst_case"]
    return prompts(inflate(generate_request(), **args), inflate(plan_request(), **args), words, big=args)


def golden() -> dict:
    """The sample prompts with placeholders for the text other calls would have made: what docs/prompts/samples/prompts holds."""
    gen, plan = generate_request(), plan_request()
    roles = P.writer_plan()
    earlier = " ".join(["[the first section would be here]"] * 3)
    return {
        "writer-1-open": P.writer_prompt(gen, roles, 0),
        "writer-2-close": P.writer_prompt(gen, roles, 1, earlier),
        "planner-1-think": P.planner_think_prompt(plan),
        "planner-2-beat": P.planner_beat_prompt(plan, "[the planner's thinking would be here]"),
        "events": P.events_prompt(gen, "[the chapter would be here]"),
        "shifts": P.shifts_prompt(gen, "[the chapter would be here]", {"happened": "[what the Events pass found]"}),
        "fill-character": P.fill_prompt(VECTORS["the page's fill_character request"]),
        "judge-world": P.judge_prompts(VECTORS["the page's judge_world request"])[0],
        "style-fit": P.style_fit_prompt(VECTORS["the page's style_fit request"]),
        "offstage": P.offstage_prompt(VECTORS["an offstage request"]),
        "end-story-character": P.end_story_prompts(VECTORS["an end-of-story request"])[0],
    }


def golden_file(prompt) -> str:
    schema = json.dumps(prompt.schema, indent=1) if prompt.schema else "(free text)"
    return f"[{prompt.name} {prompt.version}, stage: {prompt.stage}]\n\n{prompt.text}\n\n---- reply shape ----\n{schema}\n"
