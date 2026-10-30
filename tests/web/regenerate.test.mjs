import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { createMock } from "../../web/mock.js";
import { createClient, planChapter, generateChapter, regenerateChapter } from "../../web/client.js";
import { lockStaticCards } from "../../web/gate.js";
import { placeBeat, suggestedCast } from "../../web/plan.js";
import { commitChapter, regenerateGate, projectBefore, applyRegenerated, commitRegenerated, generateRequest } from "../../web/generate.js";

// A started story with two chapters written by the mock.
async function twoChapters() {
  const project = await readyProject();
  project.setup.chapter_count = 5;
  lockStaticCards(project);
  const mock = createMock(schema, { delay: 0 });
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock, pollEvery: 5 });
  for (let n = 1; n <= 2; n++) {
    const plan = await planChapter(client, schema, project, suggestedCast(project, n)).done;
    placeBeat(project, plan.beat);
    commitChapter(project, (await generateChapter(client, schema, project).done).outcome);
  }
  return { project, mock, client };
}

test("the gate says why a chapter cannot be written again", async () => {
  const { project } = await twoChapters();
  assert.equal(regenerateGate(schema, project, 3).reason, "no_chapter");
  const gate = regenerateGate(schema, project, 1);
  assert.equal(gate.ok, true);
  assert.equal(gate.later, 1);
  project.entanglements_history.states = [];
  assert.equal(regenerateGate(schema, project, 1).reason, "no_snapshot");
});

test("the trial project is the story as it stood before that chapter", async () => {
  const { project } = await twoChapters();
  const trial = projectBefore(project, 2);
  assert.equal(trial.chapters.length, 1);
  assert.equal(trial.summary_events.entries.length, 1);
  assert.equal(trial.entanglements_history.states.length, 1);
  assert.deepEqual(trial.entanglements, project.entanglements_history.states[1].state);
  const first = projectBefore(project, 1);
  assert.equal(first.chapters.length, 0);
  const request = generateRequest(schema, first, first.outline.beats[0]);
  assert.equal(request.chapter, 1);
  assert.equal(request.previous_ending, null);
  assert.deepEqual(request.earlier_events, []);
});

test("writing chapter 2 again asks from chapter 1's ending", async () => {
  const { project } = await twoChapters();
  const gate = regenerateGate(schema, project, 2);
  const request = generateRequest(schema, gate.trial, gate.beat);
  assert.equal(request.chapter, 2);
  assert.match(request.previous_ending, /Mock chapter 1/);
  assert.equal(request.earlier_events.length, 1);
});

test("regenerating replaces the chapter and its records, keeps their ids, marks later beats stale, and can be undone", async () => {
  const { project, client } = await twoChapters();
  const ids = { chapter: project.chapters[0].id, event: project.summary_events.entries[0].id, history: project.entanglements_history.states[0].id };
  const was = JSON.stringify(project);
  const result = await regenerateChapter(client, schema, project, 1).done;
  assert.equal(result.ok, true);
  assert.equal(JSON.stringify(project), was, "nothing changed until the commit");
  assert.match(result.outcome.before, /Mock chapter 1/);
  const { undo } = commitRegenerated(project, result.outcome);
  assert.equal(project.chapters.length, 2);
  assert.equal(project.summary_events.entries.length, 2);
  assert.equal(project.entanglements_history.states.length, 2);
  assert.equal(project.chapters[0].id, ids.chapter);
  assert.equal(project.summary_events.entries[0].id, ids.event);
  assert.equal(project.entanglements_history.states[0].id, ids.history);
  assert.equal(project.outline.beats.find((b) => b.chapter === 2).stale, true);
  assert.equal(project.outline.beats.find((b) => b.chapter === 1).stale, false);
  assert.ok(result.outcome.warnings.some((w) => w.kind === "later"));
  const all = [...project.chapters, ...project.summary_events.entries, ...project.entanglements_history.states, ...project.summary_shifts.shifts].map((x) => x.id);
  assert.equal(new Set(all).size, all.length, "no id is used twice");
  undo();
  assert.equal(JSON.stringify(project), was);
});

test("the Entanglements go back to what the chapter was written from, then take the new result", async () => {
  const { project, client } = await twoChapters();
  const snapshot = JSON.stringify(project.entanglements_history.states[0].state);
  project.entanglements.ties[0].bond = "Edited after chapter 2.";
  const gate = regenerateGate(schema, project, 1);
  assert.equal(JSON.stringify(gate.trial.entanglements), snapshot);
  const result = await regenerateChapter(client, schema, project, 1).done;
  commitRegenerated(project, result.outcome);
  assert.notEqual(project.entanglements.ties[0].bond, "Edited after chapter 2.");
});

test("a locked value asks again, and declining keeps it", async () => {
  const { project, client } = await twoChapters();
  const p = project.entanglements_history.states[0].state.pressures[0];
  project.locks.push({ id: "lock0001", card: "entanglements", field: "pressures", item: p.id, part: "next_move" });
  const result = await regenerateChapter(client, schema, project, 1).done;
  assert.equal(result.outcome.changes.locked.length, 1);
  const declined = applyRegenerated(schema, project, result.ctx, result.read, { overwriteLocked: false });
  assert.deepEqual(declined.unlock, []);
  commitRegenerated(project, declined);
  assert.ok(project.locks.some((l) => l.id === "lock0001"));
});

test("a failed, stopped or interrupted call changes nothing", async () => {
  const { project, client, mock } = await twoChapters();
  const was = JSON.stringify(project);
  mock.queue("bad_output");
  assert.equal((await regenerateChapter(client, schema, project, 1).done).error.kind, "bad_output");
  const call = regenerateChapter(client, schema, project, 1);
  project.outline.beats[0].turn = "Edited while the model wrote.";
  assert.equal((await call.done).reason, "changed");
  project.outline.beats[0].turn = JSON.parse(was).outline.beats[0].turn;
  assert.equal(JSON.stringify(project), was);
});
