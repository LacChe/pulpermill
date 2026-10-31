import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { readProject, projectSnapshot } from "../../web/logic.js";
import {
  STATIC_CARDS, cardLocked, lockedByStory, lockedByWriter, setWriterLock, storyStarted, lockStaticCards, unlockStaticCards,
} from "../../web/gate.js";
import { planGate, ensureBeat } from "../../web/plan.js";
import { regenerateGate } from "../../web/generate.js";

const ALL = ["style", "characters", "world", "entanglements", "setup", "outline"];

test("the writer can lock and unlock each of the six cards", () => {
  const p = {};
  for (const id of ALL) {
    assert.equal(cardLocked(p, id), false);
    setWriterLock(p, id, true);
    assert.equal(cardLocked(p, id), true);
    assert.equal(lockedByWriter(p, id), true);
    assert.equal(lockedByStory(p, id), false);
  }
  assert.equal(p.locks.length, 6);
  setWriterLock(p, "world", true);
  assert.equal(p.locks.length, 6, "locking twice adds nothing");
  for (const id of ALL) setWriterLock(p, id, false);
  assert.deepEqual(p.locks, []);
});

test("locking the four static cards by hand does not start the story", () => {
  const p = {};
  for (const id of STATIC_CARDS) setWriterLock(p, id, true);
  assert.equal(STATIC_CARDS.every((id) => cardLocked(p, id)), true);
  assert.equal(storyStarted(p), false);
});

test("starting the story adds its own lock beside the writer's, and unlocking takes off only the story's", () => {
  const p = {};
  setWriterLock(p, "style", true);
  lockStaticCards(p);
  assert.equal(storyStarted(p), true);
  assert.equal(p.locks.filter((l) => l.card === "style").length, 2);
  unlockStaticCards(p);
  assert.equal(storyStarted(p), false);
  assert.equal(lockedByWriter(p, "style"), true, "the writer's lock stays");
  assert.equal(cardLocked(p, "characters"), false);
});

test("the writer's lock button never removes the story's lock", () => {
  const p = lockStaticCards({});
  setWriterLock(p, "world", false);
  assert.equal(lockedByStory(p, "world"), true);
});

test("a writer's lock survives saving and opening the project", async () => {
  const p = await readyProject();
  setWriterLock(p, "outline", true);
  const read = readProject(projectSnapshot(schema, p), schema);
  assert.equal(read.ok, true);
  assert.equal(lockedByWriter(read.project, "outline"), true);
  assert.equal(storyStarted(read.project), false);
});

test("a locked Outline card stops planning and writing a chapter again, but not writing the next one", async () => {
  const p = lockStaticCards(await readyProject());
  const beat = ensureBeat(schema, p);
  setWriterLock(p, "outline", true);
  assert.equal(planGate(p, beat).reason, "outline_locked");
  assert.equal(regenerateGate(schema, p, 1).reason, "outline_locked");
  setWriterLock(p, "outline", false);
  assert.equal(planGate(p, beat).ok, true);
});
