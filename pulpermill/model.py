"""Loading the model: once, shared by cards and chapters. load_model() fills runtime.llm. Also gpu_report()."""
import gc
import subprocess
import os

from . import config, runtime
from .runtime import log


def gpu_report():
    """Memory and load per GPU, from nvidia-smi ([] when there is no GPU or no nvidia-smi)."""
    try:
        rows = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.used,memory.total,utilization.gpu",
                                        "--format=csv,noheader,nounits"], timeout=5).decode().strip().splitlines()
        return [dict(zip(("gpu", "used_mb", "total_mb", "util_pct"), (int(x) for x in r.split(",")))) for r in rows]
    except (OSError, subprocess.SubprocessError, ValueError):   # no nvidia-smi, it failed or timed out, or odd output: no GPU report
        return []


# Errors that more load attempts cannot fix: a missing or unreadable file, a library that is not there, an argument this build does not
# know. Anything else is retried as before: llama-cpp-python reports even an out-of-memory load only as "Failed to load model", so
# an error that says nothing is treated as maybe-memory. (Once the loader shows llama.cpp's own output, this can be made exact.)
_HOPELESS = (FileNotFoundError, PermissionError, ImportError, TypeError)


def _hopeless(e):
    return isinstance(e, _HOPELESS) or (isinstance(e, ValueError) and "does not exist" in str(e))


def _release(error):
    """After a failed load: the exception's traceback holds the half-built model, and so the GPU memory it already took, for as
    long as the exception is kept. Drop the tracebacks (the message stays) and collect, so the next attempt starts with that memory free."""
    seen, e = set(), error
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        e.__traceback__ = None
        e = e.__cause__ or e.__context__
    gc.collect()


def _check_gguf(path):
    """Fails at once, with a clear message, when the downloaded file is not a GGUF model at all (a damaged or wrong file)."""
    with open(path, "rb") as f:
        head = f.read(4)
    if head != b"GGUF":
        raise ValueError(f"{path} is not a GGUF model file (it starts with {head!r}). Delete it and download the model again.")


def _build_llama():
    """Downloads (if needed) and loads the GGUF model with the gemma chat template.
    It tries all layers on the GPU(s) first, then progressively fewer until it loads, the rest running on CPU (slower, but it
    loads). On two GPUs the layers it does offload are shared between the cards by config.TENSOR_SPLIT."""
    from huggingface_hub import hf_hub_download     # imported here so that importing this module (for gpu_report) needs neither library
    from llama_cpp import Llama

    os.makedirs(config.MODEL_DIR, exist_ok=True)
    try:                                    # the repo is not gated, so a missing HF_TOKEN secret is fine
        from kaggle_secrets import UserSecretsClient
        hf_token = UserSecretsClient().get_secret("HF_TOKEN")
    except Exception as e:                  # not on Kaggle, or no such secret
        hf_token = None
        log.info("no HF_TOKEN available (%s: %s); downloading without a token", type(e).__name__, str(e)[:120])
    model_path = hf_hub_download(repo_id=config.MODEL_REPO, filename=config.MODEL_FILE, local_dir=config.MODEL_DIR, token=hf_token)
    _check_gguf(model_path)

    try:
        gpu_count = int(subprocess.check_output(
            ["nvidia-smi", "--query-gpu=count", "--format=csv,noheader"]).decode().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):     # the count query is not supported: count the listed GPUs instead
        gpu_count = int(subprocess.check_output(["nvidia-smi", "-L"]).decode().count("GPU "))
    log.info("detected %d GPU(s)", gpu_count)

    base = dict(model_path=model_path, n_ctx=config.N_CTX, verbose=False, last_n_tokens_size=8192, n_batch=config.N_BATCH,
                chat_format="gemma")
    if config.N_THREADS:
        base["n_threads"] = config.N_THREADS

    def attempt(**kw):
        """Flash attention first (faster, smaller memory footprint); without it only if nothing else loads at this setting."""
        last = None
        for fa in ([True, False] if config.FLASH_ATTN else [False]):
            log.info("loading the model (flash attention %s, %s layers on GPU); GPU memory before: %s",
                     "on" if fa else "off", kw.get("n_gpu_layers"), gpu_report())
            try:
                return Llama(**base, flash_attn=fa, **kw)
            except Exception as e:
                last = e
                log.warning("load failed (flash attention %s): %s", "on" if fa else "off", str(e)[:200])
                if _hopeless(e):                # another setting or fewer layers cannot fix this: stop now
                    log.error("the model cannot be loaded and no other setting will help (%s: %s)", type(e).__name__, str(e)[:200])
                    raise
                _release(e)                     # about to try again: give back what the failed attempt took
        raise last

    split = dict(tensor_split=config.TENSOR_SPLIT) if gpu_count >= 2 else {}     # two GPUs share the layers by this ratio
    where = f"{gpu_count} GPUs" if gpu_count >= 2 else "a single GPU"
    last_error = None
    for n_layers in [-1, 50, 40, 30, 20, 10]:       # this model has 62 transformer blocks
        label = "all layers on GPU" if n_layers == -1 else f"{n_layers}/62 layers on GPU, rest on CPU"
        log.info("attempting model load: %s", label)
        try:
            return attempt(n_gpu_layers=n_layers, main_gpu=0, **split)
        except Exception as e:
            if _hopeless(e):
                raise
            last_error = e
    raise RuntimeError(f"could not load the model at any offload level on {where}") from last_error


def load_model():
    """Loads the model into runtime.llm (the slot every generation reads) and returns it."""
    runtime.llm = _build_llama()
    log.info("model loaded; GPU memory now: %s", gpu_report())
    return runtime.llm
