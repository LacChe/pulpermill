"""The job table and the worker threads. A job is one background generation; the page starts it and polls it. Request models are in server.py; they appear here only in annotations."""
from __future__ import annotations

import random
import threading
import time
import uuid
from typing import TYPE_CHECKING, Optional

from . import runtime
from .runtime import CANCEL, CURRENT, Cancelled, LLM_LOCK, log
from .chapter import run_chapter
from .stages import NotBuilt, STAGES
from .schema import M, Msg, to_json

if TYPE_CHECKING:       # annotations only (request models live in server, which imports this module)
    from .server import ChapterRequest, GenRequest


JOBS = {}


JOBS_LOCK = threading.RLock()    # request threads and job threads both touch JOBS and CANCEL; every access goes through this lock


MAX_JOBS = 20                    # finished results kept; old ones are dropped, a running job never is


BUSY_MSG = M("Another generation is still running on the backend. Wait for it to finish, then try again.")


def _fail(e):
    """The job record for an exception: the English text, plus the translatable message when the error carries one."""
    m = e.args[0] if e.args and isinstance(e.args[0], Msg) else None
    text = str(m) if m is not None else (str(e) if isinstance(e, (ValueError, NotBuilt)) else f"{type(e).__name__}: {e}")
    return {"status": "error", "error": text, "error_msg": to_json(m) if m is not None else None}


def _busy() -> bool:
    with JOBS_LOCK:
        return any(j.get("status") == "running" for j in JOBS.values())


def _start_job(kind: str, **fields) -> Optional[str]:
    """Registers a new running job and returns its id, or returns None if one is already running. The check and the
    registration are one step under the lock, so two requests arriving together cannot both start. Room is made by
    dropping the oldest FINISHED results; a running job is never dropped."""
    with JOBS_LOCK:
        if any(j.get("status") == "running" for j in JOBS.values()):
            return None
        for old in list(JOBS):
            if len(JOBS) < MAX_JOBS:
                break
            if JOBS[old].get("status") != "running":
                JOBS.pop(old)
                CANCEL.pop(old, None)
        jid = uuid.uuid4().hex[:8]
        while jid in JOBS:
            jid = uuid.uuid4().hex[:8]
        JOBS[jid] = {"status": "running", "kind": kind, "started": time.time(), **fields}
        CANCEL[jid] = threading.Event()
        return jid


def _finish(jid: str, record: dict):
    """Replaces a job's record with its final one (done, error or cancelled)."""
    with JOBS_LOCK:
        JOBS[jid] = record


def _cancel_event(jid: str):
    with JOBS_LOCK:
        return CANCEL.get(jid)


def _release(jid: str):
    with JOBS_LOCK:
        CANCEL.pop(jid, None)


def _stopped(jid: str):
    """Runs on the job's own thread once the model has actually stopped, so 'cancelled' means the backend is ready again."""
    try:
        with LLM_LOCK:
            runtime.llm.reset()
    except Exception:
        log.exception("model reset after a stop failed; the next job may be affected")
    _finish(jid, {"status": "cancelled"})
    log.info("job %s stopped by the user", jid)


def _progress(jid: str):
    def update(**fields):
        with JOBS_LOCK:
            job_ = JOBS.get(jid)
            if job_ is not None and job_.get("status") == "running":
                job_.update(fields)
    return update


def _pick_seed(requested) -> int:
    return random.randrange(2**31) if requested is None else int(requested) % 2**31


def _work(jid: str, req: GenRequest):
    t0 = time.time()
    CURRENT.cancel = _cancel_event(jid)
    CURRENT.seed = seed = _pick_seed(req.seed)
    CURRENT.report = _progress(jid)           # a card is one model call (or a few retries): the page's bar follows its tokens
    try:
        if req.stage not in STAGES:
            raise NotBuilt(M("unknown stage '{stage}'", stage=req.stage))
        out = STAGES[req.stage](req)
        extra = out[2] if len(out) > 2 else {}
        _finish(jid, to_json({"status": "done", "kind": "card", "card": out[0], "warnings": out[1], "seed": seed, **extra}))
        log.info("stage %s done in %.1fs, %d warning(s)", req.stage, time.time() - t0, len(out[1]))
    except Cancelled:
        _stopped(jid)
    except NotBuilt as e:
        _finish(jid, _fail(e))
    except Exception as e:
        log.exception("stage %s failed", req.stage)
        _finish(jid, _fail(e))
    finally:
        CURRENT.cancel = None
        CURRENT.seed = None
        CURRENT.report = None
        _release(jid)


def _work_chapter(jid: str, req: ChapterRequest):
    t0 = time.time()
    CURRENT.cancel = _cancel_event(jid)
    CURRENT.seed = seed = _pick_seed(req.seed)
    CURRENT.report = _progress(jid)           # the steps after the chapter text report their tokens too, so the bar can follow them
    try:
        result = run_chapter(req, _progress(jid))
        _finish(jid, to_json({"status": "done", "kind": "chapter", "seed": seed, **result}))
        log.info("chapter %d done in %.1fs, %d change(s), %d warning(s)", req.chapter_num, time.time() - t0,
                 len(result["changes"]), len(result["warnings"]))
    except Cancelled:
        _stopped(jid)
    except ValueError as e:                       # a problem with the request itself (cards, summaries, size)
        log.warning("chapter %d refused: %s", req.chapter_num, e)
        _finish(jid, _fail(e))
    except Exception as e:
        log.exception("chapter %d failed", req.chapter_num)
        _finish(jid, _fail(e))
    finally:
        CURRENT.cancel = None
        CURRENT.seed = None
        CURRENT.report = None
        _release(jid)
