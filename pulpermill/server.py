"""The FastAPI app: request models, the endpoints, and the job-and-poll pattern. CORS is open so the HTML file works when dragged into a browser (its origin is "null"). The request models are built from the MAX_REQUEST_* settings when this module is imported, so the launcher applies any override of those first."""

import json
import threading
import time
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AfterValidator, BaseModel, Field, StringConstraints
from typing import Annotated, Any, Optional

from . import config, generation, model, runtime, stages
from .runtime import CANCEL, logger
from .importer import import_cards
from .jobs import JOBS, JOBS_LOCK, _start_job, _work, _work_chapter, busy_message, running_job, start_watchdog, stuck_job
from .schema import (
    CastDraft, M, MAX_CAST, MAX_CHAPTERS, MAX_CHAPTER_NUM, MAX_CHARACTERS, OutlineDraft, RECENT_N, StyleCard,
    WorldDraft, to_json, ui_hints
)


def _small_json(v):
    if len(json.dumps(v, default=str, ensure_ascii=False, separators=(",", ":"))) > config.MAX_REQUEST_JSON:
        raise ValueError(f"too large (over {config.MAX_REQUEST_JSON:,} characters of JSON)")
    return v


Text = Annotated[str, StringConstraints(max_length=config.MAX_REQUEST_TEXT)]


ShortText = Annotated[str, StringConstraints(max_length=100)]           # names, ids, option words


CardsJson = Annotated[dict, AfterValidator(_small_json)]


AnyJson = Annotated[Any, AfterValidator(_small_json)]


app = FastAPI()
start_watchdog()                                         # looks for a hung model call every few seconds (see jobs.stuck_check)

generation.check_grammars(stages.GRAMMAR_CHECKS)         # once, when this module loads: which card schemas the JSON grammar can be built from


app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class GenRequest(BaseModel):
    stage: ShortText       # an unknown stage is answered by the job itself ("unknown stage"), not refused here
    mode: ShortText = "notes"
    notes: Text = ""       # this card's own freeform box only
    chapter: Text = ""     # the example chapter (chapter mode only: it is switched on for this card)
    chapter_use: ShortText = ""   # what the example is for: "sequel" or "parallel" (empty: the cards describe the example's own story)
    feedback: Optional[Text] = None
    cards: CardsJson = {}
    seed: Optional[int] = None   # model seed; none means a new random one (which is reported back)
    language: ShortText = "en"   # what the card text is written in; a key of LANGUAGES
    chapters: Optional[int] = Field(None, ge=1, le=MAX_CHAPTER_NUM)   # outline only: exact chapter count; when absent a count stated in the notes ("Three chapters") is used


class ChapterRequest(BaseModel):
    chapter_num: int = Field(ge=1, le=MAX_CHAPTER_NUM)   # a number past the story's own length gets a readable message later
    cards: CardsJson                  # {style, characters, world, outline}: the cards as they stand BEFORE this chapter
    summaries: list[Text] = Field(default=[], max_length=MAX_CHAPTER_NUM)   # summaries of chapters 1..n-1, in order
    prev_text: Text = ""              # full text of chapter n-1 (empty for chapter 1)
    target_words: int = Field(config.DEFAULT_TARGET_WORDS, ge=50, le=200_000)   # a target too big for the context gets a readable message later
    note: Optional[Text] = None       # what the author wants changed when this is a rewrite with a note
    seed: Optional[int] = None        # model seed; none means a new random one (which is reported back)
    language: ShortText = "en"      # what the chapter (and the summary and card notes) is written in; a key of LANGUAGES
    cast: list[ShortText] = Field(default=[], max_length=50)              # ids of the characters this chapter is written about (the main character is always added); empty: the beat's own cast


_STARTED = time.time()
_LAST_PROBE = {"at": 0.0, "state": "skipped", "detail": "not asked yet"}


@app.get("/health")
def health():
    """Whether the backend can actually write: is a model loaded, is a job running, does the idle model still answer. 200 when it can,
    503 when it cannot (no model, or the model fails its probe), so a connection test shows the problem. The probe asks for one
    token, at most every config.HEALTH_PROBE_EVERY_SECONDS, and only when no job is running."""
    loaded = runtime.llm is not None
    job = running_job()
    if loaded and job is None and time.time() - _LAST_PROBE["at"] >= config.HEALTH_PROBE_EVERY_SECONDS:
        state, detail = model.probe()
        if state != "skipped":
            _LAST_PROBE.update(at=time.time(), state=state, detail=detail)
    probe = _LAST_PROBE if loaded and _LAST_PROBE["state"] != "skipped" else None
    stuck = stuck_job()
    ok = loaded and stuck is None and not (probe and probe["state"] == "failed")
    body = {"ok": ok}
    if not loaded:                                  # the reason comes first: the page shows only the start of an error answer
        body["why"] = NOT_LOADED
    elif stuck:
        body["why"] = f"the model has not responded for {stuck['minutes']} minutes and cannot be stopped from here: restart the session"
    elif not ok:
        body["why"] = "the model failed a one-token test (" + probe["detail"] + "): restart the session"
    body.update(model=config.MODEL_FILE, model_loaded=loaded, busy=job is not None, job=job, stuck=stuck, uptime_s=int(time.time() - _STARTED),
                gpu=model.gpu_report())
    if probe:
        body["probe"] = {"state": probe["state"], "detail": probe["detail"], "seconds_ago": int(time.time() - probe["at"])}
    return JSONResponse(body, status_code=200 if ok else 503)


