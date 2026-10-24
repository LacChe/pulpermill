import "./text-setup.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { newProject, settledProject, addInstance, addItem, projectSnapshot, modelRules, setCardValues } from "../logic.js";
import { createMock, MOCK_FLAG } from "../mock.js";
import {
  parseBackendSetting, readStoredSetting, settingText, blockedByPage, createClient, fillCard, judgeCard, checkStyleFit,
} from "../client.js";

const schema = JSON.parse(readFileSync(new URL("../data/schema.en.json", import.meta.url), "utf8"));
const characters = schema.cards.characters;
const world = schema.cards.world;
const noSleep = () => Promise.resolve();

function project() {
  const p = settledProject(schema, { ...newProject(schema), example_chapter: "Once." });
  addInstance(p, characters).name = "Suvi";
  addInstance(p, characters).name = "Ola";
  p.setup.protagonist = p.characters[0].id;
  return p;
}

// A mock that also counts the calls that reach it (status checks apart).
function countingMock(options = { delay: 0 }) {
  const mock = createMock(schema, options);
  const seen = [];
  const send = mock.send;
  mock.send = (request, extra) => { if (request.call !== "status") seen.push(request); return send(request, extra); };
  mock.seen = seen;
  return mock;
}

const mockClient = (mock = countingMock(), timeouts = {}) => createClient({ setting: { kind: "mock" }, mock, timeouts, sleep: noSleep });

test("the backend setting: mock by default, an address otherwise, nothing else", () => {
  assert.deepEqual(parseBackendSetting(""), { ok: true, kind: "mock" });
  assert.deepEqual(parseBackendSetting("  Mock "), { ok: true, kind: "mock" });
  assert.deepEqual(parseBackendSetting("localhost:8000"), { ok: true, kind: "url", url: "http://localhost:8000" });
  assert.deepEqual(parseBackendSetting("https://example.com/pulp/?x=1#y"), { ok: true, kind: "url", url: "https://example.com/pulp" });
  assert.deepEqual(parseBackendSetting("http://127.0.0.1:8000///"), { ok: true, kind: "url", url: "http://127.0.0.1:8000" });
  assert.equal(parseBackendSetting("ftp://x.com").reason, "not_http");
  assert.equal(parseBackendSetting("http://").reason, "not_a_url");
  assert.deepEqual(readStoredSetting("ftp://x"), { ok: true, kind: "mock" });
  assert.equal(readStoredSetting(null).kind, "mock");
  assert.equal(settingText({ kind: "mock" }), "mock");
  assert.equal(settingText(parseBackendSetting("localhost:8000")), "http://localhost:8000");
});

test("an https page cannot call a plain http address, except one on this computer", () => {
  const url = (text) => parseBackendSetting(text);
  assert.equal(blockedByPage(url("http://example.com"), "https:"), true);
  assert.equal(blockedByPage(url("https://example.com"), "https:"), false);
  assert.equal(blockedByPage(url("http://localhost:8000"), "https:"), false);
  assert.equal(blockedByPage(url("http://127.0.0.1:8000"), "https:"), false);
  assert.equal(blockedByPage(url("http://example.com"), "http:"), false);
  assert.equal(blockedByPage({ kind: "mock" }, "https:"), false);
});

test("a fill resolves to a plan and changes nothing in the project", async () => {
  const p = project();
  const before = projectSnapshot(schema, p);
  const result = await fillCard(mockClient(), schema, p, "setup").done;
  assert.equal(result.ok, true);
  assert.ok(result.filled.length > 0);
  assert.equal(projectSnapshot(schema, p), before);
  setCardValues(schema.cards.setup, p.setup, result.next);
  assert.equal(p.setup.protagonist, p.characters[0].id);
});

test("a request the page cannot make resolves at once, without a call", async () => {
  const mock = countingMock();
  const client = mockClient(mock);
  const p = settledProject(schema, newProject(schema));
  assert.deepEqual(await fillCard(client, schema, p, "world").done, { ok: false, reason: "no_source" });
  assert.deepEqual(await checkStyleFit(client, schema, p).done, { ok: false, reason: "no_protagonist" });
  assert.equal(mock.seen.length, 0);
});

test("the backend's failures come through as they are, and nothing changes", async () => {
  const mock = countingMock();
  const client = mockClient(mock);
  const p = project();
  const before = projectSnapshot(schema, p);
  mock.queue("busy", "bad_output", "too_long");
  const kinds = [];
  for (let i = 0; i < 3; i++) kinds.push((await fillCard(client, schema, p, "world").done).error.kind);
  assert.deepEqual(kinds, ["busy", "bad_output", "too_long"]);
  assert.equal(projectSnapshot(schema, p), before);
});

