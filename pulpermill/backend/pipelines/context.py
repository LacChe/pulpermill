from dataclasses import dataclass, field
from typing import Callable

from ..config import Config
from ..engine.base import CancelFlag, Engine


@dataclass
class RunContext:
    """What a pipeline gets besides the request: the engine, the cancel flag, a way to say what stage it is in (status
    shows it), and the config."""
    engine: Engine
    cancel: CancelFlag
    set_stage: Callable[[str | None], None]
    config: Config
    notes: dict = field(default_factory=dict)   # what a pipeline wants kept with the run's record (squeeze, words per section, flags, attempts)
