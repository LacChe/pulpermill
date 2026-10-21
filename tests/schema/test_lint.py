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


# ---------------------------------------------------------------- UI wording (human-only, never sent to the model)
# Cards whose UI wording is finished. A card listed here must give every option a description and every free-text
# field a placeholder. Add a card to this set when its wording is written.
UI_DONE = {"style", "characters", "world"}
FIELD_UI = {"placeholder", "why", "examples", "empty", "add", "delete_confirm", "item_title", "visible_if"}
FIELD_KEYS = FIELD_UI | {"label", "help", "options", "item_fields", "expand", "lead_in", "item_template", "item_join"}
OPTION_KEYS = {"label", "expand", "description"}


def _targets(model, text):
    """Every (name, schema field, text entry), list item fields included."""
    for n, f in fields_of(model).items():
        yield n, f, text["fields"][n]
        if is_list_field(f):
            for sn, sf in item_fields(f).items():
                yield sn, sf, text["fields"][n]["item_fields"][sn]


@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_ui_wording_uses_known_keys_and_sensible_values(cid, lang):
    model = card(cid)[0]
    text = load_text(cid, lang)
    for n, f, t in _targets(model, text):
        unknown = set(t) - FIELD_KEYS
        assert not unknown, (n, unknown)
        meta = f.json_schema_extra
        for key in ("placeholder", "why", "empty", "add", "delete_confirm"):
            if key in t:
                assert isinstance(t[key], str) and t[key].strip(), (n, key)
                assert not tokens(t[key]), (n, key, "no tokens in plain UI text")
        if "placeholder" in t:
            assert meta["input"] in ("text", "textarea", "number"), (n, "placeholder only on typed fields")
        for key in ("empty", "add", "delete_confirm", "item_title"):
            if key in t:
                assert is_list_field(f), (n, key, "list wording only on repeating lists")
        if "item_title" in t:
            assert t["item_title"].strip() and tokens(t["item_title"]) and tokens(t["item_title"]) <= set(item_fields(f)), n
        if "examples" in t:
            ex = t["examples"]
            assert set(ex) == {"good", "avoid"}, n
            assert all(isinstance(v, list) and v and all(isinstance(s, str) and s for s in v) for v in ex.values()), n
        for value, o in t.get("options", {}).items():
            assert not set(o) - OPTION_KEYS, (n, value)
            if "description" in o:
                assert o["description"].strip() and o["description"] != o["label"] and o["description"] != o["expand"], (n, value)


@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_why_lines_are_not_repeated_or_copies_of_help(cid, lang):
    text = load_text(cid, lang)
    whys = [(n, t["why"]) for n, _, t in _targets(card(cid)[0], text) if "why" in t]
    assert len({w for _, w in whys}) == len(whys), "two fields share one 'why' line"
    for n, f, t in _targets(card(cid)[0], text):
        if "why" in t:
            assert t["why"] != t["help"], n


@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_finished_cards_describe_every_option_and_typed_field(cid, lang):
    if cid not in UI_DONE:
        pytest.skip("UI wording not written yet")
    text = load_text(cid, lang)
    for n, f, t in _targets(card(cid)[0], text):
        meta = f.json_schema_extra
        for value, o in t.get("options", {}).items():
            assert o.get("description"), (n, value)
        if is_list_field(f):
            for key in ("empty", "add", "delete_confirm", "item_title"):
                assert t.get(key), (n, key)
        if meta["input"] in ("text", "textarea", "number") and meta["kind"] in ("note", "free"):
            assert t.get("placeholder"), n


@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_ui_wording_never_repeats_model_text(cid, lang):
    """Nothing shown to the user may repeat text that is written for the model."""
    text = load_text(cid, lang)
    model_text = set()
    for _, _, t in _targets(card(cid)[0], text):
        model_text |= {t[k] for k in ("lead_in", "item_template") if k in t}
        model_text |= {o["expand"] for v, o in t.get("options", {}).items() if o["expand"] != v}
    shown = []
    for _, _, t in _targets(card(cid)[0], text):
        shown += [t[k] for k in ("placeholder", "why", "empty", "add", "delete_confirm") if k in t]
        shown += [o["description"] for o in t.get("options", {}).values() if "description" in o]
    assert not set(shown) & model_text


def _siblings(model, text):
    """(list name, item field name) -> (schema field, text entry), plus the option values of each sibling."""
    for n, f in fields_of(model).items():
        if is_list_field(f):
            yield n, item_fields(f), text["fields"][n]["item_fields"]


@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_visible_if_points_at_sibling_fields_and_real_options(cid, lang):
    model = card(cid)[0]
    text = load_text(cid, lang)
    for n, f, t in _targets(model, text):
        if "visible_if" not in t:
            continue
        cond = t["visible_if"]
        assert isinstance(cond, dict) and cond, n
    for list_name, schema_items, text_items in _siblings(model, text):
        for item_name, t in text_items.items():
            for key, wanted in (t.get("visible_if") or {}).items():
                assert key in schema_items and key != item_name, (list_name, item_name, key)
                allowed = set(options_of(schema_items[key]))
                wanted = wanted if isinstance(wanted, list) else [wanted]
                assert allowed and set(wanted) <= allowed, (list_name, item_name, key)


@pytest.mark.parametrize("cid,lang", CASES, ids=CASE_IDS)
def test_a_field_shown_only_sometimes_matches_the_block_rule_that_requires_it(cid, lang):
    """If code requires a field only when another has some value, the form must show it in exactly that case."""
    if cid not in UI_DONE:
        pytest.skip("UI wording not written yet")
    model, _, _, rules, _ = card(cid)
    text = load_text(cid, lang)
    for r in rules:
        if r.check != "required_if":
            continue
        for list_name, _, text_items in _siblings(model, text):
            target = text_items.get(r.params["field"])
            if target is not None:
                assert target.get("visible_if") == r.params["when"], r.id
