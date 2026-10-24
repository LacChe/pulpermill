import "./text-setup.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  newProject, settledProject, addInstance, addItem, fillRequest, readFillReply, planFill, setCardValues, judgeRequest,
  readJudgeReply, styleFitRequest, readStyleFitReply, readStatus, modelRules, validate, FILLABLE,
} from "../logic.js";
import { createMock, MOCK_FLAG } from "../mock.js";

const schema = JSON.parse(readFileSync(new URL("../data/schema.en.json", import.meta.url), "utf8"));
const characters = schema.cards.characters;

// A project with two people and a power, an example chapter to fill from, and every card settled.
function project() {
  const p = settledProject(schema, { ...newProject(schema), example_chapter: "Once." });
  const suvi = addInstance(p, characters);
  suvi.name = "Suvi";
  const ola = addInstance(p, characters);
  ola.name = "Ola";
  addItem(schema.cards.world.fields.find((f) => f.key === "powers"), p.world.powers).name = "The Salt Guild";
  p.setup.protagonist = suvi.id;
  return p;
}

const quick = () => createMock(schema, { delay: 0 });

test("status says idle, and busy while a call is running", async () => {
  const mock = createMock(schema, { delay: 30 });
  assert.deepEqual(readStatus(await mock.send({ call: "status" })), { ok: true, state: "idle" });
  const p = project();
  const running = mock.send(fillRequest(schema, p, "world").request);
  assert.equal((await mock.send({ call: "status" })).state, "busy");
  assert.equal(mock.busy, true);
  await running;
  assert.equal((await mock.send({ call: "status" })).state, "idle");
});

test("every fillable card gets a reply the page can read and plan, with its links resolved", async () => {
  const mock = quick();
  const p = project();
  for (const id of FILLABLE) {
    const card = schema.cards[id];
    const instance = card.many_per_project ? p.characters[0].id : null;
    const { request } = fillRequest(schema, p, id, instance);
    const read = readFillReply(card, await mock.send(request));
    assert.equal(read.ok, true, id);
    assert.deepEqual(read.ignored, [], `${id} names only the card's own fields`);
    const current = card.many_per_project ? p.characters[0] : p[id];
    const plan = planFill(card, current, read, p);
    assert.deepEqual(plan.unresolved, [], `${id} links to things that exist`);
    assert.ok(plan.filled.length + plan.replaced.length > 0, id);
  }
});

test("the sample for Entanglements links the people and the power the project has", async () => {
  const p = project();
  const card = schema.cards.entanglements;
  const read = readFillReply(card, await quick().send(fillRequest(schema, p, "entanglements").request));
  const plan = planFill(card, p.entanglements, read, p);
  setCardValues(card, p.entanglements, plan.next);
  const ids = new Set([...p.characters.map((c) => c.id), p.world.powers[0].id]);
  assert.ok(p.entanglements.ties.length > 0);
  for (const tie of p.entanglements.ties) assert.ok(ids.has(tie.tie_from) && ids.has(tie.tie_to));
  assert.equal(validate(card, p.entanglements, p, schema.common).problems.some((x) => x.kind === "invalid"), false);
});

test("setup's protagonist comes back as a name and lands as that person's id", async () => {
  const p = project();
  p.setup.protagonist = "";
  const card = schema.cards.setup;
  const read = readFillReply(card, await quick().send(fillRequest(schema, p, "setup").request));
  assert.equal(read.values.protagonist, "Suvi");
  assert.equal(planFill(card, p.setup, read, p).next.protagonist, p.characters[0].id);
  assert.equal(read.values.chapter_count, 8);
});

test("a character gets a name; a card with nothing to link to leaves links out", async () => {
  const mock = quick();
  const p = project();
  const reply = await mock.send(fillRequest(schema, p, "characters", p.characters[0].id).request);
  assert.match(reply.values.name, /^Mock character/);
  const lonely = settledProject(schema, { ...newProject(schema), example_chapter: "Once." });
  const ent = await mock.send(fillRequest(schema, lonely, "entanglements").request);
  assert.equal(ent.values.ties, undefined, "a tie with nobody to join is left out, not half made");
});

