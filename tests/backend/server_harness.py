"""Runs the real server (uvicorn, in a thread) on a free port, so tests talk to it over HTTP like the page does."""
import contextlib
import json
import socket
import threading
import time

import requests
import uvicorn

from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.pipelines import run_canned
from pulpermill.backend.server import create_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


CANNED = object()


@contextlib.contextmanager
def running(config: Config | None = None, engine: FakeEngine | None = None, run=CANNED):
    """Yields (base_url, engine). The server is stopped on exit. `run` defaults to the canned pipelines (the fake engine's words are not JSON); `run=None` is the real server code: the runner and the configured prompter."""
    config = config or Config()
    engine = engine or FakeEngine()
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(config, engine, run_canned if run is CANNED else run), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(500):
        if server.started:
            break
        time.sleep(0.01)
    else:
        raise RuntimeError("the server did not start")
    try:
        yield f"http://127.0.0.1:{port}", engine
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def post(base: str, body, token: str | None = None, timeout: float = 10, raw: bytes | None = None):
    headers = {"content-type": "application/json", "ngrok-skip-browser-warning": "1"}
    if token is not None:
        headers["x-pulpermill-token"] = token
    return requests.post(f"{base}/api", data=raw if raw is not None else json.dumps(body), headers=headers, timeout=timeout)


def wait_idle(base: str, seconds: float = 5.0, token: str | None = None) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if post(base, {"call": "status"}, token).json().get("state") == "idle":
            return True
        time.sleep(0.02)
    return False
