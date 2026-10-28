"""Valid sample replies, shaped by the request, with a fake model pass per stage so status, Stop and timing behave like
the real thing. Nothing here is a story: these are stand-ins until each call's real pipeline exists (plan sections 7, M4-M5)."""
import copy

from .context import RunContext


def _think(ctx: RunContext, stages: list[str]) -> None:
    """One short engine call per stage, saying the stage first. The engine checks Stop between tokens."""
    for name in stages:
        ctx.set_stage(name)
        ctx.engine.generate(f"(canned) {name}", max_tokens=5, cancel=ctx.cancel)


def fill(request, ctx):
    ctx.engine.generate("(canned) fill", max_tokens=5, cancel=ctx.cancel)
    return {"ok": True, "values": {}}      # "nothing to add" is a valid fill; the page leaves the card alone


def judge(request, ctx):
    ctx.engine.generate("(canned) judge", max_tokens=5, cancel=ctx.cancel)
    return {"ok": True, "results": [{"rule": rule.id, "hits": []} for rule in request.rules]}


def style_fit(request, ctx):
    ctx.engine.generate("(canned) style_fit", max_tokens=5, cancel=ctx.cancel)
    return {"ok": True, "fits": True, "message": ""}


def offstage(request, ctx):
    _think(ctx, ["offstage"])
    return {"ok": True, "did": "Canned offstage move: a background group acts.",
            "reach": "Canned reach: word of it gets to the protagonist."}


def plan(request, ctx):
    _think(ctx, ["retry", "beat"] if request.retry else ["think", "beat"])
    places = (request.world or {}).get("places") or []
    beat = {
        "when_time": "Canned time.", "collision_goal": "Canned goal.", "collision_block": "Canned block.",
        "choice_a": "Canned choice A.", "choice_b": "Canned choice B.", "turn": "Canned turn.", "ends_on": "Canned ending.",
    }
    if places and places[0].get("name"):
        beat["where"] = places[0]["name"]
    if request.legal_shifts:
        beat["shift"] = request.legal_shifts[0]
    if request.chapter != 1:
        beat["when_gap"] = "Canned gap."
    plant = (request.open_plants or [None])[0]
    if plant and plant.get("text"):
        beat["payoff"] = [plant["text"]]
    return {"ok": True, "thinking": f"Canned thinking for chapter {request.chapter}.", "beat": beat}


def generate(request, ctx):
    _think(ctx, ["write", "events", "shifts"])
    beat = request.beat or {}
    who = next((c.get("name") for c in request.cast if c.get("name")), None)
    return {
        "ok": True,
        "chapter_text": f"Canned chapter {request.chapter} of {request.chapter_count}. {beat.get('turn', '')}".strip(),
        "events": {"happened": f"Canned events of chapter {request.chapter}."},
        "shifts": [{"character": who, "decided": "Canned decision."}] if who else [],
        "changes": [],
        "new_knowledge": [],
        "shown": [],
    }


def end_story(request, ctx):
    _think(ctx, ["update"])
    return {"ok": True, "characters": copy.deepcopy(request.characters), "world": copy.deepcopy(request.world)}
