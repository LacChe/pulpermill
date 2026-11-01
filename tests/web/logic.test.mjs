import "./text-setup.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  isFilled, isVisible, blankCard, groupedFields, ensureCard, newProject, newId, blankItem, canAdd, addItem,
  removeItem, isItemEmpty, fillTemplate, itemTitle, addInstance, removeInstance, findInstance, instanceName,
  refOptions, sourceOfId, pickerSources, blockedValues, lookupLabel, oneOfChoice, chooseOneOf, fieldShown,
  inOneOf, showsOptionalTag,
} from "../../web/logic.js";
import { isSupported } from "../../web/render.js";
import { story, opening } from "./fixture.mjs";
import { validate, ruleKind, modelRules, problemsFor, CHECKS, PENDING_CHECKS, similarity, SIMILARITY_LIMIT } from "../../web/logic.js";
import { filledPaths, problemPath, problemTriggers, shownProblems, problemCounts } from "../../web/logic.js";

const schema = JSON.parse(readFileSync(new URL("../../web/data/schema.en.json", import.meta.url), "utf8"));
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
  const filled = { visible_if: { sibling: "filled" } };
  assert.equal(isVisible(filled, { sibling: "r1" }), true);
  assert.equal(isVisible(filled, { sibling: "" }), false);
  assert.equal(isVisible(filled, {}), false);
  const exact = { visible_if: { mode: "redefined" } };
  assert.equal(isVisible(exact, { mode: "redefined" }), true);
  assert.equal(isVisible(exact, { mode: "achieved" }), false);
  const many = { visible_if: { mode: ["achieved", "abandoned"] } };
  assert.equal(isVisible(many, { mode: "abandoned" }), true);
  assert.equal(isVisible(many, { mode: "redefined" }), false);
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

test("World: a rule is how the world works: a statement, its cost and what happens when it is broken, with no status or truth", () => {
  const rules = world.fields.find((f) => f.key === "rules");
  assert.deepEqual(rules.item_fields.map((f) => f.key), ["statement", "cost", "when_broken"]);
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
  assert.equal(lookupLabel(project, entItem("ties", "tie_to"), "p1"), "The Guild");
  assert.equal(lookupLabel(project, entItem("ties", "tie_from"), "p1"), "The Guild");
  assert.equal(lookupLabel(project, entItem("ties", "bond"), "rivals"), "rivals");
});

test("item titles show names, not ids", () => {
  const project = sample();
  const lookup = (f, v) => lookupLabel(project, f, v);
  assert.equal(itemTitle(entList("ties"), { tie_from: "c1", tie_to: "p1" }, lookup), "Ines → The Guild");
  assert.equal(itemTitle(entList("holdings"), { holdee: "o1", held_by: "c1" }, lookup), "Ines holds The ledger");
});

// The schema no longer has an either-or pair, but the page still honours one_of when a card declares it, so these use a list of their own.
const eitherOr = {
  key: "things", one_of: [{ fields: ["by_person", "by_chance"], label: "Source", options: {} }],
  item_fields: [{ key: "by_person", required: false }, { key: "by_chance", required: false }, { key: "plain", required: false }, { key: "later", required: false, visible_if: { by_person: "filled" } }],
};
const eoField = (key) => eitherOr.item_fields.find((f) => f.key === key);

test("either-or: the filled field is the choice; switching clears the other", () => {
  const group = eitherOr.one_of[0];
  const values = { by_person: "", by_chance: "" };
  const memory = {};
  assert.equal(oneOfChoice(group, 0, values, memory), null);
  chooseOneOf(group, 0, values, memory, "by_person");
  assert.equal(oneOfChoice(group, 0, values, memory), "by_person");
  values.by_person = "c1";
  chooseOneOf(group, 0, values, memory, "by_chance");
  assert.equal(values.by_person, "");
  assert.equal(oneOfChoice(group, 0, values, memory), "by_chance");
});

test("either-or: only the chosen field is shown, and a conditional field needs its sibling", () => {
  const values = { by_person: "", by_chance: "" };
  const memory = {};
  assert.equal(fieldShown(eitherOr, eoField("by_person"), values, memory), false);
  assert.equal(fieldShown(eitherOr, eoField("by_chance"), values, memory), false);
  memory[0] = "by_person";
  assert.equal(fieldShown(eitherOr, eoField("by_person"), values, memory), true);
  assert.equal(fieldShown(eitherOr, eoField("by_chance"), values, memory), false);
  assert.equal(fieldShown(eitherOr, eoField("later"), values, memory), false);
  values.by_person = "c1";
  assert.equal(fieldShown(eitherOr, eoField("later"), values, memory), true);
  assert.equal(fieldShown(eitherOr, eoField("plain"), values, memory), true);
});

