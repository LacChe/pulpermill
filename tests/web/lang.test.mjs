import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LANGUAGES, DEFAULT_LANGUAGE, normalizeLanguage } from "../../web/lang.js";
import { newProject, readProject, projectSnapshot, recoveryRecord, readRecovery, worthRecovering } from "../../web/logic.js";

const schema = JSON.parse(readFileSync(new URL("../../web/data/schema.en.json", import.meta.url), "utf8"));

test("the page offers English and Chinese, each by its own name", () => {
  assert.deepEqual(LANGUAGES.map((l) => l.code), ["en", "zh"]);
  assert.deepEqual(LANGUAGES.map((l) => l.name), ["English", "中文"]);
  assert.equal(DEFAULT_LANGUAGE, "en");
});

test("normalizeLanguage maps the codes a file or a browser may hold to one the page offers", () => {
  for (const code of ["zh", "zh-Hans", "zh-CN", "zh_CN", "ZH", " zh "]) assert.equal(normalizeLanguage(code), "zh", code);
  for (const code of ["en", "en-US", "EN"]) assert.equal(normalizeLanguage(code), "en", code);
  for (const code of ["fr", "xx", "", null, undefined, 7]) assert.equal(normalizeLanguage(code), "en", String(code));
});

test("a blank project is in the default language, or the one it is given", () => {
  assert.equal(newProject(schema).output_language, "en");
  assert.equal(newProject(schema, "zh").output_language, "zh");
  assert.equal(newProject(schema, "zh-Hans").output_language, "zh");
  assert.equal(newProject(schema, "fr").output_language, "en");
});

test("a file with no language opens as English, and a stray code becomes English", () => {
  const bare = JSON.stringify({ title: "Old", schema_version: schema.schema_version });
  assert.equal(readProject(bare, schema).project.output_language, "en");
  const stray = JSON.stringify({ title: "Odd", schema_version: schema.schema_version, output_language: "klingon" });
  assert.equal(readProject(stray, schema).project.output_language, "en");
});

test("a Chinese project keeps its language through save and open", () => {
  const saved = projectSnapshot(schema, newProject(schema, "zh"));
  const read = readProject(saved, schema);
  assert.equal(read.ok, true);
  assert.equal(read.project.output_language, "zh");
  assert.equal(projectSnapshot(schema, read.project), saved);
});

test("a recovery copy of a blank project is not worth offering in either language", () => {
  for (const language of ["en", "zh"]) {
    const record = recoveryRecord(schema, newProject(schema, language));
    const got = readRecovery(record, schema);
    assert.equal(got.project.output_language, language);
    assert.equal(worthRecovering(schema, got), false, language);
  }
});

test("a recovery copy with work in it is offered, in the language it was written in", () => {
  const project = { ...newProject(schema, "zh"), title: "空庭" };
  const got = readRecovery(recoveryRecord(schema, project), schema);
  assert.equal(got.project.output_language, "zh");
  assert.equal(worthRecovering(schema, got), true);
});
