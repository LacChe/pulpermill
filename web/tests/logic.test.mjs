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
import { validate, ruleKind, modelRules, problemsFor, CHECKS, PENDING_CHECKS, legalShifts, similarity, SIMILARITY_LIMIT } from "../logic.js";
import { filledPaths, problemPath, problemTriggers, shownProblems, problemCounts, modelCheckRequest } from "../logic.js";

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

// ---- Validation ----

test("rules split into code rules (a named check) and model rules (needs_model), never both", () => {
  for (const card of Object.values(schema.cards)) {
    for (const rule of card.rules) {
      assert.equal(ruleKind(rule) === "model", Boolean(rule.needs_model), rule.id);
      assert.equal(Boolean(rule.check), !rule.needs_model, rule.id);
    }
  }
  assert.ok(modelRules(schema.cards.outline).every((r) => r.needs_model));
  assert.ok(modelRules(schema.cards.outline).length > 0);
});

test("every check named in the schema has a function or is listed as pending, and nothing is listed twice", () => {
  const named = new Set(Object.values(schema.cards).flatMap((c) => c.rules.map((r) => r.check).filter(Boolean)));
  for (const name of named) assert.ok(name in CHECKS || PENDING_CHECKS.includes(name), name);
  for (const name of PENDING_CHECKS) assert.ok(named.has(name) && !(name in CHECKS), name);
});

test("an empty required field is reported as missing, at the field", () => {
  const setup = schema.cards.setup;
  const { problems } = validate(setup, blankCard(setup), {}, schema.common);
  assert.deepEqual(problems.map((p) => p.field).sort(), ["chapter_count", "disruption", "goal", "normal", "protagonist", "stakes"]);
  assert.equal(problems[0].rule, "missing");
  assert.match(problems.find((p) => p.field === "goal").message, /^Goal is empty\./);
  const filled = { ...blankCard(setup), protagonist: "c1", normal: "a", disruption: "b", goal: "c", stakes: "d", chapter_count: 12 };
  assert.deepEqual(validate(setup, filled, { characters: [{ id: "c1", name: "Ines" }] }, schema.common).problems, []);
});

test("problems inside a list item name the list, the item and the field", () => {
  const list = [];
  const beat = addItem(beatsField, list);
  const values = { beats: list };
  const { problems } = validate(outline, values, {}, schema.common);
  const goal = problemsFor(problems, "beats", beat.id, "collision_goal");
  assert.equal(goal.length, 1);
  assert.equal(goal[0].rule, "missing");
  assert.equal(problemsFor(problems, "beats", beat.id, "reveal_rule").length, 0);   // optional
  assert.equal(problemsFor(problems, "beats", beat.id, "goal_now").length, 0);       // not required by itself: a rule asks for it
});

