import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { createMock } from "../mock.js";
import { createClient, planChapter, generateChapter } from "../client.js";
import { lockStaticCards } from "../gate.js";
import { placeBeat, chapterInfo, suggestedCast, openPlants } from "../plan.js";
import { generateGate, generateRequest, applyGenerated, commitChapter, previousEnding, inputsKey } from "../generate.js";
import { readGenerateReply } from "../logic.js";

const quick = () => { const mock = createMock(schema, { delay: 0 }); return { mock, client: createClient({ setting: { ok: true, kind: "mock" }, mock, pollEvery: 5 }) }; };

// A started story with chapter 1 planned by the mock.
async function planned() {
  const project = await readyProject();
  lockStaticCards(project);
  const { mock, client } = quick();
  const cast = suggestedCast(project, 1);
  const plan = await planChapter(client, schema, project, cast).done;
  assert.equal(plan.ok, true);
  placeBeat(project, plan.beat);
  return { project, mock, client, beat: plan.beat };
}

const reply = (over = {}) => readGenerateReply({
  ok: true, chapter_text: "She went.\n\nHe stayed.",
  events: { happened: "Suvi left.", changed: "", planted: null, paid_off: [], reveals_landed: [], behaviors_seen: [], things_seen: [], goal_landed: false },
  shifts: [], changes: [], ...over,
});

test("the gate says why a chapter cannot be written", async () => {
  const project = await readyProject();
  assert.equal(generateGate(schema, project).reason, "not_started");
  lockStaticCards(project);
  assert.equal(generateGate(schema, project).reason, "no_beat");
  const { beat } = await planned();
  const p2 = (await planned()).project;
  const gate = generateGate(schema, p2);
  assert.equal(gate.ok, true);
  assert.equal(gate.chapter, 1);
  assert.equal(gate.stale, false);
  p2.outline.beats[0].cast = [];
  assert.equal(generateGate(schema, p2).reason, "cast_empty");
  assert.ok(beat);
});

test("the request carries the cast and what is in play, with links as names", async () => {
  const { project, beat } = await planned();
  const request = generateRequest(schema, project, beat);
  assert.equal(request.call, "generate");
  assert.equal(request.chapter, 1);
  assert.equal(request.previous_ending, null);
  assert.ok(request.setup.normal !== undefined, "chapter 1 carries normal and disruption");
  assert.equal(request.setup.protagonist, "Suvi");
  assert.deepEqual(request.cast.map((c) => c.name).sort(), ["Ola", "Suvi"]);
  assert.equal(request.beat.where, project.world.places.find((p) => p.id === beat.where).name);
  assert.ok(!JSON.stringify(request.beat).includes(beat.spotlight), "the spotlight is the pressure in words, not its id");
});

test("the mock's chapter is written, applied and committed as one unit", async () => {
  const { project, client } = await planned();
  const result = await generateChapter(client, schema, project).done;
  assert.equal(result.ok, true);
  const before = JSON.stringify(project);
  assert.equal(JSON.stringify(project), before, "nothing changed until the commit");
  commitChapter(project, result.outcome);
  assert.equal(project.chapters.length, 1);
  assert.equal(project.chapters[0].beat, result.beat.id);
  assert.equal(project.summary_events.entries[0].beat, result.beat.id);
  assert.equal(project.entanglements_history.states.length, 1);
  assert.equal(chapterInfo(project).next, 2);
  const ids = [project.chapters[0].id, project.summary_events.entries[0].id, project.entanglements_history.states[0].id, ...project.summary_shifts.shifts.map((s) => s.id)];
  assert.equal(new Set(ids).size, ids.length, "every record has its own id");
});

test("the history keeps the Entanglements as the chapter saw them, and the changes land in the live card", async () => {
  const { project, beat } = await planned();
  const pressure = project.entanglements.pressures[0];
  const out = applyGenerated(schema, project, beat, reply({ changes: [{ section: "pressures", item: pressure.id, field: "next_move", value: "Closes the gate." }] }));
  assert.equal(out.changes.applied.length, 1);
  assert.equal(out.entanglements.pressures[0].next_move, "Closes the gate.");
  assert.notEqual(out.history.state.pressures[0].next_move, "Closes the gate.");
  assert.equal(project.entanglements.pressures[0].next_move, pressure.next_move, "the project is not touched");
});

