// What the model said, kept in the project so the writer can read it again after reopening the file: how it thought about a
// chapter (plan notes), what the page showed after a chapter was made (chapter notes), and what it noticed at the end of
// the story (the end note). No DOM, so Node can test it. The shapes are the Pydantic models PlanNote, ChapterNote and
// EndNote in pulpermill/schema/project.py, and web/tests/contract-vectors.json holds an example both sides check.
//
// These are display records. They are never sent to a model, and nobody edits them. A note is replaced as a whole when the
// thing it is about is made again, and is dropped when that thing is gone (pruneNotes). A project with no notes has none
// of these keys. A note that does not look right is ignored rather than trusted.
import { newId } from "./logic.js";

const copy = (value) => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)));
const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const KINDS = { plan: { key: "plan_notes", link: "beat" }, chapter: { key: "chapter_notes", link: "chapter" } };
const listOf = (project, key) => (Array.isArray(project[key]) ? project[key].filter(isObject) : []);
const lines = (value) => (Array.isArray(value) ? value.filter(isObject) : []);
const words = (text) => String(text ?? "").split(/,\s*/).filter(Boolean);

// Put `note` (a raw stored note, or null to remove) in place of whatever the project holds for that target.
function put(project, kind, targetId, note) {
  const { key, link } = KINDS[kind];
  const kept = listOf(project, key).filter((n) => n[link] !== targetId);
  if (note) kept.push(note);
  if (kept.length) project[key] = kept; else delete project[key];
}

const raw = (project, kind, targetId) => listOf(project, KINDS[kind].key).find((n) => n[KINDS[kind].link] === targetId) ?? null;
const taken = (project, kind) => listOf(project, KINDS[kind].key).map((n) => n.id);

// For Undo: a copy of the stored note as it is now (or null), and putting it back.
export function copyNote(project, kind, targetId) { return copy(raw(project, kind, targetId)); }
export function putNote(project, kind, targetId, note) { put(project, kind, targetId, copy(note)); }
export function removeNote(project, kind, targetId) { put(project, kind, targetId, null); }

// ---- Plan notes: {thinking, retried} ---------------------------------------------------------------------------------
export function setPlanNote(project, beatId, { thinking, retried }) {
  put(project, "plan", beatId, { id: newId(taken(project, "plan")), beat: beatId, thinking: String(thinking ?? ""), retried: Boolean(retried) });
}

export function planNoteFor(project, beatId) {
  const note = raw(project, "plan", beatId);
  return note ? { thinking: String(note.thinking ?? ""), retried: note.retried === true } : null;
}

// ---- Chapter notes: {applied: [{label, from, to}], warnings: [{text}], before?} ----------------------------------------
export function setChapterNote(project, chapterId, { applied = [], warnings = [], before }) {
  const ids = [];
  const next = () => { const id = newId(ids); ids.push(id); return id; };
  const note = { id: newId(taken(project, "chapter")), chapter: chapterId };
  note.changes = applied.map((a) => ({ id: next(), label: String(a.label ?? ""), before: String(a.from ?? ""), after: String(a.to ?? "") }));
  note.warnings = warnings.map((w) => ({ id: next(), text: String(w.text ?? "") }));
  if (typeof before === "string") note.before = before;
  put(project, "chapter", chapterId, note);
}

export function chapterNoteFor(project, chapterId) {
  const note = raw(project, "chapter", chapterId);
  if (!note) return null;
  const out = {
    applied: lines(note.changes).map((c) => ({ label: String(c.label ?? ""), from: String(c.before ?? ""), to: String(c.after ?? "") })),
    warnings: lines(note.warnings).map((w) => ({ text: String(w.text ?? "") })),
  };
  if (typeof note.before === "string") out.before = note.before;
  return out;
}

// ---- The end note: {forced: [{character, fields: [key]}], dropped: [key], problems} -------------------------------------
export function setEndNote(project, { forced = [], dropped = [], problems = 0, madeFrom }) {
  const ids = [];
  const next = () => { const id = newId(ids); ids.push(id); return id; };
  const note = {
    id: newId(), forced: forced.map((f) => ({ id: next(), character: String(f.character ?? ""), fields: (f.fields ?? []).join(", ") })),
    problems: Number(problems) || 0,
  };
  if (dropped.length) note.dropped = dropped.join(", ");
  if (typeof madeFrom === "string" && madeFrom) note.made_from = madeFrom;
  project.end_note = note;
}

// The writer edited the copy: only the count of problems changes, the rest of what the model said stays.
export function setEndProblems(project, problems) {
  if (isObject(project.end_note)) project.end_note.problems = Number(problems) || 0;
}

export function endNoteFor(project) {
  const note = project.end_note;
  if (!isObject(note)) return null;
  return {
    forced: lines(note.forced).map((f) => ({ character: String(f.character ?? ""), fields: words(f.fields) })),
    dropped: words(note.dropped),
    problems: Number(note.problems) || 0,
    madeFrom: typeof note.made_from === "string" && note.made_from ? note.made_from : null,
  };
}

export function copyEndNote(project) { return isObject(project.end_note) ? copy(project.end_note) : null; }
export function putEndNote(project, note) { if (note) project.end_note = copy(note); else delete project.end_note; }

// ---- Tidying ------------------------------------------------------------------------------------------------------
// Drops notes about something that is gone: a beat that was deleted, a chapter that does not exist, an end note with no
// after-story copy. Returns true when it removed anything.
export function pruneNotes(project) {
  let changed = false;
  const beats = new Set((project.outline?.beats ?? []).map((b) => b.id));
  const chapters = new Set((project.chapters ?? []).map((c) => c.id));
  for (const [kind, ids] of [["plan", beats], ["chapter", chapters]]) {
    const { key, link } = KINDS[kind];
    if (!(key in project)) continue;
    const all = listOf(project, key);
    const kept = all.filter((n) => ids.has(n[link]));
    if (kept.length !== (Array.isArray(project[key]) ? project[key].length : 0)) changed = true;
    if (kept.length) project[key] = kept; else delete project[key];
  }
  if ("end_note" in project && !(isObject(project.end_note) && project.after_story)) { delete project.end_note; changed = true; }
  return changed;
}
