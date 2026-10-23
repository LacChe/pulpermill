import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { createMock } from "../mock.js";
import { createClient, planChapter, generateChapter, endStory } from "../client.js";
import { lockStaticCards } from "../gate.js";
import { placeBeat, suggestedCast } from "../plan.js";
import { commitChapter } from "../generate.js";
import { storyMarkdown, storyFileName, cardFiles, readCardFile, CARD_FILE_KEY } from "../exporting.js";

async function story(chapters, withEnd = false) {
  const project = await readyProject();
  project.title = "The Salt Coast!";
  project.setup.chapter_count = chapters;
  lockStaticCards(project);
  const mock = createMock(schema, { delay: 0 });
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock, pollEvery: 5 });
  for (let n = 1; n <= chapters; n++) {
    const plan = await planChapter(client, schema, project, suggestedCast(project, n)).done;
    placeBeat(project, plan.beat);
    commitChapter(project, (await generateChapter(client, schema, project).done).outcome);
  }
  if (withEnd) project.after_story = (await endStory(client, schema, project).done).after;
  return project;
}

test("the story is the title and every written chapter in order, in one markdown file", async () => {
  const project = await story(3);
  project.chapters.reverse();                       // the order in the file does not depend on how they are stored
  const text = storyMarkdown(project);
  assert.match(text, /^# The Salt Coast!\n\n## Chapter 1\n\nMock chapter 1 of 3\./);
  assert.ok(text.indexOf("## Chapter 1") < text.indexOf("## Chapter 2") && text.indexOf("## Chapter 2") < text.indexOf("## Chapter 3"));
  assert.equal(storyFileName(project), "the-salt-coast-story.md");
  assert.equal(storyMarkdown({ chapters: [] }), "# Untitled story\n");
});

test("each portable card is its own file, and the others are left out", async () => {
  const project = await story(1);
  const files = cardFiles(schema, project);
  assert.deepEqual(files.map((f) => f.name), [
    "the-salt-coast-style.json", "the-salt-coast-character-1-suvi.json", "the-salt-coast-character-2-ola.json", "the-salt-coast-world.json",
  ]);
  assert.deepEqual(files.map((f) => JSON.parse(f.text)[CARD_FILE_KEY]), ["style", "characters", "characters", "world"]);
  assert.equal(new Set(files.map((f) => f.name)).size, files.length);
});

test("the after-story copy goes out as its own set of files", async () => {
  const project = await story(1, true);
  const files = cardFiles(schema, project);
  assert.equal(files.length, 8);
  assert.ok(files.slice(4).every((f) => f.name.includes("after-story") && f.label.startsWith("After the story")));
  const sketch = JSON.parse(files.find((f) => f.name.includes("after-story-character-1")).text).values.sketch;
  assert.match(sketch, /changed by the story/);
});

test("a card file reads back as the same card", async () => {
  const project = await story(1);
  for (const f of cardFiles(schema, project)) {
    const read = readCardFile(f.text, schema);
    assert.equal(read.ok, true, f.name);
    assert.deepEqual(read.ignored, [], f.name);
    assert.deepEqual(read.values, JSON.parse(f.text).values);
  }
});

test("a bad card file is refused with a reason, and strangers are ignored", async () => {
  assert.equal(readCardFile("nope", schema).reason, "unreadable");
  assert.equal(readCardFile("{}", schema).reason, "not_card_file");
  assert.equal(readCardFile(JSON.stringify({ [CARD_FILE_KEY]: "dragons", values: {} }), schema).reason, "unknown_card");
  assert.equal(readCardFile(JSON.stringify({ [CARD_FILE_KEY]: "setup", values: {} }), schema).reason, "not_portable");
  assert.equal(readCardFile(JSON.stringify({ [CARD_FILE_KEY]: "world", schema_version: 99, values: {} }), schema).reason, "newer");
  const read = readCardFile(JSON.stringify({ [CARD_FILE_KEY]: "world", schema_version: 1, values: { name: "Salt", extra: 1, everyday_life: 7, places: "no" } }), schema);
  assert.deepEqual(read.values, { name: "Salt" });
  assert.deepEqual(read.ignored.sort(), ["everyday_life", "extra", "places"]);
});
