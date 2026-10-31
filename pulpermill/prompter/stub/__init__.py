"""The stub prompter: trivial prompts, the correct grammars, and a script for the fake engine, so every call runs end to end with no model."""
from .stub import StubPrompter, script


def prompter() -> StubPrompter:
    return StubPrompter()


__all__ = ["StubPrompter", "prompter", "script"]
