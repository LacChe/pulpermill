"""Safety net for every translated text folder (everything under text/ except en).

A translation may change only what people read. It must keep the same files, the same keys at every depth, the
same {tokens} in every string, no empty values, and it must leave the model-facing keys as exact copies of the
English: the writer is told the target language in English, and prompts are not translated.
"""
import pytest
import yaml
from helpers import ROOT, LANGS, tokens

OTHER = [l for l in LANGS if l != "en"]
TEXT = ROOT / "text"

# Keys whose values go to the model. They stay English in every language folder.
MODEL_KEYS = {"expand", "lead_in", "lead_in_one", "item_template", "item_join", "judge_prompt"}


def files(lang):
    return sorted(p.name for p in (TEXT / lang).glob("*.yaml"))


def load(lang, name):
    return yaml.safe_load((TEXT / lang / name).read_text(encoding="utf-8"))


def walk(en, other, path, visit):
    """Parallel walk. Keys and list lengths must match; visit(path, key, en_value, other_value) sees every leaf."""
    assert type(en) is type(other), f"{path}: type differs"
    if isinstance(en, dict):
        assert set(en) == set(other), f"{path}: keys differ: {set(en) ^ set(other)}"
        for k in en:
            walk(en[k], other[k], f"{path}/{k}", lambda p, _k, a, b, key=k: visit(p, key if _k is None else _k, a, b))
    elif isinstance(en, list):
        assert len(en) == len(other), f"{path}: list length differs"
        for i, (a, b) in enumerate(zip(en, other)):
            walk(a, b, f"{path}[{i}]", visit)
    else:
        visit(path, None, en, other)


def test_there_is_at_least_one_translation():
    assert OTHER, "no language folder besides en"


@pytest.mark.parametrize("lang", OTHER)
def test_same_files_as_english(lang):
    assert files(lang) == files("en")


@pytest.mark.parametrize("lang", OTHER)
@pytest.mark.parametrize("name", files("en"))
def test_same_keys_tokens_and_no_empty_values(lang, name):
    problems = []

    def visit(path, key, en, other):
        if isinstance(en, str):
            if not isinstance(other, str):
                problems.append(f"{path}: not a string")
            elif not other.strip() and en.strip():
                problems.append(f"{path}: empty")
            elif tokens(en) != tokens(other):
                problems.append(f"{path}: tokens {sorted(tokens(en))} became {sorted(tokens(other))}")
        elif en != other:
            problems.append(f"{path}: {en!r} became {other!r}")

    walk(load("en", name), load(lang, name), f"{lang}/{name}", visit)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("lang", OTHER)
@pytest.mark.parametrize("name", files("en"))
def test_model_facing_keys_are_identical_to_english(lang, name):
    problems = []

    def visit(path, key, en, other):
        if key in MODEL_KEYS and en != other:
            problems.append(f"{path}: model-facing text was changed")

    walk(load("en", name), load(lang, name), f"{lang}/{name}", visit)
    assert not problems, "\n".join(problems)


def test_the_page_never_shows_a_model_facing_key():
    """The identical-copy rule is safe only while the page and the data builder drop these keys."""
    import sys
    sys.path.insert(0, str(ROOT.parents[1] / "tools"))
    import build_schema
    assert MODEL_KEYS <= build_schema.MODEL_ONLY