test("the judge flags a card that says FLAG ME and nothing else, down to the list item", async () => {
  const mock = quick();
  const p = project();
  const world = schema.cards.world;
  const rule = modelRules(world).find((r) => r.fields.some((k) => world.fields.find((f) => f.key === k)?.repeat));
  const listKey = rule.fields.find((k) => world.fields.find((f) => f.key === k)?.repeat);
  const plainRule = modelRules(world).find((r) => r.fields.every((k) => !world.fields.find((f) => f.key === k)?.repeat));
  const ask = (ids) => judgeRequest(schema, p, "world", p.world, ids);

  let read = readJudgeReply(world, p.world, ask().rules.map((r) => r.id), await mock.send(ask()));
  assert.deepEqual([read.ok, read.problems.length, read.missing], [true, 0, []]);

  p.world[plainRule.fields[0]] = `Plain ${MOCK_FLAG}`;
  const item = p.world[listKey][0] ?? addItem(world.fields.find((f) => f.key === listKey), p.world[listKey]);
  const textKey = Object.keys(item).find((k) => k !== "id");
  item[textKey] = MOCK_FLAG;
  const ids = [plainRule.id, rule.id];
  read = readJudgeReply(world, p.world, ids, await mock.send(ask(ids)));
  assert.equal(read.ok, true);
  assert.ok(read.problems.some((x) => x.rule === plainRule.id && x.item === null));
  assert.ok(read.problems.some((x) => x.rule === rule.id && x.item === item.id));
});

test("style fit complains about a flagged protagonist and otherwise fits", async () => {
  const mock = quick();
  const p = project();
  assert.deepEqual(readStyleFitReply(await mock.send(styleFitRequest(schema, p).request)), { ok: true, fits: true, message: "" });
  p.characters[0].flaw = MOCK_FLAG;
  const read = readStyleFitReply(await mock.send(styleFitRequest(schema, p).request));
  assert.equal(read.fits, false);
  assert.ok(read.message);
});

test("queued failures come back in order, then the mock behaves again", async () => {
  const mock = quick();
  const p = project();
  const request = fillRequest(schema, p, "world").request;
  const card = schema.cards.world;
  mock.queue("busy", "bad_output", "too_long", "server", "stopped");
  const kinds = [];
  for (let i = 0; i < 5; i++) kinds.push(readFillReply(card, await mock.send(request)).error.kind);
  assert.deepEqual(kinds, ["busy", "bad_output", "too_long", "server", "stopped"]);
  assert.equal(readFillReply(card, await mock.send(request)).ok, true);
  mock.queue("bad_output");
  assert.equal(readJudgeReply(card, p.world, ["x"], await mock.send(judgeRequest(schema, p, "world", p.world))).error.kind, "bad_output");
  mock.queue("bad_output");
  assert.equal(readStyleFitReply(await mock.send(styleFitRequest(schema, p).request)).error.kind, "bad_output");
});

test("status checks do not use up a queued failure", async () => {
  const mock = quick();
  mock.queue("busy");
  assert.equal((await mock.send({ call: "status" })).ok, true);
  assert.equal((await mock.send(fillRequest(schema, project(), "world").request)).error.kind, "busy");
});

test("unreachable rejects like a network error; timeout never answers; Stop rejects like fetch does", async () => {
  const p = project();
  const request = fillRequest(schema, p, "world").request;
  const mock = createMock(schema, { delay: 20 });
  mock.queue("unreachable");
  await assert.rejects(mock.send(request), TypeError);

  mock.queue("timeout");
  const stop = new AbortController();
  const hung = mock.send(request, { signal: stop.signal });
  setTimeout(() => stop.abort(), 30);
  await assert.rejects(hung, { name: "AbortError" });
  assert.equal(mock.busy, false, "a stopped call is no longer running");

  const slow = new AbortController();
  const running = mock.send(request, { signal: slow.signal });
  setTimeout(() => slow.abort(), 5);
  await assert.rejects(running, { name: "AbortError" });

  const already = new AbortController();
  already.abort();
  await assert.rejects(mock.send(request, { signal: already.signal }), { name: "AbortError" });
  assert.equal((await mock.send(request)).ok, true);
});

