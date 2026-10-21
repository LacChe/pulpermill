import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  isFilled, isVisible, blankCard, groupedFields, ensureCard, setField, cardValues, newProject,
} from "../logic.js";
import { SUPPORTED_INPUTS } from "../render.js";

const schema = JSON.parse(readFileSync(new URL("../data/schema.en.json", import.meta.url), "utf8"));
const style = schema.cards.style;

test("isFilled treats empty strings, nulls and empty lists as empty", () => {
  for (const empty of [undefined, null, "", []]) assert.equal(isFilled(empty), false);
  for (const filled of ["a", 0, false, ["x"]]) assert.equal(isFilled(filled), true);
});

test("isVisible: no visible_if means always shown", () => {
  assert.equal(isVisible({ key: "a" }, {}), true);
});

test("isVisible: filled, exact value and list of values", () => {
  const filled = { visible_if: { reveal_rule: "filled" } };
  assert.equal(isVisible(filled, { reveal_rule: "r1" }), true);
  assert.equal(isVisible(filled, { reveal_rule: "" }), false);
  assert.equal(isVisible(filled, {}), false);
  const exact = { visible_if: { goal_change: "redefined" } };
  assert.equal(isVisible(exact, { goal_change: "redefined" }), true);
  assert.equal(isVisible(exact, { goal_change: "achieved" }), false);
  const many = { visible_if: { goal_change: ["achieved", "abandoned"] } };
  assert.equal(isVisible(many, { goal_change: "abandoned" }), true);
  assert.equal(isVisible(many, { goal_change: "redefined" }), false);
});

test("isVisible: every entry must hold", () => {
  const field = { visible_if: { a: "filled", b: "x" } };
  assert.equal(isVisible(field, { a: "1", b: "x" }), true);
  assert.equal(isVisible(field, { a: "1", b: "y" }), false);
});

test("every visible_if in the schema points at a sibling field", () => {
  for (const card of Object.values(schema.cards)) {
    const check = (fields) => {
      const keys = new Set(fields.map((f) => f.key));
      for (const f of fields) {
        for (const key of Object.keys(f.visible_if || {})) assert.ok(keys.has(key), `${card.id}.${f.key} -> ${key}`);
        if (f.item_fields) check(f.item_fields);
      }
    };
    check(card.fields);
  }
});

test("blankCard gives every Style field an empty string", () => {
  const blank = blankCard(style);
  assert.deepEqual(Object.keys(blank), style.fields.map((f) => f.key));
  assert.ok(Object.values(blank).every((v) => v === ""));
});

test("groupedFields keeps group order and every field exactly once", () => {
  const grouped = groupedFields(style);
  assert.deepEqual(grouped.map((g) => g.group.id), style.groups.map((g) => g.id));
  const keys = grouped.flatMap((g) => g.fields.map((f) => f.key));
  assert.deepEqual([...keys].sort(), style.fields.map((f) => f.key).sort());
});

test("groupedFields keeps a field whose group is unknown", () => {
  const card = { groups: [{ id: "a" }], fields: [{ key: "x", group: "a" }, { key: "y", group: "nope" }] };
  const grouped = groupedFields(card);
  assert.equal(grouped.length, 2);
  assert.equal(grouped[1].group, null);
  assert.equal(grouped[1].fields[0].key, "y");
});

test("ensureCard fills missing keys and never overwrites a value", () => {
  const project = newProject(schema);
  project.style = { person: "first" };
  ensureCard(project, style);
  assert.equal(project.style.person, "first");
  assert.equal(project.style.tense, "");
});

test("setField writes one value and leaves the rest", () => {
  const project = newProject(schema);
  ensureCard(project, style);
  setField(project, "style", "tense", "past");
  assert.equal(cardValues(project, "style").tense, "past");
  assert.equal(cardValues(project, "style").person, "");
});

test("the renderer can draw every Style field type, and every option has a description", () => {
  for (const f of style.fields) {
    assert.ok(SUPPORTED_INPUTS.has(f.input), `${f.key}: ${f.input}`);
    for (const o of f.options || []) assert.ok(o.description, `${f.key}.${o.value}`);
  }
});
