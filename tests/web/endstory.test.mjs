import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { createMock } from "../../web/mock.js";
import { createClient, planChapter, generateChapter, endStory } from "../../web/client.js";
import { lockStaticCards } from "../../web/gate.js";
import { placeBeat, suggestedCast } from "../../web/plan.js";
import { commitChapter } from "../../web/generate.js";
import { endGate, endStoryRequest, landEndStory, afterStoryChanges, afterStoryStale, afterStoryView, chaptersFingerprint } from "../../web/endstory.js";
import { setEndNote } from "../../web/modelnotes.js";
import { readEndStoryReply } from "../../web/logic.js";

async function finished(chapters = 2) {
  const project = await readyProject();
  project.setup.chapter_count = chapters;
  lockStaticCards(project);
  const mock = createMock(schema, { delay: 0 });
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock, pollEvery: 5 });
  for (let n = 1; n <= chapters; n++) {
    const plan = await planChapter(client, schema, project, suggestedCast(project, n)).done;
    placeBeat(project, plan.beat);
    commitChapter(project, (await generateChapter(client, schema, project).done).outcome);
  }
  return { project, mock, client };
}

test("the gate waits for the last chapter", async () => {
  const { project } = await finished(2);
  assert.equal(endGate(project).ok, true);
  project.setup.chapter_count = 3;
  assert.equal(endGate(project).reason, "not_done");
});

test("the request carries the cards and the records in words, never the chapters", async () => {
  const { project } = await finished(2);
  project.summary_shifts.shifts.push({ id: "s0000001", beat: project.outline.beats[0].id, character: project.characters[0].id, decided: "Leave." });
  const request = endStoryRequest(schema, project);
  assert.equal(request.call, "end_story");
  assert.equal(request.characters.length, 2);
  assert.equal(request.events.length, 2);
  assert.ok(request.shifts.some((s) => s.chapter === 1 && s.character === "Suvi" && s.decided === "Leave."), "shifts in words, by chapter");
  assert.ok(!JSON.stringify(request).includes("Mock chapter"), "no chapter text");
});

test("the fixed fields are put back, ids are kept, new items get ids, and nothing changes until it is stored", async () => {
  const { project, client } = await finished(2);
  const was = JSON.stringify(project);
  const result = await endStory(client, schema, project).done;
  assert.equal(result.ok, true);
  assert.equal(JSON.stringify(project), was);
  const first = result.after.characters[0];
  assert.equal(first.name, "Suvi", "the changed name was put back");
  assert.deepEqual(result.forced, [{ character: "Suvi", fields: ["name"] }]);
  assert.match(first.sketch, /changed by the story/);
  assert.deepEqual(result.after.characters.map((c) => c.id), project.characters.map((c) => c.id));
  const places = result.after.world.places;
  assert.equal(places.length, project.world.places.length + 1);
  assert.equal(new Set(places.map((p) => p.id)).size, places.length);
  assert.deepEqual(places.slice(0, project.world.places.length).map((p) => p.id), project.world.places.map((p) => p.id));
});

test("what changed is listed in words", async () => {
  const { project, client } = await finished(1);
  const result = await endStory(client, schema, project).done;
  const changes = afterStoryChanges(schema, project, result.after);
  assert.ok(changes.some((c) => c.card === "characters" && c.field === "sketch" && c.kind === "changed"));
  assert.ok(changes.some((c) => c.card === "world" && c.kind === "added" && c.after === "Mock new place"));
  assert.ok(!changes.some((c) => c.field === "name"), "a fixed field never shows as changed");
});

test("characters that come back changed in number or id are refused", async () => {
  const { project } = await finished(1);
  const base = { ok: true, characters: JSON.parse(JSON.stringify(project.characters)), world: {} };
  assert.equal(landEndStory(schema, project, readEndStoryReply({ ...base, characters: base.characters.slice(1) })).ok, false);
  const swapped = JSON.parse(JSON.stringify(base.characters)); swapped[0].id = "zzzzzzzz";
  assert.equal(landEndStory(schema, project, readEndStoryReply({ ...base, characters: swapped })).ok, false);
});

test("a value of the wrong kind is dropped and the old one stays", async () => {
  const { project } = await finished(1);
  const characters = JSON.parse(JSON.stringify(project.characters));
  characters[0].sketch = 42;
  const out = landEndStory(schema, project, readEndStoryReply({ ok: true, characters, world: { name: ["no"] } }));
  assert.equal(out.after.characters[0].sketch, project.characters[0].sketch);
  assert.ok(out.dropped.includes("sketch") && out.dropped.includes("name"));
  assert.equal(out.after.world.name, project.world.name);
});

test("a failed or stopped call changes nothing", async () => {
  const { project, client, mock } = await finished(1);
  mock.queue("bad_output");
  assert.equal((await endStory(client, schema, project).done).error.kind, "bad_output");
  mock.queue("busy");
  assert.equal((await endStory(client, schema, project).done).error.kind, "busy");
  assert.equal(project.after_story, undefined);
});

test("a chapter written again after the copy was made marks the copy out of date, and putting it back clears the mark", async () => {
  const { project, client } = await finished(2);
  const result = await endStory(client, schema, project).done;
  project.after_story = result.after;
  assert.equal(afterStoryStale(project), false, "no note, nothing says it is out of date");
  setEndNote(project, { madeFrom: chaptersFingerprint(project) });
  assert.equal(afterStoryStale(project), false);
  const was = project.chapters[1].text;
  project.chapters[1].text = "A different second chapter.";
  assert.equal(afterStoryStale(project), true);
  project.chapters[1].text = was;
  assert.equal(afterStoryStale(project), false, "undoing the rewrite clears it");
  project.chapters.reverse();
  project.summary_events.entries.reverse();
  assert.equal(afterStoryStale(project), false, "the order they are stored in does not matter");
  project.summary_shifts.shifts.push({ id: "s0000009", beat: project.outline.beats[0].id, character: project.characters[0].id, decided: "Stay." });
  assert.equal(afterStoryStale(project), true, "a changed record counts even when the words are the same");
  project.summary_shifts.shifts.pop();
  delete project.after_story;
  project.chapters[0].text = "x";
  assert.equal(afterStoryStale(project), false, "no copy, nothing to be out of date");
});

test("the fingerprint is eight hex digits and follows the text", async () => {
  const { project } = await finished(1);
  const a = chaptersFingerprint(project);
  assert.match(a, /^[0-9a-f]{8}$/);
  project.chapters[0].text += " ";
  assert.notEqual(chaptersFingerprint(project), a);
});

test("the copy's forms edit the copy itself, and the originals stay as they are", async () => {
  const { project, client } = await finished(2);
  project.after_story = (await endStory(client, schema, project).done).after;
  const view = afterStoryView(schema, project);
  assert.equal(view.characters, project.after_story.characters, "the same objects, not duplicates");
  assert.equal(view.world, project.after_story.world);
  const original = JSON.stringify(project.characters);
  view.characters[0].name = "Edited by hand";
  assert.equal(project.after_story.characters[0].name, "Edited by hand");
  assert.equal(JSON.stringify(project.characters), original);
});