test("an unknown card or call is the page's mistake", async () => {
  const mock = quick();
  assert.equal((await mock.send({ call: "fill", card: "nope" })).error.kind, "bad_request");
  assert.equal((await mock.send({ call: "judge", card: "nope" })).error.kind, "bad_request");
  assert.equal((await mock.send({ call: "dance" })).error.kind, "bad_request");
});

test("with only one person there is nobody to tie them to, so the sample leaves ties out", async () => {
  const p = settledProject(schema, { ...newProject(schema), example_chapter: "Once." });
  addInstance(p, characters).name = "Suvi";
  const reply = await quick().send(fillRequest(schema, p, "entanglements").request);
  assert.equal(reply.values.ties, undefined);
});

// ---- Story calls ----

import { readOffstageReply, readPlanReply, readGenerateReply, readEndStoryReply } from "../logic.js";

const storyBase = { schema_version: 1, language: "en" };

test("the mock answers every story call in a shape the page reads", async () => {
  const mock = quick();
  const p = project();
  const cast = p.characters.map((c) => ({ id: c.id, name: c.name }));
  const places = [{ id: "pl1", name: "The Salt Coast" }];
  assert.equal(readOffstageReply(await mock.send({ call: "offstage", ...storyBase, cast })).ok, true);
  const plan = readPlanReply(await mock.send({
    call: "plan", ...storyBase, chapter: 2, chapter_count: 8, cast, world: { places }, legal_shifts: ["easier", "harder"],
    open_plants: [{ text: "A torn page", chapter: 1 }],
  }));
  assert.equal(plan.ok, true);
  assert.match(plan.thinking, /chapter 2/);
  assert.equal(plan.beat.where, "The Salt Coast");
  assert.equal(plan.beat.shift, "easier");
  assert.deepEqual(plan.beat.payoff, ["A torn page"]);
  for (const key of ["cast", "chapter", "spotlight", "planned_from", "offstage_did", "stale"]) assert.equal(key in plan.beat, false, key);
  const chapter = readGenerateReply(await mock.send({
    call: "generate", ...storyBase, chapter: 2, chapter_count: 8, cast, beat: plan.beat,
    entanglements: { pressures: [{ id: "pr1", what: "x" }] },
  }));
  assert.equal(chapter.ok, true);
  assert.deepEqual(chapter.shifts.map((s) => s.character), ["Suvi"]);
  assert.deepEqual(chapter.changes.map((c) => [c.section, c.item]), [["pressures", "pr1"]]);
  assert.deepEqual(chapter.events.paid_off, ["A torn page"]);
  const end = readEndStoryReply(await mock.send({ call: "end_story", ...storyBase, characters: p.characters, world: p.world }));
  assert.equal(end.ok, true);
  assert.deepEqual(end.characters.map((c) => c.id), p.characters.map((c) => c.id));
});

test("the first chapter's beat has no gap since the last chapter", async () => {
  const plan = readPlanReply(await quick().send({ call: "plan", ...storyBase, chapter: 1, chapter_count: 3, cast: [], world: {} }));
  assert.equal("when_gap" in plan.beat, false);
});

test("a scripted bad output is refused by the reader of each story call", async () => {
  const readers = { offstage: readOffstageReply, plan: readPlanReply, generate: readGenerateReply, end_story: readEndStoryReply };
  for (const [call, read] of Object.entries(readers)) {
    const mock = quick();
    mock.queue("bad_output");
    assert.equal(read(await mock.send({ call, ...storyBase })).error.kind, "bad_output", call);
  }
});

test("a busy mock names the stage it is in, and says nothing once idle", async () => {
  const mock = createMock(schema, { delay: 90 });
  const running = mock.send({ call: "generate", ...storyBase, chapter: 1, chapter_count: 2, cast: [], beat: {} });
  const stages = new Set();
  for (let i = 0; i < 12; i++) {
    await new Promise((r) => setTimeout(r, 10));
    const status = readStatus(await mock.send({ call: "status" }));
    if (status.stage) stages.add(status.stage);
  }
  await running;
  assert.ok(stages.has("write") && stages.has("events"), [...stages].join());
  assert.deepEqual(readStatus(await mock.send({ call: "status" })), { ok: true, state: "idle" });
});
