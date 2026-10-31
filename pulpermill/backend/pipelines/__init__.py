"""Every call is answered the same way: the prompter gives a flow, the runner runs it (runner.run_call). `canned` answers every call
with a valid sample reply and no model work, so the server and the page can be exercised with no model (`--fake`)."""
from .context import RunContext
from . import canned

CALLS = ("fill", "judge", "style_fit", "plan", "generate")


def run(request, ctx: RunContext) -> dict:
    """The reply for one model call. Raises BackendError, Cancelled, or anything else (the server calls that `server`)."""
    from .. import runner
    return runner.run_call(request, ctx)


PIPELINES = {call: run for call in CALLS}
CANNED = {call: getattr(canned, call) for call in CALLS}


def run_canned(request, ctx: RunContext) -> dict:
    """Every call answered with a valid sample reply and no real model work: for the page and the server tests with the fake engine."""
    return CANNED[request.call](request, ctx)


__all__ = ["RunContext", "PIPELINES", "CANNED", "CALLS", "run", "run_canned"]
