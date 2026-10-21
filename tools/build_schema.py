"""Build the data file the web page renders its forms from.

Reads the Pydantic cards (structure and declared rules) and the text/<lang>/ files (wording) and writes one
JSON file per language to web/data/schema.<lang>.json. The page reads only this file and hard-codes nothing:
not the fields, not the groups, not which fields are required.

What goes in, and what stays out:
  in   structure the form needs (input type, group, required, repeat, ref, caps, flags), human-facing text
       (label, help, option labels, rule messages and fixes), and the rule declarations the browser checks
  out  everything that is only for the model (expand, lead_in, item_template, item_join, judge_prompt) and the
       hidden pipeline records (Events, Shifts, Entanglements history), which the user never sees

Run from the repo root:  python tools/build_schema.py
The tests fail if the committed files are out of date, so run it after any change to schema/ or text/.
"""
import json
import pathlib
import sys
from typing import get_args

import yaml
from pydantic_core import PydanticUndefined

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pulpermill.schema import CARDS  # noqa: E402
from pulpermill.schema.common import MAX_ITEMS  # noqa: E402
from pulpermill.schema.project import SCHEMA_VERSION  # noqa: E402

TEXT_DIR = REPO / "pulpermill" / "schema" / "text"
OUT_DIR = REPO / "web" / "data"

# Text that only the model reads. It never goes into the web data.
MODEL_ONLY = {"expand", "lead_in", "item_template", "item_join", "judge_prompt"}

# Optional UI wording the text files may add (phase 3). Copied through when present, so adding
# a key to the yaml needs no change here. The page must treat every one of them as optional.
FIELD_UI_KEYS = ["placeholder", "why", "examples", "empty", "add", "delete_confirm", "item_title", "visible_if"]
OPTION_UI_KEYS = ["description"]

# Structure flags copied from the field's declaration when set.
FLAGS = ["ref", "ref_filter_by", "ref_where", "changes", "fixed", "counted", "filled_by", "limited_by",
         "max_selected", "max_items", "uncapped", "repeat"]


def literal_values(annotation):
    """The allowed string values of a field, including inside Optional[Literal[...]]."""
    out = []
    for a in get_args(annotation):
        out += [a] if isinstance(a, str) else literal_values(a)
    return out


def build_field(key, field, text, group_ids):
    meta = field.json_schema_extra
    out = {"key": key, "label": text.get("label", key), "help": text.get("help", "")}
    out["input"] = meta["input"]
    out["kind"] = meta["kind"]
    if meta.get("group") is not None:
        assert meta["group"] in group_ids, f"{key}: unknown group {meta['group']}"
        out["group"] = meta["group"]
    out["required"] = field.is_required()
    if not field.is_required() and field.default is not PydanticUndefined and field.default is not None:
        out["default"] = field.default
    for flag in FLAGS:
        if flag in meta:
            out[flag] = meta[flag]
    for k in FIELD_UI_KEYS:
        if k in text:
            out[k] = text[k]

    options = literal_values(field.annotation) if meta["input"] in ("select", "select-multiple") else []
    if options:
        option_text = text.get("options", {})
        out["options"] = []
        for value in options:
            o = {"value": value, "label": option_text.get(value, {}).get("label", value)}
            for k in OPTION_UI_KEYS:
                if k in option_text.get(value, {}):
                    o[k] = option_text[value][k]
            out["options"].append(o)

    item_model = get_item_model(field)
    if item_model is not None:
        item_text = text.get("item_fields", {})
        out["item_fields"] = [build_field(n, f, item_text.get(n, {}), set())
                              for n, f in item_model.model_fields.items() if n != "id"]
    return out


def get_item_model(field):
    """The item model of a repeating list, or None for any other field."""
    if not (field.json_schema_extra or {}).get("repeat"):
        return None
    return get_args(field.annotation)[0]


def build_card(cid, lang_text, common):
    model, groups, _render_order, rules, meta = CARDS[cid]
    text = lang_text[cid]
    group_text = text.get("groups", {})
    group_ids = {g["id"] for g in groups}

    card = {k: meta[k] for k in ("id", "type", "reads", "portable", "between_chapters") if k in meta}
    if meta.get("many_per_project"):
        card["many_per_project"] = True
    card["label"] = text["card"]["label"]
    card["summary"] = text["card"]["summary"]
    card["groups"] = [{"id": g["id"], "collapsed": g["collapsed"],
                       "label": group_text.get(g["id"], {}).get("label", g["id"]),
                       "help": group_text.get(g["id"], {}).get("help", "")} for g in groups]
    field_text = text.get("fields", {})
    card["fields"] = [build_field(n, f, field_text.get(n, {}), group_ids)
                      for n, f in model.model_fields.items() if n != "id"]

    rule_text = text.get("rules", {})
    card["rules"] = []
    for r in rules:
        t = rule_text.get(r.id, {})
        card["rules"].append({"id": r.id, "severity": r.severity, "fields": r.fields,
                              "check": r.check, "params": r.params, "context": r.context,
                              "needs_model": r.needs_model,
                              "message": t.get("message", ""), "fix": t.get("fix", "")})

    module = sys.modules[model.__module__]
    if hasattr(module, "HOLDING_PAIRS"):                     # the table that decides who may hold what
        card["holding_pairs"] = module.HOLDING_PAIRS
    return card


def build(lang):
    lang_dir = TEXT_DIR / lang
    lang_text = {cid: yaml.safe_load((lang_dir / f"{cid}.yaml").read_text(encoding="utf-8")) for cid in CARDS}
    common = yaml.safe_load((lang_dir / "common.yaml").read_text(encoding="utf-8"))
    visible = [cid for cid in CARDS if not CARDS[cid][4].get("hidden")]
    return {
        "schema_version": SCHEMA_VERSION,
        "lang": lang,
        "max_items": MAX_ITEMS,
        "common": common,                                      # messages for the built-in reject and block rules
        "order": visible,                                      # the chain, in the order the cards are filled in
        "cards": {cid: build_card(cid, lang_text, common) for cid in visible},
    }


def languages():
    return sorted(p.name for p in TEXT_DIR.iterdir() if p.is_dir())


def render(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for lang in languages():
        path = OUT_DIR / f"schema.{lang}.json"
        path.write_text(render(build(lang)), encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
