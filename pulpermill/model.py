"""Loading the model: once, shared by cards and chapters. load_model() fills runtime.llm. Also gpu_report()."""
import errno
import gc
import glob
import shutil
import struct
import subprocess
import os
import time

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


def _gb(n):
    return f"{n / 1e9:.1f} GB"


def _expected_size(token):
    """The model file's size in bytes according to the model hub, or None when that cannot be learned (hub unreachable, odd answer)."""
    try:
        from huggingface_hub import get_hf_file_metadata, hf_hub_url
        size = get_hf_file_metadata(hf_hub_url(config.MODEL_REPO, config.MODEL_FILE), token=token).size
        return int(size) if size else None
    except Exception as e:
        log.warning("could not ask the model hub for the file's size (%s: %s)", type(e).__name__, str(e)[:120])
        return None


def _check_disk(expected):
    """Before the download: is there room for the model file? Counts a partly downloaded copy as already there and skips the
    check when the whole file is already on disk. With the real size known, too little space is an error (with what to do about it);
    with only the fallback size it is a warning, since a different model file may be smaller."""
    target = os.path.join(config.MODEL_DIR, config.MODEL_FILE)
    if os.path.exists(target) and (expected is None or os.path.getsize(target) == expected):
        return
    partial = sum(os.path.getsize(p) for p in glob.glob(os.path.join(config.MODEL_DIR, ".cache", "huggingface", "download", "*.incomplete")))
    free = shutil.disk_usage(config.MODEL_DIR).free
    size = expected or config.MODEL_SIZE_FALLBACK_BYTES
    need = max(size - partial, 0) + config.DISK_HEADROOM_BYTES
    log.info("disk space: %s free in %s, about %s needed for the model%s", _gb(free), config.MODEL_DIR, _gb(need),
             "" if expected else " (its size is a guess: the hub did not say)")
    if free >= need:
        return
    if expected is None:
        log.warning("only %s is free in %s and the model is probably about %s: the download may run out of space",
                    _gb(free), config.MODEL_DIR, _gb(size))
        return
    raise RuntimeError(f"Not enough free disk space for the model: it is {_gb(expected)} and only {_gb(free)} is free in {config.MODEL_DIR} "
                       f"(about {_gb(need)} is needed with some room to spare). Delete files you no longer need there, then run this cell again.")


def _worth_retrying(e):
    """Whether downloading again could help: not for a full disk, a refused request (404, 401, 403...), a missing library or a
    permission problem. Anything else (a dropped connection, a timeout, a server error, a throttled request) may pass."""
    if _hopeless(e) or (isinstance(e, OSError) and e.errno == errno.ENOSPC):
        return False
    status = getattr(getattr(e, "response", None), "status_code", None)
    return not (isinstance(status, int) and 400 <= status < 500 and status not in (408, 429))


def _download(hf_hub_download, token):
    """hf_hub_download with a few attempts and growing waits between them; each attempt resumes a partly downloaded file."""
    tries = max(config.DOWNLOAD_TRIES, 1)
    for i in range(tries):
        try:
            return hf_hub_download(repo_id=config.MODEL_REPO, filename=config.MODEL_FILE, local_dir=config.MODEL_DIR, token=token)
        except Exception as e:
            if i == tries - 1 or not _worth_retrying(e):
                log.error("the model download failed after %d attempt(s) (%s: %s)", i + 1, type(e).__name__, str(e)[:200])
                raise
            wait = config.DOWNLOAD_BACKOFF_SECONDS * 2 ** i
            log.warning("the model download failed (%s: %s); trying again in %d s (attempt %d of %d)",
                        type(e).__name__, str(e)[:200], wait, i + 2, tries)
            time.sleep(wait)


def _check_size(path, expected):
    """Fails at once when the downloaded file is not the size the model hub lists for it (a cut-off or wrong file)."""
    if expected is not None:
        got = os.path.getsize(path)
        if got != expected:
            raise ValueError(f"{path} is {got:,} bytes but the model repository lists {expected:,}. It is probably a partial download: "
                             "delete it and download the model again.")


