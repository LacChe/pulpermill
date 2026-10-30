import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { schema } from "./helpers.mjs";
import { newProject, projectSnapshot, readProject } from "../../web/logic.js";
import {
  setPlanNote, planNoteFor, setChapterNote, chapterNoteFor, setEndNote, setEndProblems, endNoteFor, copyNote, putNote, removeNote,
  copyEndNote, putEndNote, pruneNotes,
} from "../../web/modelnotes.js";

const golden = JSON.parse(readFileSync(new URL("../shared/contract-vectors.json", import.meta.url), "utf8")).project_notes;
const stripIds = (value) => JSON.parse(JSON.stringify(value, (key, v) => (key === "id" ? undefined : v)));

test("the notes the page writes have exactly the fields of the shared example, which the Pydantic models also accept", () => {
  const project = newProject(schema);
  setPlanNote(project, "b0000001", { thinking: golden.plan_notes[0].thinking, retried: true });
  setChapterNote(project, "c0000001", {
    applied: [{ label: "Status", from: "suspects", to: "knows", section: "knowledge", was: 1, now: 2 }],
    warnings: [{ kind: "knowledge", text: golden.chapter_notes[0].warnings[0].text }],
    before: "The first version of the chapter.",
  });
  setChapterNote(project, "c0000002", {});
  setEndNote(project, { forced: [{ character: "Suvi", fields: ["age", "appearance"] }], dropped: ["history"], problems: 2, madeFrom: golden.end_note.made_from });
  assert.deepEqual(stripIds(project.plan_notes), stripIds(golden.plan_notes));
  assert.deepEqual(stripIds(project.chapter_notes), stripIds(golden.chapter_notes));
  assert.deepEqual(stripIds(project.end_note), stripIds(golden.end_note));
  for (const list of [project.plan_notes, project.chapter_notes]) for (const n of list) assert.match(n.id, /^[0-9a-f]{8}$/);
  assert.match(project.end_note.id, /^[0-9a-f]{8}$/);
});

test("notes read back the way the panels show them", () => {
  const project = newProject(schema);
  setChapterNote(project, "c1", { applied: [{ label: "Status", from: "", to: "knows" }], warnings: [{ text: "Careful." }], before: "Old." });
  assert.deepEqual(chapterNoteFor(project, "c1"), { applied: [{ label: "Status", from: "", to: "knows" }], warnings: [{ text: "Careful." }], before: "Old." });
  assert.equal(chapterNoteFor(project, "nope"), null);
  setPlanNote(project, "b1", { thinking: "Think.", retried: false });
  assert.deepEqual(planNoteFor(project, "b1"), { thinking: "Think.", retried: false });
  setEndNote(project, { forced: [{ character: "Ola", fields: ["name"] }], dropped: [], problems: 0 });
  assert.deepEqual(endNoteFor(project), { forced: [{ character: "Ola", fields: ["name"] }], dropped: [], problems: 0, madeFrom: null });
  setEndNote(project, { problems: 1, madeFrom: "0badf00d" });
  assert.equal(endNoteFor(project).madeFrom, "0badf00d");
  setEndProblems(project, 4);
  assert.deepEqual([project.end_note.problems, project.end_note.made_from], [4, "0badf00d"], "editing the copy changes only the count");
  assert.equal("dropped" in project.end_note, false, "nothing dropped, no key");
});

test("a note is replaced as a whole, one per target, and the key goes when the last note does", () => {
  const project = newProject(schema);
  assert.equal("plan_notes" in project, false, "a project with no notes has no keys");
  setPlanNote(project, "b1", { thinking: "one" });
  setPlanNote(project, "b2", { thinking: "two" });
  setPlanNote(project, "b1", { thinking: "again", retried: true });
  assert.equal(project.plan_notes.length, 2);
  assert.deepEqual(planNoteFor(project, "b1"), { thinking: "again", retried: true });
  removeNote(project, "plan", "b1");
  removeNote(project, "plan", "b2");
  assert.equal("plan_notes" in project, false);
});

test("Undo can put a note back exactly, or take it away again", () => {
  const project = newProject(schema);
  setChapterNote(project, "c1", { applied: [{ label: "A", from: "x", to: "y" }], warnings: [] });
  const was = copyNote(project, "chapter", "c1");
  setChapterNote(project, "c1", { applied: [], warnings: [{ text: "new" }], before: "old text" });
  putNote(project, "chapter", "c1", was);
  assert.deepEqual(project.chapter_notes, [was], "same ids, same words");
  const none = copyNote(project, "chapter", "c2");
  assert.equal(none, null);
  setChapterNote(project, "c2", {});
  putNote(project, "chapter", "c2", none);
  assert.equal(project.chapter_notes.length, 1);

  setEndNote(project, { problems: 1 });
  const end = copyEndNote(project);
  setEndNote(project, { problems: 5 });
  putEndNote(project, end);
  assert.equal(project.end_note.problems, 1);
  putEndNote(project, null);
  assert.equal("end_note" in project, false);
});

test("notes about something that is gone are dropped, and the rest are kept", () => {
  const project = { ...newProject(schema), outline: { beats: [{ id: "b1" }] }, chapters: [{ id: "c1", beat: "b1" }] };
  setPlanNote(project, "b1", { thinking: "kept" });
  setPlanNote(project, "b9", { thinking: "gone" });
  setChapterNote(project, "c1", {});
  setChapterNote(project, "c9", {});
  setEndNote(project, {});
  assert.equal(pruneNotes(project), true);
  assert.deepEqual(project.plan_notes.map((n) => n.beat), ["b1"]);
  assert.deepEqual(project.chapter_notes.map((n) => n.chapter), ["c1"]);
  assert.equal("end_note" in project, false, "no after-story copy, no end note");
  assert.equal(pruneNotes(project), false);
  project.after_story = {};
  setEndNote(project, {});
  assert.equal(pruneNotes(project), false);
});

test("notes that do not look right are ignored, never trusted", () => {
  const project = { ...newProject(schema), plan_notes: "oops", chapter_notes: [1, null, { chapter: "c1", changes: "x", warnings: [5, { text: "ok" }] }], end_note: [] };
  assert.equal(planNoteFor(project, "b1"), null);
  assert.deepEqual(chapterNoteFor(project, "c1"), { applied: [], warnings: [{ text: "ok" }] });
  assert.equal(endNoteFor(project), null);
  setPlanNote(project, "b1", { thinking: "fine" });
  assert.equal(project.plan_notes.length, 1);
});

test("notes are saved with the project and come back when it is opened", () => {
  const project = newProject(schema);
  setPlanNote(project, "b1", { thinking: "Think." });
  const text = projectSnapshot(schema, project);
  const read = readProject(text, schema);
  assert.equal(read.ok, true);
  assert.deepEqual(planNoteFor(read.project, "b1"), { thinking: "Think.", retried: false });
  assert.equal("chapter_notes" in JSON.parse(projectSnapshot(schema, newProject(schema))), false, "a project without notes is unchanged");
});
