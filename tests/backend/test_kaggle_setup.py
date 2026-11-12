"""The Kaggle session steps: the check that stops a run before any slow step, and the CUDA setup (with a stand-in llama_cpp)."""
import subprocess
import sys
import types

import pytest

from pulpermill.backend import kaggle_setup
from pulpermill.backend.config import Config

TWO_T4 = [("Tesla T4", 15360), ("Tesla T4", 15360)]
SECRETS = {"PULPERMILL_TOKEN": "tok-123456", "NGROK_AUTHTOKEN": "ngrok-abcdef", "HF_TOKEN": "hf-xyz"}


def check(*, find_gpus=lambda: TWO_T4, can_reach=lambda host: True, secrets=SECRETS, model_path="/kaggle/input/m/model.gguf", **extra):
    return kaggle_setup.check_session(get_secret=lambda name: secrets.get(name), find_gpus=find_gpus, can_reach=can_reach,
                                      model_path=model_path, **extra)


def problems_of(**kwargs) -> list[str]:
    with pytest.raises(RuntimeError) as error:
        check(**kwargs)
    lines = str(error.value).splitlines()
    assert lines[0] == "The session is not ready:"
    return lines[1:]


# ---- check_session -----------------------------------------------------------------------------

def test_a_ready_session_returns_the_secrets_and_prints_no_secret_value(capsys):
    got = check()
    assert got == SECRETS
    shown = capsys.readouterr().out
    assert "Tesla T4" in shown and "found in an attached dataset" in shown
    assert not any(value in shown for value in SECRETS.values())


def test_the_model_is_split_across_as_many_gpus_as_the_settings_say():
    assert len(Config().model.tensor_split) == len(TWO_T4)      # the check and the settings agree


@pytest.mark.parametrize("found,count", [([], 0), (TWO_T4[:1], 1)])
def test_too_few_gpus_is_said_with_the_fix(found, count):
    (line,) = problems_of(find_gpus=lambda: found)
    assert f"{count} GPU(s)" in line and "GPU T4 x2" in line


def test_internet_off_names_the_host_and_what_it_is_for():
    lines = problems_of(can_reach=lambda host: False, model_path=None)
    assert any("ngrok.com" in p and "public address" in p and "Internet" in p for p in lines)
    assert any("huggingface.co" in p and "model" in p for p in lines)


def test_an_attached_model_needs_no_hugging_face(capsys):
    asked = []
    check(can_reach=lambda host: asked.append(host) or True)
    assert asked == ["ngrok.com"]
    asked.clear()
    check(can_reach=lambda host: asked.append(host) or True, model_path=None)
    assert asked == ["ngrok.com", "huggingface.co"]
    assert "will be downloaded" in capsys.readouterr().out


def test_missing_required_secrets_are_listed_by_name_and_an_optional_one_is_not_needed():
    lines = problems_of(secrets={"HF_TOKEN": None})
    assert len(lines) == 1 and "PULPERMILL_TOKEN" in lines[0] and "NGROK_AUTHTOKEN" in lines[0] and "Add-ons > Secrets" in lines[0]
    got = check(secrets={"PULPERMILL_TOKEN": "a", "NGROK_AUTHTOKEN": "b"})
    assert got["HF_TOKEN"] is None


def test_everything_wrong_is_reported_at_once_so_it_is_fixed_in_one_go():
    lines = problems_of(find_gpus=lambda: [], can_reach=lambda host: False, secrets={}, model_path=None)
    assert len(lines) == 4        # GPUs, ngrok, huggingface, secrets


def test_a_session_that_needs_no_secrets_can_say_so():
    assert check(secrets={}, required_secrets=(), optional_secrets=()) == {}


def test_outside_kaggle_the_secrets_say_where_this_runs(monkeypatch):
    monkeypatch.setitem(sys.modules, "kaggle_secrets", None)          # an import of it now raises ImportError
    with pytest.raises(RuntimeError, match="runs on Kaggle"):
        kaggle_setup.kaggle_secret("PULPERMILL_TOKEN")


def test_a_secret_that_is_not_attached_comes_back_as_none(monkeypatch):
    class Client:
        def get_secret(self, name):
            raise Exception("not attached")
    monkeypatch.setitem(sys.modules, "kaggle_secrets", types.SimpleNamespace(UserSecretsClient=Client))
    assert kaggle_setup.kaggle_secret("HF_TOKEN") is None


# ---- the GPU list and the connection test ------------------------------------------------------

