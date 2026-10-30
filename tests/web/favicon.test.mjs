import "./text-setup.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { createMock } from "../../web/mock.js";
import { createClient } from "../../web/client.js";
import { nextIconState, headAt, STEPS, TURN } from "../../web/favicon.js";
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

test("the bright segment is worked out from the clock, so a late tick still shows the right frame", () => {
  assert.equal(headAt(0), 0);
  assert.equal(headAt(TURN / STEPS), 1);
  assert.equal(headAt(TURN - 1), STEPS - 1);
  assert.equal(headAt(10 * 60 * 1000 + TURN / STEPS), 1);         // ten minutes later, the same position
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
