"""MillPrompter: picks the module for each call by name. The contract with a call module is written in README.md:
`build_flow(request, kit) -> Flow`, an optional `script(request, kit)`, an optional `VERSION`. No module, or a module that is
still the scaffold's, means the stub's flow."""
import importlib
from types import ModuleType
from typing import Any

from ..base import CALLS, Flow, Prompter
from . import common


def load_module(call: str) -> ModuleType | None:
    """The module `mill/<call>.py`, or None when there is none (the call then runs the stub's flow). Looked up on every request, so a
    module that is replaced (or a test's stand-in in sys.modules) takes effect at once."""
    name = f"{__package__}.{call}"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name == name:
            return None
        raise


class MillPrompter(Prompter):
    name = "mill"

    def __init__(self, base_version: str):
        self.base_version = base_version

    @property
    def version(self) -> str:
        """The base version plus one piece, `+<call>:<module VERSION>:<text digest>`, for each call with its own wording. The module's
        VERSION is bumped by hand with any change to its code; the digest changes by itself with any change to `text/en/<call>.yaml`,
        so edited wording can never leave the version as it was. A call still on the stub's flow adds nothing."""
        pieces = []
        for call in CALLS:
            module = load_module(call)
            own = getattr(module, "VERSION", None)
            if not own:
                continue
            digest = common.text_digest(call)
            pieces.append(f"+{call}:{own}" + (f":{digest}" if digest else ""))
        return self.base_version + "".join(pieces)

    def flow(self, call: str, request: dict, kit: Any) -> Flow:
        if call not in CALLS:
            raise ValueError(f"the mill prompter has no flow for {call!r}")
        module = load_module(call)
        if module is None:
            return common.stub_flow(call, request, kit)
        if not callable(getattr(module, "build_flow", None)):
            raise TypeError(f"the mill module for {call!r} must define build_flow(request, kit)")
        return module.build_flow(request, kit)