def test_gpus_reads_nvidia_smi(monkeypatch):
    out = "Tesla T4, 15360\nTesla T4, 15360\nnonsense line\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout=out))
    assert kaggle_setup.gpus() == TWO_T4


def test_no_nvidia_smi_or_a_failing_one_means_no_gpus(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("nvidia-smi")
    monkeypatch.setattr(subprocess, "run", missing)
    assert kaggle_setup.gpus() == []

    def failing(*a, **k):
        raise subprocess.CalledProcessError(9, "nvidia-smi")
    monkeypatch.setattr(subprocess, "run", failing)
    assert kaggle_setup.gpus() == []


def test_reachable_is_false_when_the_connection_cannot_open(monkeypatch):
    def refuse(*a, **k):
        raise OSError("no route")
    monkeypatch.setattr(kaggle_setup.socket, "create_connection", refuse)
    assert kaggle_setup.reachable("example.invalid") is False


# ---- the CUDA setup ----------------------------------------------------------------------------

def fake_llama(offload: bool):
    return types.SimpleNamespace(llama_supports_gpu_offload=lambda: offload, __version__="9.9.9")


def test_a_library_that_is_nowhere_is_not_found():
    assert kaggle_setup.preload("libpulpermill-not-a-real-library.so.99") is None


def test_the_installed_llama_cpp_is_used_when_it_loads_and_sees_the_gpu(monkeypatch, capsys):
    monkeypatch.setattr(kaggle_setup, "load_cuda_libraries", lambda: None)
    monkeypatch.setattr(kaggle_setup, "install_llama_cpp", lambda: pytest.fail("a working install must not be replaced"))
    module = fake_llama(True)
    monkeypatch.setitem(sys.modules, "llama_cpp", module)
    assert kaggle_setup.ensure_cuda_llama() is module
    assert "GPU offload: supported" in capsys.readouterr().out


def test_a_llama_cpp_without_gpu_offload_is_refused_in_plain_words(monkeypatch):
    monkeypatch.setattr(kaggle_setup, "load_cuda_libraries", lambda: None)
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama(False))
    with pytest.raises(RuntimeError, match="cannot use the GPU"):
        kaggle_setup.ensure_cuda_llama()


def test_a_llama_cpp_that_does_not_load_is_replaced_once_and_then_used(monkeypatch):
    monkeypatch.setattr(kaggle_setup, "load_cuda_libraries", lambda: None)
    tries = []

    def import_llama_cpp():
        tries.append(1)
        return None if len(tries) == 1 else fake_llama(True)

    installs = []
    monkeypatch.setattr(kaggle_setup, "import_llama_cpp", import_llama_cpp)
    monkeypatch.setattr(kaggle_setup, "install_llama_cpp", lambda: installs.append(1))
    assert kaggle_setup.ensure_cuda_llama().__version__ == "9.9.9"
    assert len(installs) == 1 and len(tries) == 2


def test_a_replacement_that_still_does_not_load_stops_with_a_message(monkeypatch):
    monkeypatch.setattr(kaggle_setup, "load_cuda_libraries", lambda: None)
    monkeypatch.setattr(kaggle_setup, "import_llama_cpp", lambda: None)
    monkeypatch.setattr(kaggle_setup, "install_llama_cpp", lambda: None)
    with pytest.raises(RuntimeError, match="still does not load"):
        kaggle_setup.ensure_cuda_llama()


def test_missing_cuda_libraries_are_installed_from_pip_then_checked_again(monkeypatch):
    seen = {"installs": [], "rounds": 0}

    def preload(name):
        seen["rounds"] += 1
        return f"{name}: found" if seen["installs"] else None

    monkeypatch.setattr(kaggle_setup, "preload", preload)
    monkeypatch.setattr(kaggle_setup, "pip", lambda *args: seen["installs"].append(args) or 0)
    kaggle_setup.load_cuda_libraries()
    assert seen["installs"] == [("nvidia-cuda-runtime-cu12", "nvidia-cublas-cu12")]
    assert seen["rounds"] == 2 * len(kaggle_setup.NEEDED_LIBRARIES)


def test_libraries_that_stay_missing_after_the_install_are_an_error_naming_the_accelerator(monkeypatch):
    monkeypatch.setattr(kaggle_setup, "preload", lambda name: None)
    monkeypatch.setattr(kaggle_setup, "pip", lambda *args: 0)
    with pytest.raises(RuntimeError, match="GPU T4 x2"):
        kaggle_setup.load_cuda_libraries()
