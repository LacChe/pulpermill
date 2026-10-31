"""Valid sample replies, shaped by the request, with a fake model pass per stage so status, Stop and timing behave like the real thing.
Nothing here is a story: these are stand-ins for the page and the server tests, and they use no prompter."""
from .context import RunContext


def _think(ctx: RunContext, names: list[str]) -> None:
    """One short engine call per stage, saying the stage first as `{name, index, of}`. The engine checks Stop between tokens."""
    for n, name in enumerate(names, 1):
        ctx.set_stage({"name": name, "index": n, "of": len(names)})
        ctx.engine.generate(f"(canned) {name}", max_tokens=5, cancel=ctx.cancel)


def fill(request, ctx):
    _think(ctx, ["fill"])
    return {"ok": True, "values": {}}      # "nothing to add" is a valid fill; the page leaves the card alone


def judge(request, ctx):
    _think(ctx, ["judge"])
    return {"ok": True, "results": [{"rule": rule.id, "hits": []} for rule in request.rules]}


def style_fit(request, ctx):
    _think(ctx, ["style_fit"])
    return {"ok": True, "fits": True, "message": ""}


def plan(request, ctx):
    _think(ctx, ["plan"])
    places = (request.world or {}).get("places") or []
    beat = {"when_time": "Canned time.", "aim": f"Canned aim for chapter {request.chapter}.", "plan": "Canned plan."}
    if places and places[0].get("name"):
        beat["where"] = places[0]["name"]
    return {"ok": True, "beat": beat}


def generate(request, ctx):
    _think(ctx, ["write", "events", "shifts"])
    return {"ok": True, "chapter_text": f"Canned chapter {request.chapter} of {request.chapter_count}.",
            "events": {"happened": f"Canned events of chapter {request.chapter}.", "changed": "Canned change."},
            "shifts": []}
