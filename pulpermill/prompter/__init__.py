"""Prompters: the replaceable wording behind the backend. `load_prompter(name)` returns the prompter in pulpermill/prompter/<name>/."""
import importlib
import pkgutil
import re

from .base import CALLS, SAMPLING, Flow, Prompter, Step

__all__ = ["CALLS", "SAMPLING", "Flow", "Prompter", "Step", "UnknownPrompter", "known_prompters", "load_prompter"]


class UnknownPrompter(RuntimeError):
    """The Config names a prompter that does not exist. Raised at startup, with the names that do."""


def known_prompters() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if m.ispkg)


def load_prompter(name: str) -> Prompter:
    """The prompter folder `name` must expose `prompter()`, which returns a Prompter whose `name` is the folder's name."""
    known = known_prompters()
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name not in known:
        raise UnknownPrompter(f"There is no prompter called {name!r}. The prompters are: {', '.join(known) or 'none'}. "
                              "Set Config.prompter to one of them.")
    found = importlib.import_module(f"{__name__}.{name}").prompter()
    if not isinstance(found, Prompter) or found.name != name or not getattr(found, "version", None):
        raise UnknownPrompter(f"The prompter {name!r} must be a Prompter named {name!r} with a version.")
    return found
