import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  isFilled, isVisible, blankCard, groupedFields, ensureCard, newProject, newId, blankItem, canAdd, addItem,
  removeItem, isItemEmpty, fillTemplate, itemTitle, addInstance, removeInstance, findInstance, instanceName,
} from "../logic.js";
import { isSupported } from "../render.js";

const schema = JSON.parse(readFileSync(new URL("../data/schema.en.json", import.meta.url), "utf8"));
const style = schema.cards.style;
const characters = schema.cards.characters;
const world = schema.cards.world;

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

test("the renderer can draw every Style, Characters and World field, and every option has a description", () => {
  for (const card of [style, characters, world]) {
    const check = (fields, where) => {
      for (const f of fields) {
        assert.ok(isSupported(f), `${where}.${f.key}`);
        for (const o of f.options || []) assert.ok(o.description, `${where}.${f.key}.${o.value}`);
        if (f.item_fields) check(f.item_fields, `${where}.${f.key}`);
      }
    };
    check(card.fields, card.id);
  }
});

test("newId makes eight hex characters and never repeats a taken id", () => {
  assert.match(newId(), /^[0-9a-f]{8}$/);
  let calls = 0;
  const random = () => (calls++ < 8 ? 0 : 0.5);   // first id "00000000", then "88888888"
  assert.equal(newId(["00000000"], random), "88888888");
});

test("blankCard for Characters: lists start empty, number starts null", () => {
  const blank = blankCard(characters);
  assert.deepEqual(blank.wants, []);
  assert.deepEqual(blank.behaviors, []);
  assert.equal(blank.age, null);
  assert.equal(blank.name, "");
});

test("blankItem has an id and an empty box for each item field", () => {
  const behaviors = characters.fields.find((f) => f.key === "behaviors");
  const item = blankItem(behaviors);
  assert.match(item.id, /^[0-9a-f]{8}$/);
  assert.equal(item.state, "");
  assert.equal(item.tendency, "");
});

test("lists are capped by max_items unless uncapped", () => {
  const wants = characters.fields.find((f) => f.key === "wants");
  assert.equal(wants.max_items, 5);
  const list = [];
  for (let i = 0; i < 5; i++) assert.ok(addItem(wants, list));
  assert.equal(canAdd(wants, list), false);
  assert.equal(addItem(wants, list), null);
  assert.equal(list.length, 5);
  assert.equal(canAdd({ uncapped: true }, list), true);
});

test("removeItem removes by id and leaves the others in order", () => {
  const list = [{ id: "a" }, { id: "b" }, { id: "c" }];
  removeItem(list, "b");
  assert.deepEqual(list.map((i) => i.id), ["a", "c"]);
  removeItem(list, "zzz");
  assert.equal(list.length, 2);
});

test("isItemEmpty ignores the id", () => {
  assert.equal(isItemEmpty({ id: "a", text: "" }), true);
  assert.equal(isItemEmpty({ id: "a", text: "x" }), false);
});

test("fillTemplate: all filled, partly filled, none filled", () => {
  const t = "when {state}, they {tendency}";
  assert.equal(fillTemplate(t, { state: "tired", tendency: "snap" }), "when tired, they snap");
  assert.equal(fillTemplate(t, { state: "tired", tendency: "" }), "when tired, they …");
  assert.equal(fillTemplate(t, { state: "", tendency: "" }), "");
});

test("fillTemplate resolves values through the lookup, lists joined with commas", () => {
  const names = { a: "Ines", b: "Tomas" };
  const resolve = (v) => names[v] ?? v;
  assert.equal(fillTemplate("{who} → {others}", { who: "a", others: ["a", "b"] }, resolve), "Ines → Ines, Tomas");
});

test("itemTitle uses the field's item_title", () => {
  const behaviors = characters.fields.find((f) => f.key === "behaviors");
  assert.equal(itemTitle(behaviors, { state: "calm", tendency: "hums" }), "when calm, they hums");
});

test("a card held many times is a list; instances can be added, found and removed", () => {
  const project = newProject(schema);
  ensureCard(project, characters);
  assert.deepEqual(project.characters, []);
  const a = addInstance(project, characters);
  const b = addInstance(project, characters);
  assert.notEqual(a.id, b.id);
  assert.equal(findInstance(project, characters, a.id), a);
  a.name = "  Ines ";
  assert.equal(instanceName(a), "Ines");
  assert.equal(instanceName(b), "");
  removeInstance(project, characters, a.id);
  assert.deepEqual(project.characters.map((i) => i.id), [b.id]);
});

test("ensureCard fills blanks inside saved instances and list items without overwriting", () => {
  const project = newProject(schema);
  project.characters = [{ id: "c1", name: "Ines", wants: [{ id: "w1", text: "be left alone" }], behaviors: [{ id: "b1", state: "calm" }] }];
  ensureCard(project, characters);
  const c = project.characters[0];
  assert.equal(c.name, "Ines");
  assert.equal(c.age, null);
  assert.equal(c.wants[0].text, "be left alone");
  assert.equal(c.behaviors[0].state, "calm");
  assert.equal(c.behaviors[0].tendency, "");
});

test("World: a rule's truth shows only for a false belief", () => {
  const rules = world.fields.find((f) => f.key === "rules");
  const truth = rules.item_fields.find((f) => f.key === "truth");
  assert.equal(isVisible(truth, { status: "false_belief" }), true);
  assert.equal(isVisible(truth, { status: "common" }), false);
  assert.equal(isVisible(truth, { status: "" }), false);
});

test("World: a new item of each list has an empty box for every item field", () => {
  for (const key of ["places", "objects", "powers", "rules", "terms"]) {
    const field = world.fields.find((f) => f.key === key);
    const item = blankItem(field);
    for (const f of field.item_fields) assert.equal(item[f.key], "", `${key}.${f.key}`);
  }
});

test("World: list items get a title from item_title", () => {
  const places = world.fields.find((f) => f.key === "places");
  assert.equal(itemTitle(places, { name: "The print shop" }), "The print shop");
  assert.equal(itemTitle(places, { name: "" }), "");
});
