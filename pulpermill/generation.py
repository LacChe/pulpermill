"""The only way anything talks to the model: one streamed generation, and the structured (JSON) call with retry used by the card stages."""
import json
import re
import time

from . import config, runtime
from .runtime import log
from .schema import M


def llm_text(messages, label="generation", progress=None, **kw):
    """
    One streamed generation, the only way anything here talks to the model. Returns (text, finish_reason).
    The stop flag is checked after every piece, so Stop takes effect within about a token; the one thing that cannot be
    interrupted is the model reading a long prompt before its first token. Also logs how long that took and how fast it wrote.
    `progress(text_so_far)` is called now and then.
    """
    if runtime.stop_requested():
        raise runtime.Cancelled()
    kw = {**runtime.seed_kw(), **kw}                  # an explicit seed (a retry's) wins over the job's
    parts, finish, pieces = [], None, 0
    t0 = time.time()
    t_first = None
    with runtime.LLM_LOCK:
        stream = runtime.llm.create_chat_completion(messages=messages, stream=True, **kw)
        try:
            for chunk in stream:
                if t_first is None:
                    t_first = time.time()
                choice = chunk["choices"][0]
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    parts.append(piece)
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
                pieces += 1
                if progress and pieces % 20 == 0:
                    progress("".join(parts))
                if pieces % 20 == 0:
                    runtime.report(tokens=pieces)
                if runtime.stop_requested():
                    raise runtime.Cancelled()
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
    runtime.report(tokens=pieces)
    now = time.time()
    read = (t_first or now) - t0
    wrote = max(now - (t_first or t0), 1e-6)
    log.info("%s: read the prompt in %.1fs, wrote ~%d tokens in %.1fs (%.1f tokens/s), finished: %s",
             label, read, pieces, wrote, pieces / wrote, finish)
    return "".join(parts), finish



def extract_json(text: str):
    """Pull the first JSON object out of a model reply (handles code fences and chatter)."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start < 0:
        raise ValueError(M("no JSON object found in the reply"))
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def strip_markdown(v):
    """Asterisks leak into prose fields; remove them before anything is shown."""
    if isinstance(v, str):
        return v.replace("*", "")
    if isinstance(v, list):
        return [strip_markdown(x) for x in v]
    if isinstance(v, dict):
        return {k: strip_markdown(x) for k, x in v.items()}
    return v


def structured_call(prompt: str, model_cls, max_tokens: int = 2000, temperature: float | None = None, post=None,
                    min_tokens: int = 1000, tweak=None):
    """Ask for JSON matching model_cls. `post` (e.g. an id resolver) runs inside the retry loop, so its errors are retried too."""
    if temperature is None:
        temperature = config.GEN_TEMP                    # read when called, so a changed setting applies
    need = len(runtime.llm.tokenize(prompt.encode("utf-8")))
    room = config.N_CTX - need - config.RETRY_RESERVE                  # what is left for the answer
    if room < min_tokens:
        raise ValueError(M("too much input: the prompt is about {need} tokens and the answer needs at least {least}, "
                           "but the model holds {ctx}. Shorten the notes or the example chapter.", need=need, least=min_tokens, ctx=config.N_CTX))
    max_tokens = min(max_tokens, room)                   # short inputs get the full answer budget
    schema = model_cls.model_json_schema()
    if tweak:
        tweak(schema)
    with runtime.LLM_LOCK:             # every generation starts from an empty context, nothing carries over from earlier runs
        runtime.llm.reset()
    ask, last_err = prompt, None
    for attempt in range(config.MAX_RETRIES + 1):
        grammar = config.GRAMMAR_MODE != "never" and runtime.GRAMMAR_OK[0] and (config.GRAMMAR_MODE == "always" or attempt > 0)
        # a repeat penalty would punish the quotes, commas and keys that JSON has to repeat, so the free attempt has none
        kw = dict(temperature=temperature, top_p=0.95, top_k=64, repeat_penalty=1.05 if grammar else 1.0, max_tokens=max_tokens,
                  **runtime.seed_kw(attempt))
        msgs = [{"role": "user", "content": ask}]
        runtime.report(attempt=attempt + 1, tokens=0, max_tokens=max_tokens)
        tag = f"{model_cls.__name__} (attempt {attempt + 1}, {'with' if grammar else 'no'} grammar)"
        text = None
        if grammar:
            try:                                         # the grammar guarantees valid JSON with every field
                text, _ = llm_text(msgs, tag, response_format={"type": "json_object", "schema": schema}, **kw)
            except runtime.Cancelled:
                raise
            except Exception as e:
                log.warning("grammar-constrained generation failed (%s); using plain generation from now on", str(e)[:200])
                runtime.GRAMMAR_OK[0] = False
        if text is None:
            text, _ = llm_text(msgs, tag, **kw)
        try:
            result = model_cls.model_validate(strip_markdown(extract_json(text)))
            return post(result) if post else result
        except runtime.Cancelled:
            raise
        except Exception as e:                       # bad JSON or failed validation
            last_err = e
            log.warning("attempt %d failed: %s", attempt + 1, str(e)[:300])
            ask = (prompt + "\n\nYour previous reply could not be used:\n" + str(e)[:800]
                   + "\nReply again with one corrected JSON object and nothing else.")
    raise ValueError(M("the model could not produce valid output after {n} tries: {why}", n=config.MAX_RETRIES + 1, why=str(last_err)[:300]))