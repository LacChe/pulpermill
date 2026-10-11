"""The only way anything talks to the model: one streamed generation, and the structured (JSON) call with retry used by the card stages."""
import json
import re
import time

from . import config, runtime
from .runtime import log, logger
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



def log_bad_reply(label, text, finish, error):
    """Writes what the model actually said to the log when a reply could not be used (a long one is cut in the middle, so
    both its start and its end, where a cut-off shows, are kept). Logging only: nothing about the generation changes."""
    limit = max(config.BAD_REPLY_LOG_CHARS, 2)
    if len(text) > limit:
        half = limit // 2
        shown = f"{text[:half]}\n[... {len(text) - 2 * half} characters left out ...]\n{text[-half:]}"
    else:
        shown = text
    cause = "reply cut off at the token limit" if finish == "length" else "unusable reply"
    logger.warning("%s: %s (%d characters, finished: %s): %s\n--- reply ---\n%s\n--- end of reply ---",
                   label, cause, len(text), finish, str(error)[:300], shown)


_OBJECT_START = re.compile(r'\{\s*["}]')       # where a JSON object can begin: a brace followed by a key's quote (or by the closing brace)


def extract_json(text: str):
    """Pull the first JSON object out of a model reply (handles code fences and chatter). A brace that cannot start a JSON object
    (a "{card}" or "{as requested}" in the chatter before it) is skipped. The first brace that can start one is the object:
    if that one is broken or cut off, it is reported as such, never replaced by a smaller object found inside it."""
    text = re.sub(r"```(?:json)?", "", text)
    found = _OBJECT_START.search(text)
    if found is None:
        raise ValueError(M("no JSON object found in the reply"))
    obj, _ = json.JSONDecoder().raw_decode(text[found.start():])
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


def grammar_problem(schema):
    """Why the JSON grammar cannot be built from this schema, or None when it can. Needs no model: only the library's
    own converter, run on the schema. That tells a broken schema apart from a call that failed for another reason."""
    from llama_cpp.llama_grammar import LlamaGrammar
    try:
        LlamaGrammar.from_json_schema(json.dumps(schema), verbose=False)
    except Exception as e:
        return f"{type(e).__name__}: {e}"[:300]
    return None


def check_grammars(entries):
    """Startup check: builds the JSON grammar from every schema in `entries` ((model class, tweak or None), the tweak being
    what structured_call applies to the schema) and logs the result. A schema whose grammar cannot be built is put in
    GRAMMAR_OFF now, so its first real call does not have to fail to find out. Needs no model and never raises. Returns
    {class name: problem or None}, empty when the library's converter is not available."""
    results = {}
    for cls, tweak in entries:
        try:
            schema = cls.model_json_schema()
            if tweak:
                tweak(schema)
            results[cls.__name__] = grammar_problem(schema)
        except ImportError as e:
            logger.warning("JSON grammar check skipped: the converter is not available (%s)", str(e)[:120])
            return {}
        except Exception as e:                   # a schema that cannot even be produced is as bad as one that does not convert
            results[cls.__name__] = f"{type(e).__name__}: {e}"[:300]
    bad = {name: why for name, why in results.items() if why}
    runtime.GRAMMAR_OFF.update(bad)
    for name, why in bad.items():
        logger.warning("JSON grammar check: %s cannot be converted (%s). This card is written without the grammar", name, why)
    if results and not bad:
        logger.info("JSON grammar check: all %d schemas convert (%s)", len(results), ", ".join(results))
    return results


def grammar_failed(name, schema, error):
    """A grammar-constrained call raised. The grammar is turned off for this card (and only this card) when the grammar
    itself cannot be built from its schema; any other cause (out of memory, a hiccup in the library) is only logged, and
    the grammar stays on for the next call."""
    try:
        problem = grammar_problem(schema)
    except Exception as e:                       # the converter is not available here: the cause cannot be told, so nothing is switched off
        logger.warning("%s: grammar-constrained generation failed (%s: %s); could not check the schema (%s: %s). Writing this attempt "
                       "without the grammar; the grammar stays on", name, type(error).__name__, str(error)[:200], type(e).__name__, str(e)[:120])
        return
    if problem:
        runtime.GRAMMAR_OFF[name] = problem
        logger.warning("%s: the JSON grammar cannot be built from this card's schema (%s). This card is written without the grammar "
                       "from now on; the other cards keep it", name, problem)
    else:
        logger.warning("%s: grammar-constrained generation failed (%s: %s), but the schema converts fine, so the cause is elsewhere. "
                       "Writing this attempt without the grammar; the grammar stays on", name, type(error).__name__, str(error)[:200])


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
    ask, last_err, cut_off = prompt, None, False
    for attempt in range(config.MAX_RETRIES + 1):
        grammar = config.GRAMMAR_MODE != "never" and model_cls.__name__ not in runtime.GRAMMAR_OFF and (config.GRAMMAR_MODE == "always" or attempt > 0)
        # a repeat penalty would punish the quotes, commas and keys that JSON has to repeat, so the free attempt has none
        kw = dict(temperature=temperature, top_p=config.CARD_TOP_P, top_k=config.CARD_TOP_K, repeat_penalty=1.05 if grammar else 1.0, max_tokens=max_tokens,
                  **runtime.seed_kw(attempt))
        msgs = [{"role": "user", "content": ask}]
        runtime.report(attempt=attempt + 1, tokens=0, max_tokens=max_tokens)
        tag = f"{model_cls.__name__} (attempt {attempt + 1}, {'with' if grammar else 'no'} grammar)"
        text, finish = None, None
        if grammar:
            try:                                         # the grammar guarantees valid JSON with every field
                text, finish = llm_text(msgs, tag, response_format={"type": "json_object", "schema": schema}, **kw)
            except runtime.Cancelled:
                raise
            except Exception as e:
                grammar_failed(model_cls.__name__, schema, e)
        if text is None:
            text, finish = llm_text(msgs, tag, **kw)
        try:
            result = model_cls.model_validate(strip_markdown(extract_json(text)))
            return post(result) if post else result
        except runtime.Cancelled:
            raise
        except Exception as e:                       # bad JSON or failed validation
            last_err, cut_off = e, finish == "length"
            log.warning("attempt %d failed: %s", attempt + 1, str(e)[:300])
            log_bad_reply(tag, text, finish, e)
            ask = (prompt + "\n\nYour previous reply could not be used:\n" + str(e)[:config.RETRY_ERROR_CHARS]
                   + "\nReply again with one corrected JSON object and nothing else.")
    if cut_off:                                  # the last reply ran into the token limit: say that, not "bad JSON"
        raise ValueError(M("the model's reply hit the {limit}-token limit before the JSON was complete, after {n} tries. "
                           "Try again, or ask for less in one go.", limit=max_tokens, n=config.MAX_RETRIES + 1))
    raise ValueError(M("the model could not produce valid output after {n} tries: {why}", n=config.MAX_RETRIES + 1, why=str(last_err)[:300]))