import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { newProject } from "../../web/logic.js";
import { createMock } from "../../web/mock.js";
import { createClient, planChapter, generateChapter } from "../../web/client.js";
import { lockStaticCards } from "../../web/gate.js";
import { placeBeat, suggestedCast } from "../../web/plan.js";
import { commitChapter } from "../../web/generate.js";
import { welcomeSteps, STEP_IDS } from "../../web/welcome.js";

const states = (project) => Object.fromEntries(welcomeSteps(schema, project).map((s) => [s.id, s.state]));

test("a blank project starts at the cards, and points at the first thing that stops the story", () => {
  const steps = welcomeSteps(schema, newProject(schema));
  assert.deepEqual(steps.map((s) => s.id), STEP_IDS);
  assert.deepEqual(steps.map((s) => s.state), ["next", "later", "later", "later", "later"]);
  assert.equal(steps[0].stop.card, "style");
});

test("with every card sound the way moves on to starting the story, then to the chapters", async () => {
  const project = await readyProject();
  assert.deepEqual(states(project), { cards: "done", start: "next", chapters: "later", end: "later", download: "later" });
  lockStaticCards(project);
  assert.deepEqual(states(project), { cards: "done", start: "done", chapters: "next", end: "later", download: "later" });
  assert.equal(welcomeSteps(schema, project).find((s) => s.id === "chapters").count, Number(project.setup.chapter_count) || 0);
});

test("once chapters are written, downloading opens, and once all are written so does ending the story", async () => {
  const project = await readyProject();
  project.setup.chapter_count = 2;
  lockStaticCards(project);
  const mock = createMock(schema, { delay: 0 });
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock, pollEvery: 5 });
  const write = async (n) => {
    const plan = await planChapter(client, schema, project, suggestedCast(project, n)).done;
    placeBeat(project, plan.beat);
    commitChapter(project, (await generateChapter(client, schema, project).done).outcome);
  };
  await write(1);
  assert.deepEqual(states(project), { cards: "done", start: "done", chapters: "next", end: "later", download: "next" });
  assert.equal(welcomeSteps(schema, project).find((s) => s.id === "chapters").written, 1);
  await write(2);
  assert.deepEqual(states(project), { cards: "done", start: "done", chapters: "done", end: "next", download: "next" });
  project.after_story = { style: {}, characters: [], world: {} };
  assert.deepEqual(states(project), { cards: "done", start: "done", chapters: "done", end: "done", download: "next" });
});

test("the steps change nothing in the project", async () => {
  const project = await readyProject();
  const before = JSON.stringify(project);
  welcomeSteps(schema, project);
  assert.equal(JSON.stringify(project), before);
});