@app.post("/generate")
def generate(req: GenRequest):
    """Starts a background job and returns at once. Long generations never hold a connection open; the page polls /job/<id>."""
    jid = _start_job("card")
    if jid is None:
        msg = busy_message()
        return {"error": str(msg), "error_msg": to_json(msg)}
    threading.Thread(target=_work, args=(jid, req), daemon=True).start()
    return {"job": jid}


@app.post("/chapter")
def chapter(req: ChapterRequest):
    """Writes one chapter from the cards, summaries and previous text the page sends, and returns the chapter, its
    summary, the updated cards and a readable list of what changed. Same job-and-poll pattern as /generate."""
    jid = _start_job("chapter", chapter_num=req.chapter_num, step="starting", words=0, target_words=req.target_words)
    if jid is None:
        msg = busy_message()
        return {"error": str(msg), "error_msg": to_json(msg)}
    threading.Thread(target=_work_chapter, args=(jid, req), daemon=True).start()
    return {"job": jid}


@app.post("/cancel/{jid}")
def cancel(jid: str):
    """Asks a running job to stop. The job's status becomes 'cancelled' only after the model has really stopped, so the page
    can keep its buttons locked until the backend is ready for the next job. Reading a long prompt cannot be interrupted;
    the stop lands as soon as the first new token arrives."""
    with JOBS_LOCK:
        j = JOBS.get(jid)
        if j is None:
            return {"ok": False, "status": "unknown"}
        if j.get("status") != "running":
            return {"ok": False, "status": j.get("status")}
        ev = CANCEL.get(jid)
        if ev is not None:
            ev.set()
        j["stopping"] = True
        return {"ok": True}


@app.get("/job/{jid}")
def job(jid: str):
    gone = M("unknown job (did the notebook restart?)")
    with JOBS_LOCK:
        j = JOBS.get(jid)
        snapshot = dict(j) if j else None          # a copy: the job thread may update the record while it is being sent
    return snapshot or {"status": "error", "error": str(gone), "error_msg": to_json(gone)}


@app.get("/schema")
def schema_hints():
    """What the page's editor needs, read from schema.py so the page keeps no copy of it."""
    return ui_hints()


CARD_SCHEMAS = {"style": StyleCard, "characters": CastDraft, "world": WorldDraft, "outline": OutlineDraft}
NOT_LOADED = "the model is not loaded yet: run the cell that loads it"
_FIXED_TOKENS = {}                       # card -> tokens of its schema as the model counts them; fixed for the session, so counted once


def _fixed_tokens():
    """The schema token counts, counted on first use, with the model not generating (the lock keeps the tokenizer off the model while
    a generation runs). None when a generation holds the model for longer than config.LIMITS_LOCK_WAIT_SECONDS."""
    if not _FIXED_TOKENS:
        if not runtime.LLM_LOCK.acquire(timeout=config.LIMITS_LOCK_WAIT_SECONDS):
            return None
        try:
            for k, c in CARD_SCHEMAS.items():
                _FIXED_TOKENS[k] = len(runtime.llm.tokenize(json.dumps(c.model_json_schema()).encode("utf-8")))
        finally:
            runtime.LLM_LOCK.release()
    return _FIXED_TOKENS


if runtime.llm is not None:                  # the launcher loads the model first: counted here, once, before any request can arrive
    _fixed_tokens()


@app.get("/limits")
def limits():
    """Sizes the page needs to show how much text each card can take."""
    if runtime.llm is None:
        return JSONResponse({"error": NOT_LOADED}, status_code=503)
    fixed = _fixed_tokens()
    if fixed is None:
        return JSONResponse({"error": "The model is busy with a generation right now. Try again in a moment."}, status_code=503)
    return {"n_ctx": config.N_CTX, "chars_per_token": config.CHARS_PER_TOKEN, "retry_reserve": config.RETRY_RESERVE,
            "max_characters": MAX_CHARACTERS, "max_cast": MAX_CAST, "max_chapters": MAX_CHAPTERS, "recent_n": RECENT_N,
            "default_words": config.DEFAULT_TARGET_WORDS, "languages": list(config.LANGUAGES),
            "max_import_json": config.MAX_REQUEST_JSON, "max_import_files": config.MAX_IMPORT_FILES,
            "stages": {k: {"out": config.MIN_TOKENS[k], "fixed": fixed[k] + config.INSTRUCTION_TOKENS} for k in CARD_SCHEMAS}}


class ImportItem(BaseModel):
    name: Annotated[str, StringConstraints(max_length=300)] = ""
    data: AnyJson = None


class ImportRequest(BaseModel):
    items: list[ImportItem] = Field(default=[], max_length=config.MAX_IMPORT_FILES)
    existing: CardsJson = {}


@app.post("/import")
def import_endpoint(req: ImportRequest):
    """Checks card files the page read against the schema. Needs no model, so it answers at once even mid-generation."""
    try:
        return to_json(import_cards([(i.name or "file", i.data) for i in req.items], req.existing))
    except Exception as e:                           # never a 500: the page shows this as a warning
        logger.exception("import failed")
        return to_json({"cards": {}, "imported": [], "warnings": [M("The import failed unexpectedly: {why}", why=f"{type(e).__name__}: {e}")], "checks": []})
