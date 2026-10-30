import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { createMock } from "../../web/mock.js";
import { createClient, planChapter, generateChapter, regenerateChapter } from "../../web/client.js";
import { lockStaticCards } from "../../web/gate.js";
import { placeBeat, suggestedCast } from "../../web/plan.js";
import { commitChapter, commitRegenerated } from "../../web/generate.js";
import { cardFiles, readCardFile, planImport, applyImport } from "../../web/exporting.js";
import { settledProject } from "../../web/logic.js";
import { watch, untouched, sameValue } from "../../web/undo.js";

test("watch puts the parts back, including ones that did not exist, and declines once they changed", () => {
  const project = { a: [1], b: "x" };
  const w = watch(project, ["a", "c"]);
  project.a = [1, 2]; project.c = "new";
  w.settle();
  assert.equal(w.undo(), true);
  assert.deepEqual(project, { a: [1], b: "x" });
  project.a = [1, 2]; project.c = "new";
  const v = watch({ ...project }, ["a"]);
  const other = { a: [1], b: "x" };
  const x = watch(other, ["a"]);
  other.a = [9]; x.settle(); other.a = [9, 10];
  assert.equal(x.undo(), false);
  assert.deepEqual(other.a, [9, 10], "a declined undo changes nothing");
  assert.ok(v);
});

test("untouched names the fields still holding what the action wrote", () => {
  assert.deepEqual(untouched({ a: "1", b: "edited" }, { a: "1", b: "2" }, ["a", "b"]), ["a"]);
  assert.equal(sameValue(undefined, null), true);
});

async function started() {
  const project = await readyProject();
  project.setup.chapter_count = 5;
  lockStaticCards(project);
  const mock = createMock(schema, { delay: 0 });
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock, pollEvery: 5 });
  const write = async (n) => {
    const plan = await planChapter(client, schema, project, suggestedCast(project, n)).done;
    placeBeat(project, plan.beat);
    return commitChapter(project, (await generateChapter(client, schema, project).done).outcome);
  };
  return { project, client, write };
}

test("Generate can be undone: the chapter and its records go and the story is as it was", async () => {
  const { project, write } = await started();
  const was = JSON.stringify(project);
  const { undo } = await write(1);
  assert.equal(project.chapters.length, 1);
  const withPlan = JSON.parse(was);
  assert.equal(undo(), true);
  assert.equal(project.chapters?.length ?? 0, 0);
  assert.equal(project.summary_events?.entries?.length ?? 0, 0);
  assert.equal(project.entanglements_history?.states?.length ?? 0, 0);
  assert.deepEqual(project.entanglements, withPlan.entanglements);
});

test("Generate's undo declines when the Entanglements were edited since", async () => {
  const { project, write } = await started();
  const { undo } = await write(1);
  project.entanglements.ties[0].bond = "Changed by hand.";
  const kept = JSON.stringify(project);
  assert.equal(undo(), false);
  assert.equal(JSON.stringify(project), kept, "nothing was changed");
});

test("Write again's undo declines when a chapter record was changed since", async () => {
  const { project, client, write } = await started();
  await write(1); await write(2);
  const result = await regenerateChapter(client, schema, project, 1).done;
  const { undo } = commitRegenerated(project, result.outcome);
  project.chapters[0].text += " (edited by hand)";
  assert.equal(undo(), false);
  assert.match(project.chapters[0].text, /edited by hand/);
});

const files = (project) => Object.fromEntries(cardFiles(schema, project).map((f) => [f.name.replace(/^.*?-(style|world|character-\d+)(-.*)?\.json$/, "$1"), f.text]));

test("undoing an imported new character keeps it when it was edited since", async () => {
  const source = files(await readyProject())["character-1"];
  const project = await readyProject();
  const done = applyImport(schema, project, planImport(schema, project, readCardFile(source, schema)));
  const added = project.characters.find((c) => c.id === done.instanceId);
  added.name = "Renamed by hand";
  assert.deepEqual(done.undo(), { done: false, skipped: [] });
  assert.equal(project.characters.length, 3);
  added.name = "Suvi";
  assert.equal(done.undo().done, true);
  assert.equal(project.characters.length, 2);
});

test("undoing an import that replaced a character leaves the fields edited since", async () => {
  const source = files(await readyProject())["character-1"];
  const project = await readyProject();
  const mine = project.characters[1];
  const before = settledProject(schema, project).characters[1];
  const done = applyImport(schema, project, planImport(schema, project, readCardFile(source, schema), { mode: "replace", id: mine.id }));
  assert.ok(done.keys.includes("name") && done.keys.length > 1);
  const live = project.characters.find((c) => c.id === mine.id);
  live.name = "Edited since";
  const back = done.undo();
  assert.equal(back.done, true);
  assert.deepEqual(back.skipped, ["name"]);
  assert.equal(live.name, "Edited since");
  const other = done.keys.find((k) => k !== "name");
  assert.deepEqual(JSON.stringify(live[other]), JSON.stringify(before[other]));
});
