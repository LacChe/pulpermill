import "./text-setup.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { createMock } from "../../web/mock.js";
import { createClient, generateChapter, fillCard } from "../../web/client.js";
import { lockStaticCards } from "../../web/gate.js";
import { generateGate, generateRequest } from "../../web/generate.js";
import { readCalls } from "../../web/logic.js";
import { reconcile, parseTag, projectName, createCollector, HANDLED_KEY } from "../../web/collect.js";
import { schema, readyProject, writeNext } from "./helpers.mjs";

const noSleep = () => Promise.resolve();
const json = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

// A project with chapter 1 written, planned for chapter 2, so the next call is the chapter 2 write.
async function readyForTwo() {
  const p = lockStaticCards(await readyProject());
  p.setup.chapter_count = 6;
  p.title = "Tale";
  const mock = createMock(schema, { delay: 0 });
  const client = createClient({ setting: { kind: "mock" }, mock, sleep: noSleep });
  await writeNext(client, p);
  const { ensureBeat, placeBeat } = await import("../../web/plan.js");
  const { planChapter } = await import("../../web/client.js");
  const beat = ensureBeat(schema, p);
  placeBeat(p, (await planChapter(client, schema, p, beat).done).beat);
  return { p, mock };
}

const memory = () => { const data = new Map(); return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, v) }; };
const button = () => ({ hidden: true, title: "", listeners: [], addEventListener(_, fn) { this.listeners.push(fn); } });

// A page that was just reloaded: its own client, collector and fake panels, talking to a backend that remembers `calls`.
function reloadedPage(project, backend) {
  const fetchImpl = async (url, init) => {
    const request = JSON.parse(init.body);
    if (request.call === "status") return json({ ok: true, state: backend.running ? "busy" : "idle", calls: backend.calls });
    if (request.call === "job") return json(backend.job(request));
    throw new TypeError("no other calls are expected");
  };
  const client = createClient({ setting: { kind: "url", url: "http://x" }, fetchImpl, sleep: noSleep, recoverEvery: 1, recoverFor: 50 });
  const landed = [];
  const notices = [];
  const collect = button();
  const collector = createCollector({
    schema, client, getProject: () => project, storage: memory(), button: collect,
    getPlanPanel: () => ({ land: (_, result) => landed.push(["plan", result]) }),
    getGeneratePanel: () => ({ land: (_, result) => landed.push(["chapter", result]) }),
    notice: (text, kind) => notices.push({ text, kind }), errorText: (error) => `error:${error.kind}`,
  });
  return { client, collector, landed, notices, collect };
}

const callOf = (p, over = {}) => ({ job_id: "gen-chap-0002", call: "generate", state: "done", project: { id: p.id, title: p.title }, tag: "chapter:2", error: null, ...over });

test("a story call names its project and what it is for; a fill names neither", async () => {
  const { p, mock } = await readyForTwo();
  const seen = [];
  const fetchImpl = async (url, init) => {
    const request = JSON.parse(init.body);
    seen.push(request);
    if (request.call === "status") return json({ ok: true, state: "idle" });
    return json(await mock.send(request));
  };
  const client = createClient({ setting: { kind: "url", url: "http://x" }, fetchImpl, sleep: noSleep });
  client.setProjectRef(() => p);
  assert.equal((await generateChapter(client, schema, p).done).ok, true);
  const sent = seen.find((r) => r.call === "generate");
  assert.deepEqual(sent.project, { id: p.id, title: "Tale" });
  assert.equal(sent.tag, "chapter:2");
  await fillCard(client, schema, p, "style").done;
  const fill = seen.find((r) => r.call === "fill");
  assert.equal(fill.project, undefined);
  assert.equal(fill.tag, undefined);
});

test("a project with no id yet is not named, and the mock never carries labels", async () => {
  const mock = createMock(schema, { delay: 0 });
  const sent = [];
  const send = mock.send;
  mock.send = (request, extra) => { sent.push(request); return send(request, extra); };
  const { p } = await readyForTwo();
  const client = createClient({ setting: { kind: "mock" }, mock, sleep: noSleep });
  client.setProjectRef(() => ({ ...p, id: undefined }));
  await generateChapter(client, schema, p).done;
  assert.equal(sent.at(-1).project, undefined);
  assert.equal(sent.at(-1).job_id, undefined);
});

test("status lists the named calls; malformed ones are dropped", () => {
  const good = { job_id: "plan-ch2-0001", call: "plan", state: "running", project: { id: "p-1", title: "Tale" }, tag: "plan:2" };
  const found = readCalls([good, { job_id: "x" }, { ...good, state: "weird" }, null, { ...good, job_id: "gen-ch2-0001", project: { id: 5 } }]);
  assert.deepEqual(found.map((c) => c.job_id), ["plan-ch2-0001", "gen-ch2-0001"]);
  assert.equal(found[1].project, null);
  assert.deepEqual(readCalls("nope"), []);
});