test("a value that is not one of the options, and too many chosen, are reported", () => {
  const list = [];
  const beat = addItem(beatsField, list);
  beat.shift = "sideways";
  beat.cast = ["a", "b", "c", "d", "e", "f"];
  const { problems } = validate(outline, { beats: list }, {}, schema.common);
  assert.equal(problemsFor(problems, "beats", beat.id, "shift")[0].rule, "not_allowed");
  assert.equal(problemsFor(problems, "beats", beat.id, "cast").find((p) => p.rule === "too_many").message, "Cast can hold at most 5 items.");
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

test("either-or and all-or-none", () => {
  const pressures = (item) => ({ pressures: [{ id: "p1", what: "x", ...item }] });
  assert.deepEqual(run("entanglements", "pressure_one_source", pressures({ source_agent: "c1" })), []);
  assert.deepEqual(run("entanglements", "pressure_one_source", pressures({})), [["pressures", "p1", "source_agent"]]);
  assert.deepEqual(run("entanglements", "pressure_one_source", pressures({ source_agent: "c1", source_circumstance: "a storm" })), [["pressures", "p1", "source_agent"]]);
  assert.deepEqual(run("outline", "offstage_both_or_neither", { beats: [beat({ offstage_did: "x" })] }), [["beats", "b1", "offstage_reach"]]);
  assert.deepEqual(run("outline", "offstage_both_or_neither", { beats: [beat({})] }), []);
  assert.deepEqual(run("outline", "offstage_both_or_neither", { beats: [beat({ offstage_did: "x", offstage_reach: "y" })] }), []);
});

test("a tie may not go from a person to themselves", () => {
  assert.deepEqual(run("entanglements", "tie_not_self", { ties: [{ id: "t1", tie_from: "c1", tie_to: "c1" }] }), [["ties", "t1", "tie_to"]]);
  assert.deepEqual(run("entanglements", "tie_not_self", { ties: [{ id: "t1", tie_from: "c1", tie_to: "c2" }, { id: "t2", tie_from: "", tie_to: "" }] }), []);
});

test("required_if: when, when_present and unless", () => {
  assert.deepEqual(run("world", "rule_false_needs_truth", { rules: [{ id: "r1", status: "false_belief", truth: "" }, { id: "r2", status: "common", truth: "" }] }), [["rules", "r1", "truth"]]);
  assert.deepEqual(run("entanglements", "next_move_for_agents", { pressures: [{ id: "p1", source_agent: "c1", next_move: "" }, { id: "p2", source_circumstance: "storm", next_move: "" }] }), [["pressures", "p1", "next_move"]]);
  assert.deepEqual(run("outline", "when_gap_after_first", { beats: [beat({ id: "b1", chapter: 1 }), beat({ id: "b2", chapter: 2 })] }), [["beats", "b2", "when_gap"]]);
  assert.deepEqual(run("outline", "goal_now_for_redefined", { beats: [beat({ goal_change: "redefined" })] }), [["beats", "b1", "goal_now"]]);
  assert.deepEqual(run("outline", "goal_now_for_redefined", { beats: [beat({ goal_change: "achieved" })] }), []);
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
  const four = ["a", "b", "c", "d"].map((id) => ({ id, what: id }));
  assert.deepEqual(run("entanglements", "pressures_active_count", { pressures: four }), [["pressures", null, null]]);
});

test("the cast must include the protagonist, and the spotlight must touch the cast", () => {
  const project = { setup: { protagonist: "c1" }, entanglements: { pressures: [{ id: "x1", what: "audit", source_agent: "g1", bears_on: ["c2"] }] } };
  assert.deepEqual(run("outline", "cast_has_protagonist", { beats: [beat({ cast: ["c2"] })] }, project), [["beats", "b1", "cast"]]);
  assert.deepEqual(run("outline", "cast_has_protagonist", { beats: [beat({ cast: ["c1"] })] }, project), []);
  assert.deepEqual(run("outline", "cast_has_protagonist", { beats: [beat({ cast: ["c2"] })] }, {}), []);
  assert.deepEqual(run("outline", "spotlight_in_cast", { beats: [beat({ cast: ["c1"], spotlight: "x1" })] }, project), [["beats", "b1", "spotlight"]]);
  assert.deepEqual(run("outline", "spotlight_in_cast", { beats: [beat({ cast: ["c1", "c2"], spotlight: "x1" })] }, project), []);
});

test("pacing: at most 2 harder in a row, at most 1 easier in a row", () => {
  const seq = (...shifts) => shifts.map((shift, i) => beat({ id: `b${i + 1}`, chapter: i + 1, shift }));
  assert.deepEqual(legalShifts(seq("", ""), seq("", "")[1]), ["harder", "easier"]);
  const beats = seq("harder", "harder", "");
  assert.deepEqual(legalShifts(beats, beats[2]), ["easier"]);
  const after = seq("harder", "easier", "");
  assert.deepEqual(legalShifts(after, after[2]), ["harder"]);
  const mixed = seq("harder", "easier", "harder", "harder", "");
  assert.deepEqual(legalShifts(mixed, mixed[4]), ["easier"]);
  assert.deepEqual(run("outline", "shift_legal", { beats: seq("harder", "harder", "harder") }), [["beats", "b3", "shift"]]);
  assert.deepEqual(run("outline", "shift_legal", { beats: seq("easier", "easier") }), [["beats", "b2", "shift"]]);
  assert.deepEqual(run("outline", "shift_legal", { beats: seq("harder", "easier", "harder", "harder", "easier") }), []);
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

test("a reveal may not repeat, and a payoff must be an earlier, still-open plant", () => {
  const project = { summary_events: { entries: [
    { id: "e1", beat: "b1", planted: "A locked room", reveals_landed: ["r1"] },
    { id: "e2", beat: "b2", planted: "A letter", paid_off: [] },
    { id: "e3", beat: "b3", paid_off: ["e1"] },
  ] } };
  const beats = [beat({ id: "b1", chapter: 1 }), beat({ id: "b2", chapter: 2 }), beat({ id: "b3", chapter: 3 }), beat({ id: "b4", chapter: 4 })];
  const withBeat = (id, extra) => ({ beats: beats.map((b) => (b.id === id ? { ...b, ...extra } : b)) });
  assert.deepEqual(run("outline", "reveal_not_repeated", withBeat("b4", { reveal_rule: "r1" }), project), [["beats", "b4", "reveal_rule"]]);
  assert.deepEqual(run("outline", "reveal_not_repeated", withBeat("b1", { reveal_rule: "r1" }), project), []);   // its own chapter
  assert.deepEqual(run("outline", "payoff_is_open_plant", withBeat("b4", { payoff: ["e2"] }), project), []);
  assert.deepEqual(run("outline", "payoff_is_open_plant", withBeat("b4", { payoff: ["e1"] }), project), [["beats", "b4", "payoff"]]);   // already paid off
  assert.deepEqual(run("outline", "payoff_is_open_plant", withBeat("b2", { payoff: ["e2"] }), project), [["beats", "b2", "payoff"]]);   // not earlier
  assert.deepEqual(run("outline", "payoff_is_open_plant", withBeat("b4", { payoff: ["e3"] }), project), [["beats", "b4", "payoff"]]);   // planted nothing
});

test("a turn too close to an earlier turn or changed line is flagged", () => {
  assert.equal(similarity("Ines learns the customer's name", "Ines learns the customers name!") >= SIMILARITY_LIMIT, true);
  assert.equal(similarity("Ines learns the customer's name", "The guild burns the east market") < SIMILARITY_LIMIT, true);
  assert.equal(similarity("", "anything at all here"), 0);
  const project = { summary_events: { entries: [{ id: "e1", beat: "b1", changed: "The landlord now knows Ines is asking questions" }] } };
  const beats = [beat({ id: "b2", chapter: 2, turn: "The landlord knows that Ines is asking questions" })];
  assert.deepEqual(run("outline", "turn_not_repeated", { beats }, project), [["beats", "b2", "turn"]]);
  const two = [beat({ id: "b1", chapter: 1, turn: "A stranger arrives with a sealed letter" }), beat({ id: "b2", chapter: 2, turn: "A stranger arrives with the sealed letter" })];
  assert.deepEqual(run("outline", "turn_not_repeated", { beats: two }), [["beats", "b2", "turn"]]);
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
  assert.deepEqual(shownFields(setupCard, values, {}, review(["goal"])), ["goal"]);
  assert.deepEqual(shownFields(setupCard, values, {}, review(["goal", "normal"])), ["goal", "normal"]);
});

test("Validate shows every code problem, including fields never visited", () => {
  const values = blankCard(setupCard);
  assert.deepEqual(shownFields(setupCard, values, {}, review([], true)),
    ["chapter_count", "disruption", "goal", "normal", "protagonist", "stakes"]);
});

test("a saved project shows its problems at once: filled fields count as already visited", () => {
  const values = { ...blankCard(setupCard), protagonist: "gone", goal: "Find the ledger" };
  const touched = [...filledPaths(setupCard, values)];
  assert.deepEqual(shownFields(setupCard, values, { characters: [] }, review(touched)), ["protagonist"]);
});

test("a rule that compares two fields is shown when the writer leaves either one", () => {
  const values = { ...blankCard(ent), pressures: [{ id: "p1", what: "Rent is due", source_agent: "c1", source_circumstance: "", next_move: "", bears_on: [] }] };
  const project = { characters: [{ id: "c1", name: "Ines" }] };
  const problems = validate(ent, values, project, schema.common).problems;
  const next = problems.find((p) => p.rule === "next_move_for_agents");
  assert.equal(problemPath(next), "pressures.p1.next_move");
  assert.ok(problemTriggers(ent, next).includes("pressures.p1.source_agent"));
  assert.equal(shownProblems(ent, [next], review(["pressures.p1.source_agent"])).length, 1);
  assert.equal(shownProblems(ent, [next], review(["pressures.p1.what"])).length, 0);
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
    beats: [{ ...blankItem(beatsField), id: "b1", chapter: 1, turn: "A letter arrives" }, { ...blankItem(beatsField), id: "b2" }],
  };
  const paths = filledPaths(outline, values);
  for (const path of ["beats", "beats.b1", "beats.b1.turn", "beats.b1.chapter"]) assert.ok(paths.has(path), path);
  for (const path of ["beats.b2", "beats.b2.turn", "beats.b1.cast"]) assert.ok(!paths.has(path), path);
  assert.equal(filledPaths(setupCard, blankCard(setupCard)).size, 0);
});

test("problemCounts splits blocking problems from warnings", () => {
  assert.deepEqual(problemCounts([]), { block: 0, warn: 0 });
  assert.deepEqual(problemCounts([{ severity: "block" }, { severity: "warn" }, { severity: "warn" }]), { block: 1, warn: 2 });
});

test("the Validate request holds the card's model rules and a snapshot of its values", () => {
  const values = { ...blankCard(setupCard), goal: "Find the ledger" };
  const request = modelCheckRequest(setupCard, values);
  assert.equal(request.card, "setup");
  assert.deepEqual(request.rules.map((r) => r.id), modelRules(setupCard).map((r) => r.id));
  assert.ok(request.rules.length > 0 && request.rules.every((r) => r.severity && r.fields.length));
  assert.deepEqual(request.values, values);
  values.goal = "changed";
  assert.equal(request.values.goal, "Find the ledger");
});

// ---- Shared vectors: web/tests/vectors.json ----
const vectors = JSON.parse(readFileSync(new URL("./vectors.json", import.meta.url), "utf8")).cases;

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