test("a change that cannot be made is dropped and says why", async () => {
  const { project, beat } = await planned();
  const p = project.entanglements.pressures[0];
  const out = applyGenerated(schema, project, beat, reply({ changes: [
    { section: "pressures", item: "nope", field: "what", value: "x" },
    { section: "pressures", item: p.id, field: "source_agent", value: "Suvi" },
    { section: "pressures", item: p.id, field: "bears_on", value: ["Nobody At All"] },
    { section: "knowledge", item: project.entanglements.knowledge[0]?.id ?? "x", field: "status", value: "dreams" },
  ] }));
  assert.equal(out.changes.applied.length, 0);
  assert.equal(out.changes.dropped.length, 4);
  assert.ok(out.warnings.some((w) => w.kind === "dropped"));
});

test("a change to a locked value asks first; declining leaves it, confirming unlocks it", async () => {
  const { project, beat } = await planned();
  const p = project.entanglements.pressures[0];
  project.locks.push({ id: "lock0001", card: "entanglements", field: "pressures", item: p.id, part: "next_move" });
  const change = { section: "pressures", item: p.id, field: "next_move", value: "Closes the gate." };
  const asked = applyGenerated(schema, project, beat, reply({ changes: [change] }));
  assert.equal(asked.changes.locked.length, 1);
  assert.deepEqual(asked.unlock, ["lock0001"]);
  const declined = applyGenerated(schema, project, beat, reply({ changes: [change] }), { overwriteLocked: false });
  assert.equal(declined.changes.applied.length, 0);
  assert.deepEqual(declined.unlock, []);
  commitChapter(project, declined);
  assert.ok(project.locks.some((l) => l.id === "lock0001"), "a declined change keeps its lock");
  assert.equal(project.entanglements.pressures[0].next_move, p.next_move);
  const { project: p2, beat: b2 } = await planned();
  p2.locks.push({ id: "lock0002", card: "entanglements" });
  const out = applyGenerated(schema, p2, b2, reply({ changes: [{ section: "ties", item: p2.entanglements.ties[0].id, field: "bond", value: "Estranged." }] }));
  assert.equal(out.changes.locked.length, 1, "a whole-card lock covers every change");
  commitChapter(p2, out);
  assert.ok(!p2.locks.some((l) => l.id === "lock0002"));
  assert.equal(p2.entanglements.ties[0].bond, "Estranged.");
});

test("shifts map to people in the chapter, once each", async () => {
  const { project, beat } = await planned();
  const out = applyGenerated(schema, project, beat, reply({ shifts: [
    { character: "Suvi", decided: "Leave." }, { character: "Suvi", fears: "Again." }, { character: "Stranger", wants: "x" },
  ] }));
  assert.equal(out.shifts.length, 1);
  assert.equal(out.shifts[0].character, project.setup.protagonist);
  assert.equal(out.shifts[0].beat, beat.id);
  assert.equal(out.warnings.filter((w) => w.kind === "unmatched").length, 2);
});

test("a plant is not counted when two are already open; a reveal with no knowledge change warns", async () => {
  const { project, beat } = await planned();
  const beat0 = project.outline.beats[0].id;
  project.summary_events = { entries: [
    { id: "e0000001", beat: "gone", happened: "a", planted: "First thing.", paid_off: [] },
    { id: "e0000002", beat: "gone2", happened: "b", planted: "Second thing.", paid_off: [] },
  ] };
  assert.equal(openPlants(project).length, 2);
  beat.plant = "Third thing.";      // only the plant the beat planned can land
  const out = applyGenerated(schema, project, beat, reply({ events: { happened: "x", planted: "Third thing.", paid_off: [], reveals_landed: [], behaviors_seen: [], things_seen: [], goal_landed: false } }));
  assert.equal(out.events.planted, "");
  assert.ok(out.warnings.some((w) => w.kind === "plant"));
  assert.ok(beat0);
  const paid = applyGenerated(schema, project, beat, reply({ events: { happened: "x", planted: "Third thing.", paid_off: ["First thing."], reveals_landed: [], behaviors_seen: [], things_seen: [], goal_landed: false } }));
  assert.deepEqual(paid.events.paid_off, ["e0000001"]);
  assert.equal(paid.events.planted, "Third thing.");
});

