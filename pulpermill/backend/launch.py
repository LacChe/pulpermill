"""Everything the Kaggle notebook does, so the notebook itself stays a few lines: check the settings, get the model, load it,
try one short generation, start the server, open the tunnel, say clearly where it is.

    from pulpermill.backend.launch import launch
    launch(token=..., ngrok_authtoken=...)
"""
import logging
import os
import sys
import threading
import time
from dataclasses import replace
from typing import Any, Callable

import uvicorn

from pulpermill.prompts import budget

from .config import Config
from .engine import download
from .engine.base import Engine
from .engine.llama import load
from .server import create_app

log = logging.getLogger("pulpermill")


def check_settings(config: Config) -> None:
    """The prompts are sized to the context in budgets.yaml; a different n_ctx here would let a prompt through that does not fit."""
    wanted = budget.budgets()["n_ctx"]
    if config.model.n_ctx != wanted:
        raise RuntimeError(f"n_ctx is {config.model.n_ctx} here but {wanted} in pulpermill/prompts/budgets.yaml. "
                           "Change both, on purpose, after measuring.")


def selftest(engine: Engine, config: Config, tokens: int = 40) -> float:
    """One short free-text generation, timed. Returns tokens per second. Proves the model answers before the page does."""
    started = time.monotonic()
    text = engine.generate("Write one sentence about a harbour at dawn.", tokens, params=config.prose)
    seconds = max(time.monotonic() - started, 1e-6)
    run = getattr(engine, "last_run", {}) or {}
    made = run.get("output_tokens") or len(text.split())
    log.info("selftest: %d tokens in %.1f s = %.1f tokens/s (prefill %.1f s)", made, seconds, made / seconds, run.get("prefill_s", 0.0))
    return made / seconds


def open_tunnel(port: int, authtoken: str | None) -> str:
    from pyngrok import ngrok
    if authtoken:
        ngrok.set_auth_token(authtoken)
    for tunnel in ngrok.get_tunnels():          # an old tunnel from an earlier run of the cell
        ngrok.disconnect(tunnel.public_url)
    return ngrok.connect(port, "http").public_url


def banner(url: str | None, port: int, token_set: bool) -> str:
    lines = ["", "=" * 64, "  Pulpermill backend is ready.",
             f"  Address: {url or f'http://127.0.0.1:{port} (no tunnel)'}",
             "  Type that address into \"Model connection\" on the page.",
             "  Access token: " + ("the one in your PULPERMILL_TOKEN secret (type it into the token box)" if token_set else "none is set; anyone with the address can use the model"),
             "  The address changes every session.", "=" * 64, ""]
    return "\n".join(lines)


def use_hub_token(hf_token: str | None) -> bool:
    """Gives the Hugging Face client the writer's token (signed-in downloads are faster and not rate-limited) and turns on the
    client's high-performance transfer (Xet; the old hf_transfer setting is deprecated). The token is only put in the environment,
    never logged. Returns whether a token was set."""
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
    return bool(hf_token)


def launch(*, token: str | None = None, ngrok_authtoken: str | None = None, hf_token: str | None = None, overrides: dict[str, Any] | None = None,
           port: int = 8000, tunnel: Callable[[int, str | None], str] | None = open_tunnel, serve: bool = True,
           engine: Engine | None = None, downloader: Callable | None = None, wait_for_server: float = 30.0,
           log_path: str | None = "/kaggle/working/pulpermill-runs.jsonl") -> dict[str, Any]:
    """Returns {"url", "server", "engine", "config"} (when serve is False; otherwise blocks until the server stops).
    `engine` lets a test skip the real model; `tunnel=None` skips ngrok."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    model = replace(Config().model, **(overrides or {}))
    config = Config(token=token or None, host="0.0.0.0", port=port, model=model, log_path=log_path)
    log.info("settings: %s n_ctx=%d", config.describe(), model.n_ctx)
    check_settings(config)
    log.info("hugging face token: %s", "set" if use_hub_token(hf_token) else "none (downloads are anonymous and slower)")
    if engine is None:
        path = download.ensure_model(model, **({"downloader": downloader} if downloader else {}))
        engine = load(model, path)
    selftest(engine, config)
    server = uvicorn.Server(uvicorn.Config(create_app(config, engine), host=config.host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    thread.start()
    deadline = time.monotonic() + wait_for_server
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("The server did not start.")
        time.sleep(0.05)
    url = tunnel(port, ngrok_authtoken) if tunnel else None
    print(banner(url, port, bool(token)), flush=True)
    result = {"url": url, "server": server, "engine": engine, "config": config}
    if serve:
        try:
            while thread.is_alive():
                thread.join(timeout=60)
                log.info("alive")
        except KeyboardInterrupt:
            server.should_exit = True
    return result