test("the Optional tag is not shown for either-or or conditional fields", () => {
  assert.equal(inOneOf(eitherOr, eoField("by_person")), true);
  assert.equal(inOneOf(eitherOr, eoField("plain")), false);
  assert.equal(showsOptionalTag(eitherOr, eoField("by_person")), false);
  assert.equal(showsOptionalTag(eitherOr, eoField("later")), false);
  assert.equal(showsOptionalTag(eitherOr, eoField("plain")), true);
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
  const field = { item_title: "{by_person}{by_chance}", item_fields: eitherOr.item_fields, one_of: eitherOr.one_of };
  assert.equal(itemTitle(field, { by_person: "", by_chance: "a storm" }), "a storm");
  assert.equal(itemTitle(field, { by_person: "Ines", by_chance: "" }), "Ines");
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

test("ref_where keeps only the entries whose key holds a wanted value; keep lets a saved choice stay", () => {
  const project = { world: { rules: [{ id: "r1", statement: "Open", kind: "a" }, { id: "r2", statement: "Hidden", kind: "b" }, { id: "r3", statement: "Myth", kind: "c" }] } };
  const where = { kind: ["b", "c"] };
  assert.deepEqual(refOptions(project, ["world.rules"], "Unnamed", { where }).map((o) => o.value), ["r2", "r3"]);
  assert.deepEqual(refOptions(project, ["world.rules"], "Unnamed", { where, keep: ["r1"] }).map((o) => o.value), ["r1", "r2", "r3"]);
  assert.equal(refOptions(project, ["world.rules"]).length, 3);
});

test("a link is named by the entry's name, statement or term, and unnamed ones by the given word", () => {
  const project = { world: { rules: [{ id: "r1", statement: "Debts are written" }], terms: [{ id: "t1", term: "toll" }], places: [{ id: "p1" }] } };
  assert.deepEqual(refOptions(project, ["world.rules", "world.terms", "world.places"], "?").map((o) => o.label), ["Debts are written", "toll", "?"]);
});

// ---- Validation ----

test("rules split into code rules (a named check) and model rules (needs_model), never both", () => {
  for (const card of Object.values(schema.cards)) {
    for (const rule of card.rules) {
      assert.equal(ruleKind(rule) === "model", Boolean(rule.needs_model), rule.id);
      assert.equal(Boolean(rule.check), !rule.needs_model, rule.id);
    }
  }
  assert.ok(modelRules(schema.cards.outline).every((r) => r.needs_model));
  assert.equal(modelRules(schema.cards.outline).length, 0);   // every outline rule is checked by code now
  assert.ok(modelRules(schema.cards.world).length > 0);
});

test("every check named in the schema has a function or is listed as pending, and nothing is listed twice", () => {
  const named = new Set(Object.values(schema.cards).flatMap((c) => c.rules.map((r) => r.check).filter(Boolean)));
  for (const name of named) assert.ok(name in CHECKS || PENDING_CHECKS.includes(name), name);
  for (const name of PENDING_CHECKS) assert.ok(named.has(name) && !(name in CHECKS), name);
});

test("an empty required field is reported as missing, at the field", () => {
  const setup = schema.cards.setup;
  const { problems } = validate(setup, blankCard(setup), {}, schema.common);
  assert.deepEqual(problems.map((p) => p.field).sort(), ["chapter_count", "disruption", "normal", "protagonist"]);
  assert.equal(problems[0].rule, "missing");
  assert.match(problems.find((p) => p.field === "normal").message, /^Normal is empty\./);
  const filled = { ...blankCard(setup), protagonist: "c1", normal: "a", disruption: "b", chapter_count: 12 };
  assert.deepEqual(validate(setup, filled, { characters: [{ id: "c1", name: "Ines" }] }, schema.common).problems.filter((p) => p.rule === "missing" || p.rule === "protagonist_link_broken"), []);
});

test("problems inside a list item name the list, the item and the field", () => {
  const list = [];
  const beat = addItem(beatsField, list);
  const values = { beats: list };
  const { problems } = validate(outline, values, {}, schema.common);
  const aim = problemsFor(problems, "beats", beat.id, "aim");
  assert.equal(aim.length, 1);
  assert.equal(aim[0].rule, "missing");
  assert.equal(problemsFor(problems, "beats", beat.id, "plan").length, 1);
  assert.equal(problemsFor(problems, "beats", beat.id, "planned_from").length, 0);   // optional
  assert.equal(problemsFor(problems, "beats", beat.id, "stale").length, 0);          // optional
});

test("a value that is not one of the options, and too many chosen, are reported", () => {
  // The beat has no option list of its own any more, so a choice field and a capped list are tried on small cards.
  const choice = { id: "t", fields: [{ key: "mood", label: "Mood", required: true, input: "select", options: [{ value: "calm", label: "Calm" }] }], rules: [] };
  const bad = validate(choice, { mood: "sideways" }, {}, schema.common).problems;
  assert.equal(problemsFor(bad, "mood", null, null)[0].rule, "not_allowed");
  const capped = { id: "t", fields: [{ key: "cast", label: "Cast", required: true, input: "select-multiple", max_selected: 5, ref: ["characters"] }], rules: [] };
  const many = validate(capped, { cast: ["a", "b", "c", "d", "e", "f"] }, {}, schema.common).problems;
  assert.equal(many.find((p) => p.rule === "too_many").message, "Cast can hold at most 5 items.");
});

test("every code rule on every card can be run by the page", () => {
  assert.deepEqual(PENDING_CHECKS, []);
  for (const card of Object.values(schema.cards)) {
    const values = card.many_per_project ? blankCard(card) : ensureCard({}, card);
    assert.deepEqual(validate(card, values, {}, schema.common).unchecked, [], card.id);
  }
});

// ---- The checks, one at a time. `run` runs one rule of a card and returns where it was broken. ----
const run = (cardId, ruleId, values, project = {}) => {
  const card = schema.cards[cardId];
  const rule = card.rules.find((r) => r.id === ruleId);
  const { problems } = validate(card, values, project, schema.common);
  return problems.filter((p) => p.rule === ruleId).map((p) => [p.field, p.item, p.key]);
};
const beat = (extra) => ({ ...blankItem(beatsField), id: "b1", chapter: 1, ...extra });

test("a beat with an aim and a plan has no missing-field problem", () => {
  assert.deepEqual(validate(outline, { beats: [beat({ where: "pl1", when_time: "Dawn", cast: ["c1"], spotlight: "t1", aim: "Find the ledger", plan: "She searches." })] }, {}, schema.common).problems.filter((p) => p.rule === "missing"), []);
});

test("a tie may not go from a person to themselves", () => {
  assert.deepEqual(run("entanglements", "tie_not_self", { ties: [{ id: "t1", tie_from: "c1", tie_to: "c1" }] }), [["ties", "t1", "tie_to"]]);
  assert.deepEqual(run("entanglements", "tie_not_self", { ties: [{ id: "t1", tie_from: "c1", tie_to: "c2" }, { id: "t2", tie_from: "", tie_to: "" }] }), []);
});

test("no rule asks for a field to be required only under a condition any more", () => {
  const checks = Object.values(schema.cards).flatMap((c) => c.rules.map((r) => r.check));
  assert.ok(!checks.includes("required_if"));
  assert.ok(!("required_if" in CHECKS));
});

test("links that no longer exist are reported, in a card and in its lists", () => {
  const project = { characters: [{ id: "c1", name: "Ines" }], world: { powers: [] } };
  assert.deepEqual(run("setup", "protagonist_link_broken", { protagonist: "gone" }, project), [["protagonist", null, null]]);
  assert.deepEqual(run("setup", "protagonist_link_broken", { protagonist: "c1" }, project), []);
  assert.deepEqual(run("setup", "protagonist_link_broken", { protagonist: "" }, project), []);
  assert.deepEqual(run("entanglements", "link_broken", { ties: [{ id: "t1", tie_from: "c1", tie_to: "gone" }] }, project), [["ties", "t1", "tie_to"]]);
  assert.deepEqual(run("outline", "outline_link_broken", { beats: [beat({ cast: ["c1", "gone"] })] }, project), [["beats", "b1", "cast"]]);
});

test("a holder must be allowed for the kind of thing", () => {
  const project = { characters: [{ id: "c1", name: "Ines" }], world: { objects: [{ id: "o1", name: "Ledger" }], places: [{ id: "pl1", name: "Shop" }], powers: [] } };
  const hold = (holdee, held_by) => run("entanglements", "holding_pair_allowed", { holdings: [{ id: "h1", holdee, held_by }] }, project);
  assert.deepEqual(hold("o1", "c1"), []);
  assert.deepEqual(hold("pl1", "pl1"), [["holdings", "h1", "held_by"]]);
  assert.deepEqual(hold("o1", ""), []);
});

test("item counts ignore empty items", () => {
  assert.deepEqual(run("characters", "wants_count", { wants: [] }), [["wants", null, null]]);
  assert.deepEqual(run("characters", "wants_count", { wants: [{ id: "a", text: "one" }, { id: "b", text: "" }] }).length, 1);
  assert.deepEqual(run("characters", "wants_count", { wants: [{ id: "a", text: "one" }, { id: "b", text: "two" }] }).length, 0);
});

test("the cast must include the protagonist, and the spotlight pair must be on stage", () => {
  const project = { setup: { protagonist: "c1" }, characters: [{ id: "c1" }, { id: "c2" }, { id: "c3" }], entanglements: { ties: [{ id: "t1", tie_from: "c2", tie_to: "c3" }] } };
  assert.deepEqual(run("outline", "cast_has_protagonist", { beats: [beat({ cast: ["c2"] })] }, project), [["beats", "b1", "cast"]]);
  assert.deepEqual(run("outline", "cast_has_protagonist", { beats: [beat({ cast: ["c1"] })] }, project), []);
  assert.deepEqual(run("outline", "cast_has_protagonist", { beats: [beat({ cast: ["c2"] })] }, {}), []);
  assert.deepEqual(run("outline", "spotlight_pair_in_cast", { beats: [beat({ cast: ["c1", "c2"], spotlight: "t1" })] }, project), [["beats", "b1", "spotlight"]]);
  assert.deepEqual(run("outline", "spotlight_pair_in_cast", { beats: [beat({ cast: ["c1", "c2", "c3"], spotlight: "t1" })] }, project), []);
});

test("the outline has no beat shift and no pacing rule any more", () => {
  assert.ok(!beatsField.item_fields.some((f) => f.key === "shift"));
  assert.ok(!outline.rules.some((r) => /shift|pacing/.test(r.id)));
});

test("names: a world may not name characters; a character may not name others or the world", () => {
  const project = {
    characters: [{ id: "c1", name: "Ines" }, { id: "c2", name: "Tomas" }],
    world: { places: [{ id: "pl1", name: "The print shop" }], objects: [], powers: [{ id: "g1", name: "The Guild" }] },
  };
  const world = { era_and_technology: "", everyday_life: "Ines would never go there.", history: "", places: [{ id: "pl1", name: "The print shop", description: "Tomas sweeps it." }], objects: [], powers: [], rules: [], terms: [] };
  const hits = run("world", "world_names_people", world, project);
  assert.deepEqual(hits, [["everyday_life", null, null], ["places", "pl1", "description"]]);
  const ines = { id: "c1", name: "Ines", sketch: "Friends with Tomas, works at the print shop.", appearance: "Ines is tall", fear: "", wants: [], behaviors: [] };
  const found = validate(schema.cards.characters, ines, project, schema.common).problems.filter((p) => p.rule === "char_other_names");
  assert.deepEqual(found.map((p) => p.field), ["sketch"]);   // her own name in "appearance" is fine
  assert.match(found[0].message, /Tomas, The print shop|The print shop, Tomas/);
  assert.deepEqual(run("world", "world_names_people", { ...world, everyday_life: "Inesa is a word, Ines.x" }, project).length, 2);
});

test("the outline has no reveal, plant or payoff fields or rules any more", () => {
  const keys = beatsField.item_fields.map((f) => f.key);
  for (const gone of ["sibling", "payoff", "planted", "ends_on", "goal_now", "collision_goal", "when_gap", "offstage_did", "offstage_reach"]) assert.ok(!keys.includes(gone), gone);
  assert.ok(!outline.rules.some((r) => /reveal|payoff|plant|offstage|when_gap/.test(r.id)));
});

test("an aim too close to an earlier aim or changed line is flagged", () => {
  assert.equal(similarity("Ines learns the customer's name", "Ines learns the customers name!") >= SIMILARITY_LIMIT, true);
  assert.equal(similarity("Ines learns the customer's name", "The guild burns the east market") < SIMILARITY_LIMIT, true);
  assert.equal(similarity("", "anything at all here"), 0);
  const project = { summary_events: { entries: [{ id: "e1", beat: "b1", changed: "The landlord now knows Ines is asking questions" }] } };
  const beats = [beat({ id: "b2", chapter: 2, aim: "The landlord knows that Ines is asking questions" })];
  assert.deepEqual(run("outline", "aim_not_repeated", { beats }, project), [["beats", "b2", "aim"]]);
  const two = [beat({ id: "b1", chapter: 1, aim: "A stranger arrives with a sealed letter" }), beat({ id: "b2", chapter: 2, aim: "A stranger arrives with the sealed letter" })];
  assert.deepEqual(run("outline", "aim_not_repeated", { beats: two }), [["beats", "b2", "aim"]]);
});

// ---- Showing problems: when the page lets a problem appear ----
const setupCard = schema.cards.setup;
const review = (touched = [], validated = false) => ({ touched: new Set(touched), validated });
const shownFields = (card, values, project, state) =>
  shownProblems(card, validate(card, values, project, schema.common).problems, state).map((p) => problemPath(p)).sort();

test("a blank, untouched card shows no problems, even though required fields are empty", () => {
  const values = blankCard(setupCard);
  assert.ok(validate(setupCard, values, {}, schema.common).problems.length > 0);
  assert.deepEqual(shownFields(setupCard, values, {}, review([...filledPaths(setupCard, values)])), []);
});

test("a problem appears once its field has been left, and not before", () => {
  const values = blankCard(setupCard);
  assert.deepEqual(shownFields(setupCard, values, {}, review(["normal"])), ["normal"]);
  assert.deepEqual(shownFields(setupCard, values, {}, review(["normal", "disruption"])), ["disruption", "normal"]);
});

test("Validate shows every code problem, including fields never visited", () => {
  const values = blankCard(setupCard);
  assert.deepEqual(shownFields(setupCard, values, {}, review([], true)),
    ["chapter_count", "disruption", "normal", "protagonist"]);
});

test("a saved project shows its problems at once: filled fields count as already visited", () => {
  const values = { ...blankCard(setupCard), protagonist: "gone", normal: "A quiet harbour", disruption: "A storm", chapter_count: 6 };
  const touched = [...filledPaths(setupCard, values)];
  // the missing person is reported by the link rule and by the advice that the protagonist should have a tie
  assert.deepEqual(shownFields(setupCard, values, { characters: [] }, review(touched)), ["protagonist", "protagonist"]);
});

test("a rule that compares two fields is shown when the writer leaves either one", () => {
  const values = { ...blankCard(ent), ties: [{ id: "t1", tie_from: "c1", tie_to: "c1", bond: "self", edge: "" }] };
  const project = { characters: [{ id: "c1", name: "Ines" }] };
  const problems = validate(ent, values, project, schema.common).problems;
  const same = problems.find((p) => p.rule === "tie_not_self");
  assert.equal(problemPath(same), "ties.t1.tie_to");
  assert.ok(problemTriggers(ent, same).includes("ties.t1.tie_from"));
  assert.equal(shownProblems(ent, [same], review(["ties.t1.tie_from"])).length, 1);
  assert.equal(shownProblems(ent, [same], review(["ties.t1.bond"])).length, 0);
});

test("problemPath names a plain field, a list, an item and a field inside an item", () => {
  assert.equal(problemPath({ field: "goal", item: null, key: null }), "goal");
  assert.equal(problemPath({ field: "beats", item: null, key: null }), "beats");
  assert.equal(problemPath({ field: "beats", item: "b1", key: null }), "beats.b1");
  assert.equal(problemPath({ field: "beats", item: "b1", key: "cast" }), "beats.b1.cast");
});

test("filledPaths lists fields, lists, items and the fields inside them, and skips empty and unticked ones", () => {
  const values = {
    ...blankCard(outline),
    beats: [{ ...blankItem(beatsField), id: "b1", chapter: 1, aim: "Find the ledger" }, { ...blankItem(beatsField), id: "b2" }],
  };
  const paths = filledPaths(outline, values);
  for (const path of ["beats", "beats.b1", "beats.b1.aim", "beats.b1.chapter"]) assert.ok(paths.has(path), path);
  for (const path of ["beats.b2", "beats.b2.aim", "beats.b1.cast"]) assert.ok(!paths.has(path), path);
  assert.equal(filledPaths(setupCard, blankCard(setupCard)).size, 0);
});

test("problemCounts splits blocking problems from warnings", () => {
  assert.deepEqual(problemCounts([]), { block: 0, warn: 0 });
  assert.deepEqual(problemCounts([{ severity: "block" }, { severity: "warn" }, { severity: "warn" }]), { block: 1, warn: 2 });
});

// ---- The backend contract ----

const contract = await import("../../web/logic.js");
const { fillRequest, readFillReply, judgeRequest, readJudgeReply, styleFitRequest, readStyleFitReply, readReply, readStatus,
  failure, relatedCards, ERROR_KINDS, FILLABLE } = contract;

const worldCard = schema.cards.world;
const projectWith = (extra = {}) => settledProject(schema, { ...newProject(schema), ...extra });

test("every request names its call, the schema version and the output language", () => {
  const project = projectWith({ output_language: "fr", example_chapter: "Once." });
  const fill = fillRequest(schema, project, "style").request;
  assert.deepEqual([fill.call, fill.schema_version, fill.language], ["fill", schema.schema_version, "fr"]);
  const plain = fillRequest(schema, projectWith({ example_chapter: "Once." }), "style").request;
  assert.equal(plain.language, schema.lang);
  assert.equal(judgeRequest(schema, project, "world", project.world).call, "judge");
});

test("fill needs the example chapter or a note for that card, and only the five fillable cards fill", () => {
  assert.deepEqual(FILLABLE, ["style", "characters", "world", "entanglements", "setup"]);
  assert.equal(fillRequest(schema, projectWith(), "world").reason, "no_source");
  assert.equal(fillRequest(schema, projectWith({ example_chapter: "   " }), "world").reason, "no_source");
  assert.equal(fillRequest(schema, projectWith({ example_chapter: "x" }), "outline").reason, "not_fillable");
  assert.equal(fillRequest(schema, projectWith(), "nope").reason, "unknown_card");
  const byChapter = fillRequest(schema, projectWith({ example_chapter: "A chapter." }), "world").request;
  assert.deepEqual([byChapter.example_chapter, byChapter.note], ["A chapter.", null]);
  const byNote = fillRequest(schema, projectWith({ card_notes: [{ id: "n1", card: "world", text: "Salt city." }] }), "world").request;
  assert.deepEqual([byNote.example_chapter, byNote.note], [null, "Salt city."]);
  assert.equal(fillRequest(schema, projectWith({ card_notes: [{ id: "n1", card: "style", text: "Dry." }] }), "world").reason, "no_source");
});

test("a note for a character only counts for that character", () => {
  const project = projectWith();
  const a = addInstance(project, characters);
  const b = addInstance(project, characters);
  project.card_notes = [{ id: "n1", card: "characters", character: a.id, text: "Suvi, archivist." }];
  assert.equal(fillRequest(schema, project, "characters", a.id).request.note, "Suvi, archivist.");
  assert.equal(fillRequest(schema, project, "characters", b.id).reason, "no_source");
  assert.equal(fillRequest(schema, project, "characters", "missing").reason, "no_instance");
  assert.equal(fillRequest(schema, project, "characters", a.id).request.instance, a.id);
});

test("a request carries a copy of the card's values and only the cards it reads", () => {
  const project = projectWith({ example_chapter: "x" });
  project.setup.goal = "Find the ledger";
  const request = fillRequest(schema, project, "setup").request;
  assert.equal(request.values.goal, "Find the ledger");
  assert.deepEqual(Object.keys(request.related).sort(), schema.cards.setup.reads.filter((id) => project[id] !== undefined).sort());
  request.values.goal = "changed";
  request.related.style.person = "changed";
  assert.equal(project.setup.goal, "Find the ledger");
  assert.notEqual(project.style.person, "changed");
  assert.deepEqual(fillRequest(schema, project, "world").request.related, {});
  assert.deepEqual(relatedCards(schema, project, schema.cards.style), {});
});

test("the reply envelope: ok replies pass, failures keep their kind, anything else is a bad output", () => {
  assert.deepEqual(readReply({ ok: true, x: 1 }), { ok: true, x: 1 });
  assert.deepEqual(readReply({ ok: false, error: { kind: "busy", detail: "mid-chapter" } }), failure("busy", "mid-chapter"));
  assert.equal(readReply({ ok: false, error: { kind: "weird" } }).error.kind, "server");
  for (const bad of [null, undefined, "text", [], {}, { ok: "yes" }]) assert.equal(readReply(bad).error.kind, "bad_output");
  assert.ok(["busy", "bad_output", "too_long", "stopped", "unreachable", "timeout"].every((k) => ERROR_KINDS.includes(k)));
});

test("status is idle or busy", () => {
  assert.deepEqual(readStatus({ ok: true, state: "idle" }), { ok: true, state: "idle" });
  assert.equal(readStatus({ ok: true, state: "busy" }).state, "busy");
  assert.equal(readStatus({ ok: true, state: "sleeping" }).error.kind, "bad_output");
  assert.equal(readStatus({ ok: false, error: { kind: "server" } }).error.kind, "server");
});

test("a fill reply keeps the card's own fields and names the rest", () => {
  const key = worldCard.fields[0].key;
  const reply = readFillReply(worldCard, { ok: true, values: { [key]: "x", surprise: 1 } });
  assert.deepEqual(reply, { ok: true, values: { [key]: "x" }, ignored: ["surprise"] });
  assert.equal(readFillReply(worldCard, { ok: true }).error.kind, "bad_output");
  assert.equal(readFillReply(worldCard, { ok: true, values: [] }).error.kind, "bad_output");
  assert.equal(readFillReply(worldCard, { ok: false, error: { kind: "stopped" } }).error.kind, "stopped");
});

test("a fill reply keeps a list's items", () => {
  const card = schema.cards.entanglements;
  const reply = { ok: true, values: { ties: [{ tie_from: "Ines", tie_to: "Tomas", bond: "sisters" }] } };
  const read = readFillReply(card, reply);
  assert.equal(read.ok, true);
  assert.deepEqual(read.values.ties, [{ tie_from: "Ines", tie_to: "Tomas", bond: "sisters" }]);
});

test("the judge request lists the card's model rules, or only the ones asked for", () => {
  const project = projectWith();
  const all = judgeRequest(schema, project, "world", project.world);
  assert.deepEqual(all.rules.map((r) => r.id), modelRules(worldCard).map((r) => r.id));
  assert.ok(all.rules.every((r) => r.id && r.fields.length));
  assert.deepEqual(all.rules[0], { id: all.rules[0].id, fields: modelRules(worldCard)[0].fields });
  const some = judgeRequest(schema, project, "world", project.world, ["everyday_has_friction"]);
  assert.deepEqual(some.rules.map((r) => r.id), ["everyday_has_friction"]);
  assert.deepEqual(some.values, project.world);
  assert.equal(some.instance, null);
});

test("a judge reply becomes problems the page shows like any other; unanswered rules are missing, not passed", () => {
  const project = projectWith();
  const sent = ["everyday_has_friction", "era_is_fact_not_mood", "history_no_people"];
  const reply = { ok: true, results: [
    { rule: "everyday_has_friction", hits: [{ field: "everyday_life" }] },
    { rule: "era_is_fact_not_mood", hits: [] },
  ] };
  const read = readJudgeReply(worldCard, project.world, sent, reply);
  assert.equal(read.ok, true);
  assert.deepEqual(read.answered, ["everyday_has_friction", "era_is_fact_not_mood"]);
  assert.deepEqual(read.missing, ["history_no_people"]);
  assert.equal(read.problems.length, 1);
  const [p] = read.problems;
  assert.deepEqual([p.rule, p.kind, p.severity, p.field, p.item], ["everyday_has_friction", "model", "warn", "everyday_life", null]);
  assert.ok(p.message && p.fix);
});

test("a judge reply ignores rules that were not asked, and rejects shapes it cannot use", () => {
  const project = projectWith();
  const sent = ["everyday_has_friction"];
  const extra = readJudgeReply(worldCard, project.world, sent, { ok: true, results: [
    { rule: "era_is_fact_not_mood", hits: [{ field: "everyday_life" }] }, { rule: "no_such_rule", hits: [] },
  ] });
  assert.deepEqual([extra.problems.length, extra.answered, extra.missing], [0, [], sent]);
  assert.equal(readJudgeReply(worldCard, project.world, sent, { ok: true }).error.kind, "bad_output");
  assert.equal(readJudgeReply(worldCard, project.world, sent, { ok: true, results: [{ rule: sent[0] }] }).error.kind, "bad_output");
  assert.equal(readJudgeReply(worldCard, project.world, sent, { ok: true, results: [{ rule: sent[0], hits: [{ field: "nope" }] }] }).error.kind, "bad_output");
  assert.equal(readJudgeReply(worldCard, project.world, sent, { ok: false, error: { kind: "too_long" } }).error.kind, "too_long");
});

test("a judge hit on a list item that is gone falls back to the whole field", () => {
  const project = projectWith();
  const listField = worldCard.fields.find((f) => f.repeat && modelRules(worldCard).some((r) => r.fields.includes(f.key)));
  const rule = modelRules(worldCard).find((r) => r.fields.includes(listField.key));
  const item = addItem(listField, project.world[listField.key]);
  const hit = (id) => readJudgeReply(worldCard, project.world, [rule.id], { ok: true, results: [{ rule: rule.id, hits: [{ field: listField.key, item: id, key: "x" }] }] }).problems[0];
  assert.deepEqual([hit(item.id).item, hit(item.id).key], [item.id, "x"]);
  assert.deepEqual([hit("gone").item, hit("gone").key], [null, null]);
});

test("style fit needs the protagonist Setup chose", () => {
  const project = projectWith();
  assert.equal(styleFitRequest(schema, project).reason, "no_protagonist");
  const hero = addInstance(project, characters);
  project.setup.protagonist = hero.id;
  hero.name = "Suvi";
  project.style.person = "first";
  const { request } = styleFitRequest(schema, project);
  assert.deepEqual([request.call, request.protagonist.name, request.style.person], ["style_fit", "Suvi", "first"]);
  hero.name = "changed";
  assert.equal(request.protagonist.name, "Suvi");
  project.setup.protagonist = "gone";
  assert.equal(styleFitRequest(schema, project).reason, "no_protagonist");
});

test("a style fit reply says whether it fits", () => {
  assert.deepEqual(readStyleFitReply({ ok: true, fits: true }), { ok: true, fits: true, message: "" });
  assert.deepEqual(readStyleFitReply({ ok: true, fits: false, message: "Too guarded." }), { ok: true, fits: false, message: "Too guarded." });
  assert.equal(readStyleFitReply({ ok: true, fits: "yes" }).error.kind, "bad_output");
  assert.equal(readStyleFitReply({ ok: false, error: { kind: "busy" } }).error.kind, "busy");
});

// ---- Saving, opening and the recovery copy ----

const importIo = {};
const io = await import("../../web/logic.js");
Object.assign(importIo, io);
const { settledProject, projectSnapshot, hasUnsavedChanges, projectFileName, readProject,
  RECOVERY_KEY, recoveryRecord, readRecovery, worthRecovering } = importIo;

test("a settled project has every card in full, and settling does not change the original", () => {
  const project = newProject(schema);
  const settled = settledProject(schema, project);
  assert.deepEqual(Object.keys(project), ["title", "schema_version"]);
  for (const id of schema.order) assert.ok(id in settled, id);
  assert.deepEqual(settled.characters, []);
});

test("visiting a card is not a change, typing is", () => {
  const project = newProject(schema);
  const saved = projectSnapshot(schema, project);
  ensureCard(project, style);                       // the page fills in blanks when a card is shown
  assert.equal(hasUnsavedChanges(schema, project, saved), false);
  project.style.narrator_note = "Dry and a little tired";
  assert.equal(hasUnsavedChanges(schema, project, saved), true);
  project.style.narrator_note = "";
  assert.equal(hasUnsavedChanges(schema, project, saved), false);
});

test("adding a character is a change", () => {
  const project = newProject(schema);
  const saved = projectSnapshot(schema, project);
  addInstance(project, characters);
  assert.equal(hasUnsavedChanges(schema, project, saved), true);
});

test("file names come from the title and stay safe", () => {
  assert.equal(projectFileName({ title: "" }), "pulpermill-project.json");
  assert.equal(projectFileName({}), "pulpermill-project.json");
  assert.equal(projectFileName({ title: "The Salt Road" }), "the-salt-road.json");
  assert.equal(projectFileName({ title: "  Who killed Mr. X?! / part 2 " }), "who-killed-mr-x-part-2.json");
  assert.equal(projectFileName({ title: "???" }), "pulpermill-project.json");
  assert.equal(projectFileName({ title: "盐路 的故事" }), "盐路-的故事.json");
  assert.ok(projectFileName({ title: "a".repeat(200) }).length <= 65);
});

test("a saved project reads back as the same project", () => {
  const project = newProject(schema);
  project.title = "Round trip";
  project.style = { ...blankCard(style), narrator_note: "Find the lighthouse" };
  const one = addInstance(project, characters);
  one.name = "Mara";
  const text = projectSnapshot(schema, project);
  const read = readProject(text, schema);
  assert.equal(read.ok, true);
  assert.equal(projectSnapshot(schema, read.project), text);
  assert.equal(read.project.characters[0].name, "Mara");
});

test("the saved file is the project, nothing wrapped around it", () => {
  const data = JSON.parse(projectSnapshot(schema, newProject(schema)));
  assert.equal(data.schema_version, schema.schema_version);
  assert.equal(data.title, "");
});

test("opening says why a file cannot be used", () => {
  const v = schema.schema_version;
  assert.equal(readProject("not json {", schema).reason, "unreadable");
  assert.equal(readProject("", schema).reason, "unreadable");
  assert.equal(readProject("[1,2]", schema).reason, "not_project");
  assert.equal(readProject("null", schema).reason, "not_project");
  assert.equal(readProject('{"title":"x"}', schema).reason, "not_project");
  assert.equal(readProject(`{"schema_version":"${v}"}`, schema).reason, "not_project");
  for (const other of [v + 1, v - 1]) {
    const refused = readProject(`{"schema_version":${other}}`, schema);
    assert.deepEqual([refused.ok, refused.reason], [false, "version"]);
    assert.match(refused.message, new RegExp(`version ${other}.*version ${v}`));
  }
  const bad = readProject(`{"schema_version":${v},"characters":{"a":1}}`, schema);
  assert.deepEqual([bad.ok, bad.reason, bad.card], [false, "damaged", "characters"]);
  assert.equal(readProject(`{"schema_version":${v},"characters":[1]}`, schema).reason, "damaged");
  assert.equal(readProject(`{"schema_version":${v},"style":[]}`, schema).reason, "damaged");
});

test("opening copes with a byte-order mark and a project that has no cards yet", () => {
  const read = readProject(`﻿{"schema_version":${schema.schema_version},"title":"x"}`, schema);
  assert.equal(read.ok, true);
  assert.equal(read.project.title, "x");
});

test("an older file still opens and says it is older", () => {
  if (schema.schema_version < 2) {
    const fake = { ...schema, schema_version: schema.schema_version + 1 };
    const read = readProject(JSON.stringify({ schema_version: schema.schema_version }), fake);
    assert.deepEqual([read.ok, read.older], [true, true]);
  }
});

test("the recovery copy reads back with what the page needs to offer it", () => {
  const project = newProject(schema);
  project.title = "Half done";
  addInstance(project, characters).name = "Mara";
  const text = recoveryRecord(schema, project, new Date("2026-10-22T07:30:00Z"));
  const got = readRecovery(text, schema);
  assert.equal(got.title, "Half done");
  assert.equal(got.characters, 1);
  assert.equal(got.savedAt, "2026-10-22T07:30:00.000Z");
  assert.equal(worthRecovering(schema, got), true);
  assert.ok(RECOVERY_KEY.length > 0);
});

test("a blank recovery copy is not worth offering, and a bad one is ignored", () => {
  const blank = readRecovery(recoveryRecord(schema, newProject(schema)), schema);
  assert.equal(worthRecovering(schema, blank), false);
  assert.equal(worthRecovering(schema, null), false);
  assert.equal(readRecovery("nope", schema), null);
  assert.equal(readRecovery("{}", schema), null);
  assert.equal(readRecovery(JSON.stringify({ saved_at: "x", project: { title: "no version" } }), schema), null);
  const newer = JSON.stringify({ saved_at: "x", project: { schema_version: schema.schema_version + 1 } });
  assert.equal(readRecovery(newer, schema), null);
});

// ---- What a tab or a dropdown entry says ----

const { cardStatus, combineStatus, projectStatus } = await import("../../web/logic.js");
const reviewOf = () => ({ touched: new Set(), validated: false });
const miniCard = {
  id: "mini", label: "Mini",
  fields: [{ key: "a", label: "A", type: "text", required: true }, { key: "b", label: "B", type: "text" }],
  rules: [],
};
const miniCommon = { missing: { message: "{label} is needed", fix: "Fill it in" } };

test("a blank card has nothing started and nothing to show", () => {
  const s = cardStatus(miniCard, { a: "", b: "" }, {}, miniCommon, reviewOf());
  assert.deepEqual(s, { started: false, ready: false, block: 0, warn: 0 });
});

test("a started card with a required field missing is not ready, and does not nag until visited", () => {
  const s = cardStatus(miniCard, { a: "", b: "something" }, {}, miniCommon, reviewOf());
  assert.equal(s.started, true);
  assert.equal(s.ready, false);
  assert.equal(s.block, 0);                                  // the missing field has not been reached
  const left = { touched: new Set(["a"]), validated: false };
  assert.equal(cardStatus(miniCard, { a: "", b: "something" }, {}, miniCommon, left).block, 1);
  const checked = { touched: new Set(), validated: true };
  assert.equal(cardStatus(miniCard, { a: "", b: "something" }, {}, miniCommon, checked).block, 1);
});

test("a started card with nothing blocking is ready", () => {
  const s = cardStatus(miniCard, { a: "x", b: "" }, {}, miniCommon, reviewOf());
  assert.deepEqual(s, { started: true, ready: true, block: 0, warn: 0 });
});

test("combining statuses: ready only when every one is, counts add up", () => {
  const ready = { started: true, ready: true, block: 0, warn: 0 };
  const bad = { started: true, ready: false, block: 2, warn: 1 };
  const blank = { started: false, ready: false, block: 0, warn: 0 };
  assert.deepEqual(combineStatus([ready, ready]), { started: true, ready: true, block: 0, warn: 0 });
  assert.deepEqual(combineStatus([ready, bad]), { started: true, ready: false, block: 2, warn: 1 });
  assert.deepEqual(combineStatus([ready, blank]), { started: true, ready: false, block: 0, warn: 0 });
  assert.deepEqual(combineStatus([]), { started: false, ready: false, block: 0, warn: 0 });
});

test("a blank project has every tab empty", () => {
  const { cards, instances } = projectStatus(schema, newProject(schema), reviewOf);
  assert.deepEqual(Object.keys(cards), schema.order);
  for (const id of schema.order) assert.deepEqual(cards[id], { started: false, ready: false, block: 0, warn: 0 }, id);
  assert.deepEqual(instances.characters, []);
});

test("a saved project shows its problems on the tabs at once, and a blank extra character spoils the tick", () => {
  const project = newProject(schema);
  project.style = { ...blankCard(style), person: "not a real option" };
  const a = addInstance(project, characters);
  a.name = "Mara";
  addInstance(project, characters);
  const { cards, instances } = projectStatus(schema, project, reviewOf);
  assert.equal(cards.style.started, true);
  assert.ok(cards.style.block >= 1);
  assert.equal(cards.characters.started, true);
  assert.equal(cards.characters.ready, false);
  assert.equal(instances.characters.length, 2);
  assert.equal(instances.characters[0].status.started, true);
  assert.equal(instances.characters[1].status.started, false);
  assert.equal(cards.world.started, false);
});

test("status does not change the project it looks at", () => {
  const project = newProject(schema);
  const before = JSON.stringify(project);
  projectStatus(schema, project, reviewOf);
  assert.equal(JSON.stringify(project), before);
});

test("each character is judged with its own review state", () => {
  const project = newProject(schema);
  const a = addInstance(project, characters);
  const b = addInstance(project, characters);
  a.name = "A"; b.name = "B";
  const reviews = new Map();
  const of = (key) => { if (!reviews.has(key)) reviews.set(key, { touched: new Set(), validated: false }); return reviews.get(key); };
  of(`characters:${a.id}`).validated = true;
  const { instances } = projectStatus(schema, project, of);
  assert.ok(instances.characters[0].status.block > instances.characters[1].status.block);
});

// ---- Fixed and live fields ----

const { flagsUsed } = await import("../../web/logic.js");

test("a card says which of the fixed and live flags it uses", () => {
  assert.deepEqual(flagsUsed(style), { fixed: false, changes: false });
  assert.deepEqual(flagsUsed(characters), { fixed: true, changes: false });
  assert.deepEqual(flagsUsed(ent), { fixed: false, changes: false });   // no live fields now: ties change through shifts
  assert.deepEqual(flagsUsed(world), { fixed: false, changes: false });
  assert.deepEqual(flagsUsed({ fields: [] }), { fixed: false, changes: false });
});

test("no field is both fixed and live, so it never gets two tags", () => {
  const walk = (fields, where) => {
    for (const f of fields) {
      assert.ok(!(f.fixed && f.changes), `${where}.${f.key} is both`);
      walk(f.item_fields ?? [], `${where}.${f.key}`);
    }
  };
  for (const card of Object.values(schema.cards)) walk(card.fields, card.id);
});

// ---- Shared vectors: tests/shared/rule-vectors.json ----
const vectors = JSON.parse(readFileSync(new URL("../shared/rule-vectors.json", import.meta.url), "utf8")).cases;

for (const c of vectors) {
  test(`vector: ${c.card} / ${c.rule}: ${c.name}`, () => {
    const card = schema.cards[c.card];
    assert.ok(card.rules.some((r) => r.id === c.rule), `unknown rule ${c.rule}`);
    const { problems } = validate(card, c.values, c.project, schema.common);
    const found = problems.filter((p) => p.rule === c.rule);
    assert.deepEqual(found.map((p) => [p.field, p.item, p.key]), c.broken);
    if (c.message_contains) assert.ok(found.every((p) => p.message.includes(c.message_contains)), found[0]?.message);
  });
}

test("the vectors cover every code rule, both broken and not broken", () => {
  for (const card of Object.values(schema.cards)) {
    for (const rule of card.rules.filter((r) => ruleKind(r) === "code")) {
      const cases = vectors.filter((c) => c.card === card.id && c.rule === rule.id);
      assert.ok(cases.some((c) => c.broken.length > 0), `${card.id}/${rule.id} has no broken case`);
      assert.ok(cases.some((c) => c.broken.length === 0), `${card.id}/${rule.id} has no passing case`);
    }
  }
});

// ---- Landing a fill ----

const landing = await import("../../web/logic.js");
const { wordsToId, resolveFillLinks, planFill, setCardValues, filledFieldKeys } = landing;
const landEnt = schema.cards.entanglements;
const landSetup = schema.cards.setup;

// A project with two people, one power, and a second "Ola" so a name can be ambiguous.
function peopleProject() {
  const project = projectWith();
  const suvi = addInstance(project, characters);
  suvi.name = "Suvi";
  const ola = addInstance(project, characters);
  ola.name = "Ola";
  const guild = addItem(schema.cards.world.fields.find((f) => f.key === "powers"), project.world.powers);
  guild.name = "The Salt Guild";
  return { project, suvi, ola, guild };
}

test("words become ids: names match without caring about case or spacing, ids pass through, nothing is guessed", () => {
  const { project, suvi, guild } = peopleProject();
  const sources = ["characters", "world.powers"];
  assert.deepEqual(wordsToId(project, sources, "Suvi"), { id: suvi.id });
  assert.deepEqual(wordsToId(project, sources, "  the  SALT guild "), { id: guild.id });
  assert.deepEqual(wordsToId(project, sources, suvi.id), { id: suvi.id });
  assert.deepEqual(wordsToId(project, sources, "Nobody"), { none: true });
  assert.deepEqual(wordsToId(project, sources, ""), { none: true });
  const twin = addInstance(project, characters);
  twin.name = "suvi";
  assert.deepEqual(wordsToId(project, sources, "Suvi"), { several: true });
  addInstance(project, characters);
  assert.deepEqual(wordsToId(project, sources, ""), { none: true }, "an entry with no name yet is never matched");
});

test("a fill's links become ids, inside list items too; unmatched words are left empty and reported", () => {
  const { project, suvi, ola } = peopleProject();
  const reply = { ties: [
    { tie_from: "Suvi", tie_to: "Ola", bond: "sisters" },
    { tie_from: "Suvi", tie_to: "The Harbour Board", bond: "owes them" },
  ] };
  const { values, unresolved } = resolveFillLinks(landEnt, reply, project);
  assert.deepEqual([values.ties[0].tie_from, values.ties[0].tie_to, values.ties[0].bond], [suvi.id, ola.id, "sisters"]);
  assert.equal(values.ties[1].tie_to, "");
  assert.deepEqual(unresolved, [
    { field: "ties", index: 1, key: "tie_to", words: "The Harbour Board", why: "none" },
  ]);
  assert.equal(reply.ties[0].tie_from, "Suvi", "the reply itself is not changed");
  const one = resolveFillLinks(landSetup, { protagonist: "Ola", normal: "A quiet harbour" }, project);
  assert.deepEqual([one.values.protagonist, one.values.normal, one.unresolved], [ola.id, "A quiet harbour", []]);
});

test("a fill reply of the wrong kind is a bad output", () => {
  const read = (card, values) => readFillReply(card, { ok: true, values });
  assert.equal(read(landEnt, { ties: "none" }).error.kind, "bad_output");
  assert.equal(read(landEnt, { ties: [{ bond: ["a"] }] }).error.kind, "bad_output");
  assert.equal(read(landEnt, { ties: ["Suvi"] }).error.kind, "bad_output");
  assert.equal(read(landSetup, { normal: ["x"] }).error.kind, "bad_output");
  assert.equal(read(landSetup, { normal: { a: 1 } }).error.kind, "bad_output");
  assert.equal(read(landSetup, { chapter_count: 8, normal: "x" }).ok, true);
  assert.equal(read(landEnt, { ties: [{ bond: "x", surprise: [1] }] }).ok, true);
});

test("planning a fill: empty fields fill, written ones are named as replaced, same words stay put", () => {
  const { project, suvi } = peopleProject();
  const current = project.setup;
  current.normal = "My own normal";
  current.disruption = "Same disruption";
  const reply = { values: { protagonist: "Suvi", normal: "The model's normal", disruption: "Same disruption", chapter_count: 8, surprise: 1 }, ignored: ["surprise"] };
  const plan = planFill(landSetup, current, reply, project);
  assert.deepEqual([plan.filled.sort(), plan.replaced, plan.unchanged], [["chapter_count", "protagonist"], ["normal"], ["disruption"]]);
  assert.deepEqual([plan.next.protagonist, plan.next.normal, plan.next.chapter_count], [suvi.id, "The model's normal", 8]);
  assert.deepEqual(plan.ignored, ["surprise"]);
  assert.equal(current.normal, "My own normal", "planning changes nothing");
  assert.equal(plan.before.normal, "My own normal");
  assert.deepEqual(filledFieldKeys(landSetup, current), ["normal", "disruption"]);
});

test("an empty answer never wipes what the writer wrote, and fields the model skipped stay as they were", () => {
  const { project } = peopleProject();
  const current = project.setup;
  current.normal = "Keep me";
  current.disruption = "And me";
  const plan = planFill(landSetup, current, { values: { normal: "", disruption: null, chapter_count: 9 } }, project);
  assert.deepEqual([plan.filled, plan.replaced, plan.unchanged], [["chapter_count"], [], []]);
  assert.equal(plan.next.normal, "Keep me");
  assert.equal(plan.next.disruption, "And me");
});

test("filled lists get fresh ids; the same list again changes nothing and keeps its ids", () => {
  const { project, suvi, ola } = peopleProject();
  const reply = { values: { ties: [{ tie_from: "Suvi", tie_to: "Ola", bond: "sisters", edge: "" }] } };
  const first = planFill(landEnt, project.entanglements, reply, project);
  assert.deepEqual([first.filled, first.replaced], [["ties"], []]);
  const [tie] = first.next.ties;
  assert.match(tie.id, /^[0-9a-f]{8}$/);
  assert.deepEqual([tie.tie_from, tie.tie_to, tie.bond], [suvi.id, ola.id, "sisters"]);
  setCardValues(landEnt, project.entanglements, first.next);
  const again = planFill(landEnt, project.entanglements, reply, project);
  assert.deepEqual([again.unchanged, again.filled, again.replaced], [["ties"], [], []]);
  assert.equal(again.next.ties[0].id, tie.id);
  const other = planFill(landEnt, project.entanglements, { values: { ties: [{ tie_from: "Ola", tie_to: "Suvi", bond: "rivals" }] } }, project);
  assert.deepEqual(other.replaced, ["ties"]);
  assert.notEqual(other.next.ties[0].id, tie.id);
});

test("setting values in place keeps the same object, never touches the id, and Undo puts the old values back", () => {
  const { project, suvi } = peopleProject();
  suvi.appearance = "Sunburnt";
  const target = suvi;
  const plan = planFill(characters, target, { values: { appearance: "Tall", sketch: "An archivist", id: "hijack" } }, project);
  assert.equal(plan.next.id, suvi.id);
  setCardValues(characters, target, plan.next);
  assert.equal(target, project.characters[0]);
  assert.deepEqual([target.id, target.appearance, target.sketch], [suvi.id, "Tall", "An archivist"]);
  setCardValues(characters, target, plan.before);
  assert.deepEqual([target.id, target.appearance, target.sketch], [suvi.id, "Sunburnt", ""]);
  plan.before.appearance = "mutated";
  assert.equal(target.appearance, "Sunburnt", "values are copied, not shared");
});

// ---- The writer's notes ----

const notesApi = await import("../../web/logic.js");
const { noteFor, setNote, setExample } = notesApi;

test("a note is kept per card, and per character for Characters; a blank note is no note", () => {
  const project = projectWith();
  const a = addInstance(project, characters);
  const b = addInstance(project, characters);
  assert.equal(noteFor(project, "world"), "");
  setNote(project, "world", null, "Salt city.");
  setNote(project, "characters", a.id, "Suvi, archivist.");
  setNote(project, "characters", b.id, "Ola, her sister.");
  assert.equal(noteFor(project, "world"), "Salt city.");
  assert.equal(noteFor(project, "characters", a.id), "Suvi, archivist.");
  assert.equal(noteFor(project, "characters", b.id), "Ola, her sister.");
  assert.equal(project.card_notes.length, 3);
  assert.ok(project.card_notes.every((n) => /^[0-9a-f]{8}$/.test(n.id)));
  assert.equal("character" in project.card_notes.find((n) => n.card === "world"), false);
  const id = project.card_notes.find((n) => n.card === "world").id;
  setNote(project, "world", null, "Salt city, grey.");
  assert.equal(project.card_notes.find((n) => n.card === "world").id, id, "editing keeps the note's id");
  assert.equal(project.card_notes.length, 3);
  setNote(project, "world", null, "   ");
  assert.equal(noteFor(project, "world"), "");
  assert.equal(project.card_notes.length, 2);
  setNote(project, "characters", a.id, "");
  setNote(project, "characters", b.id, "");
  assert.equal("card_notes" in project, false, "no notes, no key: an empty box is not a change");
});

test("the example chapter is left out of the project when blank", () => {
  const project = projectWith();
  setExample(project, "Once upon a time.");
  assert.equal(project.example_chapter, "Once upon a time.");
  setExample(project, "  \n");
  assert.equal("example_chapter" in project, false);
});

test("deleting a character takes that character's note with it", () => {
  const project = projectWith();
  const a = addInstance(project, characters);
  const b = addInstance(project, characters);
  setNote(project, "characters", a.id, "About A.");
  setNote(project, "characters", b.id, "About B.");
  setNote(project, "world", null, "Salt city.");
  removeInstance(project, characters, a.id);
  assert.deepEqual(project.card_notes.map((n) => [n.card, n.character ?? null]), [["characters", b.id], ["world", null]]);
  removeInstance(project, characters, b.id);
  setNote(project, "world", null, "");
  assert.equal("card_notes" in project, false);
});

// ---- The contract vectors ----
// tests/shared/contract-vectors.json is shared with the backend's tests (tests/schema/test_contract.py): the page must build
// exactly the golden requests and read every valid reply, and the backend must accept the same requests and replies.

const contractVectors = JSON.parse(readFileSync(new URL("../shared/contract-vectors.json", import.meta.url), "utf8"));
const vectorsApi = await import("../../web/logic.js");
const planApi = await import("../../web/plan.js");
const generateApi = await import("../../web/generate.js");

test("the golden requests are exactly what the page builds", () => {
  const project = {
    title: "Golden", schema_version: schema.schema_version,
    style: { person: "first" },
    characters: [{ id: "c0000001", name: "Suvi" }],
    setup: { protagonist: "c0000001" },
    card_notes: [
      { id: "n0000001", card: "setup", text: "Suvi must find the ledger." },
      { id: "n0000002", card: "characters", character: "c0000001", text: "An archivist." },
    ],
  };
  const twoStories = story();
  const blankOpening = () => { const p = opening(); p.setup.normal = ""; p.setup.disruption = ""; return p; };
  const built = {
    status: { call: "status" },
    fill_setup: vectorsApi.fillRequest(schema, project, "setup").request,
    fill_character: vectorsApi.fillRequest(schema, project, "characters", "c0000001").request,
    judge_world: vectorsApi.judgeRequest(schema, project, "world", { name: "The Salt Coast", everyday_life: "Ordinary." }, ["everyday_has_friction"]),
    style_fit: vectorsApi.styleFitRequest(schema, project).request,
    plan: planApi.planRequest(schema, twoStories, twoStories.outline.beats[1]),
    plan_retry: planApi.planRequest(schema, twoStories, twoStories.outline.beats[1], {
      retry: { beat: { where: "The Archive", when_time: "Dusk", aim: "Suvi wants the ledger.", plan: "Nothing changes." }, problems: ["The aim is too like chapter 1's aim."] },
    }),
    plan_chapter_1: planApi.planRequest(schema, blankOpening(), blankOpening().outline.beats[0]),
    generate: generateApi.generateRequest(schema, twoStories, twoStories.outline.beats[1]),
    generate_chapter_1: generateApi.generateRequest(schema, opening(), opening().outline.beats[0]),
  };
  const golden = contractVectors.requests.filter((v) => v.golden);
  assert.deepEqual(golden.map((v) => v.golden).sort(), Object.keys(built).sort(), "every request the page makes has a golden case");
  for (const v of golden) assert.deepEqual(JSON.parse(JSON.stringify(built[v.golden])), v.data, v.name);
});

test("every valid reply is read and every invalid one refused", () => {
  const read = (v) => {
    switch (v.call) {
      case "status": return vectorsApi.readStatus(v.data);
      case "fill": return vectorsApi.readFillReply(schema.cards[v.card], v.data);
      case "judge": return vectorsApi.readJudgeReply(schema.cards[v.card], v.values, v.asked, v.data);
      case "style_fit": return vectorsApi.readStyleFitReply(v.data);
      case "job": return vectorsApi.readJobReply(v.data);
      case "cancel": return vectorsApi.readCancelReply(v.data);
      case "plan": return vectorsApi.readPlanReply(v.data);
      case "generate": return vectorsApi.readGenerateReply(v.data);
      default: throw new Error(`no reader for ${v.call}`);
    }
  };
  assert.deepEqual([...new Set(contractVectors.replies.map((v) => v.call))].sort(), ["cancel", "fill", "generate", "job", "judge", "plan", "status", "style_fit"]);
  for (const v of contractVectors.replies) {
    const result = read(v);
    // A failure the backend may send is read as a failure with its kind; any other reply is read when it is valid.
    const isFailure = v.data.ok === false;
    assert.equal(result.ok, isFailure ? false : v.valid, v.name);
    if (v.page?.kind) assert.equal(result.error.kind, v.page.kind, v.name);
    if (!v.valid) assert.equal(result.error.kind, "bad_output", v.name);
  }
});

test("a busy status may name its stage as {name, index, of}; an idle one never has one", () => {
  const stage = { name: "events", index: 2, of: 3 };
  assert.deepEqual(vectorsApi.readStatus({ ok: true, state: "busy", stage }), { ok: true, state: "busy", stage });
  assert.deepEqual(vectorsApi.readStatus({ ok: true, state: "busy", stage: { name: "dreaming", index: 1 } }), { ok: true, state: "busy", stage: { name: "dreaming", index: 1, of: null } });
  assert.deepEqual(vectorsApi.readStatus({ ok: true, state: "idle", stage }), { ok: true, state: "idle" });
  assert.equal(vectorsApi.readStatus({ ok: true, state: "busy", stage: "write" }).error.kind, "bad_output");
  assert.deepEqual(vectorsApi.STORY_CALLS, ["plan", "generate"]);
});

test("a stage is put in words: a known name by its label, an unknown one generically, with the step when it is known", () => {
  assert.equal(vectorsApi.stageText(null), "");
  assert.match(vectorsApi.stageText({ name: "write", index: 1, of: 3 }), /writing the chapter.*step 1 of 3/);
  assert.equal(vectorsApi.stageText({ name: "dreaming", index: 1, of: null }), "The model is working…");
  assert.match(vectorsApi.stageText({ name: "dreaming", index: 2, of: 4 }), /working.*step 2 of 4/);
});

test("a chapter reply is tidied: text kept, events trimmed, the shifts read as they are", () => {
  const read = vectorsApi.readGenerateReply({
    ok: true, chapter_text: "Text.", events: { happened: " Happened. ", changed: "  " },
    shifts: [{ card: "characters", target: "c1", patch: { fear: "fire", wants: [{ op: "add", values: { text: "x" } }] } }, { card: "world", patch: { history: "h" } }],
  });
  assert.equal(read.ok, true);
  assert.deepEqual(read.events, { happened: "Happened.", changed: null });
  assert.deepEqual(read.shifts.map((s) => [s.card, s.target]), [["characters", "c1"], ["world", null]]);
  assert.equal(vectorsApi.readGenerateReply({ ok: true, chapter_text: "Text.", events: {}, shifts: [] }).error.kind, "bad_output");
  assert.equal(vectorsApi.readGenerateReply({ ok: true, chapter_text: "Text.", events: { happened: "H" }, shifts: [], extra: 1 }).ok, false);
});

test("a plan reply holds a beat and nothing else", () => {
  assert.deepEqual(vectorsApi.readPlanReply({ ok: true, beat: { aim: "x" } }), { ok: true, beat: { aim: "x" } });
  assert.equal(vectorsApi.readPlanReply({ ok: true, beat: "x" }).error.kind, "bad_output");
  assert.equal(vectorsApi.readPlanReply({ ok: true, beat: {}, thinking: "x" }).error.kind, "bad_output");
});
