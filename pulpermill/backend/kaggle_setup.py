"""The steps the Kaggle notebook takes before the server starts, so the notebook itself is a list of short cells: check the session
(GPUs, internet, secrets) and make llama-cpp-python load with CUDA. Nothing here starts the server; launch.py does that.

    from pulpermill.backend.kaggle_setup import check_session, ensure_cuda_llama
    secrets = check_session()          # stops with a plain list of everything to fix, before any slow step
    ensure_cuda_llama()                # a few minutes the first time; run again after a restart
"""
import ctypes
import glob
import importlib
import os
import site
import socket
import subprocess
import sys
from typing import Callable

from .config import Config
from .engine import download

REQUIRED_SECRETS = ("PULPERMILL_TOKEN", "NGROK_AUTHTOKEN")
OPTIONAL_SECRETS = ("HF_TOKEN",)


# ---- The session -------------------------------------------------------------------------------

def gpus() -> list[tuple[str, int]]:
    """The GPUs nvidia-smi can see, as [(name, memory in MB)]. Empty when there is no GPU or no nvidia-smi."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.strip().splitlines():
        name, _, memory = line.rpartition(",")
        try:
            found.append((name.strip(), int(float(memory))))
        except ValueError:
            continue
    return found


def reachable(host: str, port: int = 443, timeout: float = 8.0) -> bool:
    """Whether a connection to the host opens. With Internet off in the notebook settings it does not."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def kaggle_secret(name: str) -> str | None:
    """One secret from the notebook's Add-ons > Secrets, or None when it is not set or not attached to this notebook."""
    try:
        from kaggle_secrets import UserSecretsClient
    except ImportError as error:
        raise RuntimeError("This runs on Kaggle: the kaggle_secrets package is not available here.") from error
    try:
        return UserSecretsClient().get_secret(name) or None
    except Exception:
        return None


def check_session(*, required_secrets: tuple[str, ...] = REQUIRED_SECRETS, optional_secrets: tuple[str, ...] = OPTIONAL_SECRETS,
                  get_secret: Callable[[str], str | None] = kaggle_secret, find_gpus: Callable[[], list[tuple[str, int]]] = gpus,
                  can_reach: Callable[[str], bool] = reachable, model_path: str | None = None) -> dict[str, str | None]:
    """Checks what would otherwise fail after a long wait: enough GPUs, Internet, the model, the secrets. Prints what it found.
    Raises one RuntimeError that lists everything that needs fixing, so it is fixed in one go. Returns the secrets by name (None for
    an optional one that is not set); their values are never printed. `model_path` is only for tests: where the model is."""
    config = Config()
    problems = []

    needed = len(config.model.tensor_split)          # the model is split across this many GPUs
    found = find_gpus()
    if len(found) < needed:
        problems.append(f"The session has {len(found)} GPU(s) and the model is split across {needed}. "
                        "In the session options, set Accelerator to GPU T4 x2.")
    else:
        print("GPUs:", ", ".join(f"{name} ({memory / 1024:.0f} GB)" for name, memory in found))

    model = model_path or download.find_existing(config.model)
    if model:
        print("Model: found in an attached dataset, nothing to download:", model)
    else:
        print(f"Model: {config.model.file} will be downloaded (attach a dataset that holds it to skip this).")
    internet_for = [("ngrok.com", "the public address")] + ([] if model else [("huggingface.co", "downloading the model")])
    for host, why in internet_for:
        if not can_reach(host):
            problems.append(f"{host} cannot be reached, and it is needed for {why}. In the session options, turn Internet on.")

    secrets, missing = {}, []
    for name in (*required_secrets, *optional_secrets):
        secrets[name] = get_secret(name) or None
        if not secrets[name] and name in required_secrets:
            missing.append(name)
    if missing:
        problems.append(f"These secrets are not set: {', '.join(missing)}. Add them under Add-ons > Secrets and make sure each is attached to this notebook.")
    print("Secrets:", ", ".join(f"{name} {'set' if value else 'not set'}" for name, value in secrets.items()) or "none needed")

    if problems:
        raise RuntimeError("\n".join(["The session is not ready:"] + [f"  - {p}" for p in problems]))
    return secrets


# ---- llama-cpp-python with CUDA ----------------------------------------------------------------

# The CUDA 12 runtime libraries the llama-cpp-python wheels link against. Kaggle's image may carry only CUDA 13.
NEEDED_LIBRARIES = ["libcudart.so.12", "libcublasLt.so.12", "libcublas.so.12"]


