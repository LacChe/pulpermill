import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { createMock } from "../mock.js";
import { createClient, planChapter } from "../client.js";
import { lockStaticCards } from "../gate.js";
import { placeBeat, suggestedCast, planRequest, useCounts, nameMap } from "../plan.js";
import { generateRequest } from "../generate.js";
import { mentions, usageOf, choose, SEND_MAX } from "../usage.js";
import { addItem } from "../logic.js";

test("a name counts only as a whole word, and a sentence is never matched by its words", () => {
  assert.equal(mentions("Suvi walked to the Harbour.", "suvi"), true);
  assert.equal(mentions("Ola's coat hung there.", "Ola"), true, "a possessive is the name");
  assert.equal(mentions("Angola is far.", "Ola"), false, "a name inside another word is not the name");
  assert.equal(mentions("The cellar flooded again at the spring tide.", "The cellar under the shop floods on the spring tide"), false, "a sentence is judged by the model, not by its words");
  assert.equal(mentions("Then the cellar under the shop floods on the spring tide, again.", "The cellar under the shop floods on the spring tide"), true, "unless it is quoted whole");
  assert.equal(mentions("The Parish Council of Hollow met.", "the Parish Council of Hollow"), true, "a long name is still a name");
  assert.equal(mentions("", "Suvi"), false);
});

test("choose keeps what the beat names, then the least used, and never more than the cap unless the beat names more", () => {
  const items = Array.from({ length: 9 }, (_, i) => ({ id: `i${i}` }));
  const used = { i0: { uses: 5, last: 4 }, i1: { uses: 1, last: 2 }, i2: { uses: 1, last: 1 }, i3: { uses: 3, last: 3 } };
  const got = choose(items, used, { planned: new Set(["i0"]) }).map((i) => i.id);
  assert.equal(got.length, SEND_MAX);
  assert.ok(got.includes("i0"), "the planned one is kept though it is the most used");
  assert.deepEqual(got, ["i0", "i4", "i5", "i6", "i7"], "the planned one, then the ones never used");
  const many = choose(items, {}, { planned: new Set(items.slice(0, 7).map((i) => i.id)) });
  assert.equal(many.length, 7, "everything the beat names is carried, past the cap");
});

test("a value is used only when a written chapter says it", async () => {
  const project = await readyProject();
  const [first] = project.characters;
  const place = project.world.places[0];
  project.outline = { beats: [{ id: "b1", chapter: 1, where: place.id, cast: [first.id], spotlight: "" }] };
  assert.deepEqual(usageOf(project), {}, "a beat that is only planned uses nothing up");
  project.chapters = [{ id: "c1", beat: "b1", text: "Nothing in particular happened." }];
  assert.equal(usageOf(project)[first.id], undefined);
  assert.equal(usageOf(project)[place.id], undefined);
  project.chapters[0].text = `${first.name} went to ${place.name}.`;
  assert.deepEqual(usageOf(project)[first.id], { uses: 1, last: 1 });
  assert.deepEqual(usageOf(project)[place.id], { uses: 1, last: 1 });
  assert.equal(usageOf(project, 1)[first.id], undefined, "the chapter being written again does not count itself");
});

test("knowledge, ties and holdings count as used only when the chapter's record says it showed them", async () => {
  const project = await readyProject();
  const [first] = project.characters;
  const place = project.world.places[0];
  const ent = project.entanglements;
  project.outline = { beats: [{ id: "b1", chapter: 1, where: place.id, cast: [first.id], spotlight: "" }] };
  project.chapters = [{ id: "c1", beat: "b1", text: `${first.name} went to ${place.name}.` }];
  project.summary_events = { entries: [{ id: "e1", beat: "b1", happened: "x" }] };
  const sentences = [ent.knowledge[0]?.id, ent.ties[0]?.id].filter(Boolean);
  for (const id of sentences) assert.equal(usageOf(project)[id], undefined, "naming it is not showing it");
  project.summary_events.entries[0].entanglements_shown = sentences;
  for (const id of sentences) assert.deepEqual(usageOf(project)[id], { uses: 1, last: 1 });
  assert.equal(usageOf(project, 1)[sentences[0]], undefined, "the chapter being written again does not count itself");
});