test("the previous chapter's end is carried into the next request", async () => {
  const { project, client } = await planned();
  const result = await generateChapter(client, schema, project).done;
  commitChapter(project, result.outcome);
  assert.match(previousEnding(project), /Mock chapter 1/);
  assert.equal(previousEnding({ chapters: [{ text: "x ".repeat(3000) }] }).length <= 1500, true);
});

test("editing the Entanglements while the model writes throws the chapter away", async () => {
  const { project, client, mock } = await planned();
  const call = generateChapter(client, schema, project);
  project.entanglements.ties[0].bond = "Changed meanwhile.";
  const result = await call.done;
  assert.deepEqual([result.ok, result.reason], [false, "changed"]);
  assert.equal(project.chapters ?? undefined, undefined);
  assert.ok(mock);
});

test("a failed or stopped call changes nothing", async () => {
  const { project, client, mock } = await planned();
  const before = JSON.stringify(project);
  mock.queue("bad_output");
  const bad = await generateChapter(client, schema, project).done;
  assert.deepEqual([bad.ok, bad.error.kind], [false, "bad_output"]);
  mock.queue("too_long");
  assert.equal((await generateChapter(client, schema, project).done).error.kind, "too_long");
  const slow = createMock(schema, { delay: 50 });
  const c2 = createClient({ setting: { ok: true, kind: "mock" }, mock: slow, pollEvery: 5 });
  const call = generateChapter(c2, schema, project);
  call.stop();
  assert.equal((await call.done).error.kind, "stopped");
  assert.equal(JSON.stringify(project), before);
});

test("the status names the stage while the chapter is written", async () => {
  const { project } = await planned();
  const slow = createMock(schema, { delay: 90 });
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock: slow, pollEvery: 10 });
  const seen = new Set();
  client.onChange(() => seen.add(client.state.stage));
  await generateChapter(client, schema, project).done;
  for (const stage of ["write", "events", "shifts"]) assert.ok(seen.has(stage), `saw ${stage}`);
});

test("the inputs key changes when the beat changes", async () => {
  const { project, beat } = await planned();
  const a = inputsKey(schema, project, beat);
  assert.notEqual(a, inputsKey(schema, project, { ...beat, turn: "Different." }));
});

test("an extractor that echoes an open plant plants nothing, and a beat plant that duplicates one is not counted", async () => {
  const { project, beat } = await planned();
  project.summary_events = { entries: [{ id: "e0000001", beat: "gone", happened: "a", planted: "The pond is warm.", paid_off: [] }] };
  beat.plant = "";
  const echo = applyGenerated(schema, project, beat, reply({ events: { happened: "x", planted: "The pond is warm.", paid_off: [], reveals_landed: [], behaviors_seen: [], things_seen: [], goal_landed: false } }));
  assert.equal(echo.events.planted, "", "the beat planned nothing");
  beat.plant = "The pond is warm.";
  const again = applyGenerated(schema, project, beat, reply({ events: { happened: "x", planted: "The pond is warm.", paid_off: [], reveals_landed: [], behaviors_seen: [], things_seen: [], goal_landed: false } }));
  assert.equal(again.events.planted, "", "the same words are already open");
});

test("two plants with the same words get different labels, so a payoff names one of them", async () => {
  const { project, beat } = await planned();
  project.outline.beats[0].chapter = 1;
  project.summary_events = { entries: [
    { id: "e0000001", beat: project.outline.beats[0].id, happened: "a", planted: "The pond is warm.", paid_off: [] },
    { id: "e0000002", beat: "later", happened: "b", planted: "The pond is warm.", paid_off: [] },
  ] };
  const texts = openPlants(project).map((p) => p.text);
  assert.equal(new Set(texts).size, 2);
  const out = applyGenerated(schema, project, beat, reply({ events: { happened: "x", planted: null, paid_off: [openPlants(project).find((p) => p.id === "e0000002").text], reveals_landed: [], behaviors_seen: [], things_seen: [], goal_landed: false } }));
  assert.deepEqual(out.events.paid_off, ["e0000002"]);
});

test("a change value written as old -> new keeps only the new words", async () => {
  const { project, beat } = await planned();
  const tie = project.entanglements.ties[0];
  const out = applyGenerated(schema, project, beat, reply({ changes: [{ section: "ties", item: tie.id, field: "bond", value: `${tie.bond} -> grown close` }] }));
  assert.equal(out.entanglements.ties.find((x) => x.id === tie.id).bond, "grown close");
});
