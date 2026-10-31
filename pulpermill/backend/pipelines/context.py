from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import Config
from ..engine.base import CancelFlag, Engine


@dataclass
class RunContext:
    """What a pipeline gets besides the request: the engine, the cancel flag, a way to say what stage it is in (status shows it as
    `{name, index, of}`), the config and the prompter the call is answered with."""
    engine: Engine
    cancel: CancelFlag
    set_stage: Callable[[dict | None], None]
    config: Config
    prompter: Any = None                        # a pulpermill.prompter.Prompter; None only for the canned pipeline
    notes: dict = field(default_factory=dict)   # what the run wants kept with its record (squeeze, prompter, every step's attempts)
