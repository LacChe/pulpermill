import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { applyLanguageToProject, LANGUAGES } from "../../web/lang.js";
import { newProject, isBlankProject, projectSnapshot, hasUnsavedChanges, worthRecovering, readRecovery, recoveryRecord } from "../../web/logic.js";
import { msg } from "../../web/text.js";

const schema = JSON.parse(readFileSync(new URL("../../web/data/schema.en.json", import.meta.url), "utf8"));
const html = readFileSync(new URL("../../web/index.html", import.meta.url), "utf8");

test("the project follows the page: same language changes nothing, a blank project is rebased, a project with work is changed", () => {
  const project = newProject(schema);
  assert.equal(applyLanguageToProject(project, "en", true), "same");
  assert.equal(applyLanguageToProject(project, "zh", true), "rebase");
  assert.equal(project.output_language, "zh");
  assert.equal(applyLanguageToProject(project, "en", false), "changed");
  assert.equal(project.output_language, "en");
  assert.equal(applyLanguageToProject(project, "zh-Hans", false), "changed");
  assert.equal(project.output_language, "zh");
});

test("a blank project is blank in whichever language it is in, and a title makes it not blank", () => {
  assert.equal(isBlankProject(schema, newProject(schema)), true);
  assert.equal(isBlankProject(schema, newProject(schema, "zh")), true);
  assert.equal(isBlankProject(schema, { ...newProject(schema, "zh"), title: "空庭" }), false);
  assert.equal(isBlankProject(schema, { ...newProject(schema), example_chapter: "Once." }), false);
});

test("flipping a blank project does not make it unsaved work, and flipping a project with work does", () => {
  const blank = newProject(schema);
  let saved = projectSnapshot(schema, blank);
  const wasBlank = isBlankProject(schema, blank);
  assert.equal(applyLanguageToProject(blank, "zh", wasBlank), "rebase");
  assert.equal(hasUnsavedChanges(schema, blank, saved), true);        // until the page rebases its saved copy, as app.js does
  saved = projectSnapshot(schema, blank);
  assert.equal(hasUnsavedChanges(schema, blank, saved), false);
  assert.equal(worthRecovering(schema, readRecovery(recoveryRecord(schema, blank), schema)), false);

  const work = { ...newProject(schema), title: "Salt Coast" };
  const before = projectSnapshot(schema, work);
  assert.equal(applyLanguageToProject(work, "zh", isBlankProject(schema, work)), "changed");
  assert.equal(hasUnsavedChanges(schema, work, before), true);
});

test("a new project takes the page's language, so a flip carries to the next New", () => {
  assert.equal(newProject(schema, "zh").output_language, "zh");
  assert.equal(newProject(schema, "en").output_language, "en");
});

test("the switch sits in the top bar, which does not lock: it only rewords the page, so it works while a model call runs", () => {
  const bar = html.slice(html.indexOf('<header class="bar">'), html.indexOf("</header>"));
  assert.ok(bar.includes('id="language"'), "the language group is not in the top bar");
  assert.doesNotMatch(bar.slice(0, bar.indexOf(">") + 1), /data-locks/);
  assert.match(bar, /id="language"[^>]*role="group"[^>]*data-text-attrs="aria-label:page\.language"/);
});

test("the group is named from the bundle, and the buttons are built from the language list (a language's own name)", () => {
  assert.equal(msg("page.language"), "Language");
  assert.deepEqual(LANGUAGES.map((l) => [l.code, l.short]), [["en", "EN"], ["zh", "中文"]]);
  const app = readFileSync(new URL("../../web/app.js", import.meta.url), "utf8");
  assert.match(app, /LANGUAGES\.map\(/);
  assert.match(app, /aria-pressed/);
});

test("the font stacks can show Chinese", () => {
  const css = readFileSync(new URL("../../web/style.css", import.meta.url), "utf8");
  assert.match(css, /--font-ui:[^;]*"PingFang SC"[^;]*"Microsoft YaHei"[^;]*"Noto Sans CJK SC"/);
  assert.match(css, /--font-prose:[^;]*"Noto Serif CJK SC"/);
});
