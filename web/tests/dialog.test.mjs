import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { bundle } from "./text-setup.mjs";

const WEB = new URL("../", import.meta.url);

test("no part of the page asks with the browser's own confirm box", () => {
  const found = [];
  for (const file of readdirSync(WEB).filter((f) => f.endsWith(".js") && f !== "mock.js")) {
    readFileSync(new URL(file, WEB), "utf8").split("\n").forEach((line, at) => {
      if (/\b(window\.)?(confirm|alert|prompt)\(/.test(line.split("//")[0])) found.push(`${file}:${at + 1}`);
    });
  }
  assert.deepEqual(found, []);
});

test("the dialog's two buttons are worded in the bundle", () => {
  assert.equal(typeof bundle.dialog.ok, "string");
  assert.equal(typeof bundle.dialog.cancel, "string");
});