test("nothing answering is unreachable, and the page says so", async () => {
  const mock = countingMock();
  const client = mockClient(mock);
  mock.queue("unreachable");
  assert.equal((await fillCard(client, schema, project(), "world").done).error.kind, "unreachable");
  assert.equal(client.state.connection, "unreachable");
  assert.equal(client.state.working, false);
  assert.equal(await client.checkStatus(), "idle");
});

test("no answer in time is a timeout, and the page waits for the backend to be idle", async () => {
  const mock = countingMock({ delay: 0 });
  const client = mockClient(mock, { fill: 20 });
  mock.queue("timeout");
  const result = await fillCard(client, schema, project(), "world").done;
  assert.equal(result.error.kind, "timeout");
  assert.deepEqual(client.state, { working: false, connection: "idle", setting: { kind: "mock" }, stage: null });
});

test("Stop ends the call with a stopped failure and the page is free again", async () => {
  const client = mockClient(countingMock({ delay: 80 }));
  const call = fillCard(client, schema, project(), "world");
  assert.equal(client.state.working, true);
  setTimeout(call.stop, 5);
  const result = await call.done;
  assert.equal(result.error.kind, "stopped");
  assert.equal(client.state.working, false);
  assert.equal(client.state.connection, "idle");
  assert.equal((await fillCard(client, schema, project(), "world").done).ok, true);
});

test("one model call at a time per page; status checks are always allowed", async () => {
  const client = mockClient(countingMock({ delay: 30 }));
  const first = fillCard(client, schema, project(), "world");
  const second = await fillCard(client, schema, project(), "style").done;
  assert.equal(second.error.kind, "busy");
  assert.equal(await client.checkStatus(), "busy");
  assert.equal((await first.done).ok, true);
  assert.equal(await client.checkStatus(), "idle");
});

test("listeners hear when a call starts and ends", async () => {
  const client = mockClient();
  const heard = [];
  const off = client.onChange((state) => heard.push(state.working));
  await fillCard(client, schema, project(), "world").done;
  off();
  await fillCard(client, schema, project(), "world").done;
  assert.deepEqual(heard.filter((w, i) => i === 0 || w !== heard[i - 1]), [true, false]);
});

// ---- A real backend, with a fake fetch ----

