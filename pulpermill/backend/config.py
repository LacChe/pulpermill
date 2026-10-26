"""Everything the server and engine are set by, in one place. The notebook builds a Config and passes it in; nothing
else reads the environment.

SAMPLING: the numbers below are the previous version's (its CHAPTER_GEN and EXTRACT_GEN) and are only a starting point.
The writer supplies the real sampling and model parameters; change them here and nowhere else. One set per kind of call
(free prose, free thinking, constrained JSON). Recorded with every run so results can be compared.

MODEL: the previous version ran the Q4_K_M quant at n_ctx 16384; this one is planned for the 6-bit quant (about 22 GB).
n_ctx must equal pulpermill/prompts/budgets.yaml (the prompts are sized to it); the launcher refuses to start if they differ,
so a measured change is made in both places on purpose."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Sampling:
    temperature: float = 1.0        # mlabonne's recommended value for this abliterated model
    top_p: float = 0.95
    top_k: int = 64
    min_p: float = 0.0
    repeat_penalty: float = 1.05    # kept gentle: Gemma's space-in-token vocabulary fuses words under a stronger one
    frequency_penalty: float = 0.05
    seed: int | None = None

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ModelSettings:
    repo: str = "bartowski/mlabonne_gemma-3-27b-it-abliterated-GGUF"
    file: str = "mlabonne_gemma-3-27b-it-abliterated-Q6_K.gguf"     # CHECK the exact file name on the repo page
    directory: str = "/kaggle/temp/models"  # scratch disk: much roomier than /kaggle/working (about 20 GB, saved with the notebook); gone when the session ends
    search_dirs: tuple[str, ...] = ("/kaggle/input",)   # looked through first for a file of this name, so a dataset that holds the model is used as it is (no download, no disk used)
    n_ctx: int = 12288                      # must equal budgets.yaml n_ctx
    n_batch: int = 256                      # also the size of one prefill step, so Stop can land between steps
    tensor_split: tuple[float, ...] = (0.58, 0.42)     # from the previous version; re-tune at M2 with the 6-bit file
    flash_attn: bool = True                 # the loader retries without it if this build rejects it
    swa_full: bool = False                  # False: Gemma 3's sliding-window layers keep only their window, which saves several GB; True made the 6-bit file not fit
    kv_cache_type: str | None = None        # None = f16. "q8_0" halves the cache but needs flash_attn; decide at M2
    n_threads: int | None = None
    min_free_vram_mb: int = 400             # per GPU, after loading: less than this and the launcher stops with a plain message
    download_tries: int = 4                 # a partly downloaded file is resumed, not started over
    download_backoff_seconds: float = 10    # doubles each time
    disk_headroom_bytes: int = 10**9
    size_fallback_bytes: int = 23 * 10**9   # the file's size for the disk check when the hub does not say


@dataclass(frozen=True)
class Config:
    token: str | None = None                # the shared secret; None or "" means the server asks for none
    host: str = "127.0.0.1"
    port: int = 8000
    poll_interval: float = 0.1              # how often a running call looks for a client that went away (seconds)
    prompt_version_note: str = ""           # free text recorded in the run log's first line
    log_path: str | None = None            # one JSON line per call (runlog.py); None = keep in memory only. The launcher sets it.
    max_body_bytes: int = 4_000_000         # a request larger than this is bad_request; the biggest real project is far below it
    model: ModelSettings = field(default_factory=ModelSettings)
    prose: Sampling = field(default_factory=Sampling)          # the writer pass
    thinking: Sampling = field(default_factory=Sampling)       # the planner's first pass
    constrain: str = "always"               # "always": every JSON call is grammar-constrained. "repair": the first attempt is
                                            # free (about twice as fast, measured on the old setup) and only the retry is constrained.
    # Chinese writes a name or a term as one or two single-character tokens, so a repeat penalty works against the words a story
    # has to repeat, and a hot sampler picks look-alike characters (the old setup produced 张期 for 张强). The previous version's
    # values for the writer pass; a starting point, tune by looking at a chapter. Used for `language == "zh"` only.
    prose_zh: Sampling = field(default_factory=lambda: Sampling(temperature=0.8, top_p=0.9, top_k=40, repeat_penalty=1.0, frequency_penalty=0.0))
    structured: Sampling = field(default_factory=lambda: Sampling(temperature=0.2, repeat_penalty=1.0, frequency_penalty=0.0))   # constrained JSON

    def prose_for(self, language: str | None) -> Sampling:
        """The writer pass's sampling for the story's language: Chinese has its own set, every other language uses `prose`."""
        return self.prose_zh if language == "zh" else self.prose

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        token = os.environ.get("PULPERMILL_TOKEN") or None
        return cls(token=token, **overrides)

    def describe(self) -> str:
        """A line safe to log: says whether a token is set, never what it is."""
        return f"host={self.host} port={self.port} token={'set' if self.token else 'none'}"
