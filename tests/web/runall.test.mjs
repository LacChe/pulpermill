import "./text-setup.mjs";
// Run all: plans and writes every remaining chapter in turn, stops at the first problem, keeps what is written, and can be stopped.
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { createMock } from "../../web/mock.js";
import { createClient } from "../../web/client.js";
import { createRunAll, STRINGS } from "../../web/runall.js";
import { lockStaticCards } from "../../web/gate.js";
import { chapterInfo, beatForChapter } from "../../web/plan.js";
import { errorText } from "../../web/render.js";

async function setup({ chapters = 6, delay = 0 } = {}) {
  const project = await readyProject();
  project.setup.chapter_count = chapters;
  lockStaticCards(project);
  const mock = createMock(schema, { delay });
  const client = createClient({ setting: { kind: "mock" }, mock, pollEvery: 5, sleep: () => Promise.resolve() });
  const log = { notices: [], changed: 0, redraws: 0 };
  const runAll = createRunAll({
    schema, client, getProject: () => project, errorText,
    changed: () => { log.changed++; }, redraw: () => { log.redraws++; },
    notice: (text, kind = "") => log.notices.push({ text, kind }),
  });
  return { project, mock, client, runAll, log };
}

test("it runs a 6-chapter story to the end, saving after each step", async () => {
  const { project, runAll, log } = await setup();
  const result = await runAll.start(project);
  assert.deepEqual([result.ok, result.written], [true, 6]);
  assert.equal((project.chapters ?? []).length, 6);
  assert.ok(chapterInfo(project).done);
  assert.equal(project.summary_events.entries.length, 6);
  assert.equal(project.outline.beats.length, 6);
  for (const beat of project.outline.beats) assert.match(beat.plan, /Mock plan/);
  assert.equal(log.changed, 12, "one save after each plan and each chapter");
  assert.equal(log.notices.length, 1);
  assert.equal(log.notices[0].kind, "");
  assert.match(log.notices[0].text, /6 chapter/);
  assert.equal(runAll.running, false);
});

test("a failure at chapter 3 leaves chapters 1 and 2 committed and says which chapter failed and why", async () => {
  const { project, mock, runAll, log } = await setup();
  mock.queue(undefined, undefined, undefined, undefined, "bad_output");   // plan 1, write 1, plan 2, write 2, then plan 3 fails
  const result = await runAll.start(project);
  assert.deepEqual([result.ok, result.written, result.stoppedAt], [false, 2, 3]);
  assert.equal((project.chapters ?? []).length, 2);
  assert.equal(beatForChapter(project, 3), null, "the failed chapter leaves no empty beat behind");
  const notice = log.notices.at(-1);
  assert.equal(notice.kind, "notice-bad");
  assert.match(notice.text, /chapter 3/);
  assert.match(notice.text, /planning/);
  assert.ok(notice.text.includes(errorText({ kind: "bad_output" })));
  assert.ok(notice.text.includes(STRINGS.kept));
  assert.equal(runAll.running, false);
});

test("a failure while writing stops there and keeps the plan", async () => {
  const { project, mock, runAll, log } = await setup();
  mock.queue(undefined, undefined, undefined, "too_long");                 // plan 1, write 1, plan 2, write 2 fails
  const result = await runAll.start(project);
  assert.deepEqual([result.written, result.stoppedAt], [1, 2]);
  assert.match(log.notices.at(-1).text, /writing/);
  assert.ok(beatForChapter(project, 2).plan, "the plan of chapter 2 stays, so the single button can write it");
});

test("a gate that refuses stops the run with its reason", async () => {
  const { project, runAll, log } = await setup();
  project.setup.protagonist = "";                                          // no tie can be spotlighted without people: break the cast
  const first = project.entanglements.ties[0];
  project.entanglements.ties = project.entanglements.ties.filter((t) => t !== first && t.id !== first.id);
  const result = await runAll.start(project);
  assert.equal(result.ok, false);
  assert.equal((project.chapters ?? []).length, 0);
  assert.equal(log.notices.at(-1).kind, "notice-bad");
});

