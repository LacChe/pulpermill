"""The launcher's own steps, with the fake engine and no tunnel."""
import pytest

try:
    import uvicorn  # noqa: F401
    import requests
except ImportError:
    pytest.skip("uvicorn and requests are needed", allow_module_level=True)

from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.launch import banner, check_settings, launch, selftest
from pulpermill.prompts import budget

from server_harness import free_port


def test_an_n_ctx_that_differs_from_the_budgets_is_refused():
    from dataclasses import replace
    config = Config()
    check_settings(config)                      # the shipped settings agree
    with pytest.raises(RuntimeError) as error:
        check_settings(replace(config, model=replace(config.model, n_ctx=config.model.n_ctx + 1)))
    assert "budgets.yaml" in str(error.value)
    assert config.model.n_ctx == budget.budgets()["n_ctx"]


def test_selftest_reports_tokens_per_second():
    assert selftest(FakeEngine(), Config()) > 0


def test_launch_starts_a_server_that_answers_and_the_banner_never_shows_the_token():
    port = free_port()
    out = launch(token="s3cret", port=port, tunnel=None, serve=False, engine=FakeEngine())
    try:
        url = f"http://127.0.0.1:{port}/api"
        assert requests.post(url, json={"call": "status"}).status_code == 401
        ok = requests.post(url, json={"call": "status"}, headers={"x-pulpermill-token": "s3cret"})
        assert ok.json() == {"ok": True, "state": "idle"}
    finally:
        out["server"].should_exit = True
    text = banner("https://x.ngrok.app", port, True)
    assert "https://x.ngrok.app" in text and "s3cret" not in text


def test_a_hugging_face_token_goes_to_the_hub_client_and_never_into_the_log(monkeypatch, caplog):
    import os
    from pulpermill.backend.launch import use_hub_token
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert use_hub_token(None) is False and "HF_TOKEN" not in os.environ
    assert use_hub_token("hf_secret") is True and os.environ["HF_TOKEN"] == "hf_secret"
    assert "hf_secret" not in caplog.text
