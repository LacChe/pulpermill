import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { lockReason, createLock, applyLock, callsModel } from "../../web/busy.js";

const fakeClient = (state) => { const hooks = []; return { state, onChange: (f) => hooks.push(f), fire: () => hooks.forEach((f) => f(state)) }; };
const fakeRun = () => { const hooks = []; return { running: false, onChange: (f) => hooks.push(f), fire: () => hooks.forEach((f) => f()) }; };

test("the reasons, strongest first", () => {
  assert.equal(lockReason({}), null);
  assert.equal(lockReason({ working: true }), "call");
  assert.equal(lockReason({ working: true, stopping: true }), "stopping");
  assert.equal(lockReason({ connection: "busy" }), "remote");
  assert.equal(lockReason({}, true), "run-all");
  assert.equal(lockReason({ connection: "ok" }), null);
});

test("the lock reads the live state and tells listeners only when the reason changes", () => {
  const client = fakeClient({ working: false, stopping: false, connection: "ok" });
  const run = fakeRun();
  const lock = createLock({ client, runAll: run });
  const seen = [];
  lock.onChange((r) => seen.push(r));
  client.fire(); assert.deepEqual(seen, []);
  client.state.working = true; client.fire(); client.fire();
  assert.deepEqual(seen, ["call"]);
  client.state.working = false; run.running = true; client.fire();   // between two calls of a run: still locked
  assert.equal(lock.locked, true);
  assert.deepEqual(seen, ["call", "run-all"]);
  run.running = false; run.fire();
  assert.equal(lock.locked, false);
  assert.deepEqual(seen, ["call", "run-all", null]);
});

test("applyLock makes the model-call buttons and the connection fields inert, and frees them", () => {
  const controls = [{ inert: false }, { inert: false }];
  const attrs = new Map();
  let asked = "";
  const root = { body: { toggleAttribute: (n, on) => (on ? attrs.set(n, "") : attrs.delete(n)), dataset: {} }, querySelectorAll: (q) => { asked = q; return controls; } };
  applyLock(root, "call");
  assert.ok(controls.every((a) => a.inert)); assert.ok(attrs.has("data-locked")); assert.equal(root.body.dataset.lockReason, "call");
  assert.equal(asked, "[data-locks], [data-calls]");
  applyLock(root, null);
  assert.ok(controls.every((a) => !a.inert)); assert.ok(!attrs.has("data-locked"));
});

test("callsModel marks a button as one that starts a model call", () => {
  const button = { dataset: {} };
  assert.equal(callsModel(button), button);
  assert.equal(button.dataset.calls, "");
});

const read = (file) => readFileSync(new URL(`../../web/${file}`, import.meta.url), "utf8");

test("index.html: only the connection fields lock as areas; Check and Stop and the rest of the page stay live", () => {
  const html = read("index.html");
  const locking = [...html.matchAll(/<([a-z0-9]+)[^>]*\bdata-locks\b[^>]*>/gi)].map((m) => /id="([^"]+)"/.exec(m[0])?.[1] ?? m[1]);
  assert.equal(locking.length, 2, "the two connection labels (address and token) and nothing else");
  for (const m of html.matchAll(/<label class="backend[^"]*"[^>]*>/g)) assert.match(m[0], /data-locks/);
  for (const id of ["check", "stop", "save", "new", "open", "import", "language", "card", "chapters", "cards"]) {
    const tag = new RegExp(`<[a-z0-9]+[^>]*id="${id}"[^>]*>`).exec(html)?.[0];
    assert.ok(tag && !/data-locks/.test(tag), `${id} must not lock as an area`);
  }
});

test("every button that starts a model call is marked, and no other button is", () => {
  const marked = {
    "render.js": 2,          // Fill, and Validate (which asks the model about its rules)
    "planpanel.js": 2,       // plan a chapter, and run all
    "generatepanel.js": 1,   // write the next chapter
    "chapterpanel.js": 1,    // write a chapter again
    "story.js": 1,           // begin the story (the model checks the voice against the protagonist)
  };
  for (const [file, count] of Object.entries(marked)) {
    const source = read(file);
    const found = (source.match(/callsModel\(|"data-calls"/g) ?? []).length;
    assert.equal(found, count, `${file} marks ${count} model-call buttons`);
  }
  assert.doesNotMatch(read("endpanel.js"), /callsModel|data-calls/, "ending the story needs no model");
  assert.doesNotMatch(read("importpanel.js"), /callsModel|data-calls/, "importing needs no model");
});
