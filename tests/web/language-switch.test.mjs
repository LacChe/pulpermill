import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bundleFiles, loadBundles, replaceContents } from "../../web/lang.js";
import { msg, section, setText, applyStaticText } from "../../web/text.js";
import { bundle } from "./text-setup.mjs";

const schemaEn = JSON.parse(readFileSync(new URL("../../web/data/schema.en.json", import.meta.url), "utf8"));
const clone = (x) => JSON.parse(JSON.stringify(x));

// A stand-in for the second language: the English files with the language named and one word changed in each.
const textZh = () => { const t = clone(bundle); t._meta = { language: "zh", name: "中文" }; t.common.unnamed = "无名"; return t; };
const schemaZh = () => { const s = clone(schemaEn); s.lang = "zh"; s.cards.style.label = "文风"; return s; };
const served = (files) => async (url) => { if (!(url in files)) throw new Error(`${url}: 404`); return clone(files[url]); };

test("a language's two files are named from its code", () => {
  assert.deepEqual(bundleFiles("zh"), { text: "data/text.zh.json", schema: "data/schema.zh.json" });
  assert.deepEqual(bundleFiles("en"), { text: "data/text.en.json", schema: "data/schema.en.json" });
});

test("loadBundles reads both files of the language asked for", async () => {
  const getJson = served({ "data/text.zh.json": textZh(), "data/schema.zh.json": schemaZh() });
  const loaded = await loadBundles("zh-Hans", getJson);
  assert.equal(loaded.language, "zh");
  assert.equal(loaded.text.common.unnamed, "无名");
  assert.equal(loaded.schema.cards.style.label, "文风");
});

test("loadBundles refuses a missing file and a file of the wrong language", async () => {
  await assert.rejects(loadBundles("zh", served({ "data/text.zh.json": textZh() })), /404/);
  await assert.rejects(loadBundles("zh", served({ "data/text.zh.json": bundle, "data/schema.zh.json": schemaZh() })), /not the zh text/);
  await assert.rejects(loadBundles("zh", served({ "data/text.zh.json": textZh(), "data/schema.zh.json": schemaEn })), /not the zh schema/);
});

test("replaceContents keeps the object, so a panel holding it sees the new wording and no old key", () => {
  const held = clone(schemaEn);
  const panel = { schema: held };                        // what a panel keeps from the day it was made
  const next = schemaZh();
  delete next.max_items;
  const same = replaceContents(held, next);
  assert.equal(same, held);
  assert.equal(panel.schema.cards.style.label, "文风");
  assert.equal(panel.schema.lang, "zh");
  assert.equal("max_items" in panel.schema, false);
  assert.deepEqual(panel.schema.order, schemaEn.order);  // the cards and their order are the same in every language
});

test("swapping the text bundle changes every section view, and swapping back restores it", () => {
  const common = section("common");
  assert.equal(common.unnamed, "Unnamed");
  try {
    setText(textZh());
    assert.equal(common.unnamed, "无名");
    assert.equal(msg("common.unnamed"), "无名");
    setText(bundle);
    assert.equal(common.unnamed, "Unnamed");
  } finally {
    setText(bundle);
  }
});

test("applyStaticText sets the page language from the bundle, and again after a swap", () => {
  const root = { querySelectorAll: () => [], documentElement: { lang: "" } };
  try {
    applyStaticText(root);
    assert.equal(root.documentElement.lang, "en");
    setText(textZh());
    applyStaticText(root);
    assert.equal(root.documentElement.lang, "zh");
    setText(bundle);
    applyStaticText(root);
    assert.equal(root.documentElement.lang, "en");
  } finally {
    setText(bundle);
  }
});

test("neither app.js nor text.js names a language's file: the language decides which files are read", () => {
  for (const name of ["app.js", "text.js"]) {
    const code = readFileSync(new URL(`../../web/${name}`, import.meta.url), "utf8")
      .split("\n").filter((line) => !line.trim().startsWith("//")).join("\n");
    assert.doesNotMatch(code, /(?:text|schema)\.(?:en|zh)\.json/, name);
    assert.doesNotMatch(code, /TEXT_FILE/, name);
  }
});