test("every chapter of a run is planned with choose and the rules and objects, and the picked pair lands on the beat", async () => {
  const { project, mock, runAll } = await setup({ chapters: 2 });
  const plans = [];
  const send = mock.send.bind(mock);
  mock.send = (request, options) => { if (request.call === "plan") plans.push(request); return send(request, options); };
  const outcome = await runAll.start(project);
  assert.equal(outcome.ok, true);
  assert.equal(plans.length, 2);
  for (const request of plans) {
    assert.equal(request.choose, true, "Run all asks the planner to choose");
    assert.ok(Array.isArray(request.pressure_options));
  }
  const first = project.outline.beats.find((b) => Number(b.chapter) === 1);
  assert.ok(first.spotlight, "the picked tie is on the beat");
});

test("a beat the writer already planned is written as it is, not planned again", async () => {
  const { project, mock, runAll } = await setup({ chapters: 2 });
  const sent = [];
  const send = mock.send.bind(mock);
  mock.send = (request, options) => { sent.push(request.call); return send(request, options); };
  await runAll.start(project);
  assert.equal(sent.filter((c) => c === "plan").length, 2);
  // a second story whose first chapter is planned by hand
  const again = await setup({ chapters: 2 });
  const calls = [];
  const send2 = again.mock.send.bind(again.mock);
  again.mock.send = (request, options) => { calls.push(request.call); return send2(request, options); };
  const { newBeat, commitPlan } = await import("../../web/plan.js");
  const { planChapter } = await import("../../web/client.js");
  const made = await planChapter(again.client, schema, again.project, newBeat(schema, again.project, 1)).done;
  made.beat.plan = "My own plan.";                                          // the writer edited the plan by hand
  commitPlan(again.project, made.beat);
  calls.length = 0;
  const outcome = await again.runAll.start(again.project);
  assert.equal(outcome.ok, true, JSON.stringify(again.log.notices));
  assert.equal(again.project.outline.beats.find((b) => Number(b.chapter) === 1).plan, "My own plan.");
  assert.deepEqual(calls.filter((c) => c === "plan").length, 1, "only chapter 2 was planned");
});

test("the first chapter starts from the beat the panel shows (its spotlight and cast)", async () => {
  const { project, mock, runAll } = await setup({ chapters: 1 });
  const { newBeat } = await import("../../web/plan.js");
  const beat = newBeat(schema, project, 1);
  let spotlight = null;
  const send = mock.send.bind(mock);
  mock.send = (request, options) => { if (request.call === "plan") spotlight = request.spotlight; return send(request, options); };
  await runAll.start(project, beat);
  assert.equal(spotlight, beat.spotlight);
});

test("Stop mid-run cancels the call, ends the loop and keeps the finished chapters", async () => {
  const { project, runAll, log } = await setup({ delay: 30 });
  const run = runAll.start(project);
  while ((project.chapters ?? []).length < 2) await new Promise((r) => setTimeout(r, 5));
  assert.ok(runAll.running);
  assert.match(runAll.progressText(), /Chapter \d of 6/);
  runAll.stop();
  const result = await run;
  assert.equal(result.reason, "stopped");
  assert.ok((project.chapters ?? []).length >= 2 && (project.chapters ?? []).length < 6);
  assert.equal(log.notices.at(-1).kind, "");
  assert.match(log.notices.at(-1).text, /Stopped during chapter/);
  assert.equal(runAll.running, false);
});

test("it will not start twice, nor on a finished story", async () => {
  const { project, runAll } = await setup({ chapters: 1, delay: 10 });
  const first = runAll.start(project);
  assert.equal((await runAll.start(project)).reason, "running");
  await first;
  assert.equal((await runAll.start(project)).reason, "nothing_to_do");
});

test("opening another project ends the run without a word", async () => {
  const { project, runAll, log } = await setup({ delay: 20 });
  let current = project;
  const again = createRunAll({ schema, client: (await setup()).client, getProject: () => current, errorText, changed() {}, redraw() {}, notice: (t) => log.notices.push(t) });
  const run = again.start(project);
  current = {};
  const result = await run;
  assert.equal(result.reason, "switched");
  assert.equal(log.notices.length, 0);
  assert.ok(runAll);
});
