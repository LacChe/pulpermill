import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { remember, foldedItems, openState, forgetFolds } from "../folds.js";
import { secondsSince } from "../elapsed.js";
import { createClient } from "../client.js";
import { createMock } from "../mock.js";
import { schema } from "./helpers.mjs";

const fakeDetails = () => {
  const listeners = [];
  return { open: false, addEventListener: (_, fn) => listeners.push(fn), toggle(open) { this.open = open; listeners.forEach((fn) => fn()); } };
};

test("a fold the writer changed comes back as they left it when the panel is drawn again", () => {
  forgetFolds();
  const first = fakeDetails();
  remember(first, "card:group", true);
  assert.equal(first.open, true, "the first time, the fallback");
  first.toggle(false);
  const again = fakeDetails();
  remember(again, "card:group", true);
  assert.equal(again.open, false, "drawn again, the writer's choice wins over the fallback");
  forgetFolds();
  assert.equal(openState.size + foldedItems.size, 0);
  const fresh = fakeDetails();
  remember(fresh, "card:group", true);
  assert.equal(fresh.open, true, "a new project starts from the fallbacks");
});

test("seconds since a call began are whole seconds, never negative", () => {
  assert.equal(secondsSince(1000, 13999), 12);
  assert.equal(secondsSince(5000, 1000), 0);
});

test("the client says when the running call began, and nothing once it ends", async () => {
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock: createMock(schema, { delay: 0 }), pollEvery: 5 });
  assert.equal(client.state.since, null);
  const call = client.start({ call: "status" });
  await call.done;
  assert.equal(client.state.since, null);
});
