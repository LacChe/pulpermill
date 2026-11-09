import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { story, opening, schema } from "./fixture.mjs";
import {
  generateGate, generateRequest, previousEnding, inputsKey, landShifts, applyGenerated, commitChapter,
  projectBefore, regenerateGate, regenerateKey, applyRegenerated, commitRegenerated,
} from "../../web/generate.js";
import { readGenerateReply } from "../../web/logic.js";
import { beatInWords, planRequest } from "../../web/plan.js";
import { effectiveProject } from "../../web/effective.js";

const copy = (x) => JSON.parse(JSON.stringify(x));
const read = (extra = {}) => readGenerateReply({ ok: true, chapter_text: "Chapter two text.", events: { happened: "Suvi hid the ledger.", changed: "Marit knows." }, shifts: [], ...extra });
const beat2 = (p) => p.outline.beats[1];

test("a chapter can be written once the story has started, with a beat, a sound cast and no blocking problems", () => {
  const p = story();
  const gate = generateGate(schema, p);
  assert.deepEqual([gate.ok, gate.chapter, gate.beat.id, gate.stale], [true, 2, "b0000002", false]);
  assert.equal(generateGate(schema, { ...p, locks: [] }).reason, "not_started");
  assert.equal(generateGate(schema, { ...p, setup: { ...p.setup, chapter_count: 1 } }).reason, "done");
  const none = story(); none.outline.beats.pop();
  assert.equal(generateGate(schema, none).reason, "no_beat");
  const noLead = story(); beat2(noLead).cast = ["c0000002"];
  assert.equal(generateGate(schema, noLead).reason, "cast_no_protagonist");
  const blocked = story(); beat2(blocked).aim = "";
  const result = generateGate(schema, blocked);
  assert.equal(result.reason, "beat_blocked");
  assert.ok(result.problems.length > 0);
});

test("a plan whose inputs changed since it was made warns and does not block", () => {
  const p = story();
  p.outline.beats[1].planned_from = "00000000";
  const gate = generateGate(schema, p);
  assert.equal(gate.ok, true);
  assert.equal(gate.stale, true);
});

test("the end of the last chapter is cut to a clean start, and chapter 1 has none", () => {
  const p = story();
  p.chapters[0].text = "First paragraph that is long.\n\nSecond paragraph, which closes the chapter.";
  assert.equal(previousEnding(p, 1000), p.chapters[0].text);
  const cut = previousEnding(p, 50);
  assert.ok(cut.length <= 50 && p.chapters[0].text.endsWith(cut));
  assert.equal(previousEnding(opening()), null);
  assert.equal(previousEnding(p, 1000, 2), p.chapters[0].text, "the chapter before the one asked for");
  assert.equal(previousEnding(p, 1000, 1), null);
});

test("the generate request opens the story only in chapter 1, and reads the cards going into the chapter", () => {
  const p = story();
  p.shifts.entries.push({ id: "s1", beat: "b0000001", card: "entanglements", target: null, patch: { ties: [{ op: "replace", id: "t1000001", values: { edge: "to leave it be" } }] } });
  const request = generateRequest(schema, p, beat2(p));
  assert.deepEqual(request.setup, { chapter_count: 8 });
  assert.equal(request.protagonist, "c0000001");
  assert.equal(request.ties.find((t) => t.id === "t1000001").edge, "to leave it be");
  assert.equal(request.cast[0].fear, "Being found out", "people do not change in a chapter");
  assert.deepEqual(request.beat, { where: "The Archive", when_time: "Dusk, the second day", aim: beat2(p).aim, plan: beat2(p).plan, spotlight: "t1000001" });
  const first = generateRequest(schema, opening(), opening().outline.beats[0]);
  assert.deepEqual(Object.keys(first.setup).sort(), ["chapter_count", "disruption", "normal", "protagonist"]);
  assert.equal(first.previous_ending, null);
});

