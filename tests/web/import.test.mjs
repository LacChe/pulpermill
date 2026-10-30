import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { newProject, settledProject, addInstance, setNote, noteFor } from "../../web/logic.js";
import { lockStaticCards } from "../../web/gate.js";
import { cardFiles, readCardFile, fileKind, planImport, planBatchImport, applyImport, linksLost, relinkMap, CARD_FILE_KEY } from "../../web/exporting.js";

const characters = schema.cards.characters;
const filesOf = (project) => Object.fromEntries(cardFiles(schema, project).map((f) => [f.name.replace(/^.*?-(style|world|character-\d+)(-.*)?\.json$/, "$1"), f.text]));
const read = (text) => readCardFile(text, schema);
const blank = () => settledProject(schema, newProject(schema));

test("a file's kind is told apart, so each button can say where a wrong file belongs", async () => {
  const files = filesOf(await readyProject());
  assert.equal(fileKind(files.style), "card");
  assert.equal(fileKind(JSON.stringify({ title: "x", schema_version: 1 })), "project");
  assert.equal(fileKind("{}"), "other");
  assert.equal(fileKind("[1]"), "other");
  assert.equal(fileKind("nope"), "unreadable");
});

test("a choice that is not one of the options, and a part of an item that does not fit, are left out", () => {
  const sex = JSON.stringify({ [CARD_FILE_KEY]: "characters", schema_version: 1, values: { id: "aaaaaaaa", name: "Ola", sex: "dragon", age: 30 } });
  const got = read(sex);
  assert.deepEqual(got.values, { id: "aaaaaaaa", name: "Ola", age: 30 });
  assert.deepEqual(got.ignored, ["sex"]);
  const items = JSON.stringify({ [CARD_FILE_KEY]: "characters", schema_version: 1, values: { behaviors: [{ id: "b1", state: "nervous", tendency: "paces", extra: 1 }, { state: 5 }] } });
  const parts = read(items);
  assert.deepEqual(parts.values.behaviors, [{ id: "b1", state: "nervous", tendency: "paces" }, {}]);
  assert.deepEqual(parts.ignored, ["behaviors"]);
});

test("a character comes in as a new character and keeps its id when nobody here has it", async () => {
  const files = filesOf(await readyProject());
  const project = blank();
  const got = read(files["character-1"]);
  const plan = planImport(schema, project, got);
  assert.equal(plan.ok && plan.mode, "add");
  assert.equal(plan.id, got.values.id);
  assert.deepEqual(plan.replaced, []);
  assert.equal(project.characters?.length ?? 0, 0, "planning changes nothing");
  const done = applyImport(schema, project, plan);
  assert.equal(project.characters.length, 1);
  assert.equal(done.instanceId, got.values.id);
  assert.equal(project.characters[0].name, "Suvi");
  assert.deepEqual(project.characters[0].behaviors.map((b) => b.id), got.values.behaviors.map((b) => b.id));
});

test("a batch keeps valid files and reports invalid, duplicate, and conflicting files", async () => {
  const source = await readyProject();
  const files = filesOf(source);
  const project = blank();
  const duplicateStyle = { file: "style-copy.json", text: files.style };
  const result = planBatchImport(schema, project, [
    { file: "style.json", text: files.style },
    duplicateStyle,
    { file: "bad.json", text: "not json" },
  ]);
  assert.equal(result.accepted.length, 1);
  assert.equal(result.accepted[0].read.card, "style");
  assert.deepEqual(result.failed.map((failure) => failure.reason), ["duplicate_batch", "unreadable"]);

  applyImport(schema, project, result.accepted[0].plan);
  const conflict = planBatchImport(schema, project, [
    { file: "character.json", text: files["character-1"] },
    { file: "same-character.json", text: files["character-1"] },
  ]);
  assert.equal(conflict.accepted.length, 1);
  assert.equal(conflict.failed[0].reason, "conflicting_id");
});

