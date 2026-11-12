"""The two Kaggle notebooks: the launcher that people run, and the development tools. They cannot run here (no GPU, no Kaggle), so
this checks what can go wrong without running them: broken Python, names that no longer exist, settings used before they are set,
and anything saved in them that should not be."""
import ast
import importlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOKS = ["pulpermill_backend", "pulpermill_dev"]


def load(name: str) -> dict:
    return json.loads((ROOT / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8"))


def code_cells(name: str) -> list[str]:
    return ["".join(c["source"]) for c in load(name)["cells"] if c["cell_type"] == "code"]


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_every_code_cell_is_valid_python(name):
    for source in code_cells(name):
        ast.parse(source)


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_nothing_is_saved_in_a_notebook_but_its_cells(name):
    nb = load(name)
    for cell in nb["cells"]:
        assert cell.get("id")
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
    assert set(nb["metadata"]) == {"kernelspec", "language_info"}
    assert len({c["id"] for c in nb["cells"]}) == len(nb["cells"])


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_every_name_a_cell_imports_from_the_code_exists(name):
    seen = 0
    for source in code_cells(name):
        for module, names in re.findall(r"^from (pulpermill\.[\w.]+|tools\.[\w.]+) import (.+)$", source, flags=re.M):
            if module.startswith("tools."):
                continue          # tools/ is not a package that is installed; the cell runs from the clone
            target = importlib.import_module(module)
            for item in (n.strip() for n in names.split(",")):
                assert hasattr(target, item), f"{name}: {module} has no {item}"
                seen += 1
    assert seen


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_the_settings_are_set_before_the_cell_that_uses_them(name):
    cells = code_cells(name)
    first = next(i for i, s in enumerate(cells) if "BRANCH =" in s)
    used = next(i for i, s in enumerate(cells) if "--branch" in s and "BRANCH" in s)
    assert first < used


def test_the_launcher_starts_the_server_once_after_the_checks_and_the_cuda_setup():
    cells = code_cells("pulpermill_backend")
    steps = [next(i for i, s in enumerate(cells) if marker in s) for marker in ("check_session()", "ensure_cuda_llama()", "launch(")]
    assert steps == sorted(steps) and sum("launch(" in s for s in cells) == 1
    launch = cells[steps[2]]
    assert "secrets[" in launch and "port=PORT" in launch and "prompter=PROMPTER" in launch and "trace=TRACE" in launch


def test_the_launcher_defaults_are_the_safe_ones():
    settings = next(s for s in code_cells("pulpermill_backend") if "BRANCH =" in s)
    for line in ("PROMPTER = \"mill\"", "DEBUG = False", "TRACE = False", "PORT = 8000"):
        assert line in settings
    assert "do not share or commit" in settings


def test_the_launcher_has_no_measuring_or_trial_cells_and_the_dev_notebook_never_starts_the_server():
    launcher = "\n".join(code_cells("pulpermill_backend"))
    assert "measure_all" not in launcher and "make_complete" not in launcher and "pulpermill-runs.jsonl" not in launcher
    assert not any("launch(" in s for s in code_cells("pulpermill_dev"))
    assert "measure_all" in "\n".join(code_cells("pulpermill_dev"))


def test_the_launcher_names_every_secret_and_the_accelerator_in_its_opening_cell():
    first = "".join(load("pulpermill_backend")["cells"][0]["source"])
    for word in ("GPU T4 x2", "Internet", "PULPERMILL_TOKEN", "NGROK_AUTHTOKEN", "HF_TOKEN", "Run All"):
        assert word in first