def pip(*args: str) -> int:
    """pip install into this session's Python, quietly. Returns pip's exit code."""
    return subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args]).returncode


def search_dirs() -> list[str]:
    """The folders that may hold the CUDA libraries: the system's usual places and the nvidia packages pip installs."""
    roots = ["/usr/local/cuda*/lib64", "/usr/local/cuda*/targets/*/lib", "/usr/local/nvidia/lib64",
             "/usr/lib/x86_64-linux-gnu", "/opt/conda/lib"]
    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        roots.append(sp + "/nvidia/*/lib")
    return [d for r in roots for d in glob.glob(r)]


def preload(name: str) -> str | None:
    """Loads one library into this process (RTLD_GLOBAL, so the loader finds it by name when libllama.so loads). Returns where it
    came from, or None when it is nowhere. Changing LD_LIBRARY_PATH would not help: it is read when the process starts."""
    try:
        ctypes.CDLL(name, mode=ctypes.RTLD_GLOBAL)
        return f"{name}: on the system path"
    except OSError:
        pass
    for d in search_dirs():
        for path in sorted(glob.glob(os.path.join(d, name + "*"))):
            try:
                ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
                return f"{name}: {path}"
            except OSError:
                continue
    return None


def load_cuda_libraries() -> None:
    """Loads the CUDA 12 libraries, installing them from pip first when they are not on the system."""
    found = {n: preload(n) for n in NEEDED_LIBRARIES}
    if not all(found.values()):
        print("CUDA 12 libraries not found:", [n for n, v in found.items() if not v], "- installing them from pip")
        if pip("nvidia-cuda-runtime-cu12", "nvidia-cublas-cu12"):
            raise RuntimeError("The CUDA 12 runtime packages could not be installed (pip's output is above).")
        importlib.invalidate_caches()
        found = {n: preload(n) for n in NEEDED_LIBRARIES}
    for n, v in found.items():
        print(v or f"{n}: NOT FOUND")
    if not all(found.values()):
        raise RuntimeError("A CUDA 12 library is still missing. Check that the accelerator is set to GPU T4 x2.")


def import_llama_cpp():
    """The llama_cpp module, or None when the installed one does not load (Kaggle's image may ship one that does not)."""
    try:
        import llama_cpp
        return llama_cpp
    except Exception as e:
        print("llama-cpp-python does not load:", type(e).__name__, e)
        for name in [m for m in sys.modules if m == "llama_cpp" or m.startswith("llama_cpp.")]:
            del sys.modules[name]            # drop a half-loaded module so a fresh install is the one imported
        return None


def install_llama_cpp() -> None:
    """Replaces the installed llama-cpp-python with a ready-made CUDA 12 wheel. The wheel comes from that index only, so pip cannot pick
    a source package and compile a CPU build. --no-deps keeps pip from touching the image's own packages, so the few dependencies the
    wheel needs are installed by name."""
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "llama-cpp-python"])
    for cuda in ("cu121", "cu124"):
        if pip("llama-cpp-python", "--no-deps", "--only-binary=:all:", "--index-url",
               f"https://abetlen.github.io/llama-cpp-python/whl/{cuda}") == 0:
            break
    else:
        raise RuntimeError("No ready-made llama-cpp-python wheel could be installed (pip's output is above).")
    if pip("diskcache", "jinja2", "typing-extensions", "numpy"):
        raise RuntimeError("The dependencies of llama-cpp-python could not be installed (pip's output is above).")
    importlib.invalidate_caches()


def ensure_cuda_llama():
    """Makes llama-cpp-python load and able to use the GPU: loads the CUDA 12 libraries, uses the installed package if it loads and
    otherwise installs a CUDA 12 build, then checks GPU offload. Safe to run again; it must be run again after a restart, because the
    libraries are loaded into this process. Returns the llama_cpp module."""
    load_cuda_libraries()
    llama_cpp = import_llama_cpp()
    if llama_cpp is None:
        install_llama_cpp()
        llama_cpp = import_llama_cpp()
        if llama_cpp is None:
            raise RuntimeError("llama-cpp-python was installed but still does not load (the message is above).")
    if not llama_cpp.llama_supports_gpu_offload():
        raise RuntimeError("llama-cpp-python loaded but cannot use the GPU. The model would run on the CPU, far too slowly.")
    print("llama-cpp-python", llama_cpp.__version__, "GPU offload: supported")
    return llama_cpp
