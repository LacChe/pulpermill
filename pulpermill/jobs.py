"""The job table and the worker threads. A job is one background generation; the page starts it and polls it. Request models are in server.py; they appear here only in annotations."""
from __future__ import annotations

import random
import threading
import time
import uuid
from typing import TYPE_CHECKING, Optional

from . import config, runtime
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


STUCK_MSG = "The model has not responded for {minutes} minutes and cannot be stopped from here. Restart the notebook session, then run its cells again."
STUCK = {}                       # job id -> when the watchdog took it for stuck (its thread is still inside the hung model call)
_LAST_PROGRESS = {}              # job id -> when it last reported anything


def _fail(e):
    """The job record for an exception: the English text, plus the translatable message when the error carries one."""
    m = e.args[0] if e.args and isinstance(e.args[0], Msg) else None
    text = str(m) if m is not None else (str(e) if isinstance(e, (ValueError, NotBuilt)) else f"{type(e).__name__}: {e}")
    return {"status": "error", "error": text, "error_msg": to_json(m) if m is not None else None}


def _busy() -> bool:
    with JOBS_LOCK:
        return bool(STUCK) or any(j.get("status") == "running" for j in JOBS.values())


def busy_message():
    """Why a new job is refused: another one is running, or the model is stuck and only a restart helps."""
    with JOBS_LOCK:
        stuck = bool(STUCK)
    return M(STUCK_MSG, minutes=max(1, int(config.JOB_STALL_SECONDS // 60))) if stuck else BUSY_MSG


def stuck_job():
    """{"job", "minutes"} of a job the watchdog found stuck, or None."""
    with JOBS_LOCK:
        jid = next(iter(STUCK), None)
    return None if jid is None else {"job": jid, "minutes": max(1, int(config.JOB_STALL_SECONDS // 60))}


def stuck_check(now=None):
    """The watchdog's look: a running job that has reported nothing for config.JOB_STALL_SECONDS is marked as failed with a message that
    says to restart. Nothing else can be done: the job's thread is inside a model call that does not return, holding the model, and
    a thread cannot be stopped from outside. New jobs are refused meanwhile (they would only queue behind the hung one). If the call does
    come back after all, _finish clears the mark."""
    now = time.time() if now is None else now
    with JOBS_LOCK:
        for jid, j in list(JOBS.items()):
            if j.get("status") != "running" or jid in STUCK:
                continue
            quiet = now - _LAST_PROGRESS.get(jid, j.get("started", now))
            if quiet > config.JOB_STALL_SECONDS:
                STUCK[jid] = now
                JOBS[jid] = {"kind": j.get("kind"), "stuck": True, **_fail(ValueError(M(STUCK_MSG, minutes=max(1, int(quiet // 60)))))}
                log.error("job %s (%s) has reported nothing for %d s: the model call looks hung and cannot be stopped from here. "
                          "New jobs are refused until the session is restarted.", jid, j.get("kind"), quiet)


_WATCHDOG = None


def start_watchdog():
    """Starts the thread that runs stuck_check every config.WATCHDOG_EVERY_SECONDS. Safe to call again."""
    global _WATCHDOG
    if _WATCHDOG is not None and _WATCHDOG.is_alive():
        return

    def loop():
        while True:
            time.sleep(config.WATCHDOG_EVERY_SECONDS)
            try:
                stuck_check()
            except Exception:
                log.exception("watchdog check failed")

    _WATCHDOG = threading.Thread(target=loop, daemon=True, name="pulpermill-watchdog")
    _WATCHDOG.start()


def running_job():
    """{"kind", "seconds"} of the job that is running now, or None."""
    with JOBS_LOCK:
        for j in JOBS.values():
            if j.get("status") == "running":
                return {"kind": j.get("kind"), "seconds": int(time.time() - j.get("started", time.time()))}
    return None


def _start_job(kind: str, **fields) -> Optional[str]:
    """Registers a new running job and returns its id, or returns None if one is already running. The check and the
    registration are one step under the lock, so two requests arriving together cannot both start. Room is made by
    dropping the oldest FINISHED results; a running job is never dropped."""
    with JOBS_LOCK:
        if STUCK or any(j.get("status") == "running" for j in JOBS.values()):
            return None
        for old in list(JOBS):
            if len(JOBS) < MAX_JOBS:
                break
            if JOBS[old].get("status") != "running":
                JOBS.pop(old)
                CANCEL.pop(old, None)
                _LAST_PROGRESS.pop(old, None)
        jid = uuid.uuid4().hex[:8]
        while jid in JOBS:
            jid = uuid.uuid4().hex[:8]
        JOBS[jid] = {"status": "running", "kind": kind, "started": time.time(), **fields}
        _LAST_PROGRESS[jid] = time.time()
        CANCEL[jid] = threading.Event()
        return jid


def _finish(jid: str, record: dict):
    """Replaces a job's record with its final one (done, error or cancelled)."""
    with JOBS_LOCK:
        JOBS[jid] = record
        _LAST_PROGRESS.pop(jid, None)
        if STUCK.pop(jid, None) is not None:
            log.warning("job %s came back after all (it had been taken for stuck); new jobs are accepted again", jid)


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
                _LAST_PROGRESS[jid] = time.time()
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