test("a card with malformed World fields is rejected as incorrectly formatted", async () => {
  const project = blank();
  const oldWorld = {
    [CARD_FILE_KEY]: "world",
    schema_version: schema.schema_version,
    values: {
      name: "Thimble Hollow",
      era_and_technology: "A small village.",
      everyday_life: "The village makes bread.",
      history: "It has been making bread for 200 years.",
      places: [{ name: "the bakery", description: "Warm.", effect: 42, id: "7fae5dab" }],
      objects: [{ name: "the Weather Oven", description: "A black oven.", significance: "It determines weather.", id: "e3bcb97e" }],
      powers: [{ name: "The Parish Council", nature: "organisation", hold: "belief", felt: "Notices.", id: "15385843" }],
      rules: [{ statement: "Only applewood works.", cost: "Expensive.", status: "false_belief", when_broken: "Punished", truth: "Pearwood works.", id: "8af35c43" }],
      terms: [{ term: "loafcast", meaning: "A forecast in bread.", id: "c8a6a1a3" }],
    },
  };
  const result = planBatchImport(schema, project, [{ file: "old-world.json", text: JSON.stringify(oldWorld) }]);
  assert.equal(result.accepted.length, 0);
  assert.equal(result.failed[0].reason, "wrong_format");
  assert.equal(project.world.name, "");
});

test("the same character brought in twice gets a new id the second time", async () => {
  const files = filesOf(await readyProject());
  const project = blank();
  const got = read(files["character-1"]);
  applyImport(schema, project, planImport(schema, project, got));
  const second = planImport(schema, project, got);
  assert.notEqual(second.id, got.values.id);
  assert.match(second.id, /^[0-9a-f]{8}$/);
  applyImport(schema, project, second);
  assert.equal(new Set(project.characters.map((c) => c.id)).size, 2);
});

test("a character can replace one of the writer's own, which keeps its id, its notes and its place in Setup", async () => {
  const files = filesOf(await readyProject());
  const project = await readyProject();
  const mine = project.characters[1];
  setNote(project, "characters", mine.id, "Ola is the harbour clerk.");
  const before = settledProject(schema, project);
  const got = read(files["character-1"]);
  const plan = planImport(schema, project, got, { mode: "replace", id: mine.id });
  assert.equal(plan.mode, "replace");
  assert.ok(plan.replaced.includes("Name"), "the writer is told which of their words change");
  const done = applyImport(schema, project, plan);
  assert.equal(done.instanceId, mine.id);
  assert.equal(project.characters[1].name, "Suvi");
  assert.equal(project.characters[1].id, mine.id);
  assert.equal(noteFor(project, "characters", mine.id), "Ola is the harbour clerk.");
  assert.equal(project.setup.protagonist, before.setup.protagonist);
  done.undo();
  assert.deepEqual(settledProject(schema, project), before);
});

test("undoing a new character takes it out again", async () => {
  const files = filesOf(await readyProject());
  const project = await readyProject();
  const before = settledProject(schema, project);
  const done = applyImport(schema, project, planImport(schema, project, read(files["character-1"])));
  assert.equal(project.characters.length, 3);
  done.undo();
  assert.deepEqual(settledProject(schema, project), before);
});

test("replacing a character that is not there is refused", async () => {
  const files = filesOf(await readyProject());
  assert.equal(planImport(schema, blank(), read(files["character-1"]), { mode: "replace", id: "nope" }).reason, "no_target");
});

test("Style and World fill an empty card and say what they would replace in a filled one", async () => {
  const files = filesOf(await readyProject());
  const empty = blank();
  const first = planImport(schema, empty, read(files.world));
  assert.deepEqual(first.replaced, []);
  assert.ok(first.filled.includes("Name"));
  applyImport(schema, empty, first);
  assert.equal(empty.world.name, (await readyProject()).world.name);

  const filled = await readyProject();
  filled.world.name = "My own coast";
  const plan = planImport(schema, filled, read(files.world));
  assert.ok(plan.replaced.includes("Name"));
  const before = settledProject(schema, filled);
  const done = applyImport(schema, filled, plan);
  assert.notEqual(filled.world.name, "My own coast");
  done.undo();
  assert.deepEqual(settledProject(schema, filled), before);
});

