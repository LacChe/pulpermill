"""The mill scaffold: loads by name, answers every call through the real server and runner on a fake engine, refuses an unknown call
like the stub, and picks a call's own module by name."""
import json
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "backend"))

from pulpermill import contract  # noqa: E402
from pulpermill.backend.config import Config  # noqa: E402
from pulpermill.backend.engine import FakeEngine  # noqa: E402
from pulpermill.backend.kit import Kit  # noqa: E402
from pulpermill.prompter import CALLS, UnknownPrompter, known_prompters, load_prompter  # noqa: E402
from pulpermill.prompter.mill import VERSION, common, script  # noqa: E402
from server_harness import post, running, wait_idle  # noqa: E402

VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]
VALID = [v for v in VECTORS if v["valid"] and v["data"]["call"] in CALLS]
PKG = "pulpermill.prompter.mill"


def request(call):
    return next(v["data"] for v in VALID if v["data"]["call"] == call)


def test_mill_loads_by_name_with_a_version_and_the_default_is_still_the_stub():
    mill = load_prompter("mill")
    assert mill.name == "mill" and mill.version.startswith(VERSION) and "mill" in known_prompters()
    assert Config().prompter == "stub"
    with pytest.raises(UnknownPrompter):
        load_prompter("Mill")


def test_the_version_is_the_base_while_every_call_is_the_scaffold():
    assert load_prompter("mill").version == "mill-0.1"


@pytest.mark.parametrize("vector", VALID, ids=lambda v: v["name"])
def test_every_valid_vector_is_answered_on_the_mill_prompter(vector):
    req = vector["data"]
    engine = FakeEngine()
    engine.script(*script(req["call"], req, Kit(req)))
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base, _):
        response = post(base, req)
        body = response.json()
        assert response.status_code == 200 and body["ok"] is True, body
        assert contract.parse_reply(req["call"], body).ok is True
        assert wait_idle(base)


def test_every_call_has_a_vector_and_a_flow():
    assert {v["data"]["call"] for v in VALID} == set(CALLS)
    for call in CALLS:
        req = request(call)
        flow = load_prompter("mill").flow(call, req, Kit(req))
        assert flow.next([]) is not None and flow.worst_case()


def test_an_unknown_call_is_refused_like_the_stub_refuses_it():
    with pytest.raises(ValueError, match="no flow for 'offstage'"):
        load_prompter("mill").flow("offstage", {}, None)
    with pytest.raises(ValueError):
        load_prompter("stub").flow("offstage", {}, None)


def _fake_module(monkeypatch, call, **attrs):
    module = types.ModuleType(f"{PKG}.{call}")
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, f"{PKG}.{call}", module)
    return module


def test_a_calls_own_module_is_picked_by_name_and_the_others_still_run_the_stub(monkeypatch):
    seen = []
    plan_req = request("plan")
    sentinel = object()

    def build_flow(req, kit):
        seen.append(req)
        return sentinel

    _fake_module(monkeypatch, "plan", build_flow=build_flow, VERSION="plan-9")
    mill = load_prompter("mill")
    assert mill.flow("plan", plan_req, Kit(plan_req)) is sentinel and seen == [plan_req]
    fill_req = request("fill")
    assert mill.flow("fill", fill_req, Kit(fill_req)).next([]).name == "fill"      # untouched calls stay on the stub's flow
    assert mill.version == "mill-0.1+plan:plan-9"


def test_a_module_that_is_missing_falls_back_and_one_without_build_flow_is_an_error(monkeypatch):
    monkeypatch.setitem(sys.modules, f"{PKG}.judge", None)          # an import of None raises ModuleNotFoundError for that name
    req = request("judge")
    assert load_prompter("mill").flow("judge", req, Kit(req)) is not None
    _fake_module(monkeypatch, "judge")
    with pytest.raises(TypeError, match="build_flow"):
        load_prompter("mill").flow("judge", req, Kit(req))


def test_the_modules_own_script_is_used_when_it_has_one(monkeypatch):
    _fake_module(monkeypatch, "style_fit", build_flow=lambda r, k: None, script=lambda r, k: ["own"])
    assert script("style_fit", request("style_fit"), None) == ["own"]
    _fake_module(monkeypatch, "style_fit", build_flow=lambda r, k: types.SimpleNamespace())
    with pytest.raises(NotImplementedError, match="style_fit"):
        script("style_fit", request("style_fit"), None)


def test_a_wording_edit_changes_the_version_by_itself(monkeypatch, tmp_path):
    _fake_module(monkeypatch, "generate", build_flow=lambda r, k: None, VERSION="g-1")
    mill = load_prompter("mill")
    monkeypatch.setattr(common, "TEXT", tmp_path)
    (tmp_path / "en").mkdir()
    path = tmp_path / "en" / "generate.yaml"
    path.write_text("# header only\n")
    assert mill.version == "mill-0.1+generate:g-1"
    path.write_text("write: Tell it well.\n")
    first = mill.version
    path.write_text("write: Tell it very well.\n")
    assert first != mill.version and first.startswith("mill-0.1+generate:g-1:") and len(first.split(":")[-1]) == 6


def test_the_wording_files_exist_for_every_call_and_start_empty():
    for call in CALLS:
        assert common.load_text(call) == {} and common.text_digest(call) == ""


def test_clip_cuts_at_a_sentence_end_or_a_word_and_never_below_the_floor():
    text = "One short sentence here. Another sentence follows it. A third one closes the passage."
    assert common.clip(text, 1.0) == text
    assert common.clip(text, 0.7) == "One short sentence here. Another sentence follows it."
    assert common.clip("word " * 40, 0.5).endswith("word") and len(common.clip("word " * 40, 0.01)) >= 30
    assert common.clip("short", 0.1) == "short"


def test_labelled_shows_the_handle_of_an_item():
    req = request("generate")
    scope = Kit(req).handles.of_card("characters")[0]
    key = next(k for k in ("wants", "behaviors") if scope.handles(k))
    item = scope.item(scope.handles(key)[0], key)
    assert common.labelled(scope, key, item, "text") == f"{key}.1: text"
