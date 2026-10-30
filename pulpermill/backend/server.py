"""The HTTP layer: one route, CORS, the token, the busy lock, status, Stop, and the mapping from failures to the
contract's error replies. Nothing here knows how a call is answered; that is pipelines.run.

Why it is built this way:
- The model call runs in its own thread, so the event loop is always free to answer `status` and to notice that the
  client went away (Stop). That is the property most likely to be broken by accident, so it has its own tests.
- The lock is taken before the thread starts and released by the thread itself as its very last step, whatever
  happened. `status` therefore says "idle" only after inference has really ended.
- A client that disconnects sets the cancel flag. The call then answers nothing the page can use and changes nothing."""
import asyncio
import hmac
import json
import logging
import threading
import time
from typing import Any, Callable

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from pulpermill import contract
from pulpermill.schema.project import SCHEMA_VERSION

from . import pipelines as default_pipelines
from . import runlog
from .config import Config
from .engine.base import CancelFlag, Engine
from .errors import BackendError, Cancelled
from .pipelines.context import RunContext

log = logging.getLogger("pulpermill")

CORS = {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "POST",
    "access-control-allow-headers": "content-type, ngrok-skip-browser-warning, x-pulpermill-token",
    "access-control-max-age": "600",
}
TOKEN_HEADER = "x-pulpermill-token"


def _fail(kind: str, detail: str = "") -> JSONResponse:
    return JSONResponse(contract.error_reply(kind, detail), status_code=contract.HTTP_STATUS[kind], headers=CORS)


def _short(error: ValidationError) -> str:
    """The first problem in plain words: where it is and what is wrong. Never the value, which may be the writer's text."""
    first = error.errors(include_input=False, include_url=False)[0]
    where = ".".join(str(part) for part in first.get("loc", ()))
    return f"{where}: {first.get('msg', 'invalid')}"[:300]