test("a pressure counts as used by the spotlight, whatever the chapter's record says it showed", async () => {
  const project = await readyProject();
  const [first] = project.characters;
  const place = project.world.places[0];
  const [pressure] = project.entanglements.pressures;
  project.outline = { beats: [{ id: "b1", chapter: 1, where: place.id, cast: [first.id], spotlight: pressure.id }] };
  project.chapters = [{ id: "c1", beat: "b1", text: `${pressure.what} ${first.name} went to ${place.name}.` }];
  project.summary_events = { entries: [{ id: "e1", beat: "b1", happened: "x", entanglements_shown: [] }] };
  assert.deepEqual(usageOf(project)[pressure.id], { uses: 1, last: 1 }, "spotlit and never shown still counts");
  project.summary_events.entries[0].entanglements_shown = [pressure.id];
  assert.equal(usageOf(project)[pressure.id].uses, 1, "shown as well as spotlit counts once");
  assert.equal(usageOf(project, 1)[pressure.id], undefined, "the chapter being written again does not count itself");
  project.outline.beats[0].spotlight = "";
  assert.equal(usageOf(project)[pressure.id], undefined, "shown without the spotlight is not a use of a pressure");
});

async function crowded() {
  const project = await readyProject();
  lockStaticCards(project);
  const places = schema.cards.world.fields.find((f) => f.key === "places");
  for (let i = 0; i < 8; i++) Object.assign(addItem(places, project.world.places), { name: `Spare place ${i}`, description: `A spare place, number ${i}.` });
  const mock = createMock(schema, { delay: 0 });
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock, pollEvery: 5 });
  return { project, client };
}

test("the planner and the writer are sent at most five places, and the planner counts them from chapter text", async () => {
  const { project, client } = await crowded();
  const request = planRequest(schema, project, suggestedCast(project, 1));
  assert.ok(project.world.places.length > SEND_MAX);
  assert.equal(request.world.places.length, SEND_MAX);
  assert.equal(request.use_counts.places.length, SEND_MAX);
  const plan = await planChapter(client, schema, project, suggestedCast(project, 1)).done;
  placeBeat(project, plan.beat);
  const beat = project.outline.beats.at(-1);
  const sent = generateRequest(schema, project, beat);
  assert.ok(sent.world.places.length <= SEND_MAX + 1);
  assert.ok(sent.world.places.some((p) => p.id === beat.where), "the place the beat is set in is always sent");
});

test("the place a beat names is sent even when it is the most used", async () => {
  const { project, client } = await crowded();
  const plan = await planChapter(client, schema, project, suggestedCast(project, 1)).done;
  placeBeat(project, plan.beat);
  const beat = project.outline.beats.at(-1);
  const busy = project.world.places.find((p) => p.name === "Spare place 7");
  beat.where = busy.id;
  const sent = generateRequest(schema, project, beat);
  assert.ok(sent.world.places.some((p) => p.id === busy.id));
});

test("what the beat's words name is sent too, as are the cast's things", async () => {
  const { project, client } = await crowded();
  const plan = await planChapter(client, schema, project, suggestedCast(project, 1)).done;
  placeBeat(project, plan.beat);
  const beat = project.outline.beats.at(-1);
  beat.turn = "The ledger is found in Spare place 6, behind the stove.";
  const sent = generateRequest(schema, project, beat);
  assert.ok(sent.world.places.some((p) => p.name === "Spare place 6"), "a place named in the beat's text is carried");
});

test("a used place gives way to the unused ones", async () => {
  const { project } = await crowded();
  const place = project.world.places[0];
  project.outline = { beats: [{ id: "b1", chapter: 1, where: place.id, cast: [project.characters[0].id], spotlight: "" }] };
  project.chapters = [{ id: "c1", beat: "b1", text: `They all met at ${place.name}.` }];
  const request = planRequest(schema, project, [project.characters[0].id]);
  assert.ok(!request.world.places.some((p) => p.name === place.name), "five places have not been used; the used one is left out");
  assert.equal(useCounts(project, null).places[place.id], 1);
});