function fakeFetch(handler) {
  const calls = [];
  const fetchImpl = (url, init) => {
    calls.push({ url, init });
    return new Promise((resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
      Promise.resolve(handler(url, init, calls.length)).then(resolve, reject);
    });
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}
const json = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const realClient = (fetchImpl, timeouts = {}) =>
  createClient({ setting: parseBackendSetting("localhost:8000"), fetchImpl, timeouts, sleep: noSleep });

test("a real backend gets the request as JSON at <address>/api", async () => {
  const fetchImpl = fakeFetch(() => json({ ok: true, fits: true }));
  const p = project();
  const result = await checkStyleFit(realClient(fetchImpl), schema, p).done;
  assert.deepEqual(result, { ok: true, fits: true, message: "" });
  const [call] = fetchImpl.calls;
  assert.equal(call.url, "http://localhost:8000/api");
  assert.equal(call.init.method, "POST");
  assert.equal(JSON.parse(call.init.body).call, "style_fit");
  assert.equal(JSON.parse(call.init.body).protagonist.name, "Suvi");
});

test("a real backend's failures: its own words win, then the status code, then a bad output", async () => {
  const p = project();
  const kind = async (handler) => (await checkStyleFit(realClient(fakeFetch(handler)), schema, p).done).error.kind;
  assert.equal(await kind(() => json({ ok: false, error: { kind: "too_long", detail: "x" } }, 500)), "too_long");
  assert.equal(await kind(() => json(null, 503)), "busy");
  assert.equal(await kind(() => json(null, 429)), "busy");
  assert.equal(await kind(() => json(null, 400)), "bad_request");
  assert.equal(await kind(() => json(null, 413)), "too_long");
  assert.equal(await kind(() => json(null, 502)), "bad_output");
  assert.equal(await kind(() => json(null, 409)), "stopped");
  assert.equal(await kind(() => json(null, 500)), "server");
  assert.equal(await kind(() => json(["not", "an", "answer"])), "bad_output");
  assert.equal(await kind(() => ({ ok: true, status: 200, json: async () => { throw new SyntaxError("x"); } })), "bad_output");
  assert.equal(await kind(() => { throw new TypeError("Failed to fetch"); }), "unreachable");
});

test("with a real backend, Stop aborts the request and the page waits until status says idle", async () => {
  let statusChecks = 0;
  const fetchImpl = fakeFetch((url, init) => {
    const request = JSON.parse(init.body);
    if (request.call === "status") return json({ ok: true, state: ++statusChecks < 3 ? "busy" : "idle" });
    return new Promise(() => {});
  });
  const client = realClient(fetchImpl);
  const call = checkStyleFit(client, schema, project());
  setTimeout(call.stop, 5);
  const result = await call.done;
  assert.equal(result.error.kind, "stopped");
  assert.equal(statusChecks, 3, "it kept asking until the backend was idle");
  assert.equal(client.state.connection, "idle");
});

test("a status check that cannot reach the backend says unreachable", async () => {
  const client = realClient(fakeFetch(() => { throw new TypeError("Failed to fetch"); }));
  assert.equal(await client.checkStatus(), "unreachable");
  const bad = realClient(fakeFetch(() => json({ ok: true, state: "sleeping" })));
  assert.equal(await bad.checkStatus(), "unreachable");
});

// ---- Judging, with memory ----

function flaggedWorld() {
  const p = project();
  const plain = modelRules(world).find((r) => r.fields.every((k) => !world.fields.find((f) => f.key === k)?.repeat));
  return { p, plain, key: plain.fields[0] };
}

test("judging asks only about rules whose fields changed; an unchanged card makes no call", async () => {
  const mock = countingMock();
  const client = mockClient(mock);
  const { p, plain, key } = flaggedWorld();
  const first = await judgeCard(client, schema, p, "world", p.world).done;
  assert.deepEqual([first.ok, first.problems.length, first.fromMemory], [true, 0, []]);
  assert.equal(mock.seen.length, 1);
  assert.equal(first.asked.length, modelRules(world).length);

  const again = await judgeCard(client, schema, p, "world", p.world).done;
  assert.equal(mock.seen.length, 1, "no call at all");
  assert.deepEqual([again.asked, again.fromMemory.length, again.missing], [[], modelRules(world).length, []]);

  p.world[key] = `Plain ${MOCK_FLAG}`;
  const changed = await judgeCard(client, schema, p, "world", p.world).done;
  assert.equal(mock.seen.length, 2);
  assert.ok(changed.asked.includes(plain.id));
  assert.ok(changed.asked.length < modelRules(world).length, "only the rules that read that field");
  assert.ok(changed.problems.some((x) => x.rule === plain.id));

  const third = await judgeCard(client, schema, p, "world", p.world).done;
  assert.equal(mock.seen.length, 2);
  assert.ok(third.problems.some((x) => x.rule === plain.id), "the warning comes back from memory too");
});

test("a failed judge is not remembered, and changing the backend clears memory", async () => {
  const mock = countingMock();
  const client = mockClient(mock);
  const { p } = flaggedWorld();
  mock.queue("bad_output");
  assert.equal((await judgeCard(client, schema, p, "world", p.world).done).error.kind, "bad_output");
  assert.equal(client.judgeCache.size, 0);
  assert.equal((await judgeCard(client, schema, p, "world", p.world).done).ok, true);
  assert.ok(client.judgeCache.size > 0);
  client.setSetting({ kind: "mock" });
  assert.equal(client.judgeCache.size, 0);
});

test("judging a list item remembers by the item's content, so editing it asks again", async () => {
  const mock = countingMock();
  const client = mockClient(mock);
  const p = project();
  const rule = modelRules(world).find((r) => r.fields.some((k) => world.fields.find((f) => f.key === k)?.repeat));
  const listKey = rule.fields.find((k) => world.fields.find((f) => f.key === k)?.repeat);
  const item = addItem(world.fields.find((f) => f.key === listKey), p.world[listKey]);
  const textKey = Object.keys(item).find((k) => k !== "id");
  await judgeCard(client, schema, p, "world", p.world, [rule.id]).done;
  await judgeCard(client, schema, p, "world", p.world, [rule.id]).done;
  assert.equal(mock.seen.length, 1);
  item[textKey] = MOCK_FLAG;
  const read = await judgeCard(client, schema, p, "world", p.world, [rule.id]).done;
  assert.equal(mock.seen.length, 2);
  assert.ok(read.problems.some((x) => x.item === item.id));
});

test("the style-fit check resolves to fits and a message", async () => {
  const client = mockClient();
  const p = project();
  assert.deepEqual(await checkStyleFit(client, schema, p).done, { ok: true, fits: true, message: "" });
  p.characters[0].flaw = MOCK_FLAG;
  const bad = await checkStyleFit(client, schema, p).done;
  assert.equal(bad.fits, false);
});

test("stop() ends the call this page has going, and does nothing when there is none", async () => {
  const client = mockClient(countingMock({ delay: 80 }));
  client.stop();
  const call = fillCard(client, schema, project(), "world");
  setTimeout(() => client.stop(), 5);
  assert.equal((await call.done).error.kind, "stopped");
  assert.equal(client.state.working, false);
});

// ---- Story calls: progress and a lost connection ----

const realSleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const generateRequest = { call: "generate", schema_version: 1, language: "en", chapter: 1, chapter_count: 3, beat: {}, cast: [], entanglements: {} };

test("while a story call runs the page asks status and shows the stage the backend names, then clears it", async () => {
  const mock = createMock(schema, { delay: 120 });
  const client = createClient({ setting: { kind: "mock" }, mock, sleep: realSleep, pollEvery: 10 });
  const seen = [];
  client.onChange((state) => { if (state.stage && seen.at(-1) !== state.stage) seen.push(state.stage); });
  const reply = await client.start(generateRequest).done;
  assert.equal(reply.ok, true);
  assert.deepEqual(seen, ["write", "events", "shifts"]);
  assert.equal(client.state.stage, null);
  assert.equal(client.state.working, false);
});

test("a plan that is retried names the retry stage", async () => {
  const mock = createMock(schema, { delay: 80 });
  const client = createClient({ setting: { kind: "mock" }, mock, sleep: realSleep, pollEvery: 5 });
  const seen = new Set();
  client.onChange((state) => { if (state.stage) seen.add(state.stage); });
  await client.start({ call: "plan", schema_version: 1, language: "en", chapter: 1, chapter_count: 3, retry: { thinking: "x", beat: {}, problems: ["y"] } }).done;
  assert.ok(seen.has("retry"));
});

test("short calls do not poll status", async () => {
  let statusChecks = 0;
  const fetchImpl = async (url, { body }) => {
    const request = JSON.parse(body);
    if (request.call === "status") { statusChecks += 1; return json({ ok: true, state: "busy" }); }
    await realSleep(40);
    return json({ ok: true, fits: true, message: "" });
  };
  const client = createClient({ setting: { kind: "url", url: "http://x" }, fetchImpl, sleep: realSleep, pollEvery: 5 });
  await client.start({ call: "style_fit", style: {}, protagonist: {} }).done;
  assert.equal(statusChecks, 0);
});

test("a connection that drops during a story call ends it as unreachable after a few failed checks", async () => {
  let aborted = false;
  const fetchImpl = (url, { body, signal }) => {
    const request = JSON.parse(body);
    if (request.call === "status") return Promise.reject(new TypeError("Failed to fetch"));
    return new Promise((resolve, reject) => signal.addEventListener("abort", () => { aborted = true; reject(Object.assign(new Error("aborted"), { name: "AbortError" })); }));
  };
  const client = createClient({ setting: { kind: "url", url: "http://x" }, fetchImpl, sleep: realSleep, pollEvery: 5, lostAfter: 3, timeouts: { generate: 5000 } });
  const reply = await client.start(generateRequest).done;
  assert.equal(reply.error.kind, "unreachable");
  assert.equal(aborted, true);
  assert.equal(client.state.working, false);
});

test("one failed status check among good ones does not end the call", async () => {
  let checks = 0;
  const fetchImpl = async (url, { body }) => {
    const request = JSON.parse(body);
    if (request.call === "status") { checks += 1; if (checks === 2) throw new TypeError("blip"); return json({ ok: true, state: "busy", stage: "write" }); }
    await realSleep(80);
    return json({ ok: true, did: "a", reach: "b" });
  };
  const client = createClient({ setting: { kind: "url", url: "http://x" }, fetchImpl, sleep: realSleep, pollEvery: 5, lostAfter: 3 });
  const reply = await client.start({ call: "offstage", schema_version: 1, language: "en" }).done;
  assert.equal(reply.ok, true);
  assert.ok(checks > 2);
});

// ---- Planning a chapter ----

import { readyProject } from "./helpers.mjs";
import { lockStaticCards } from "../gate.js";
import { planChapter } from "../client.js";

async function startedProject() {
  const p = lockStaticCards(await readyProject());
  p.setup.chapter_count = 6;
  return p;
}

test("planning calls the model for a beat, with no offstage move in chapter 1, and changes nothing", async () => {
  const p = await startedProject();
  const text = JSON.stringify(p);
  const mock = countingMock();
  const result = await planChapter(mockClient(mock), schema, p, [p.characters[0].id]).done;
  assert.equal(result.ok, true);
  assert.deepEqual(mock.seen.map((r) => r.call), ["plan"]);
  assert.equal(result.beat.chapter, 1);
  assert.equal(result.offstage, null);
  assert.equal(result.retried, false);
  assert.deepEqual(result.blockers, []);
  assert.match(result.thinking, /chapter 1/);
  assert.equal(JSON.stringify(p), text, "the page decides what to land");
});

test("an offstage move comes first when one is due, and goes into the plan request and the beat", async () => {
  const p = await startedProject();
  const [suvi] = p.characters;
  p.outline = { beats: [{ id: "b1", chapter: 1, where: p.world.places[0].id, cast: [suvi.id], spotlight: p.entanglements.pressures[0].id, shift: "harder" }] };
  p.chapters = [{ id: "c1", beat: "b1", text: "One." }];
  p.summary_events = { entries: [{ id: "e1", beat: "b1", happened: "It happened." }] };
  const mock = countingMock();
  const result = await planChapter(mockClient(mock), schema, p, [suvi.id]).done;
  assert.deepEqual(mock.seen.map((r) => r.call), ["offstage", "plan"]);
  assert.deepEqual(mock.seen[1].offstage, result.offstage);
  assert.equal(result.beat.offstage_did, result.offstage.did);
  assert.equal(result.beat.chapter, 2);
});

test("a beat the blocking rules refuse is sent back once with the rules' words, and the second answer is used", async () => {
  const p = await startedProject();
  const [suvi] = p.characters;
  const mock = countingMock();
  const send = mock.send;
  let first = true;
  mock.send = async (request, extra) => {
    const reply = await send(request, extra);
    if (request.call === "plan" && first) { first = false; return { ...reply, beat: { ...reply.beat, turn: "" } }; }
    return reply;
  };
  const result = await planChapter(mockClient(mock), schema, p, [suvi.id]).done;
  assert.deepEqual(mock.seen.map((r) => r.call), ["plan", "plan"]);
  assert.equal(mock.seen[0].retry, null);
  assert.ok(mock.seen[1].retry.problems.length > 0);
  assert.equal(mock.seen[1].retry.beat.turn, "", "the failed attempt goes back as it was");
  assert.equal(result.retried, true);
  assert.deepEqual(result.blockers, []);
  assert.ok(result.beat.turn);
});

test("a beat that still fails after the retry is returned with its problems, never retried again", async () => {
  const p = await startedProject();
  const mock = countingMock();
  const send = mock.send;
  mock.send = async (request, extra) => {
    const reply = await send(request, extra);
    return request.call === "plan" ? { ...reply, beat: { ...reply.beat, turn: "" } } : reply;
  };
  const result = await planChapter(mockClient(mock), schema, p, [p.characters[0].id]).done;
  assert.equal(mock.seen.length, 2);
  assert.equal(result.ok, true);
  assert.equal(result.retried, true);
  assert.ok(result.blockers.length > 0);
});

test("a failed call changes nothing and comes back as its failure", async () => {
  const p = await startedProject();
  const mock = countingMock();
  mock.queue("busy");
  const result = await planChapter(mockClient(mock), schema, p, [p.characters[0].id]).done;
  assert.equal(result.error.kind, "busy");
  const bad = countingMock();
  bad.queue("bad_output");
  assert.equal((await planChapter(mockClient(bad), schema, p, [p.characters[0].id]).done).error.kind, "bad_output");
});

test("a plan the page cannot make says why, without calling the model", async () => {
  const p = await startedProject();
  const mock = countingMock();
  const client = mockClient(mock);
  assert.equal((await planChapter(client, schema, { ...p, locks: [] }, [p.characters[0].id]).done).reason, "not_started");
  assert.equal((await planChapter(client, schema, p, [p.characters[1].id]).done).reason, "cast_no_protagonist");
  assert.equal(mock.seen.length, 0);
});

test("Stop ends the plan and no second call is made", async () => {
  const p = await startedProject();
  const mock = countingMock({ delay: 60 });
  const call = planChapter(mockClient(mock), schema, p, [p.characters[0].id]);
  setTimeout(() => call.stop(), 10);
  const result = await call.done;
  assert.equal(result.error.kind, "stopped");
  assert.equal(mock.seen.length, 1);
});