def _check_gguf(path):
    """Fails at once, with a clear message, when the downloaded file is not a GGUF model at all (a damaged or wrong file)."""
    with open(path, "rb") as f:
        head = f.read(4)
    if head != b"GGUF":
        raise ValueError(f"{path} is not a GGUF model file (it starts with {head!r}). Delete it and download the model again.")


# GGUF metadata value types: how many bytes a fixed-size one takes (the string and array types are handled in _skip_value)
_GGUF_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_GGUF_INTS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 10: "<Q", 11: "<q"}
_REFERENCE_BLOCKS = 62                  # the transformer blocks of the model this loader was tuned for (Gemma 3 27B)
_REFERENCE_LADDER = (50, 40, 30, 20, 10)   # layers on the GPU for that model after "all of them" fails; other sizes scale from it


def _read_value(f, kind):
    """One GGUF metadata value, read for its content (a string or an integer; anything else comes back as None)."""
    if kind == 8:
        length = struct.unpack("<Q", f.read(8))[0]
        if length > 1 << 20:                                # a key or an architecture name is short: this is not a GGUF header
            raise ValueError(f"implausible GGUF string length {length}")
        return f.read(length).decode("utf-8", "replace")
    if kind in _GGUF_INTS:
        fmt = _GGUF_INTS[kind]
        return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]
    _skip_value(f, kind)
    return None


def _skip_value(f, kind):
    if kind in _GGUF_SIZES:
        f.seek(_GGUF_SIZES[kind], 1)
    elif kind == 8:
        f.seek(struct.unpack("<Q", f.read(8))[0], 1)
    elif kind == 9:                                         # an array: its element type, its length, then the elements
        item, count = struct.unpack("<IQ", f.read(12))
        if item in _GGUF_SIZES:
            f.seek(_GGUF_SIZES[item] * count, 1)
        else:
            for _ in range(count):
                _skip_value(f, item)
    else:
        raise ValueError(f"unknown GGUF value type {kind}")


