"""Structure and text lint for every card, in every language. Holds no design decisions:
those are pinned separately in test_decisions.py."""
import pytest
from helpers import *
from pulpermill.schema.common import Item, MAX_ITEMS


# ---------------------------------------------------------------- structure only
@pytest.mark.parametrize("cid", CARD_IDS)
def test_lists_are_items_with_ids_and_caps_follow_the_policy(cid):
    for n, f in fields_of(card(cid)[0]).items():
        meta = f.json_schema_extra
        if is_list_field(f):
            assert meta["input"] is None and meta["kind"] in ("items", "pairs")
            assert issubclass(item_model(f), Item), n
            if meta.get("uncapped"):
                assert (cid, n) in UNCAPPED and "max_items" not in meta and not f.metadata, n
            else:
                assert meta["max_items"] == MAX_ITEMS and [m.max_length for m in f.metadata] == [MAX_ITEMS], n
        else:
            assert (cid, n) not in UNCAPPED, n


@pytest.mark.parametrize("cid", CARD_IDS)
def test_input_types_are_html_and_selects_have_choices_or_a_ref(cid):
    for n, f in all_fields(card(cid)[0]):
        meta = f.json_schema_extra
        if meta["kind"] == "snapshot":
            continue
        assert meta["input"] in ALLOWED_INPUTS, n
        is_choice = meta["input"] in ("select", "select-multiple")
        assert is_choice == (bool(options_of(f)) or "ref" in meta), n
        if "ref" in meta:
            assert not options_of(f), n


@pytest.mark.parametrize("cid", CARD_IDS)
def test_refs_point_at_real_sources(cid):
    valid = ref_sources()
    for n, f in all_fields(card(cid)[0]):
        meta = f.json_schema_extra
        if "ref" in meta:
            assert meta["ref"] and set(meta["ref"]) <= valid, n
        if "ref_filter_by" in meta:
            assert "ref" in meta, n


@pytest.mark.parametrize("cid", CARD_IDS)
def test_live_fields_only_on_mutable_cards(cid):
    model, _, _, _, meta = card(cid)
    flagged = [n for n, f in all_fields(model) if f.json_schema_extra.get("changes")]
    assert bool(flagged) == (meta["between_chapters"] == "mutable")


@pytest.mark.parametrize("cid", CARD_IDS)
def test_rules_are_well_formed(cid):
    model, _, _, rules, _ = card(cid)
    names = {sn for n, f in fields_of(model).items() if is_list_field(f) for sn in item_fields(f)}
    assert len({r.id for r in rules}) == len(rules)
    for r in rules:
        assert (r.needs_model and not r.check) or (not r.needs_model and r.check), r.id
        assert r.severity == "warn" or (r.severity == "block" and r.check in BLOCK_CHECKS), r.id
        assert set(r.fields) <= set(fields_of(model)), r.id
        for key in ("field", "when_present", "group_by"):
            if key in r.params:
                assert r.params[key] in names, (r.id, key)
        assert set(r.params.get("fields", [])) <= names, r.id
        for key in ("when", "unless"):
            assert set(r.params.get(key, {})) <= names, (r.id, key)


def test_snapshots_point_at_a_registered_card():
    for cid in CARD_IDS:
        for n, f in all_fields(card(cid)[0]):
            if f.json_schema_extra["kind"] == "snapshot":
                assert f.annotation is CARDS[f.json_schema_extra["snapshot_of"]][0], n


@pytest.mark.parametrize("cid", CARD_IDS)
def test_hidden_records_are_replaced_per_chapter(cid):
    meta = card(cid)[4]
    if meta["type"] == "record":
        assert meta["hidden"] and meta["between_chapters"] == "per_chapter"


# ---------------------------------------------------------------- text, per language
@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_text_covers_exactly_the_fields_groups_and_rules(cid, lang):
    model, groups, order, rules, meta = card(cid)
    text = load_text(cid, lang)
    fields = fields_of(model)
    assert set(text["fields"]) == set(fields)
    assert {g["id"] for g in groups} == {f.json_schema_extra["group"] for f in fields.values()} == set(text["groups"])
    assert set(text["rules"]) == {r.id for r in rules}
    assert text["card"]["label"] and text["card"]["summary"]
    for g in text["groups"].values():
        assert g["label"] and g["help"]
    if meta.get("sent_to_model", True):
        assert sorted(n for p in order for n in p) == sorted(fields)
    else:
        assert order == []


@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_every_label_help_and_choice_has_text(cid, lang):
    model, _, _, _, _ = card(cid)
    text = load_text(cid, lang)
    for n, f in fields_of(model).items():
        ft = text["fields"][n]
        assert ft["label"] and ft["help"], n
        if is_list_field(f):
            assert set(ft["item_fields"]) == set(item_fields(f)), n
            targets = {sn: (sf, ft["item_fields"][sn]) for sn, sf in item_fields(f).items()}
        else:
            targets = {n: (f, ft)}
        for tn, (tf, tt) in targets.items():
            assert tt["label"] and tt["help"], tn
            meta = tf.json_schema_extra
            if "ref" in meta or meta["kind"] == "snapshot":
                assert "options" not in tt, tn
            elif meta["input"] in ("select", "select-multiple"):
                assert set(tt["options"]) == set(options_of(tf)), tn
                assert all(o["label"] and o["expand"] for o in tt["options"].values()), tn


@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_templates_use_only_known_tokens(cid, lang):
    model, _, _, _, meta = card(cid)
    if not meta.get("sent_to_model", True):
        return
    text = load_text(cid, lang)
    base = {"value", "items"} | ({"name"} if "name" in fields_of(model) else set())
    for n, f in fields_of(model).items():
        fm, ft = f.json_schema_extra, text["fields"][n]
        if fm["kind"] == "free":
            assert "value" in tokens(ft["lead_in"]) and tokens(ft["lead_in"]) <= base, n
        if fm["kind"] in ("items", "pairs"):
            names = set(item_fields(f))
            assert "items" in tokens(ft["lead_in"]) and tokens(ft["lead_in"]) <= base, n
            assert tokens(ft["item_template"]) and tokens(ft["item_template"]) <= names and ft["item_join"], n
            for sn, it in ft["item_fields"].items():
                for o in it.get("options", {}).values():
                    assert tokens(o["expand"]) <= names, (n, sn)
        for o in ft.get("options", {}).values():
            assert tokens(o["expand"]) <= base, n


@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_every_rule_has_wording(cid, lang):
    for r in card(cid)[3]:
        t = load_text(cid, lang)["rules"][r.id]
        assert t["message"] and t["fix"], r.id
        assert bool(t.get("judge_prompt")) == r.needs_model, r.id


@pytest.mark.parametrize("lang", LANGS)
def test_common_messages(lang):
    common = load_common(lang)
    assert set(common) == COMMON_KEYS
    assert all(v["message"] and v["fix"] for v in common.values())


def test_other_languages_match_english_keys_and_tokens():
    """Same keys everywhere, and every {token} in a template is unchanged by translation."""
    def walk(a, b, path):
        assert type(a) is type(b), path
        if isinstance(a, dict):
            assert set(a) == set(b), path
            for k in a:
                walk(a[k], b[k], f"{path}/{k}")
        elif isinstance(a, str):
            assert tokens(a) == tokens(b), path
    for lang in [l for l in LANGS if l != "en"]:
        walk(load_common("en"), load_common(lang), f"{lang}/common")
        for cid in CARD_IDS:
            walk(load_text(cid, "en"), load_text(cid, lang), f"{lang}/{cid}")