test("reconcile: own running call is taken over, own finished one collected, other projects' only reported", () => {
  const project = { id: "mine-1" };
  const own = (state, tag, call = "generate", id = `${call}-${state}-${tag}`.replace(":", "-").padEnd(8, "0")) => ({ job_id: id, call, state, tag, project: { id: "mine-1", title: "" } });
  const calls = [own("running", "chapter:2"), own("done", "plan:3", "plan"), own("done", "again:1"), own("failed", "chapter:4"), own("running", "again:2"),
    { job_id: "other-job-01", call: "generate", state: "running", tag: "chapter:1", project: { id: "theirs-9", title: "Else" } },
    { job_id: "nolabel-0001", call: "generate", state: "running", tag: null, project: null }];
  const found = reconcile({ calls, project });
  assert.equal(found.running.tag, "chapter:2");
  assert.deepEqual(found.collect.map((c) => c.tag), ["plan:3"]);
  assert.deepEqual(found.report.map((c) => c.tag), ["again:1", "chapter:4"]);
  assert.deepEqual(found.wait.map((c) => c.tag), ["again:2"]);
  assert.deepEqual(found.other.map((c) => c.project.id), ["theirs-9"]);
  const handled = new Set([found.collect[0].job_id, found.other[0].job_id]);
  const again = reconcile({ calls, project, handled });
  assert.deepEqual([again.collect.length, again.other.length], [0, 0]);
  assert.equal(reconcile({ calls, project: null }).other.length, 6, "a blank project owns nothing");
  assert.deepEqual(parseTag("chapter:12"), { kind: "chapter", n: 12 });
  assert.equal(parseTag("chapter:x"), null);
  assert.equal(projectName({ id: "p-1", title: "Tale" }), "“Tale”");
  assert.equal(projectName({ id: "p-1", title: "" }), "p-1");
});

test("after a reload a finished chapter for this project is offered with Collect, applied once, and not offered again", async () => {
  const { p, mock } = await readyForTwo();
  const reply = await mock.send(generateRequest(schema, p, generateGate(schema, p).beat));
  const page = reloadedPage(p, { calls: [callOf(p)], job: () => reply });
  await page.client.checkStatus();
  page.collector.follow();
  assert.equal(page.collect.hidden, false);
  assert.match(page.notices.at(-1).text, /chapter 2/);
  assert.equal(page.landed.length, 0, "nothing is applied until Collect is pressed");
  await page.collector.collect();
  assert.equal(page.landed.length, 1);
  const [kind, result] = page.landed[0];
  assert.equal(kind, "chapter");
  assert.equal(result.ok, true);
  assert.match(result.outcome.chapter.text, /Mock chapter 2/);
  assert.equal(page.collect.hidden, true);
  await page.collector.collect();
  assert.equal(page.landed.length, 1, "a second press applies nothing");
});

test("a finished chapter for another chapter than the next one is refused with its reason, not applied", async () => {
  const { p, mock } = await readyForTwo();
  const reply = await mock.send(generateRequest(schema, p, generateGate(schema, p).beat));
  const page = reloadedPage(p, { calls: [callOf(p, { tag: "chapter:5" })], job: () => reply });
  await page.client.checkStatus();
  page.collector.follow();
  await page.collector.collect();
  assert.deepEqual([page.landed[0][1].ok, page.landed[0][1].reason], [false, "other_chapter"]);
});

test("after a reload a running call for this project is taken over and landed when it finishes, and Run all does not go on", async () => {
  const { p, mock } = await readyForTwo();
  const reply = await mock.send(generateRequest(schema, p, generateGate(schema, p).beat));
  let polls = 0;
  const backend = { running: true, calls: [callOf(p, { state: "running" })], job: () => (++polls < 3 ? { ok: true, state: "running" } : reply) };
  const page = reloadedPage(p, backend);
  await page.client.checkStatus();
  page.collector.follow();
  assert.equal(page.client.state.working, true, "the page shows the call as its own");
  assert.match(page.notices.at(-1).text, /Reconnected/);
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(page.landed.length, 1);
  assert.equal(page.landed[0][1].ok, true);
  assert.equal(page.client.state.working, false);
});

test("a call for another project is named by its title, or its id when it has none, and cannot be collected here", async () => {
  const { p } = await readyForTwo();
  for (const [title, shown] of [["Their Tale", "“Their Tale”"], ["", "other-77"]]) {
    const calls = [{ job_id: "gen-oth-0001", call: "generate", state: "running", tag: "chapter:3", project: { id: "other-77", title } }];
    const page = reloadedPage(p, { running: true, calls, job: () => ({ ok: true, state: "running" }) });
    await page.client.checkStatus();
    page.collector.follow();
    assert.ok(page.notices.at(-1).text.includes(shown), page.notices.at(-1).text);
    assert.equal(page.notices.at(-1).kind, "notice-bad");
    assert.equal(page.collect.hidden, true);
    assert.equal(page.client.state.working, false);
  }
});

test("a call that failed while the page was away is said once, and a result that cannot be fetched is not marked as handled", async () => {
  const { p } = await readyForTwo();
  const failed = reloadedPage(p, { calls: [callOf(p, { state: "failed", error: "bad_output" })], job: () => ({}) });
  await failed.client.checkStatus();
  failed.collector.follow();
  assert.match(failed.notices.at(-1).text, /could not finish chapter 2 \(bad_output\)/);
  const count = failed.notices.length;
  failed.collector.follow();
  assert.equal(failed.notices.length, count, "not said twice");
  assert.ok(failed.collector.handled.has("gen-chap-0002"));
  const gone = reloadedPage(p, { calls: [callOf(p)], job: () => ({ ok: true, state: "unknown" }) });
  await gone.client.checkStatus();
  gone.collector.follow();
  await gone.collector.collect();
  assert.ok(gone.notices.some((n) => n.text === "error:unreachable"));
  assert.equal(gone.collector.handled.has("gen-chap-0002"), false, "nothing was applied, so it may be tried again");
  assert.equal(HANDLED_KEY, "pulpermill.handled");
});
