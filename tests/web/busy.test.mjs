import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { lockReason, createLock, applyLock } from "../../web/busy.js";

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

test("applyLock makes every area inert, and frees them", () => {
  const areas = [{ inert: false }, { inert: false }];
  const attrs = new Map();
  const root = { body: { toggleAttribute: (n, on) => (on ? attrs.set(n, "") : attrs.delete(n)), dataset: {} }, querySelectorAll: () => areas };
  applyLock(root, "call");
  assert.ok(areas.every((a) => a.inert)); assert.ok(attrs.has("data-locked")); assert.equal(root.body.dataset.lockReason, "call");
  applyLock(root, null);
  assert.ok(areas.every((a) => !a.inert)); assert.ok(!attrs.has("data-locked"));
});

test("index.html: Check and Stop sit outside every lockable area, and every other control is inside one", () => {
  const html = readFileSync(new URL("../../web/index.html", import.meta.url), "utf8");
  // walk the tags, tracking which ones carrying data-locks are open
  const stack = []; const outside = [];
  const voids = new Set(["input", "meta", "link", "br", "img"]);
  for (const m of html.matchAll(/<(\/?)([a-z0-9]+)([^>]*)>/gi)) {
    const [, close, tag, rest] = m; const t = tag.toLowerCase();
    if (close) { while (stack.length && stack.pop().tag !== t); continue; }
    const entry = { tag: t, locks: /\bdata-locks\b/.test(rest) };
    const inside = stack.some((e) => e.locks) || entry.locks;
    const id = /id="([^"]+)"/.exec(rest)?.[1];
    if ((t === "button" || t === "input") && !inside) outside.push(id ?? t);
    if (!voids.has(t) && !/\/\s*>$/.test(rest)) stack.push(entry);
  }
  assert.deepEqual(outside.sort(), ["check", "stop"]);
  assert.match(html, /id="planning-panels"[^>]*data-locks|data-locks[^>]*id="planning-panels"/);
});
