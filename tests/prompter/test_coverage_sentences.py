"""C1 item 5 (from A6): no value runs into the next sentence, and there is no doubled stop. Every field is rendered with a value that ends without
a full stop and with one, in every call that carries it; then the full prompts of every valid contract vector are scanned for a lower-case word
followed straight by a capitalised word with no punctuation or line end between them, other than a name of a person or a place. No model."""
import re
from pathlib import Path

import pytest

from test_coverage_support import VECTORS, Ref, allowlist, is_number, placements, prompts, schema_fields, sentinel

FIELDS = [f for f in schema_fields() if not f.is_list and f.id not in allowlist() and not f.options and not is_number(f)]
NAMES = {"name", "term", "tie_from", "tie_to", "holdee", "held_by", "protagonist", "where", "cast", "spotlight"}      # a name may sit before a capital
FREE = [f for f in FIELDS if (f.item or f.key) not in NAMES]
CALLS = ("fill", "judge", "style_fit", "plan", "generate")


def after_value(text: str, value: str):
    for m in re.finditer(re.escape(value), text, flags=re.I):
        yield text[m.end():m.end() + 12]


@pytest.mark.parametrize("ref", FREE, ids=lambda f: f.id)
def test_a_value_ends_cleanly_with_or_without_a_full_stop(ref):
    base = sentinel(ref)
    seen = 0
    for ends_with_stop in (False, True):
        value = base + ("." if ends_with_stop else "")
        for p in placements(ref, value):
            for step, text in prompts(p.call, p.request).items():
                for tail in after_value(text, value if not ends_with_stop else value):
                    seen += 1
                    where = f"{ref.id} ({'with' if ends_with_stop else 'without'} a stop) in the {p.call} call, step {step}: {tail!r}"
                    if ends_with_stop:
                        assert not re.match(r"[\"'”’)\]]*[.!?…,;:]", tail), f"doubled stop: {where}"
                    else:
                        assert not re.match(r"[\"'”’)\]]*[ \t]+[A-Z]", tail), f"runs into the next sentence: {where}"
    assert seen, f"{ref.id} was shown nowhere to check"


def test_the_checker_catches_a_run_on_and_a_doubled_stop():
    assert not re.match(r"[\"'”’)\]]*[.!?…,;:]", " Next") and re.match(r"[\"'”’)\]]*[ \t]+[A-Z]", " Next")
    assert re.match(r"[\"'”’)\]]*[.!?…,;:]", "..")


def words_of_names(node, out: set[str]) -> set[str]:
    if isinstance(node, dict):
        for key, v in node.items():
            if key in ("name", "term", "where", "when", "when_time", "tie_from", "tie_to") and isinstance(v, str):
                out.update(re.findall(r"[A-Z][\w'’-]*", v))
            words_of_names(v, out)
    elif isinstance(node, list):
        for v in node:
            words_of_names(v, out)
    return out


ROOT = Path(__file__).resolve().parents[2]


def authored_names() -> set[str]:
    """The capitalised words the wording files themselves put after a lower-case word: card names ("the Setup card") and the invented people and
    places in their examples ("Odile was hired by Corrin"). They are authored text, not a value joined to a template; a value is checked below."""
    out: set[str] = set()
    for folder in ("pulpermill/schema/text/en", "pulpermill/prompter/mill/text/en", "pulpermill/prompts/text/en"):
        for path in (ROOT / folder).glob("*.yaml"):
            out.update(m.group(2) for m in re.finditer(r"(?<![\w'’-])([a-z][a-z'’-]*) ([A-Z][\w'’-]*)", path.read_text(encoding="utf-8")))
    return out


ALWAYS = {"I", "JSON", "Act", "English", "Chinese", "Simplified", "Traditional", "Han", "Gemma", "NOTE", "Style", "Characters", "Character", "World",
          "Entanglements", "Setup", "Outline"}
VECTOR_REQUESTS = [v for v in VECTORS if v["valid"] and v["data"].get("call") in CALLS]


@pytest.mark.parametrize("vector", VECTOR_REQUESTS, ids=lambda v: v["name"][:70])
def test_no_full_prompt_of_a_contract_vector_runs_a_lower_case_word_into_a_capital(vector):
    request = vector["data"]
    allowed = words_of_names(request, ALWAYS | authored_names())
    bad = []
    for step, text in prompts(request["call"], request).items():
        for m in re.finditer(r"(?<![\w'’-])([a-z][a-z'’-]*) ([A-Z][\w'’-]*)", text):
            if m.group(2) not in allowed:
                bad.append((step, text[max(0, m.start() - 30):m.end() + 20].replace("\n", "⏎")))
    assert not bad, bad[:6]
