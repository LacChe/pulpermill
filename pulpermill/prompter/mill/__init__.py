"""The `mill` prompter: wording for the five calls, one module per call. A call whose module has not been written yet runs the stub's
flow, so `mill` can be selected (`Config.prompter = "mill"`) from the start. See README.md in this folder."""
from typing import Any

from .mill import MillPrompter, load_module

VERSION = "mill-0.1"        # the base of the version string; MillPrompter.version adds one piece per call that has its own wording


def prompter() -> MillPrompter:
    return MillPrompter(VERSION)


def script(call: str, request: dict, kit: Any) -> list[str]:
    """What a fake engine must return, one text per step, for a valid reply to `request` (`engine.script(*script(...))`).
    A call module with its own wording supplies `script(request, kit)`; a call still on the stub's flow uses the stub's script."""
    module = load_module(call)
    if module is not None and hasattr(module, "script"):
        return module.script(request, kit)
    flow = prompter().flow(call, request, kit)
    if not hasattr(flow, "script"):
        raise NotImplementedError(f"the mill module for {call!r} has its own flow but no script(request, kit) for the fake engine")
    return flow.script()


__all__ = ["MillPrompter", "VERSION", "prompter", "script"]
