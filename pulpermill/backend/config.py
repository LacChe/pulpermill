"""Everything the server and engine are set by, in one place. The notebook builds a Config and passes it in; nothing
else reads the environment.

SAMPLING IS A PLACEHOLDER. The writer supplies the real sampling and model parameters; until then these are neutral
defaults, one set per kind of call (free prose, free thinking, constrained JSON). Change them here and nowhere else."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Sampling:
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 40
    min_p: float = 0.05
    repeat_penalty: float = 1.0
    seed: int | None = None


@dataclass(frozen=True)
class Config:
    token: str | None = None                # the shared secret; None or "" means the server asks for none
    host: str = "127.0.0.1"
    port: int = 8000
    poll_interval: float = 0.1              # how often a running call looks for a client that went away (seconds)
    prompt_version_note: str = ""           # free text recorded with run records (M6)
    prose: Sampling = field(default_factory=Sampling)          # the writer pass
    thinking: Sampling = field(default_factory=Sampling)       # the planner's first pass
    structured: Sampling = field(default_factory=lambda: Sampling(temperature=0.3))   # constrained JSON

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        token = os.environ.get("PULPERMILL_TOKEN") or None
        return cls(token=token, **overrides)

    def describe(self) -> str:
        """A line safe to log: says whether a token is set, never what it is."""
        return f"host={self.host} port={self.port} token={'set' if self.token else 'none'}"
