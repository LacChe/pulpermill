// Writing a chapter: everything the page works out in code around the one generate call. No DOM, so Node can test it.
//
// The model writes the chapter, then says what happened and what changed (events) and proposes the shifts: sparse copies of
// the Characters, World and Entanglements cards (P0, A1 to A3). The page turns the reply into records: it maps the words in a
// patch to ids, gives each added item its id, checks every patch against its card (effective.js validatePatch) and keeps what
// is valid. Nothing here changes the project until commitChapter, which changes all of it at once (A8).

import { envelope, wordsToId, isFilled, newId, lookupLabel } from "./logic.js";
import { effectiveProject, validatePatch, applyPatch } from "./effective.js";
import { storyStarted, cardLocked } from "./gate.js";
import { watch } from "./undo.js";
import { msg, joinList } from "./text.js";
import {
  chapterInfo, beatForChapter, beatBlockers, castProblem, planIsStale, planInputsHash, scene, beatInWords, eventsInWords, chapterOfBeat,
} from "./plan.js";

export const PREVIOUS_ENDING_CHARS = 1500;   // how much of the last chapter's end the model is shown

const copyOf = (value) => JSON.parse(JSON.stringify(value));
const asList = (value) => (Array.isArray(value) ? value : isFilled(value) ? [value] : []);

// The parts of the project a chapter and its records live in: what an Undo of Generate or Write again puts back.
const CHAPTER_PARTS = ["chapters", "summary_events", "shifts"];

// ---- Can a chapter be written? ----------------------------------------------------------

// {ok, chapter, beat, stale} or {ok: false, reason, ...}. Reasons: not_started, done, no_beat, cast_<why>, beat_blocked (with
// `problems`). A plan made from inputs that have changed is `stale`: it warns, it never blocks.
export function generateGate(schema, project) {
  if (!storyStarted(project)) return { ok: false, reason: "not_started" };
  const info = chapterInfo(project);
  if (info.done) return { ok: false, reason: "done" };
  const beat = beatForChapter(project, info.next);
  if (!beat) return { ok: false, reason: "no_beat" };
  const eff = effectiveProject(project, info.next);
  const why = castProblem(eff, beat.cast, beat.spotlight);
  if (why) return { ok: false, reason: `cast_${why}` };
  const problems = beatBlockers(schema, project, beat);
  if (problems.length) return { ok: false, reason: "beat_blocked", problems };
  return { ok: true, chapter: info.next, beat, stale: planIsStale(project, beat) };
}

// ---- The request ----------------------------------------------------------------------------

