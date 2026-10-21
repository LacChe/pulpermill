import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  isFilled, isVisible, blankCard, groupedFields, ensureCard, newProject, newId, blankItem, canAdd, addItem,
  removeItem, isItemEmpty, fillTemplate, itemTitle, addInstance, removeInstance, findInstance, instanceName,
  refOptions, sourceOfId, pickerSources, blockedValues, lookupLabel, oneOfChoice, chooseOneOf, fieldShown,
  inOneOf, showsOptionalTag,
} from "../logic.js";
import { isSupported } from "../render.js";

const schema = JSON.parse(readFileSync(new URL("../data/schema.en.json", import.meta.url), "utf8"));
const style = schema.cards.style;
const characters = schema.cards.characters;
const world = schema.cards.world;
const ent = schema.cards.entanglements;
const entList = (key) => ent.fields.find((f) => f.key === key);
const entItem = (list, key) => entList(list).item_fields.find((f) => f.key === key);

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

test("the renderer can draw every Style, Characters, World and Entanglements field, and every option has a description", () => {
  for (const card of [style, characters, world, ent]) {
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

const sample = () => ({
  characters: [{ id: "c1", name: "Ines" }, { id: "c2", name: "" }],
  world: {
    powers: [{ id: "p1", name: "The Guild" }],
    objects: [{ id: "o1", name: "The ledger" }],
    places: [{ id: "pl1", name: "The print shop" }],
    rules: [{ id: "r1", statement: "Ink never dries in the east wing" }],
  },
});

test("refOptions lists entries of each source in order, with names or the unnamed word", () => {
  const options = refOptions(sample(), ["characters", "world.powers"], "Unnamed");
  assert.deepEqual(options.map((o) => [o.value, o.label, o.source]), [
    ["c1", "Ines", "characters"], ["c2", "Unnamed", "characters"], ["p1", "The Guild", "world.powers"],
  ]);
  assert.equal(refOptions(sample(), ["world.rules"])[0].label, "Ink never dries in the east wing");
  assert.deepEqual(refOptions({}, ["characters", "world.places"]), []);
});

test("sourceOfId finds which list an id is in", () => {
  assert.equal(sourceOfId(sample(), ["world.objects", "world.places"], "pl1"), "world.places");
  assert.equal(sourceOfId(sample(), ["world.objects", "world.places"], "nope"), null);
});

test("holders are filtered by what is being held", () => {
  const heldBy = entItem("holdings", "held_by");
  const siblings = entList("holdings").item_fields;
  const project = sample();
  assert.deepEqual(pickerSources(heldBy, { holdee: "o1" }, siblings, project, ent), ["characters", "world.powers", "world.places"]);
  assert.deepEqual(pickerSources(heldBy, { holdee: "pl1" }, siblings, project, ent), ["characters", "world.powers"]);
  assert.deepEqual(pickerSources(heldBy, { holdee: "" }, siblings, project, ent), heldBy.ref);
});

test("a tie's two ends block each other's choice", () => {
  const ties = entList("ties");
  const from = entItem("ties", "tie_from");
  const to = entItem("ties", "tie_to");
  assert.deepEqual(blockedValues(ent, ties, from, { tie_from: "", tie_to: "c1" }), ["c1"]);
  assert.deepEqual(blockedValues(ent, ties, to, { tie_from: "c1", tie_to: "" }), ["c1"]);
  assert.deepEqual(blockedValues(ent, ties, from, { tie_from: "", tie_to: "" }), []);
  assert.deepEqual(blockedValues(ent, entList("holdings"), entItem("holdings", "held_by"), { holdee: "o1" }), []);
});

test("lookupLabel: option label, linked name, or the stored value", () => {
  const project = sample();
  assert.equal(lookupLabel(project, entItem("knowledge", "status"), "misled"), "Misled");
  assert.equal(lookupLabel(project, entItem("ties", "tie_from"), "p1"), "The Guild");
  assert.equal(lookupLabel(project, entItem("ties", "bond"), "rivals"), "rivals");
});

test("item titles show names, not ids", () => {
  const project = sample();
  const lookup = (f, v) => lookupLabel(project, f, v);
  assert.equal(itemTitle(entList("ties"), { tie_from: "c1", tie_to: "p1" }, lookup), "Ines → The Guild");
  assert.equal(itemTitle(entList("holdings"), { holdee: "o1", held_by: "c1" }, lookup), "Ines holds The ledger");
  assert.equal(itemTitle(entList("knowledge"), { person: "c1", status: "knows", rule: "r1", fact: "" }, lookup),
    "Ines: Knows Ink never dries in the east wing");
});

test("either-or: the filled field is the choice; switching clears the other", () => {
  const owner = entList("pressures");
  const group = owner.one_of[0];
  const values = { source_agent: "", source_circumstance: "" };
  const memory = {};
  assert.equal(oneOfChoice(group, 0, values, memory), null);
  chooseOneOf(group, 0, values, memory, "source_agent");
  assert.equal(oneOfChoice(group, 0, values, memory), "source_agent");
  values.source_agent = "c1";
  chooseOneOf(group, 0, values, memory, "source_circumstance");
  assert.equal(values.source_agent, "");
  assert.equal(oneOfChoice(group, 0, values, memory), "source_circumstance");
});

test("either-or: only the chosen field is shown, and next move needs an agent", () => {
  const owner = entList("pressures");
  const agent = entItem("pressures", "source_agent");
  const circumstance = entItem("pressures", "source_circumstance");
  const nextMove = entItem("pressures", "next_move");
  const values = { source_agent: "", source_circumstance: "" };
  const memory = {};
  assert.equal(fieldShown(owner, agent, values, memory), false);
  assert.equal(fieldShown(owner, circumstance, values, memory), false);
  memory[0] = "source_agent";
  assert.equal(fieldShown(owner, agent, values, memory), true);
  assert.equal(fieldShown(owner, circumstance, values, memory), false);
  assert.equal(fieldShown(owner, nextMove, values, memory), false);
  values.source_agent = "c1";
  assert.equal(fieldShown(owner, nextMove, values, memory), true);
});

test("the Optional tag is not shown for either-or or conditional fields", () => {
  const owner = entList("pressures");
  assert.equal(inOneOf(owner, entItem("pressures", "source_agent")), true);
  assert.equal(showsOptionalTag(owner, entItem("pressures", "source_agent")), false);
  assert.equal(showsOptionalTag(owner, entItem("pressures", "next_move")), false);
  assert.equal(showsOptionalTag(null, { required: false }), true);
  assert.equal(showsOptionalTag(null, { required: true }), false);
});

test("every link field on Entanglements has a placeholder and an empty message", () => {
  for (const list of ent.fields) {
    for (const f of list.item_fields) {
      if (!f.ref) continue;
      assert.ok(f.no_options, `${list.key}.${f.key}`);
      if (f.input === "select") assert.ok(f.placeholder, `${list.key}.${f.key}`);
    }
  }
});

test("a title for an either-or pair shows whichever half is used", () => {
  const lookup = (f, v) => lookupLabel(sample(), f, v);
  assert.equal(itemTitle(entList("knowledge"), { person: "c1", status: "suspects", rule: "", fact: "the key is in the well" }, lookup),
    "Ines: Suspects the key is in the well");
  assert.equal(itemTitle(entList("knowledge"), { person: "c1", status: "", rule: "", fact: "" }, lookup), "Ines: …");
});

test("Setup: every field is supported, starts blank, and the protagonist picker has its empty message", () => {
  const setup = schema.cards.setup;
  for (const f of setup.fields) assert.ok(isSupported(f), f.key);
  const blank = blankCard(setup);
  assert.equal(blank.protagonist, "");
  assert.equal(blank.chapter_count, null);
  const lead = setup.fields.find((f) => f.key === "protagonist");
  assert.ok(lead.no_options && lead.placeholder);
});

const outline = schema.cards.outline;
const beatsField = outline.fields.find((f) => f.key === "beats");

test("Outline: every field is supported and every link field has an empty message", () => {
  assert.ok(isSupported(beatsField));
  for (const f of beatsField.item_fields) {
    if (f.ref) assert.ok(f.no_options, f.key);
  }
});

test("a beat added by hand takes the next chapter number", () => {
  const list = [];
  assert.equal(addItem(beatsField, list).chapter, 1);
  assert.equal(addItem(beatsField, list).chapter, 2);
  list[1].chapter = 7;
  assert.equal(addItem(beatsField, list).chapter, 8);
  assert.equal(itemTitle(beatsField, list[0]), "Chapter 1");
});

test("ref_where keeps only rules with the wanted status, and drops rules that already came to light", () => {
  const project = {
    world: { rules: [
      { id: "r1", statement: "Open secret", status: "common" },
      { id: "r2", statement: "Hidden", status: "uncommon" },
      { id: "r3", statement: "A myth", status: "false_belief" },
      { id: "r4", statement: "Already out", status: "uncommon" },
    ] },
    summary_events: { entries: [{ id: "e1", reveals_landed: ["r4"] }] },
  };
  const where = { status: ["uncommon", "false_belief"] };
  assert.deepEqual(refOptions(project, ["world.rules"], "Unnamed", { where }).map((o) => o.value), ["r2", "r3"]);
  assert.deepEqual(refOptions(project, ["world.rules"], "Unnamed", { where, keep: ["r4"] }).map((o) => o.value), ["r2", "r3", "r4"]);
  assert.equal(refOptions(project, ["world.rules"]).length, 4);
});

test("payoff offers only open plants, named by what was planted", () => {
  const project = { summary_events: { entries: [
    { id: "e1", planted: "A locked back room" },
    { id: "e2", planted: "A stranger's letter", paid_off: [] },
    { id: "e3", planted: "", paid_off: ["e1"] },
    { id: "e4", happened: "nothing planted" },
  ] } };
  assert.deepEqual(refOptions(project, ["summary_events.entries"]).map((o) => [o.value, o.label]), [["e2", "A stranger's letter"]]);
});

test("pressures are named by what they are", () => {
  const project = { entanglements: { pressures: [{ id: "p1", what: "The audit" }] } };
  assert.equal(refOptions(project, ["entanglements.pressures"])[0].label, "The audit");
});
