"""Fetching the model into the session. A partly downloaded file is resumed by the hub client, so a retry does not start over."""
import logging
import shutil
import time
from pathlib import Path
from typing import Callable

from ..config import ModelSettings

log = logging.getLogger("pulpermill")


def default_downloader(repo: str, filename: str, directory: str) -> str:
    from huggingface_hub import hf_hub_download
    return hf_hub_download(repo_id=repo, filename=filename, local_dir=directory)


def remote_size(repo: str, filename: str) -> int | None:
    try:
        from huggingface_hub import HfApi
        info = HfApi().model_info(repo, files_metadata=True)
        for sibling in info.siblings or []:
            if sibling.rfilename == filename and sibling.size:
                return int(sibling.size)
    except Exception:
        pass
    return None


def ensure_model(settings: ModelSettings, *, downloader: Callable[[str, str, str], str] = default_downloader,
                 sleep: Callable[[float], None] = time.sleep, size: int | None = None,
                 free_bytes: Callable[[str], int] | None = None) -> str:
    """The path to the model file, downloading it if it is not there. Raises RuntimeError with a plain sentence."""
    folder = Path(settings.directory)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / settings.file
    if target.exists() and target.stat().st_size > 0:
        log.info("model already on disk: %s (%.1f GB)", target.name, target.stat().st_size / 1e9)
        return str(target)
    known = size if size is not None else remote_size(settings.repo, settings.file)
    need = (known or settings.size_fallback_bytes) + settings.disk_headroom_bytes
    free = (free_bytes or (lambda p: shutil.disk_usage(p).free))(str(folder))
    if free < need:
        message = f"Not enough disk space for the model: {free / 1e9:.1f} GB free, about {need / 1e9:.1f} GB needed."
        if known:
            raise RuntimeError(message)
        log.warning("%s (the size is a guess, so going on)", message)
    delay = settings.download_backoff_seconds
    for attempt in range(1, settings.download_tries + 1):
        started = time.monotonic()
        try:
            log.info("downloading %s/%s (attempt %d of %d)", settings.repo, settings.file, attempt, settings.download_tries)
            path = downloader(settings.repo, settings.file, settings.directory)
            log.info("download finished in %.0f s", time.monotonic() - started)
            return str(path)
        except Exception as error:
            log.warning("download attempt %d failed: %s", attempt, str(error)[:200])
            if attempt == settings.download_tries:
                raise RuntimeError(f"The model could not be downloaded after {attempt} tries. Check the internet setting and the file name.") from None
            sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")
