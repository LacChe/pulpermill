"""One module per call. Each pipeline is `run(request, ctx) -> reply dict`. `canned` answers every call with a valid sample
reply and exists so the server and the page can be exercised with no model; the real pipelines replace it call by call."""
from .context import RunContext
from . import canned

PIPELINES = {
    "fill": canned.fill, "judge": canned.judge, "style_fit": canned.style_fit, "offstage": canned.offstage,
    "plan": canned.plan, "generate": canned.generate, "end_story": canned.end_story,
}


def run(request, ctx: RunContext) -> dict:
    """The reply for one model call. Raises BackendError, Cancelled, or anything else (the server calls that `server`)."""
    return PIPELINES[request.call](request, ctx)


__all__ = ["RunContext", "PIPELINES", "run"]