// The end of the chapter before `chapter` (or of the last one written), cut at a paragraph or a sentence where that can be
// done without losing most of it. Null for chapter 1.
export function previousEnding(project, limit = PREVIOUS_ENDING_CHARS, chapter = null) {
  const written = project.chapters ?? [];
  const last = chapter === null ? written.at(-1) : written.find((c) => chapterOfBeat(project, c.beat) === chapter - 1);
  if (!isFilled(last?.text)) return null;
  const text = last.text.trim();
  if (text.length <= limit) return text;
  const tail = text.slice(-limit);
  const cut = tail.search(/\n\s*\n|[.!?]["”']?\s/);
  return (cut > 0 && cut < limit / 2 ? tail.slice(cut).replace(/^[.!?"”'\s]+/, "") : tail).trim();
}

// Write the chapter of `beat`. The cards are the effective ones going into that chapter, and only the opening chapter is sent the
// opening (Setup's normal and disruption, and the protagonist inside it: the protagonist travels at the top level).
export function generateRequest(schema, project, beat) {
  const chapter = Number(beat.chapter);
  const eff = effectiveProject(project, chapter);
  const setup = copyOf(eff.setup ?? {});
  if (chapter > 1) { delete setup.protagonist; delete setup.normal; delete setup.disruption; }
  return {
    ...envelope(schema, project, "generate"),
    chapter, chapter_count: chapterInfo(project).count,
    style: copyOf(eff.style ?? {}),
    setup,
    protagonist: eff.setup?.protagonist ?? "",
    ...scene(eff, chapter, beat.cast, { where: beat.where }),
    earlier_events: eventsInWords(eff, chapter - 1),
    previous_ending: chapter > 1 ? previousEnding(project, PREVIOUS_ENDING_CHARS, chapter) : null,
    beat: beatInWords(eff, beat),
  };
}

// What a result was made from. If it differs when the model answers, the writer edited something meanwhile, and the
// chapter would be written about a state that is gone, so it is thrown away.
export function inputsKey(schema, project, beat) {
  return JSON.stringify([planInputsHash(project, beat), beat, (project.chapters ?? []).length, (project.shifts?.entries ?? []).length]);
}

// ---- Turning the reply into records ----------------------------------------------------------

// Every id the project holds anywhere, so a new id is never one already in use.
function usedIds(value, out = new Set()) {
  if (Array.isArray(value)) for (const v of value) usedIds(v, out);
  else if (value && typeof value === "object") {
    if (typeof value.id === "string") out.add(value.id);
    for (const v of Object.values(value)) usedIds(v, out);
  }
  return out;
}

const itemFields = (schema, card, key) => schema.cards[card]?.fields.find((f) => f.key === key)?.item_fields ?? [];

// What one value reads as: a link by the name it points at, a list joined, anything else as it is.
function show(project, def, value) {
  if (Array.isArray(value)) return joinList(value.map((v) => (def?.ref ? lookupLabel(project, def, v) : String(v))));
  if (value === null || value === undefined || value === "") return "";
  return def?.ref ? lookupLabel(project, def, value) : String(value);
}

// A list item in a few words: its first two filled values, links by name.
function itemWords(project, defs, item) {
  const parts = defs.filter((d) => d.key !== "id" && isFilled(item[d.key])).slice(0, 2).map((d) => show(project, d, item[d.key]));
  return parts.join(" · ");
}

// The words in an operation's values turned into ids, against the cards as they stand. Returns {values} or {why}.
function mapValues(schema, project, card, key, values) {
  const defs = itemFields(schema, card, key);
  const out = {};
  for (const [name, value] of Object.entries(values)) {
    const def = defs.find((d) => d.key === name);
    if (def?.ref && typeof value === "string") {
      const found = wordsToId(project, def.ref, value);
      if (!found.id) return { why: msg(found.several ? "records.whyMatchesSeveral" : "records.whyMatchesNothing", { words: value }) };
      out[name] = found.id;
    } else out[name] = value;
  }
  return { values: out };
}

// The shifts the model proposed, as the entries to store. `project` is the effective project going into the chapter.
// Returns {entries, warnings, changes}: entries are {id, beat, card, target, patch} in order Characters, World, Entanglements;
// changes are the lines the chapter note shows, {label, before, after}.
export function landShifts(schema, project, beat, proposed, taken = usedIds(project)) {
  const eff = effectiveProject(project, Number(beat.chapter));
  let working = { characters: copyOf(eff.characters ?? []), world: copyOf(eff.world ?? {}), entanglements: copyOf(eff.entanglements ?? {}) };
  const cast = asList(beat.cast);
  const warnings = [];
  const entries = [];
  const changes = [];
  const seen = new Set();
  const max = schema.max_shifts_per_chapter ?? 7;
  const order = { characters: 0, world: 1, entanglements: 2 };
  const nameOf = (id) => (eff.characters ?? []).find((c) => c.id === id)?.name ?? id;
  const sorted = proposed.map((s, i) => ({ s, i })).sort((a, b) => order[a.s.card] - order[b.s.card] || a.i - b.i).map((x) => x.s);
  for (const shift of sorted) {
    const what = shift.card === "characters" ? nameOf(shift.target) : schema.cards[shift.card].label;
    const leave = (why) => warnings.push({ kind: "shift", text: msg("records.shiftLeftOut", { what, why }) });
    const key = `${shift.card}|${shift.target ?? ""}`;
    if (shift.card === "characters") {
      if (!(working.characters ?? []).some((c) => c.id === shift.target)) { leave(msg("records.whyNoCharacter")); continue; }
      if (!cast.includes(shift.target)) { warnings.push({ kind: "shift", text: msg("records.notInChapter", { name: what }) }); continue; }
    }
    if (seen.has(key)) { warnings.push({ kind: "shift", text: msg("records.shiftTwice", { what }) }); continue; }
    if (entries.length >= max) { warnings.push({ kind: "shift", text: msg("records.shiftsTooMany", { max }) }); break; }
    // Turn the words into ids and give each addition its id; an operation that cannot be made is left out.
    const card = shift.card === "characters" ? working.characters.find((c) => c.id === shift.target) : working[shift.card];
    const patch = {};
    const lost = [];
    for (const [field, value] of Object.entries(shift.patch)) {
      if (!Array.isArray(value)) { patch[field] = value; continue; }
      const ops = [];
      for (const op of value) {
        const items = Array.isArray(card?.[field]) ? card[field] : [];
        if (op.op !== "add" && !items.some((i) => i.id === op.id)) { lost.push(msg("records.whyNoItem", { op: op.op })); continue; }
        if (op.op === "remove") { ops.push({ op: "remove", id: op.id }); continue; }
        const mapped = mapValues(schema, working, shift.card, field, op.values);
        if (mapped.why) { lost.push(mapped.why); continue; }
        if (op.op === "add") { const id = newId([...taken]); taken.add(id); ops.push({ op: "add", id, values: mapped.values }); }
        else ops.push({ op: "replace", id: op.id, values: mapped.values });
      }
      if (ops.length) patch[field] = ops;
    }
    if (!Object.keys(patch).length) { leave(lost[0] ?? msg("records.whyEmpty")); continue; }
    const problems = validatePatch(schema, shift.card, patch);
    if (problems.length) { leave(problems[0].message); continue; }
    for (const why of new Set(lost)) warnings.push({ kind: "shift", text: msg("records.shiftPartLeftOut", { what, why }) });
    seen.add(key);
    entries.push({ id: newId([...taken]), beat: beat.id, card: shift.card, target: shift.target ?? null, patch });
    taken.add(entries.at(-1).id);
    // The lines the chapter note shows: what each field was and what it is now.
    const defs = schema.cards[shift.card].fields;
    for (const [field, value] of Object.entries(patch)) {
      const def = defs.find((d) => d.key === field);
      const label = shift.card === "characters" ? `${what}: ${def.label}` : `${schema.cards[shift.card].label}: ${def.label}`;
      if (!Array.isArray(value)) { changes.push({ label, before: show(project, def, card[field]), after: show(project, def, value) }); continue; }
      const subs = def.item_fields ?? [];
      for (const op of value) {
        const was = (card[field] ?? []).find((i) => i.id === op.id);
        if (op.op === "add") changes.push({ label, before: "", after: itemWords(working, subs, op.values) });
        else if (op.op === "remove") changes.push({ label, before: itemWords(working, subs, was), after: "" });
        else for (const [name, v] of Object.entries(op.values)) {
          const sub = subs.find((d) => d.key === name);
          if (JSON.stringify(was[name]) !== JSON.stringify(v)) changes.push({ label: `${label} (${itemWords(working, subs, was)}): ${sub.label}`, before: show(working, sub, was[name]), after: show(working, sub, v) });
        }
      }
    }
    // Later entries see what this one made (a place added to the World can be held in the same chapter).
    if (shift.card === "characters") working.characters = working.characters.map((c) => (c.id === shift.target ? applyPatch(c, patch) : c));
    else working[shift.card] = applyPatch(working[shift.card], patch);
  }
  return { entries, warnings, changes };
}

// Everything one chapter adds to the project, worked out and checked, with nothing changed.
//   read   the checked reply (readGenerateReply)
// Returns {ok: true, chapter, events, shifts, changes, warnings}.
export function applyGenerated(schema, project, beat, read) {
  const taken = usedIds(project);
  const fresh = () => { const id = newId([...taken]); taken.add(id); return id; };
  const landed = landShifts(schema, project, beat, read.shifts, taken);
  return {
    ok: true,
    chapter: { id: fresh(), beat: beat.id, text: read.chapter_text.trim() },
    events: { id: fresh(), beat: beat.id, happened: read.events.happened, changed: read.events.changed ?? "" },
    shifts: landed.entries,
    changes: landed.changes,
    warnings: landed.warnings,
  };
}

// Puts a chapter and everything that goes with it into the project, all at once: the chapter, its events and its shifts. The
// outcome is used up: build a new one rather than committing it twice. Returns {project, undo}: undo takes the chapter and
// everything with it out again and answers true, or answers false and changes nothing when any of those parts has been changed since.
export function commitChapter(project, outcome) {
  const undo = watch(project, CHAPTER_PARTS);
  const events = project.summary_events ?? { entries: [] };
  const shifts = project.shifts ?? { entries: [] };
  events.entries = [...(events.entries ?? []), outcome.events];
  shifts.entries = [...(shifts.entries ?? []), ...outcome.shifts];
  Object.assign(project, { summary_events: events, shifts, chapters: [...(project.chapters ?? []), outcome.chapter] });
  undo.settle();
  return { project, undo: () => undo.undo() };
}

// ---- Writing a chapter again ---------------------------------------------------------------------
// Regenerating chapter N goes back to the state going into N: only the records of the chapters before it count. It reuses N's
// beat. The old chapter stays until the new one commits (a failed or stopped call changes nothing). The shifts of N and of every
// later chapter are dropped when it commits, and later chapters stay where they are, with their beats marked stale.

const chapterNumber = (project, beatId) => Number((project.outline?.beats ?? []).find((b) => b.id === beatId)?.chapter) || 0;

// The project as it stood when chapter `number` was about to be written: no chapter or record from `number` on.
export function projectBefore(project, number) {
  const trial = copyOf(project);
  const early = (x) => chapterNumber(project, x.beat) < number;
  trial.chapters = (project.chapters ?? []).filter(early).map(copyOf);
  trial.summary_events = { ...(project.summary_events ?? {}), entries: (project.summary_events?.entries ?? []).filter(early).map(copyOf) };
  trial.shifts = { ...(project.shifts ?? {}), entries: (project.shifts?.entries ?? []).filter(early).map(copyOf) };
  return trial;
}

// {ok, number, beat, trial, chapter, later} or {ok: false, reason}: not_started, outline_locked, no_chapter, cast_<why>, beat_blocked (with
// `problems`). `later` is how many chapters come after this one.
export function regenerateGate(schema, project, number) {
  if (!storyStarted(project)) return { ok: false, reason: "not_started" };
  if (cardLocked(project, "outline")) return { ok: false, reason: "outline_locked" };    // it marks the later beats stale
  const written = project.chapters ?? [];
  const chapter = written.find((c) => chapterNumber(project, c.beat) === number);
  if (!chapter) return { ok: false, reason: "no_chapter" };
  const trial = projectBefore(project, number);
  const beat = trial.outline.beats.find((b) => b.id === chapter.beat);
  const why = castProblem(effectiveProject(trial, number), beat.cast, beat.spotlight);
  if (why) return { ok: false, reason: `cast_${why}` };
  const problems = beatBlockers(schema, trial, beat);
  if (problems.length) return { ok: false, reason: "beat_blocked", problems };
  return { ok: true, number, beat, trial, chapter, later: written.length - number };
}

// What the page checks when the model answers: nothing the new chapter depends on was edited meanwhile.
export function regenerateKey(schema, project, number) {
  const chapter = (project.chapters ?? []).find((c) => chapterNumber(project, c.beat) === number);
  return JSON.stringify([project.outline?.beats ?? [], (project.chapters ?? []).map((c) => c.id), chapter?.text ?? null, project.shifts?.entries ?? []]);
}

// The records of a regenerated chapter, from the model's reply. The chapter and its events keep their ids (later records point at
// them); the shifts get new ones. Warns about the later chapters, which were written from the old version.
export function applyRegenerated(schema, project, ctx, read) {
  const { trial, beat, number } = ctx;
  const out = applyGenerated(schema, trial, beat, read);
  const old = {
    chapter: (project.chapters ?? []).find((c) => c.beat === beat.id),
    events: (project.summary_events?.entries ?? []).find((e) => e.beat === beat.id),
  };
  out.chapter.id = old.chapter.id;
  out.events.id = old.events.id;
  out.before = old.chapter.text;
  if ((project.chapters ?? []).length > number) out.warnings.push({ kind: "later", text: msg("records.laterStale", { n: project.chapters.length - number }) });
  return out;
}

// Replaces chapter N's text and events, drops the shifts of N and of every later chapter and puts the new ones in, and marks every
// later beat stale, all at once. Returns an undo that puts everything back as it was, unless the writer has changed any of it since.
export function commitRegenerated(project, outcome) {
  const undo = watch(project, [...CHAPTER_PARTS, "outline"]);
  const beat = outcome.chapter.beat;
  const number = chapterNumber(project, beat);
  const stale = (project.outline.beats ?? []).map((b) => (Number(b.chapter) > number ? { ...b, stale: true } : b));
  Object.assign(project, {
    chapters: project.chapters.map((c) => (c.beat === beat ? outcome.chapter : c)),
    summary_events: { ...project.summary_events, entries: project.summary_events.entries.map((e) => (e.beat === beat ? outcome.events : e)) },
    shifts: { ...project.shifts, entries: [...(project.shifts?.entries ?? []).filter((s) => chapterNumber(project, s.beat) < number), ...outcome.shifts] },
    outline: { ...project.outline, beats: stale },
  });
  undo.settle();
  return { undo: () => undo.undo() };      // true, or false (and nothing changed) when any of those parts was changed since
}