test("the beat in words carries the spotlight tie's id as stored, and leaves the key out when the beat has none", () => {
  const p = story();
  const beat = beat2(p);
  assert.equal(beatInWords(p, beat).spotlight, "t1000001");
  assert.deepEqual(Object.keys(beatInWords(p, beat)).sort(), ["aim", "plan", "spotlight", "when_time", "where"]);
  assert.equal(beatInWords(p, { ...beat, outcome: "lost" }).outcome, "lost", "the planned outcome goes to the events step with the beat");
  const bare = { ...beat, spotlight: "" };
  assert.deepEqual(Object.keys(beatInWords(p, bare)).sort(), ["aim", "plan", "when_time", "where"]);
  delete bare.spotlight;
  assert.equal("spotlight" in beatInWords(p, bare), false);
  assert.equal(beatInWords(p, { ...beat, spotlight: "t1000002" }).spotlight, "t1000002", "the id is whatever the beat stores");
});

test("the inputs key changes with the plan, the picks and what has been written", () => {
  const p = story();
  const key = inputsKey(schema, p, beat2(p));
  assert.equal(inputsKey(schema, copy(p), beat2(copy(p))), key);
  const edited = copy(p); edited.characters[0].sketch = "Changed";
  assert.notEqual(inputsKey(schema, edited, beat2(edited)), key);
  const written = copy(p); written.chapters.push({ id: "k2", beat: "b0000002", text: "x" });
  assert.notEqual(inputsKey(schema, written, beat2(written)), key);
});

const shift = (card, patch, target = null) => ({ card, target, patch });
const edge = (text, id = "t1000001") => shift("entanglements", { ties: [{ op: "replace", id, values: { edge: text } }] });

test("a shift becomes an entry: it gets an id, the words become ids, and it says its beat", () => {
  const p = story();
  const proposed = [
    shift("entanglements", { holdings: [{ op: "add", values: { holdee: "The ledger", held_by: "Suvi" } }, { op: "remove", id: "h1000001" }], ties: [{ op: "replace", id: "t1000001", values: { edge: "to take her home at once" } }] }),
  ];
  const landed = landShifts(schema, p, beat2(p), proposed);
  assert.deepEqual(landed.entries.map((e) => [e.card, e.target]), [["entanglements", null]]);
  assert.ok(landed.entries.every((e) => e.beat === "b0000002" && e.id));
  const holdings = landed.entries[0].patch.holdings;
  assert.deepEqual([holdings[0].op, holdings[0].values, holdings[1]], ["add", { holdee: "o0000001", held_by: "c0000001" }, { op: "remove", id: "h1000001" }]);
  assert.match(holdings[0].id, /./);
  assert.deepEqual(landed.warnings, []);
  const change = landed.changes.find((c) => c.after === "to take her home at once");
  assert.equal(change.before, "to bring her daughter home");
});

test("a shift that cannot be used is left out with a warning, and the rest are kept", () => {
  const p = story();
  const landed = landShifts(schema, p, beat2(p), [
    shift("entanglements", { holdings: [{ op: "add", values: { holdee: "The Moon", held_by: "Suvi" } }] }),   // matches nothing
    shift("entanglements", { holdings: [{ op: "remove", id: "h9999999" }] }),             // no such item
    shift("entanglements", { ties: [{ op: "replace", id: "t1000001", values: { tie_from: "Suvi" } }] }),      // an identity field
    edge("Real change"),
    edge("A second entry for the Entanglements", "t1000002"),
  ]);
  assert.deepEqual(landed.entries.map((e) => [e.card, e.target]), [["entanglements", null]]);
  assert.equal(landed.entries[0].patch.ties[0].values.edge, "Real change");
  assert.equal(landed.warnings.length, 4);
  assert.ok(landed.warnings.every((w) => w.kind === "shift" && w.text));
});

test("part of a shift can be left out while the rest stands", () => {
  const p = story();
  const landed = landShifts(schema, p, beat2(p), [shift("entanglements", { holdings: [{ op: "add", values: { holdee: "The Moon", held_by: "Suvi" } }], ties: [{ op: "replace", id: "t1000001", values: { edge: "new aim" } }] })]);
  assert.deepEqual(Object.keys(landed.entries[0].patch), ["ties"]);
  assert.equal(landed.warnings.length, 1);
});

