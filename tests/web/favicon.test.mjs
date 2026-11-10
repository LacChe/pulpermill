import "./text-setup.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { createMock } from "../../web/mock.js";
import { createClient } from "../../web/client.js";
import { nextIconState, frameAt, FLIP, mountTabIcon } from "../../web/favicon.js";
import { schema } from "./helpers.mjs";

test("a call starting makes the icon generating, whatever it was", () => {
  for (const from of ["default", "done", "failed", "generating"]) assert.equal(nextIconState(from, { type: "start" }), "generating");
});

test("a call ending says done or failed only when the tab is hidden", () => {
  assert.equal(nextIconState("generating", { type: "finish", outcome: "ok", hidden: true }), "done");
  assert.equal(nextIconState("generating", { type: "finish", outcome: "failed", hidden: true }), "failed");
  assert.equal(nextIconState("generating", { type: "finish", outcome: "ok", hidden: false }), "default");
  assert.equal(nextIconState("generating", { type: "finish", outcome: "failed", hidden: false }), "default");
});

test("a call the writer stopped goes straight back to the default icon", () => {
  assert.equal(nextIconState("generating", { type: "finish", outcome: "stopped", hidden: true }), "default");
});

test("coming back to the tab or touching the page clears done and failed, and leaves generating alone", () => {
  assert.equal(nextIconState("done", { type: "seen" }), "default");
  assert.equal(nextIconState("failed", { type: "seen" }), "default");
  assert.equal(nextIconState("generating", { type: "seen" }), "generating");
  assert.equal(nextIconState("default", { type: "seen" }), "default");
});

test("the frame is worked out from the clock, so a late tick still shows the right frame", () => {
  assert.equal(frameAt(0), 0);
  assert.equal(frameAt(FLIP - 1), 0);
  assert.equal(frameAt(FLIP), 1);
  assert.equal(frameAt(2 * FLIP), 0);
  assert.equal(frameAt(10 * 60 * 1000 + FLIP), 1);                // ten minutes later, the same alternation
});

test("the client tells listeners how each model call ended, but not status checks", async () => {
  const mock = createMock(schema, { delay: 0 });
  let next = { ok: true };
  mock.send = async (request) => (request.call === "status" ? { ok: true, state: "idle" } : next);
  const client = createClient({ mock, pollEvery: 60000 });
  const replies = [];
  client.onFinish((reply) => replies.push(reply));
  await client.checkStatus();
  assert.equal(replies.length, 0);
  await client.start({ call: "fill" }).done;
  assert.equal(replies.length, 1);
  assert.equal(replies[0].ok, true);
  next = { ok: false, error: { kind: "server" } };
  await client.start({ call: "fill" }).done;
  assert.equal(replies.length, 2);
  assert.equal(replies[1].ok, false);
});

// ---- Painting from the page's colours -----------------------------------------------------------
// A stand-in page with a canvas that records the colour the letter P is drawn in, and tokens the test can change like a theme would.

function fakePage({ canvas = true } = {}) {
  const tokens = { "--accent": "#111111", "--surface-1": "#222222", "--line": "#333333", "--bad": "#444444" };
  const drawn = [];                                          // the fill colour at each fillText: the idle icon's letter
  const ctx = new Proxy({ roundRect() {}, fillText() { drawn.push(ctx.fillStyle); } }, {
    get: (target, key) => (key in target ? target[key] : () => {}),
    set: (target, key, value) => { target[key] = value; return true; },
  });
  let painted = 0;
  const listeners = {};
  const makeLink = () => ({ rel: "", replaceWith(next) { page.icon = next; } });   // a real <link> can be swapped for another
  const page = {
    icon: makeLink(), tokens, drawn, listeners,
    get painted() { return painted; },
    hidden: false,
    head: { append(link) { page.icon = link; } },
    defaultView: { getComputedStyle: () => ({ getPropertyValue: (name) => tokens[name] ?? "" }), addEventListener() {} },
    createElement: (tag) => (tag === "canvas" ? { getContext: () => (canvas ? ctx : null), toDataURL: () => `data:image/png;base64,${++painted}` } : makeLink()),
    querySelector: () => page.icon,
    addEventListener: (name, fn) => { (listeners[name] ??= []).push(fn); },
    fire: (name) => { for (const fn of listeners[name] ?? []) fn({ type: name }); },
  };
  return page;
}
const idleClient = () => ({ onChange() {}, onFinish() {} });

test("the icon is painted as soon as it is mounted, from the page's colours, replacing the static one", () => {
  const page = fakePage();
  mountTabIcon(idleClient(), { doc: page });
  assert.equal(page.painted, 1);
  assert.match(page.icon.href, /^data:image\/png/);
  assert.deepEqual(page.drawn, ["#111111"]);
});

test("a theme change paints the icon again in the new colours, though its state did not change", () => {
  const page = fakePage();
  const icon = mountTabIcon(idleClient(), { doc: page });
  page.tokens["--accent"] = "#abcdef";
  page.fire("themechange");
  assert.equal(page.painted, 2);
  assert.deepEqual(page.drawn, ["#111111", "#abcdef"]);
  page.tokens["--accent"] = "#fedcba";
  icon.refresh();                                            // the same thing on request
  assert.equal(page.painted, 3);
  assert.equal(page.drawn.at(-1), "#fedcba");
  assert.equal(icon.state(), "default");
});

test("without canvas support the static icon stays, and refresh is still there to call", () => {
  const page = fakePage({ canvas: false });
  const icon = mountTabIcon(idleClient(), { doc: page });
  assert.equal(page.painted, 0);
  assert.doesNotThrow(() => icon.refresh());
  assert.equal(icon.state(), "default");
});