def _block_count(path):
    """The number of transformer blocks the model file says it has ("<architecture>.block_count" in its GGUF header), or None
    when it cannot be read. Reads only the header, stops at the first match and never raises: a file this cannot read is the
    loader's business to reject, not this function's."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"GGUF":
                return None
            version, _tensors, pairs = struct.unpack("<IQQ", f.read(20))
            if version not in (2, 3) or pairs > 100_000:
                return None
            arch, counts = None, {}
            for _ in range(pairs):
                key = _read_value(f, 8)
                (kind,) = struct.unpack("<I", f.read(4))
                value = _read_value(f, kind)
                if key == "general.architecture":
                    arch = value
                elif key.endswith(".block_count") and isinstance(value, int):
                    counts[key] = value
                if arch is not None and f"{arch}.block_count" in counts:
                    break
            found = counts.get(f"{arch}.block_count") if arch is not None else None
            return found if found is not None and 0 < found <= 1000 else None
    except Exception:
        return None


def _ladder(blocks):
    """How many layers to try on the GPU(s), in order: all of them, then fewer. For the 62-block model it is exactly the steps
    it was tuned with; another size gets the same fractions of its own block count."""
    steps = [max(1, round(blocks * k / _REFERENCE_BLOCKS)) for k in _REFERENCE_LADDER]
    return [-1, *dict.fromkeys(s for s in steps if s < blocks)]


def _tensor_split(gpu_count):
    """The share of the model each GPU takes. config.TENSOR_SPLIT is written for the machine this was tuned on; it is used when it
    has one value per GPU, and any other number of GPUs gets an even split (a split with fewer values than GPUs leaves the rest unused)."""
    want = config.TENSOR_SPLIT
    if want and len(want) == gpu_count:
        return list(want)
    log.info("config.TENSOR_SPLIT has %d value(s) but there are %d GPUs: splitting the model evenly", len(want or []), gpu_count)
    return [1.0 / gpu_count] * gpu_count


_NO_GPU = ("No GPU found (nvidia-smi is missing or lists no devices). In the notebook settings, set the accelerator to GPU T4 x2, "
           "then run the cells again from the top.")


def _gpu_count():
    """How many NVIDIA GPUs nvidia-smi reports. Raises a RuntimeError that says what to do when there are none (the technical
    detail goes to the log), instead of letting the second nvidia-smi call fail with a raw traceback."""
    problems = []
    try:
        count = int(subprocess.check_output(["nvidia-smi", "--query-gpu=count", "--format=csv,noheader"], timeout=10).decode().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as e:     # the count query is not supported: count the listed GPUs instead
        problems.append(f"{type(e).__name__}: {str(e)[:150]}")
        try:
            count = int(subprocess.check_output(["nvidia-smi", "-L"], timeout=10).decode().count("GPU "))
        except (OSError, subprocess.SubprocessError, ValueError) as e2:
            problems.append(f"{type(e2).__name__}: {str(e2)[:150]}")
            count = 0
    if count < 1:
        log.error("no GPU: %s", "; then ".join(problems) or "nvidia-smi reports 0 devices")
        raise RuntimeError(_NO_GPU)
    log.info("detected %d GPU(s)", count)
    return count


def _build_llama():
    """Downloads (if needed) and loads the GGUF model with the gemma chat template.
    It tries all layers on the GPU(s) first, then progressively fewer until it loads, the rest running on CPU (slower, but it
    loads). On two GPUs the layers it does offload are shared between the cards by config.TENSOR_SPLIT."""
    from huggingface_hub import hf_hub_download     # imported here so that importing this module (for gpu_report) needs neither library
    from llama_cpp import Llama

    gpu_count = _gpu_count()                # first, so a notebook without a GPU says so at once instead of after a 17 GB download
    os.makedirs(config.MODEL_DIR, exist_ok=True)
    try:                                    # the repo is not gated, so a missing HF_TOKEN secret is fine
        from kaggle_secrets import UserSecretsClient
        hf_token = UserSecretsClient().get_secret("HF_TOKEN")
    except Exception as e:                  # not on Kaggle, or no such secret
        hf_token = None
        log.info("no HF_TOKEN available (%s: %s); downloading without a token", type(e).__name__, str(e)[:120])
    expected = _expected_size(hf_token)
    _check_disk(expected)
    model_path = _download(hf_hub_download, hf_token)
    _check_size(model_path, expected)
    _check_gguf(model_path)

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

    blocks = _block_count(model_path)
    if blocks is None:
        log.warning("could not read the layer count from the model file; assuming %d", _REFERENCE_BLOCKS)
        blocks = _REFERENCE_BLOCKS
    else:
        log.info("the model has %d transformer blocks (read from the file)", blocks)
    split = dict(tensor_split=_tensor_split(gpu_count)) if gpu_count >= 2 else {}     # several GPUs share the layers by this ratio
    where = f"{gpu_count} GPUs" if gpu_count >= 2 else "a single GPU"
    last_error = None
    for n_layers in _ladder(blocks):
        label = "all layers on GPU" if n_layers == -1 else f"{n_layers}/{blocks} layers on GPU, rest on CPU"
        log.info("attempting model load: %s", label)
        try:
            return attempt(n_gpu_layers=n_layers, main_gpu=0, **split)
        except Exception as e:
            if _hopeless(e):
                raise
            last_error = e
    raise RuntimeError(f"could not load the model at any offload level on {where}") from last_error


def load_model():
    """Loads the model into runtime.llm (the slot every generation reads) and returns it. Run again while a model is loaded, it
    leaves that one alone: a second copy would be loaded while the first still holds the GPU memory, and run out of it."""
    if runtime.llm is not None:
        log.info("the model is already loaded, so it is not loaded a second time (that would run out of GPU memory). "
                 "To load it again with different settings, restart the session first.")
        return runtime.llm
    runtime.llm = _build_llama()
    log.info("model loaded; GPU memory now: %s", gpu_report())
    return runtime.llm