test("applying a reply makes the chapter, its events and its shifts, and changes nothing", () => {
  const p = story();
  const was = JSON.stringify(p);
  const out = applyGenerated(schema, p, beat2(p), read({ shifts: [edge("to make her daughter stay")] }));
  assert.equal(JSON.stringify(p), was);
  assert.deepEqual([out.chapter.beat, out.chapter.text, out.events.beat, out.events.happened, out.events.changed], ["b0000002", "Chapter two text.", "b0000002", "Suvi hid the ledger.", "Marit knows."]);
  assert.notEqual(out.chapter.id, out.events.id);
  assert.equal(out.shifts.length, 1);
  assert.ok(out.changes.length >= 1);
});

test("committing adds the chapter, its events and its shifts together, and one undo takes them out", () => {
  const p = story();
  const out = applyGenerated(schema, p, beat2(p), read({ shifts: [edge("to make her daughter stay")] }));
  const { undo } = commitChapter(p, out);
  assert.deepEqual([p.chapters.length, p.summary_events.entries.length, p.shifts.entries.length], [2, 2, 1]);
  assert.equal(effectiveProject(p, 3).entanglements.ties[0].edge, "to make her daughter stay");
  assert.equal(undo(), true);
  assert.deepEqual([p.chapters.length, p.summary_events.entries.length, p.shifts.entries.length], [1, 1, 0]);
});

test("an undo refuses when the chapter's records were changed since", () => {
  const p = story();
  const { undo } = commitChapter(p, applyGenerated(schema, p, beat2(p), read()));
  p.chapters[1].text = "Edited by hand.";
  assert.equal(undo(), false);
  assert.equal(p.chapters.length, 2);
});

test("the first chapter works from a project with no shifts or events records yet", () => {
  const o = opening();
  delete o.shifts; delete o.summary_events;
  const { project } = commitChapter(o, applyGenerated(schema, o, o.outline.beats[0], read()));
  assert.equal(project.chapters.length, 1);
  assert.equal(project.summary_events.entries.length, 1);
  assert.deepEqual(project.shifts.entries, []);
});

// ---- Writing a chapter again -------------------------------------------------------------------

function threeChapters() {
  const p = story();
  const second = applyGenerated(schema, p, beat2(p), read({ shifts: [edge("to make her daughter stay")] }));
  commitChapter(p, second);
  p.outline.beats.push({ id: "b0000003", chapter: 3, where: "p0000002", when_time: "Night", cast: ["c0000001", "c0000002"], spotlight: "t1000001", aim: "Suvi wants to leave town.", plan: "She packs." });
  const third = applyGenerated(schema, p, p.outline.beats[2], read({ shifts: [edge("to trust her daughter")] }));
  commitChapter(p, third);
  return p;
}

test("the state before chapter N holds only the records of the chapters before it", () => {
  const p = threeChapters();
  const trial = projectBefore(p, 2);
  assert.deepEqual([trial.chapters.length, trial.summary_events.entries.length, trial.shifts.entries.length], [1, 1, 0]);
  assert.equal(p.chapters.length, 3, "the project is not changed");
  assert.equal(effectiveProject(trial, 2).entanglements.ties[0].edge, "to bring her daughter home");
});

test("writing a chapter again needs a started story, an open outline and a written chapter", () => {
  const p = threeChapters();
  const gate = regenerateGate(schema, p, 2);
  assert.deepEqual([gate.ok, gate.number, gate.beat.id, gate.later], [true, 2, "b0000002", 1]);
  assert.equal(regenerateGate(schema, { ...p, locks: [] }, 2).reason, "not_started");
  assert.equal(regenerateGate(schema, { ...p, locks: [...p.locks, { id: "lx", card: "outline" }] }, 2).reason, "outline_locked");
  assert.equal(regenerateGate(schema, p, 4).reason, "no_chapter");
});

test("the request to write chapter N again reads the state going into N", () => {
  const p = threeChapters();
  const gate = regenerateGate(schema, p, 2);
  const request = generateRequest(schema, gate.trial, gate.beat);
  assert.equal(request.ties.find((t) => t.id === "t1000001").edge, "to bring her daughter home");
  assert.equal(request.previous_ending, p.chapters[0].text);
  assert.deepEqual(request.earlier_events.map((e) => e.chapter), [1]);
});

