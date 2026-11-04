"""The web data file is built from the schema and text files. These tests keep the committed copy honest."""
import json
import pytest
from helpers import *
from tools import build_schema


def walk(node):
    """Every dict key and string value in a nested structure."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)
    elif isinstance(node, str):
        yield node


@pytest.mark.parametrize("lang", LANGS)
def test_committed_data_is_up_to_date(lang):
    path = build_schema.OUT_DIR / f"schema.{lang}.json"
    assert path.exists(), f"missing {path}: run python tools/build_schema.py"
    assert path.read_text(encoding="utf-8") == build_schema.render(build_schema.build(lang)), \
        f"{path.name} is out of date: run python tools/build_schema.py"


@pytest.mark.parametrize("lang", LANGS)
def test_no_model_only_text_reaches_the_page(lang):
    data = build_schema.build(lang)
    keys = {x for x in walk(data)}
    assert not keys & build_schema.MODEL_ONLY
    # No model-facing wording either: none of the option expansions or judge prompts may appear as a value.
    leaked = set()
    for cid in CARD_IDS:
        t = load_text(cid, lang)
        for f in t.get("fields", {}).values():
            groups = [f.get("options", {})] + [sub.get("options", {}) for sub in f.get("item_fields", {}).values()]
            for options in groups:
                # An expansion that is the same word as its option value (knows, suspects) is allowed to appear.
                leaked |= {o["expand"] for value, o in options.items() if o["expand"] != value}
        leaked |= {r["judge_prompt"] for r in t.get("rules", {}).values() if "judge_prompt" in r}
    assert leaked and not leaked & {x for x in walk(data)}


@pytest.mark.parametrize("lang", LANGS)
def test_only_user_cards_are_included_in_chain_order(lang):
    data = build_schema.build(lang)
    expected = [cid for cid in CARD_IDS if not card(cid)[4].get("hidden")]
    assert data["order"] == expected == list(data["cards"])


@pytest.mark.parametrize("lang", LANGS)
def test_fields_keep_declaration_order_and_required_comes_from_the_schema(lang):
    data = build_schema.build(lang)
    for cid, c in data["cards"].items():
        model = card(cid)[0]
        assert [f["key"] for f in c["fields"]] == list(fields_of(model))
        for f in c["fields"]:
            assert f["required"] == model.model_fields[f["key"]].is_required(), f"{cid}.{f['key']}"


@pytest.mark.parametrize("lang", LANGS)
def test_choices_rules_and_groups_are_complete(lang):
    data = build_schema.build(lang)
    for cid, c in data["cards"].items():
        group_ids = {g["id"] for g in c["groups"]}
        keys = {f["key"] for f in c["fields"]}
        for f in c["fields"]:
            assert f.get("group") in group_ids, f"{cid}.{f['key']}"
            for sub in [f] + f.get("item_fields", []):
                if sub["input"] in ("select", "select-multiple"):
                    assert bool(sub.get("options")) != bool(sub.get("ref")), f"{cid}.{sub['key']}"
        for r in c["rules"]:
            assert set(r["fields"]) <= keys, r["id"]
            assert r["message"], r["id"]
