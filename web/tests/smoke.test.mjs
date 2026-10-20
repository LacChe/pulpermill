// Placeholder so `node --test web` has something to run until the real tests (shared vectors) arrive.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("the page exists and has a title", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.match(html, /<title>Pulpermill<\/title>/);
});
