"""Shared mutable state: the model slot, the generation lock, the running job's stop flag and report hook, the loggers.

The model is read as `runtime.llm` every time it is used, never copied with `from .runtime import llm`: a copy made at import
time would be None forever. The lock, the loggers, CURRENT, CANCEL and Cancelled are created once and never rebound, so importing
them by name is fine.
"""
import logging
import logging.handlers
import sys
import threading

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")      # for the libraries that log to the root logger


_FILE_PROBLEM_SHOWN = False


def _own_logger(name, fmt):
    """A logger that writes to stdout (Kaggle shows stdout reliably, stderr from a background thread not always), and also to
    config.LOG_FILE when that is set. It does not pass its messages on to the root logger, so nothing is printed twice."""
    lg = logging.getLogger(name)
    lg.setLevel(logging.INFO)
    if not lg.handlers:
        handlers = [logging.StreamHandler(sys.stdout)]
        if config.LOG_FILE:
            try:
                handlers.append(logging.handlers.RotatingFileHandler(config.LOG_FILE, maxBytes=10**6, backupCount=1, encoding="utf-8"))
            except OSError as e:
                global _FILE_PROBLEM_SHOWN
                if not _FILE_PROBLEM_SHOWN:             # both loggers hit the same problem: say it once
                    _FILE_PROBLEM_SHOWN = True
                    print(f"could not open the log file {config.LOG_FILE} ({e}); logging to the screen only", file=sys.stdout)
        for h in handlers:
            h.setFormatter(logging.Formatter(fmt))
            lg.addHandler(h)
        lg.propagate = False
    return lg


log = _own_logger("cardgen", "%(asctime)s %(levelname)s %(message)s")
logger = _own_logger("pulpmill", "%(levelname)s %(name)s: %(message)s")      # schema logs through this one

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
