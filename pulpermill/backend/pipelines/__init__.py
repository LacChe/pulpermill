"""One module per call. Each pipeline is `run(request, ctx) -> reply dict`. `canned` answers every call with a valid sample
reply and exists so the server and the page can be exercised with no model; the real pipelines replace it call by call."""
from .context import RunContext
from . import canned, simple, story

PIPELINES = {
    "fill": simple.fill, "judge": simple.judge, "style_fit": simple.style_fit, "offstage": story.offstage,
    "plan": story.plan, "generate": story.generate, "end_story": story.end_story,
}


CANNED = {call: getattr(canned, call) for call in PIPELINES}


def run_canned(request, ctx: RunContext) -> dict:
    """Every call answered with a valid sample reply and no real model work: for the page and the server tests with the fake engine."""
    return CANNED[request.call](request, ctx)


def run(request, ctx: RunContext) -> dict:
    """The reply for one model call. Raises BackendError, Cancelled, or anything else (the server calls that `server`)."""
    return PIPELINES[request.call](request, ctx)


__all__ = ["RunContext", "PIPELINES", "CANNED", "run", "run_canned"]