test("a regenerated chapter keeps its ids, and committing it replaces its records, drops its shifts and the later ones, and marks later beats stale", () => {
  const p = threeChapters();
  const gate = regenerateGate(schema, p, 2);
  const key = regenerateKey(schema, p, 2);
  const out = applyRegenerated(schema, p, gate, readGenerateReply({ ok: true, chapter_text: "A new second chapter.", events: { happened: "New events." }, shifts: [edge("to make peace")] }));
  assert.deepEqual([out.chapter.id, out.events.id], [p.chapters[1].id, p.summary_events.entries[1].id]);
  assert.equal(out.before, "Chapter two text.");
  assert.ok(out.warnings.some((w) => w.kind === "later"));
  assert.equal(regenerateKey(schema, p, 2), key, "building the outcome changes nothing");
  const { undo } = commitRegenerated(p, out);
  assert.equal(p.chapters[1].text, "A new second chapter.");
  assert.equal(p.chapters.length, 3);
  assert.equal(p.chapters[2].text, "Chapter two text.", "the later chapter is untouched");
  assert.deepEqual(p.shifts.entries.map((s) => [s.beat, s.patch.ties[0].values.edge]), [["b0000002", "to make peace"]], "chapter 3's shift is gone, chapter 2's is the new one");
  assert.deepEqual(p.outline.beats.map((b) => b.stale ?? false), [false, false, true]);
  assert.equal(effectiveProject(p, 3).entanglements.ties[0].edge, "to make peace");
  assert.equal(undo(), true);
  assert.equal(p.chapters[1].text, "Chapter two text.");
  assert.equal(p.shifts.entries.length, 2);
  assert.deepEqual(p.outline.beats.map((b) => b.stale ?? false), [false, false, false]);
});

test("regenerating the latest chapter warns about nothing later", () => {
  const p = threeChapters();
  const gate = regenerateGate(schema, p, 3);
  const out = applyRegenerated(schema, p, gate, read());
  assert.equal(out.warnings.some((w) => w.kind === "later"), false);
});

// Three chapters written and the fourth beat planned; shifts of chapters 2 and 3 change the edge of the tie "t1000001", so going into
// chapters 1, 2, 3, 4 it reads: home, home, stay, trust.
function edgeStory() {
  const p = story();
  const edgeShift = (id, beat, edge) => ({ id, beat, card: "entanglements", target: null, patch: { ties: [{ op: "replace", id: "t1000001", values: { edge } }] } });
  p.outline.beats.push(
    { id: "b0000003", chapter: 3, where: "p0000001", when_time: "Night", cast: ["c0000001", "c0000002"], spotlight: "t1000001", aim: "Suvi wants out.", plan: "She runs." },
    { id: "b0000004", chapter: 4, where: "p0000002", when_time: "Dawn", cast: ["c0000001", "c0000002"], spotlight: "t1000001", aim: "Suvi wants to stay.", plan: "She unpacks." });
  p.chapters.push({ id: "k0000002", beat: "b0000002", text: "Chapter two." }, { id: "k0000003", beat: "b0000003", text: "Chapter three." });
  p.shifts.entries.push(edgeShift("s0000001", "b0000002", "to make her daughter stay"), edgeShift("s0000002", "b0000003", "to trust her daughter"));
  return p;
}

test("the generate request carries the spotlight tie's earlier edges, the same trail the plan request sent", () => {
  const p = edgeStory();
  const beat4 = p.outline.beats.find((b) => b.id === "b0000004");
  const request = generateRequest(schema, p, beat4);
  assert.deepEqual(request.spotlight_edges, ["to bring her daughter home", "to make her daughter stay"]);
  assert.deepEqual(request.spotlight_edges, planRequest(schema, p, beat4).spotlight_edges);
  assert.equal("spotlight" in request, false, "the spotlight itself still travels only in the plan request");
  assert.deepEqual(generateRequest(schema, p, { ...beat4, spotlight: "t1000002" }).spotlight_edges, [], "the Board tie's edge never changed");
  assert.deepEqual(generateRequest(schema, story(), beat2(story())).spotlight_edges, []);
  const first = opening();
  assert.deepEqual(generateRequest(schema, first, first.outline.beats[0]).spotlight_edges, []);
});