test("a card that is locked takes nothing in", async () => {
  const files = filesOf(await readyProject());
  const project = await readyProject();
  lockStaticCards(project);
  for (const kind of ["style", "character-1", "world"]) assert.equal(planImport(schema, project, read(files[kind])).reason, "locked", kind);
});

test("replacing the World counts the links it would leave pointing at nothing, and its own file leaves none", async () => {
  const project = await readyProject();
  const files = filesOf(project);
  assert.equal(planImport(schema, project, read(files.world)).lost, null, "the same world keeps every link");

  const stranger = JSON.parse(files.world);
  stranger.values.objects = stranger.values.objects.map((o, i) => ({ ...o, id: `ffffff0${i}`, name: `Other ${i}` }));
  const plan = planImport(schema, project, read(JSON.stringify(stranger)));
  assert.ok(plan.lost.count >= 1);
  assert.deepEqual(plan.lost.cards, ["Entanglements"]);
  assert.equal(linksLost(schema, project, project.world), null);
});

test("a replaced World with new ids but the same names keeps the links by re-pointing them, and Undo puts them back", async () => {
  const project = await readyProject();
  const files = filesOf(project);
  const before = JSON.stringify(project);
  const swapped = JSON.parse(files.world);
  for (const key of ["places", "objects", "powers", "rules"]) swapped.values[key] = swapped.values[key].map((o, i) => ({ ...o, id: `ee${key[0]}00${i}` }));
  const plan = planImport(schema, project, read(JSON.stringify(swapped)));
  assert.equal(plan.lost, null, "every link has a same-named match");
  assert.ok(plan.relinked >= 1);
  const done = applyImport(schema, project, plan);
  const ids = new Set(Object.values({ ...swapped.values }).flat().filter((x) => x && x.id).map((x) => x.id));
  assert.equal(linksLost(schema, project, project.world), null);
  assert.notEqual(JSON.stringify(project), before);
  assert.ok(JSON.stringify(project).includes("ee"), [...ids].length ? "links now name the new ids" : "");
  assert.equal(done.undo().done, true);
  assert.equal(JSON.stringify(project), before);
});

test("names that match more than one thing, or none, are not relinked", async () => {
  const project = await readyProject();
  const world = JSON.parse(filesOf(project).world).values;
  const twin = { ...world.objects[0], id: "twin0001" };
  const next = { ...world, objects: [{ ...world.objects[0], id: "twin0000" }, twin] };
  assert.deepEqual(relinkMap(project, next).objects, {}, "two same-named newcomers are ambiguous");
  assert.deepEqual(relinkMap(project, { ...world, objects: [{ ...world.objects[0], id: "x0000001", name: "Nothing alike" }] }).objects, {});
});

test("what the writer exported comes back the same in a new project", async () => {
  const project = await readyProject();
  const files = filesOf(project);
  const fresh = blank();
  for (const kind of ["style", "character-1", "character-2", "world"]) applyImport(schema, fresh, planImport(schema, fresh, read(files[kind])));
  const was = settledProject(schema, project);
  const now = settledProject(schema, fresh);
  assert.deepEqual(now.style, was.style);
  assert.deepEqual(now.world, was.world);
  assert.deepEqual(now.characters, was.characters);
});

test("unrelated cards and the character list are not touched by a replace", async () => {
  const files = filesOf(await readyProject());
  const project = await readyProject();
  const person = addInstance(project, characters);
  const before = settledProject(schema, project);
  applyImport(schema, project, planImport(schema, project, read(files.style)));
  const after = settledProject(schema, project);
  assert.deepEqual(after.entanglements, before.entanglements);
  assert.deepEqual(after.characters, before.characters);
  assert.ok(after.characters.some((c) => c.id === person.id));
});
