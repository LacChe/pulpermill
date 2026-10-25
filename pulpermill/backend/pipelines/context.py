from dataclasses import dataclass
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
