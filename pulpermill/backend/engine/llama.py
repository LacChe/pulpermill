"""The real engine, over llama-cpp-python. Everything that touches the library goes through `llm` (a Llama object) and
`grammar_factory`, so the logic here is tested with a stand-in and only the loading needs the real library.

How a call runs:
  1. The user turn is wrapped in Gemma's chat template (pulpermill.prompts.tokens.chat_text) and tokenized ONCE with
     add_bos=True, special=True. The template text carries no <bos> of its own, so there is exactly one.
  2. Prefill is done by hand, one n_batch-sized step at a time, so Stop can land between steps. All but the last
     token is evaluated; llama-cpp-python's own prefix reuse then finds nothing left to do except the last token.
  3. Generation streams; the cancel flag is looked at before every token. Cancelling closes the stream.
  4. Each call records what the run log needs in `last_run`: tokens, prefill and generation seconds, why it stopped.
"""
import json
import logging
import time
from typing import Any, Callable

from pulpermill.prompts import tokens as gemma

from ..config import ModelSettings, Sampling
from ..errors import Cancelled
from .base import CancelFlag, Engine
from .gpu import check_memory, free_vram_mb

log = logging.getLogger("pulpermill")

STOP = ["<end_of_turn>"]


class LlamaEngine(Engine):
    def __init__(self, llm, settings: ModelSettings, *, grammar_factory: Callable[[str], Any] | None = None,
                 model_name: str = ""):
        self.llm = llm
        self.settings = settings
        self.model_name = model_name or settings.file
        self._grammar_factory = grammar_factory or _default_grammar
        self.last_run: dict[str, Any] = {}

    # -- tokens -------------------------------------------------------------------------------------------------
    def _ids(self, user_text: str) -> list[int]:
        return list(self.llm.tokenize(gemma.chat_text(user_text).encode("utf-8"), add_bos=True, special=True))

    def count_tokens(self, text: str) -> int:
        """Tokens the model would see for this user turn: <bos> + the chat template. Must equal tokens.chat_tokens(text)."""
        return len(self._ids(text))

    # -- generation ---------------------------------------------------------------------------------------------
    def generate(self, prompt: str, max_tokens: int, *, constraint: dict[str, Any] | None = None,
                 on_token: Callable[[str], None] | None = None, cancel: CancelFlag | None = None,
                 params: Sampling | None = None) -> str:
        params = params or Sampling()
        ids = self._ids(prompt)
        if len(ids) + max_tokens > self.settings.n_ctx:
            raise ValueError(f"{len(ids)} prompt tokens + {max_tokens} reply tokens do not fit n_ctx {self.settings.n_ctx}")
        grammar = self._grammar_factory(json.dumps(constraint)) if constraint is not None else None
        run: dict[str, Any] = {"prompt_tokens": len(ids), "output_tokens": 0, "prefill_s": 0.0, "generation_s": 0.0,
                               "constrained": constraint is not None, "stop": None, "sampling": params.as_dict()}
        self.last_run = run
        if cancel:
            cancel.raise_if_cancelled()
        # Prefill, by hand, so Stop is heard between steps.
        started = time.monotonic()
        self.llm.reset()
        step = max(1, self.settings.n_batch)
        body = ids[:-1]
        for at in range(0, len(body), step):
            if cancel:
                cancel.raise_if_cancelled()
            self.llm.eval(body[at:at + step])
        run["prefill_s"] = time.monotonic() - started
        # Generation.
        pieces: list[str] = []
        started = time.monotonic()
        stream = self.llm.create_completion(
            prompt=ids, max_tokens=max_tokens, stream=True, stop=STOP, grammar=grammar,
            temperature=params.temperature, top_p=params.top_p, top_k=params.top_k, min_p=params.min_p,
            repeat_penalty=params.repeat_penalty, frequency_penalty=params.frequency_penalty,
            **({"seed": params.seed} if params.seed is not None else {}))
        try:
            for chunk in stream:
                choice = chunk["choices"][0]
                text = choice.get("text") or ""
                if text:
                    pieces.append(text)
                    run["output_tokens"] += 1
                    if on_token:
                        on_token(text)
                if choice.get("finish_reason"):
                    run["stop"] = choice["finish_reason"]
                if cancel and cancel.cancelled:
                    run["stop"] = "cancelled"
                    raise Cancelled()
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
            run["generation_s"] = time.monotonic() - started
        run["truncated"] = run["stop"] == "length"
        return "".join(pieces)

    def info(self) -> dict[str, Any]:
        free = free_vram_mb()
        return {"model": self.model_name, "n_ctx": self.settings.n_ctx, "free_vram_mb": sum(free) if free else None}


def _default_grammar(schema_json: str):
    from llama_cpp import LlamaGrammar
    return LlamaGrammar.from_json_schema(schema_json)


_CACHE_TYPES = {"f16": "GGML_TYPE_F16", "q8_0": "GGML_TYPE_Q8_0", "q4_0": "GGML_TYPE_Q4_0"}


def load(settings: ModelSettings, model_path: str, *, llama_class=None) -> LlamaEngine:
    """Load the model across the GPUs and check memory. Logs the free VRAM before and after. Retries once without flash
    attention if this build of the library rejects it. Raises RuntimeError with a plain sentence if memory is too tight."""
    if llama_class is None:
        import llama_cpp
        llama_class = llama_cpp.Llama
        cache = {}
        if settings.kv_cache_type:
            kind = getattr(llama_cpp, _CACHE_TYPES[settings.kv_cache_type])
            cache = {"type_k": kind, "type_v": kind}
    else:
        cache = {}
    before = free_vram_mb()
    log.info("loading %s: n_ctx=%d n_batch=%d tensor_split=%s flash_attn=%s cache=%s free VRAM before=%s MB",
             settings.file, settings.n_ctx, settings.n_batch, list(settings.tensor_split), settings.flash_attn,
             settings.kv_cache_type or "f16", before)
    started = time.monotonic()
    options = dict(model_path=model_path, n_ctx=settings.n_ctx, n_batch=settings.n_batch, n_gpu_layers=-1,
                   tensor_split=list(settings.tensor_split), n_threads=settings.n_threads, verbose=False,
                   swa_full=settings.swa_full, **cache)
    llm, failure = None, None
    try:
        llm = llama_class(flash_attn=settings.flash_attn, **options)
    except Exception as error:
        failure = str(error)[:200]
    if llm is None:
        if not settings.flash_attn:
            raise RuntimeError(f"The model could not be loaded: {failure}")
        log.warning("loading with flash attention failed (%s); trying without it", failure)
        import gc
        gc.collect()        # the failed attempt may still hold the GPU's memory until it is collected
        try:
            llm = llama_class(flash_attn=False, **options)
        except Exception as error:
            raise RuntimeError(f"The model could not be loaded: {str(error)[:200]}. Free VRAM now: {free_vram_mb()} MB. "
                               f"First attempt: {failure}") from None
    after = free_vram_mb()
    log.info("model loaded in %.0f s; free VRAM after=%s MB", time.monotonic() - started, after)
    problem = check_memory(after, settings.min_free_vram_mb)
    if problem:
        raise RuntimeError(problem)
    return LlamaEngine(llm, settings)
