import { test } from "node:test";
import assert from "node:assert/strict";
import { readProject, projectSnapshot as projectText, newProject, settledProject, addInstance } from "../logic.js";
import { schema, readyProject } from "./helpers.mjs";
import {
  STATIC_CARDS, GATE_CARDS, cardLocked, storyStarted, lockStaticCards, unlockStaticCards, canUnlock, startGate,
} from "../gate.js";

const characters = schema.cards.characters;

test("the static cards and the cards the gate checks", () => {
  assert.deepEqual(STATIC_CARDS, ["style", "characters", "world", "setup"]);
  assert.deepEqual(GATE_CARDS, ["style", "characters", "world", "entanglements", "setup"]);
  for (const id of GATE_CARDS) assert.ok(schema.cards[id], id);
});

test("a card is locked by a lock that names the whole card and nothing narrower", () => {
  const p = { locks: [{ id: "l1", card: "world", field: "places" }, { id: "l2", card: "characters", owner: "c1" }, { id: "l3", card: "style" }] };
  assert.equal(cardLocked(p, "world"), false);
  assert.equal(cardLocked(p, "characters"), false);
  assert.equal(cardLocked(p, "style"), true);
  assert.equal(cardLocked({}, "style"), false);
});

test("starting the story locks the four static cards, once, and leaves the rest alone", () => {
  const p = { locks: [{ id: "l1", card: "world", field: "places" }] };
  assert.equal(storyStarted(p), false);
  lockStaticCards(p);
  assert.equal(storyStarted(p), true);
  assert.equal(p.locks.length, 1 + 4, "the narrow lock stays, one whole-card lock per static card");
  lockStaticCards(p);
  assert.equal(p.locks.length, 5, "pressing it twice adds nothing");
  assert.equal(new Set(p.locks.map((l) => l.id)).size, 5, "every lock has its own id");
  for (const id of ["entanglements", "outline"]) assert.equal(cardLocked(p, id), false, id);
  const none = lockStaticCards({});
  assert.equal(none.locks.length, 4);
});

test("unlocking takes off the whole-card locks and keeps the narrow ones", () => {
  const p = lockStaticCards({ locks: [{ id: "l1", card: "world", field: "places" }] });
  unlockStaticCards(p);
  assert.deepEqual(p.locks, [{ id: "l1", card: "world", field: "places" }]);
  assert.equal(storyStarted(p), false);
});

test("the cards can be unlocked only until a chapter has been written", () => {
  assert.equal(canUnlock({}), true);
  assert.equal(canUnlock({ chapters: [] }), true);
  assert.equal(canUnlock({ chapters: [{ id: "x" }] }), false);
});

test("an empty project stops on every card, and a project with no characters says so", () => {
  const gate = startGate(schema, newProject(schema));
  assert.equal(gate.ok, false);
  const stopped = gate.stops.map((s) => s.card);
  for (const id of ["style", "characters", "world", "setup"]) assert.ok(stopped.includes(id), id);
  assert.equal(stopped.includes("outline"), false, "the outline has no beats yet and is not part of the gate");
  const people = gate.stops.find((s) => s.card === "characters");
  assert.deepEqual([people.count, people.id, people.problems], [0, null, []]);
  const style = gate.stops.find((s) => s.card === "style");
  assert.ok(style.count > 0 && style.problems[0].message);
});

test("a stop for a character names the character and holds the rule's words", () => {
  const p = settledProject(schema, newProject(schema));
  const person = addInstance(p, characters);
  person.name = "Suvi";
  const stop = startGate(schema, p).stops.find((s) => s.card === "characters");
  assert.equal(stop.id, person.id);
  assert.equal(stop.name, "Suvi");
  assert.ok(stop.count > 0);
  assert.ok(stop.problems.every((x) => x.message));
});

test("a project whose cards are all sound passes the gate", async () => {
  const gate = startGate(schema, await readyProject());
  assert.deepEqual(gate, { ok: true, stops: [] });
});

test("one broken card is the only stop, and fixing it opens the gate", async () => {
  const p = await readyProject();
  p.world.name = "";
  const gate = startGate(schema, p);
  assert.deepEqual(gate.stops.map((s) => s.card), ["world"]);
  p.world.name = "The Salt Coast";
  assert.equal(startGate(schema, p).ok, true);
});

test("the gate counts only what blocks: a warning does not stop the story", async () => {
  const p = await readyProject();
  const before = startGate(schema, p);
  p.world.era_and_technology = p.world.era_and_technology + " (a long, vague mood rather than a fact)";
  assert.deepEqual(startGate(schema, p), before);
});

test("the gate does not change the project it reads", async () => {
  const p = await readyProject();
  const text = JSON.stringify(p);
  startGate(schema, p);
  assert.equal(JSON.stringify(p), text);
});

test("the locks survive saving and opening the project", async () => {
  const p = lockStaticCards(await readyProject());
  const read = readProject(projectText(schema, p), schema);
  assert.equal(read.ok, true);
  assert.equal(storyStarted(read.project), true);
});
