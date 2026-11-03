"""C1, design rule 1: every card value is used somewhere. For every field of every card in `pulpermill/schema/` (taken from the schema's own
models, item fields of lists included) a unique sentinel is put into a valid request of each call that can carry it, the mill flow is driven to
its prompts, and the test records which call and step shows it. A field that no call shows fails, unless `coverage_allowlist.yaml` lists it
as code-only with a reason. A choice is covered when every one of its options reaches a prompt as its explanatory sentence. No model, no network.

Set PULPERMILL_COVERAGE_TABLE=<path> to write the field-by-call table as markdown."""
import os
from pathlib import Path

import pytest

from test_coverage_support import Ref, allowlist, expected_text, schema_fields, shown_in, value_for

FIELDS = schema_fields()
ITEMS = [f for f in FIELDS if not f.is_list]
LISTS = [f for f in FIELDS if f.is_list]
ALLOWED = allowlist()


def where_shown(ref: Ref) -> dict[str, dict[str, list[str]]]:
    """{option or 'value': {call: [step names]}} for one field."""
    if ref.options:
        return {option: shown_in(ref, option, expected_text(ref, option, expand)) for option, expand in ref.options.items()}
    value = value_for(ref)
    return {"value": shown_in(ref, value, expected_text(ref, value))}


def test_the_schema_lists_the_cards_and_their_item_fields():
    ids = {f.id for f in FIELDS}
    assert {"style.genre", "characters.behaviors.tendency", "world.places.effect", "entanglements.ties.edge", "setup.chapter_count",
            "outline.beats.aim", "summary_events.entries.changed", "shifts.entries.patch"} <= ids
    assert all(f.item for f in FIELDS if not f.is_list and f.card in ("outline", "summary_events", "shifts"))      # those cards hold only lists


def test_the_allowlist_holds_only_real_code_only_fields_with_a_reason():
    ids = {f.id for f in FIELDS}
    assert ALLOWED, "the allowlist is empty, but the page-computed fields of the outline, events and shifts are code-only"
    for key, reason in ALLOWED.items():
        assert key in ids, f"{key} is not a field of any card (remove it from the allowlist)"
        assert isinstance(reason, str) and reason.startswith("code-only:") and len(reason.split()) >= 6, f"{key} needs a code-only reason"


@pytest.mark.parametrize("ref", [f for f in ITEMS if f.id in ALLOWED], ids=lambda f: f.id)
def test_an_allowlisted_field_really_is_never_shown(ref):
    shown = any(where_shown(ref).values())
    assert not shown, f"{ref.id} reaches a prompt, so it does not belong in the allowlist"


@pytest.mark.parametrize("ref", [f for f in ITEMS if f.id not in ALLOWED], ids=lambda f: f.id)
def test_rule1_every_card_value_reaches_at_least_one_prompt(ref):
    missing = [name for name, found in where_shown(ref).items() if not found]
    assert not missing, (f"{ref.id}: nothing the model reads shows {'these options' if ref.options else 'the value'}: {missing}. "
                         f"Show it in a call's prompt, or add the field to coverage_allowlist.yaml as code-only with a reason.")


@pytest.mark.parametrize("ref", LISTS, ids=lambda f: f.id)
def test_rule1_every_list_is_covered_through_its_item_fields(ref):
    items = [f for f in ITEMS if (f.card, f.key) == (ref.card, ref.key)]
    assert items, f"{ref.id} has no item fields"
    if ref.id in ALLOWED:
        assert all(f.id in ALLOWED for f in items), f"{ref.id} is allowlisted but some of its items are not"
    else:
        assert any(f.id not in ALLOWED for f in items), f"{ref.id} is covered only through items that are all allowlisted"
        assert not [f.id for f in items if f.id in ALLOWED and any(where_shown(f).values())]


def test_the_coverage_table_lists_every_field_and_the_calls_that_carry_it():
    rows = []
    for ref in FIELDS:
        if ref.is_list:
            continue
        if ref.id in ALLOWED:
            rows.append((ref.id, "—", "code-only: " + ALLOWED[ref.id].split(":", 1)[1].strip()))
            continue
        calls: dict[str, set[str]] = {}
        for found in where_shown(ref).values():
            for call, steps in found.items():
                calls.setdefault(call, set()).update(s.split("#")[0] for s in steps)
        rows.append((ref.id, ", ".join(f"{c} ({'/'.join(sorted(s))})" for c, s in sorted(calls.items())) or "NOT SHOWN", ""))
    assert len(rows) == len(ITEMS) and not [r for r in rows if r[1] == "NOT SHOWN"]
    target = os.environ.get("PULPERMILL_COVERAGE_TABLE")
    if target:
        lines = ["| Card field | Call (step) that shows it | Note |", "| --- | --- | --- |"]
        lines += [f"| `{field}` | {calls} | {note} |" for field, calls, note in rows]
        Path(target).write_text("\n".join(lines) + "\n", encoding="utf-8")
