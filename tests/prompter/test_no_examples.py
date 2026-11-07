"""No example text reaches a model. A model copies what it is shown: a sample phrase in a rule shows up in the story (the planner's sample
minor people turned into a tech with a tablet in a pre-industrial village), and a sample in the card-fill rules shows up in the cards.
Rules are stated in words. The schema's good and avoid examples are for the human page only, so no code that builds a prompt may read them."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2] / "pulpermill"
MODEL_TEXT = sorted([*(ROOT / "prompter" / "mill" / "text" / "en").glob("*.yaml"), *(ROOT / "prompts" / "text" / "en").glob("*.yaml")])
PROMPT_CODE = sorted([*(ROOT / "prompter").rglob("*.py"), *(ROOT / "prompts").rglob("*.py"), *(ROOT / "backend").rglob("*.py")])

# Keys whose value is a format demonstration with placeholders, not sample content.
FORMAT_DEMOS = {"shifts_example", "finish_example"}

MARKERS = re.compile(r"\be\.g\.|\bfor example\b|\bfor instance\b|\bsuch as\b|\bsounds like\b|\blooks like\b|\blike this\b", re.I)
QUOTED = re.compile(r"[\"“‘][^\"”’{}]*[A-Za-z]{3}[^\"”’{}]*[\"”’]")          # a quoted phrase; a quoted {placeholder} is not one
LEAKED = re.compile(r"\b(tech|stallholder|woodcutter|clerk|permit|auditor|cellar|boat|regatta|orsini|odile|corrin|jaunty|approval)\b", re.I)


def strings(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FORMAT_DEMOS:
                continue
            yield from strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from strings(value, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def test_no_model_facing_text_holds_an_example():
    found = []
    for file in MODEL_TEXT:
        for path, text in strings(yaml.safe_load(file.read_text(encoding="utf-8"))):
            for name, pattern in (("marker", MARKERS), ("quoted phrase", QUOTED), ("leaked word", LEAKED)):
                hit = pattern.search(text)
                if hit:
                    found.append(f"{file.name}{path}: {name} {hit.group(0)!r}")
    assert not found, "example text in model-facing wording:\n" + "\n".join(found)


def test_the_fill_wording_has_no_example_keys():
    fill = yaml.safe_load((ROOT / "prompter" / "mill" / "text" / "en" / "fill.yaml").read_text(encoding="utf-8"))
    assert not [key for key in fill if key.startswith("examples")]


def test_no_code_that_builds_a_prompt_reads_the_schema_examples():
    readers = [f"{file.relative_to(ROOT)}:{n}" for file in PROMPT_CODE
               for n, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1)
               if re.search(r"""[\["']examples["']\]?|\.get\(["']examples["']""", line) and not line.lstrip().startswith("#")]
    assert not readers, "the schema's examples are for the human page; prompt code must not read them: " + ", ".join(readers)
