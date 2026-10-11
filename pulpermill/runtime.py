"""Shared mutable state: the model slot, the generation lock, the running job's stop flag and report hook, the loggers.

The model is read as `runtime.llm` every time it is used, never copied with `from .runtime import llm`: a copy made at import
time would be None forever. The lock, the loggers, CURRENT, CANCEL and Cancelled are created once and never rebound, so importing
them by name is fine.
"""
import logging
import sys
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("cardgen")

# schema logs through this logger, so it gets its own stdout handler (Kaggle shows stdout reliably)
logger = logging.getLogger("pulpmill")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.propagate = False

llm = None                       # set by model.load_model()
LLM_LOCK = threading.Lock()      # llama.cpp handles one generation at a time


class Cancelled(Exception):
    """The user pressed Stop. Raised out of the model call, caught where the job ends. Never swallow it."""


CURRENT = threading.local()      # the running job's stop flag lives here, so no function has to pass it along
CANCEL = {}                      # job id -> threading.Event
GRAMMAR_OFF = {}                # schema name -> why the JSON grammar cannot be built for it; such a card is written without the grammar from then on


def stop_requested() -> bool:
    ev = getattr(CURRENT, "cancel", None)
    return ev is not None and ev.is_set()


def report(**fields):
    """Tell the page how a card job is going (which try, how many tokens so far). Chapter jobs report their own steps."""
    r = getattr(CURRENT, "report", None)
    if r:
        r(**fields)


def seed_kw(offset=0) -> dict:
    """The running job's seed as a keyword for the model call. `offset` varies it between retries: the same seed with the
    same prompt would give the same unusable answer again."""
    s = getattr(CURRENT, "seed", None)
    return {} if s is None else {"seed": (s + offset) % 2**31}