class Job:
    """Whether a model call is running, and what stage it says it is in. The only state the server keeps."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stage: str | None = None

    def try_begin(self) -> bool:
        return self._lock.acquire(blocking=False)

    def end(self) -> None:
        self._stage = None
        self._lock.release()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    @property
    def stage(self) -> str | None:
        return self._stage if self.busy else None

    def set_stage(self, stage: str | None) -> None:
        if stage is None or stage in contract.STAGES:
            self._stage = stage


class JobRecord:
    """One call that carried a job_id: its name, what it is doing, and (once it ends) its outcome, kept for the page to fetch."""

    def __init__(self, job_id: str, call: str, cancel: CancelFlag):
        self.id, self.call, self.cancel = job_id, call, cancel
        self.outcome: tuple[str, Any] | None = None       # ("ok", reply) or ("fail", (kind, detail)); None while running
        self.finished_at: float | None = None


class JobStore:
    """The calls the page named, newest last. Held in memory only: when the server restarts they are gone, and the page is
    told "unknown". At most `keep` finished calls are kept; a running one is never dropped."""

    def __init__(self, keep: int = 30):
        self._lock = threading.Lock()
        self._records: dict[str, JobRecord] = {}
        self.keep = keep

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._records.get(job_id)

    def add(self, record: JobRecord) -> None:
        with self._lock:
            self._records[record.id] = record

    def finish(self, record: JobRecord, outcome: tuple[str, Any]) -> None:
        with self._lock:
            record.outcome = outcome
            record.finished_at = time.time()
            finished = sorted((r for r in self._records.values() if r.outcome is not None), key=lambda r: r.finished_at)
            for old in finished[: max(len(finished) - self.keep, 0)]:
                del self._records[old.id]


def create_app(config: Config, engine: Engine, run: Callable[[Any, RunContext], dict] | None = None) -> Starlette:
    """`run(request_model, ctx) -> reply dict` answers one model call. It defaults to the pipelines package."""
    run = run or default_pipelines.run
    job = Job()
    jobs = JobStore(config.jobs_kept)
    runs = runlog.RunLog(config.log_path, config)

    def token_ok(request: Request) -> bool:
        if not config.token:
            return True
        given = request.headers.get(TOKEN_HEADER, "")
        return hmac.compare_digest(given.encode(), config.token.encode())

    def work(model, cancel: CancelFlag, loop, done: "asyncio.Future", record: JobRecord | None = None) -> None:
        """The model call, in a thread. Always ends by releasing the lock, then hands the outcome to the handler."""
        started = time.monotonic()
        started_at = time.time()
        outcome: tuple[str, Any]
        stages = runlog.Stages(job.set_stage)
        ctx = RunContext(engine=engine, cancel=cancel, set_stage=stages, config=config)
        try:
            reply = run(model, ctx)
            cancel.raise_if_cancelled()
            try:
                contract.parse_reply(model.call, reply)
            except ValidationError as error:
                log.error("call=%s reply failed the contract: %s", model.call, _short(error))
                raise BackendError("bad_output", "") from None
            outcome = ("ok", reply)
        except Cancelled:
            outcome = ("fail", ("stopped", ""))
        except BackendError as error:
            outcome = ("fail", (error.kind, error.detail))
        except Exception:
            log.exception("call=%s failed", model.call)
            outcome = ("fail", ("server", "The model's server hit an unexpected problem."))
        finally:
            seconds = time.monotonic() - started
            stages.close()
            result = "server"
            try:
                result = outcome[0] if outcome[0] == "ok" else outcome[1][0]
                log.info("call=%s done secs=%.2f result=%s retries=%s", model.call, seconds, result,
                         sum(max(len(p.get("attempts", [])) - 1, 0) for p in ctx.notes.get("passes", [])))
                runs.add(runlog.build(model.call, started_at, seconds, result, stages.done, ctx.notes))     # before the lock is released: idle means the record is written
                if runs.failed:
                    log.warning("the run log could not be written (%s); records are kept in memory only", runs.failed)
                    runs.path, runs.failed = None, None
            except Exception:
                log.exception("the run record for call=%s could not be written", model.call)
            finally:
                if record is not None:
                    jobs.finish(record, outcome)        # before the lock is released: idle means the answer can be fetched
                job.end()
        try:
            loop.call_soon_threadsafe(lambda: done.done() or done.set_result(outcome))
        except RuntimeError:
            pass    # the loop is gone (shutting down); nobody is waiting

    async def api(request: Request) -> Response:
        if request.method == "OPTIONS":
            return Response(status_code=204, headers=CORS)         # the preflight never carries the token
        if not token_ok(request):
            return _fail("unauthorized")
        raw = await request.body()
        if len(raw) > config.max_body_bytes:
            return _fail("bad_request", "The request is too large.")
        try:
            data = await asyncio.to_thread(_loads, raw)
            model = contract.parse_request(data)
        except ValueError:
            return _fail("bad_request", "The request was not JSON.")
        except ValidationError as error:
            return _fail("bad_request", _short(error))
        if model.call == "status":
            body: dict[str, Any] = {"ok": True, "state": "busy" if job.busy else "idle"}
            if job.stage:
                body["stage"] = job.stage
            return JSONResponse(body, headers=CORS)
        if model.call == "job":
            record = jobs.get(model.job_id)
            if record is None:
                return JSONResponse({"ok": True, "state": "unknown"}, headers=CORS)
            if record.outcome is None:
                body = {"ok": True, "state": "running"}
                if job.stage:
                    body["stage"] = job.stage
                return JSONResponse(body, headers=CORS)
            kind, value = record.outcome
            return JSONResponse(value, headers=CORS) if kind == "ok" else _fail(*value)
        if model.call == "cancel":
            record = jobs.get(model.job_id)
            if record is None or record.outcome is not None:
                return JSONResponse({"ok": True, "state": "unknown"}, headers=CORS)
            log.info("call=%s job=%s cancelled by the page", record.call, record.id)
            record.cancel.set()
            return JSONResponse({"ok": True, "state": "cancelled"}, headers=CORS)
        if model.schema_version > SCHEMA_VERSION:
            return _fail("bad_request", f"This server knows project files up to version {SCHEMA_VERSION}, not {model.schema_version}.")
        job_id = getattr(model, "job_id", None)
        if job_id and (known := jobs.get(job_id)) is not None:
            # The page sent this call again (it lost the answer). It is the same call: answer with where it stands.
            if known.outcome is None:
                return JSONResponse({"ok": True, "state": "running", **({"stage": job.stage} if job.stage else {})}, headers=CORS)
            kind, value = known.outcome
            return JSONResponse(value, headers=CORS) if kind == "ok" else _fail(*value)
        if not job.try_begin():
            return _fail("busy")
        cancel = CancelFlag()
        record = JobRecord(job_id, model.call, cancel) if job_id else None
        if record:
            jobs.add(record)
        loop = asyncio.get_running_loop()
        done: asyncio.Future = loop.create_future()
        threading.Thread(target=work, args=(model, cancel, loop, done, record), daemon=True, name=f"call-{model.call}").start()
        begun = loop.time()
        while not done.done():
            await asyncio.wait({done}, timeout=config.poll_interval)
            if not done.done() and await request.is_disconnected():
                if record:
                    # A named call outlives its connection: the page asks for the answer later (call "job").
                    log.info("call=%s job=%s client went away: the call goes on", model.call, job_id)
                    return Response(status_code=499, headers=CORS)
                if not cancel.cancelled:
                    log.info("call=%s client went away: cancelling", model.call)
                    cancel.set()
            if not done.done() and not cancel.cancelled and loop.time() - begun >= config.stream_after:
                return StreamingResponse(_stream(model.call, done, cancel, bool(record)), media_type="application/json", headers=CORS)
        kind, value = done.result()
        if kind == "ok" and not cancel.cancelled:
            return JSONResponse(value, headers=CORS)
        return _fail(*(value if kind == "fail" else ("stopped", "")))

    async def _stream(call: str, done: "asyncio.Future", cancel: CancelFlag, named: bool = False):
        """A slow call's answer: a blank at once (so the headers go out) and every `heartbeat` seconds, then the reply as the
        JSON body. A JSON parser ignores the leading blanks. The status is 200 whatever the outcome: the page reads the
        contract's `ok` and `error.kind` from the body, which are the same as the status would have said."""
        try:
            yield b" "
            while not done.done():
                await asyncio.wait({done}, timeout=config.heartbeat)
                if not done.done():
                    yield b" "
            kind, value = done.result()
            if kind == "ok" and not cancel.cancelled:
                body = value
            else:
                body = contract.error_reply(*(value if kind == "fail" else ("stopped", "")))
            yield json.dumps(body).encode()
        except (asyncio.CancelledError, GeneratorExit):
            if named:
                log.info("call=%s client went away: the call goes on", call)
            elif not cancel.cancelled:
                log.info("call=%s client went away: cancelling", call)
                cancel.set()
            raise

    app = Starlette(routes=[Route("/api", api, methods=["POST", "OPTIONS"])])
    app.state.runs = runs
    return app


def _loads(raw: bytes) -> Any:
    return json.loads(raw)
