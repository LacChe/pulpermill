"""What the GPUs have free, read from nvidia-smi (no extra package). None when there is no GPU or no nvidia-smi."""
import shutil
import subprocess


def free_vram_mb() -> list[int] | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=15, check=True).stdout
        return [int(line.strip()) for line in out.splitlines() if line.strip()]
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def check_memory(free_after_mb: list[int] | None, minimum_mb: int) -> str | None:
    """A plain sentence when memory is too tight after loading, else None. Unknown memory is not an error."""
    if not free_after_mb:
        return None
    tight = [i for i, free in enumerate(free_after_mb) if free < minimum_mb]
    if tight:
        shown = ", ".join(f"GPU {i} has {free_after_mb[i]} MB free" for i in tight)
        return (f"Memory is too tight after loading the model ({shown}; at least {minimum_mb} MB is wanted). "
                "Lower n_ctx (and budgets.yaml with it), use the q8_0 cache type, or change the tensor split.")
    return None
