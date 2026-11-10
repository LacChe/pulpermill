import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { newProject } from "../../web/logic.js";
import { createMock } from "../../web/mock.js";
import { createClient, planChapter, generateChapter } from "../../web/client.js";
import { lockStaticCards } from "../../web/gate.js";
import { ensureBeat, placeBeat } from "../../web/plan.js";
import { commitChapter } from "../../web/generate.js";
import { welcomePhases, PHASE_IDS } from "../../web/welcome.js";

const states = (project) => Object.fromEntries(welcomePhases(schema, project).phases.map((p) => [p.id, p.state]));

test("a blank project starts in Design, and points at the first thing that stops the story", () => {
  const facts = welcomePhases(schema, newProject(schema));
  assert.deepEqual(facts.phases.map((p) => p.id), PHASE_IDS);
  assert.deepEqual(facts.phases.map((p) => p.state), ["next", "later"]);
  assert.equal(facts.stop.card, "style");
  assert.equal(facts.canStart, false);
  assert.ok(facts.cards.some((c) => !c.ready));
});

test("with every card sound the story can start, and starting it moves the writer on to Write", async () => {
  const project = await readyProject();
  let facts = welcomePhases(schema, project);
  assert.deepEqual(states(project), { design: "next", write: "later" });
  assert.equal(facts.canStart, true);
  assert.ok(facts.cards.every((c) => c.ready));
  assert.equal(facts.stop, null);
  lockStaticCards(project);
  facts = welcomePhases(schema, project);
  assert.deepEqual(states(project), { design: "done", write: "next" });
  assert.equal(facts.canStart, false);
  assert.equal(facts.count, Number(project.setup.chapter_count) || 0);
});

test("chapters written are counted, and Write is done once all are written", async () => {
  const project = await readyProject();
  project.setup.chapter_count = 2;
  lockStaticCards(project);
  const mock = createMock(schema, { delay: 0 });
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock, pollEvery: 5 });
  const write = async () => {
    const plan = await planChapter(client, schema, project, ensureBeat(schema, project)).done;
    placeBeat(project, plan.beat);
    commitChapter(project, (await generateChapter(client, schema, project).done).outcome);
  };
  await write();
  let facts = welcomePhases(schema, project);
  assert.deepEqual([facts.written, facts.allWritten, facts.finished], [1, false, false]);
  assert.deepEqual(states(project), { design: "done", write: "next" });
  await write();
  facts = welcomePhases(schema, project);
  assert.deepEqual([facts.written, facts.allWritten], [2, true]);
  assert.deepEqual(states(project), { design: "done", write: "done" });
  project.after_story = { style: {}, characters: [], world: {}, entanglements: {} };
  assert.equal(welcomePhases(schema, project).finished, true);
});

test("the guide changes nothing in the project", async () => {
  const project = await readyProject();
  const before = JSON.stringify(project);
  welcomePhases(schema, project);
  assert.equal(JSON.stringify(project), before);
});
