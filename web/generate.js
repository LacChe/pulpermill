// Writing a chapter: everything the page works out in code around the one generate call. No DOM, so Node can test it.
//
// The model writes the chapter, then reads it twice (what happened, and how people and their entanglements moved).
// The page then turns the reply into records: it maps names to ids, applies the proposed changes to the live
// Entanglements, finds the changes that would overwrite a locked value, and builds everything the commit needs. Nothing
// here changes the project until commitChapter, which changes all of it at once.

import { envelope, settledProject, wordsToId, isFilled, validate, newId } from "./logic.js";
import { storyStarted } from "./gate.js";
import {
  chapterInfo, beatForChapter, beatBlockers, castProblem, planIsStale, entanglementsHash, currentGoal, openPlants,
  availableReveals, latestShifts, nameMap, fieldDefs, entanglementsFor, castCards, beatInWords, eventsInWords,
} from "./plan.js";

export const PREVIOUS_ENDING_CHARS = 1500;   // how much of the last chapter's end the model is shown
export const MAX_OPEN_PLANTS = 2;            // the schema's open_plants_max
export const MAX_SHIFTS = 5;                 // the schema's shifts_per_chapter_max

const copyOf = (value) => JSON.parse(JSON.stringify(value));
const asList = (value) => (Array.isArray(value) ? value : isFilled(value) ? [value] : []);
const squash = (text) => String(text ?? "").trim().replace(/\s+/g, " ").toLowerCase();

// ---- Can a chapter be written? ----------------------------------------------------------

// {ok, chapter, beat, stale} or {ok: false, reason, ...}. Reasons: not_started, done, no_beat, cast_<why>, beat_blocked
// (with `problems`), entanglements_blocked (with `problems`). A plan made from older Entanglements is `stale`: it warns, it never blocks.
export function generateGate(schema, project) {
  if (!storyStarted(project)) return { ok: false, reason: "not_started" };
  const info = chapterInfo(project);
  if (info.done) return { ok: false, reason: "done" };
  const beat = beatForChapter(project, info.next);
  if (!beat) return { ok: false, reason: "no_beat" };
  const why = castProblem(project, beat.cast);
  if (why) return { ok: false, reason: `cast_${why}` };
  const problems = beatBlockers(schema, project, beat);
  if (problems.length) return { ok: false, reason: "beat_blocked", problems };
  const settled = settledProject(schema, project);
  const held = validate(schema.cards.entanglements, settled.entanglements, settled, schema.common).problems.filter((p) => p.severity === "block");
  if (held.length) return { ok: false, reason: "entanglements_blocked", problems: held.map((p) => [p.message, p.fix].filter(Boolean).join(" ")) };
  return { ok: true, chapter: info.next, beat, stale: planIsStale(schema, project, beat) };
}

// ---- The request ----------------------------------------------------------------------------

// The end of the last chapter, cut at a paragraph or a sentence where that can be done without losing most of it.
export function previousEnding(project, limit = PREVIOUS_ENDING_CHARS) {
  const last = (project.chapters ?? []).at(-1)?.text;
  if (!isFilled(last)) return null;
  const text = last.trim();
  if (text.length <= limit) return text;
  const tail = text.slice(-limit);
  const cut = tail.search(/\n\s*\n|[.!?]["”']?\s/);
  return (cut > 0 && cut < limit / 2 ? tail.slice(cut).replace(/^[.!?"”'\s]+/, "") : tail).trim();
}

// The whole World as the writer sees it (canon, hidden truths included: they reach a character only through Knowledge), with
// each object's holder named.
function worldForWriter(schema, project, names) {
  const w = settledProject(schema, project).world;
  const held = new Map((project.entanglements?.holdings ?? []).map((h) => [h.holdee, names.get(h.held_by) ?? ""]));
  return { ...w, objects: w.objects.map((o) => ({ ...o, held_by: held.get(o.id) ?? "" })) };
}

export function generateRequest(schema, project, beat) {
  const info = chapterInfo(project);
  const names = nameMap(project);
  const settled = settledProject(schema, project);
  const setup = { ...copyOf(settled.setup), protagonist: names.get(project.setup?.protagonist) ?? "" };
  if (info.next > 1) { delete setup.normal; delete setup.disruption; }      // used once, in chapter 1
  return {
    ...envelope(schema, project, "generate"),
    chapter: info.next, chapter_count: info.count,
    style: copyOf(settled.style),
    setup,
    goal: currentGoal(project),
    cast: castCards(project, beat.cast).map(copyOf),
    world: worldForWriter(schema, project, names),
    entanglements: entanglementsFor(schema, project, beat.cast, names, { allPressures: false }),
    standing: latestShifts(project, beat.cast, names),
    earlier_events: eventsInWords(project, info.next - 1),
    previous_ending: previousEnding(project),
    beat: beatInWords(schema, project, beat, names),
    open_plants: openPlants(project).map(({ text, chapter }) => ({ text, chapter })),
    available_reveals: availableReveals(project).map(({ statement, truth, status }) => ({ statement, truth, status })),
  };
}

// What a result was made from. If it differs when the model answers, the writer edited something meanwhile, and the
// chapter would be written about a state that is gone, so it is thrown away.
export function inputsKey(schema, project, beat) {
  return JSON.stringify([entanglementsHash(schema, project), beat, (project.chapters ?? []).length]);
}

// ---- Turning the reply into records ----------------------------------------------------------

function behaviorMatch(project, castIds, words) {
  const want = squash(words);
  const hits = [];
  for (const id of castIds) {
    const person = (project.characters ?? []).find((c) => c.id === id);
    for (const b of person?.behaviors ?? []) if (squash(b.state) === want) hits.push(b.id);
  }
  return hits.length === 1 ? { id: hits[0] } : hits.length ? { several: true } : { none: true };
}

// A lock covers a change when it names the Entanglements card (or the card and nothing narrower), or the list, the item, or the box.
const lockCovers = (lock, change) => lock.card === "entanglements" && !lock.owner
  && (!lock.field || lock.field === change.section) && (!lock.item || lock.item === change.item) && (!lock.part || lock.part === change.field);

// A value as words for the review: links by name.
function show(def, value, names) {
  const one = (v) => names.get(v) ?? String(v ?? "");
  if (Array.isArray(value)) return value.map(one).join(", ");
  const option = def.options?.find((o) => o.value === value);
  if (option) return option.label ?? option.value;
  return def.ref ? one(value) : String(value ?? "");
}

function resolveChangeValue(def, change, project) {
  if (def.ref) {
    const words = def.input === "select-multiple" ? (Array.isArray(change.value) ? change.value : [change.value]) : change.value;
    if (def.input === "select-multiple") {
      const ids = [];
      for (const w of words) {
        const found = wordsToId(project, def.ref, w);
        if (!found.id) return { why: `“${w}” matches nothing in the cards` };
        ids.push(found.id);
      }
      return ids.length ? { value: ids } : { why: "an empty list" };
    }
    if (typeof words !== "string") return { why: "not a name" };
    const found = wordsToId(project, def.ref, words);
    return found.id ? { value: found.id } : { why: `“${words}” matches ${found.several ? "more than one entry" : "nothing"} in the cards` };
  }
  if (def.options?.length) {
    return def.options.some((o) => o.value === change.value) ? { value: change.value } : { why: `“${change.value}” is not one of the choices` };
  }
  return typeof change.value === "string" && change.value.trim() ? { value: change.value.trim() } : { why: "no words" };
}

// Applies the proposed changes to a copy of the Entanglements. A change is dropped (and says why) when its item does not exist,
// its field is not one that moves, its value does not match the cards, or the result would break a blocking rule.
// Returns {entanglements, applied, dropped, locked}. With overwriteLocked false, changes to locked values are dropped too.
function applyChanges(schema, project, changes, { overwriteLocked }) {
  const names = nameMap(project);
  const before = settledProject(schema, project);
  const next = copyOf(before.entanglements);
  const applied = [];
  const dropped = [];
  const locks = project.locks ?? [];
  for (const change of changes) {
    const item = next[change.section]?.find((i) => i.id === change.item);
    const def = fieldDefs(schema, "entanglements", change.section).find((d) => d.key === change.field);
    const drop = (why) => dropped.push({ ...change, why });
    if (!item) { drop("there is no such entry"); continue; }
    if (!def?.changes) { drop("that field does not change"); continue; }
    const got = resolveChangeValue(def, change, project);
    if (got.why) { drop(got.why); continue; }
    if (JSON.stringify(item[change.field]) === JSON.stringify(got.value)) continue;       // no change at all
    const covering = locks.filter((l) => lockCovers(l, change));
    if (covering.length && !overwriteLocked) { drop("it is locked"); continue; }
    applied.push({
      section: change.section, item: change.item, field: change.field, label: def.label ?? def.key,
      was: item[change.field], now: got.value,
      from: show(def, item[change.field], names), to: show(def, got.value, names),
      locks: covering.map((l) => l.id),
    });
    item[change.field] = got.value;
  }
  // A change that would break a blocking rule on its entry is undone, entry by entry.
  const trial = { ...before, entanglements: next };
  const old = new Set(validate(schema.cards.entanglements, before.entanglements, before, schema.common).problems.filter((p) => p.severity === "block").map((p) => `${p.item}|${p.message}`));
  const fresh = validate(schema.cards.entanglements, next, trial, schema.common).problems
    .filter((p) => p.severity === "block" && p.item && !old.has(`${p.item}|${p.message}`));
  for (const bad of new Set(fresh.map((p) => p.item))) {
    const why = fresh.find((p) => p.item === bad).message;
    for (const a of applied.filter((x) => x.item === bad)) {
      const section = next[a.section].find((i) => i.id === bad);
      section[a.field] = a.was;
      dropped.push({ section: a.section, item: a.item, field: a.field, value: a.to, why: `it would break a rule: ${why}` });
    }
  }
  const kept = applied.filter((a) => !fresh.some((p) => p.item === a.item));
  return { entanglements: next, applied: kept, dropped, locked: kept.filter((a) => a.locks.length) };
}

// Everything one chapter adds to the project, worked out and checked, with nothing changed.
//   read   the checked reply (readGenerateReply)
//   opts.overwriteLocked  whether changes to locked values stay in (the writer's answer to the confirmation)
// Returns {ok: true, chapter, events, shifts, history, entanglements, changes: {applied, dropped, locked}, warnings, unlock}.
export function applyGenerated(schema, project, beat, read, { overwriteLocked = true } = {}) {
  const warnings = [];
  const e = read.events;
  const cast = asList(beat.cast);
  const entries = project.summary_events?.entries ?? [];
  const taken = [];
  const fresh = () => { const id = newId([...taken, ...entries.map((x) => x.id), ...(project.summary_shifts?.shifts ?? []).map((x) => x.id),
    ...(project.chapters ?? []).map((x) => x.id), ...(project.entanglements_history?.states ?? []).map((x) => x.id)]); taken.push(id); return id; };

  // Names to ids. What matches nothing is left out and mentioned, never guessed.
  const link = (sources, words, what) => {
    const found = wordsToId(project, sources, words);
    if (!found.id) warnings.push({ kind: "unmatched", text: `${what} “${words}” matches ${found.several ? "more than one entry" : "nothing"}, so it was left out.` });
    return found.id ?? null;
  };
  const plants = openPlants(project);
  const paid = [];
  for (const words of e.paid_off) {
    const plant = plants.find((p) => squash(p.text) === squash(words));
    if (plant) paid.push(plant.id); else warnings.push({ kind: "unmatched", text: `The payoff “${words}” is not an open plant, so it was left out.` });
  }
  const availableIds = new Set(availableReveals(project).map((r) => r.id));
  const reveals = e.reveals_landed.map((w) => link(["world.rules"], w, "The reveal")).filter((id) => {
    if (id && !availableIds.has(id)) warnings.push({ kind: "unmatched", text: "A reveal that had already come to light was named again, so it was left out." });
    return id && availableIds.has(id);
  });
  const behaviors = [];
  for (const w of e.behaviors_seen) {
    const found = behaviorMatch(project, cast, w);
    if (found.id) behaviors.push(found.id); else warnings.push({ kind: "unmatched", text: `The behavior “${w}” matches ${found.several ? "more than one" : "no"} behavior of the cast, so it was left out.` });
  }
  const things = e.things_seen.map((w) => link(["world.objects"], w, "The thing")).filter(Boolean);

  // A chapter plants at most one thing, and at most two plants stay open at once.
  let planted = e.planted;
  if (planted && plants.length - paid.length >= MAX_OPEN_PLANTS) {
    warnings.push({ kind: "plant", text: `Two plants were already open, so what this chapter planted (“${planted}”) is not counted as a plant.` });
    planted = null;
  }
  const event = {
    id: fresh(), beat: beat.id, happened: e.happened, changed: e.changed ?? "", planted: planted ?? "",
    paid_off: paid, reveals_landed: reveals, behaviors_seen: behaviors, things_seen: things, goal_landed: e.goal_landed,
  };
  if (beat.goal_change && !e.goal_landed) warnings.push({ kind: "goal", text: "The beat planned a change to the goal, but the chapter did not carry it out. It stays pending." });
  if (beat.reveal_rule && !reveals.includes(beat.reveal_rule)) warnings.push({ kind: "reveal", text: "The beat planned a reveal that the chapter did not make, so it is still available." });

  // Who moved: only people in the chapter, once each.
  const shifts = [];
  for (const s of read.shifts) {
    const id = link(["characters"], s.character, "The character");
    if (!id) continue;
    if (!cast.includes(id)) { warnings.push({ kind: "unmatched", text: `“${s.character}” moved, but was not in this chapter, so it was left out.` }); continue; }
    if (shifts.some((x) => x.character === id)) { warnings.push({ kind: "unmatched", text: `“${s.character}” appeared twice in the shifts, so the second was left out.` }); continue; }
    if (shifts.length >= MAX_SHIFTS) continue;
    const { character, ...texts } = s;
    shifts.push({ id: fresh(), beat: beat.id, character: id, ...texts });
  }

  const changes = applyChanges(schema, project, read.changes, { overwriteLocked });
  if (reveals.length && !changes.applied.some((a) => a.section === "knowledge")) {
    warnings.push({ kind: "knowledge", text: "A reveal landed, but nobody's knowledge changed. Check the Knowledge list in Entanglements." });
  }
  for (const d of changes.dropped) warnings.push({ kind: "dropped", text: `A proposed change to ${d.field} was left out: ${d.why}.` });

  const settled = settledProject(schema, project);
  return {
    ok: true,
    chapter: { id: fresh(), beat: beat.id, text: read.chapter_text.trim() },
    events: event,
    shifts,
    history: { id: fresh(), beat: beat.id, state: copyOf(settled.entanglements) },
    entanglements: changes.entanglements,
    changes: { applied: changes.applied, dropped: changes.dropped, locked: changes.locked },
    warnings,
    unlock: overwriteLocked ? [...new Set(changes.locked.flatMap((a) => a.locks))] : [],
  };
}

// Puts a chapter and everything that goes with it into the project, all at once: the chapter, its events and shifts, the
// Entanglements it was written from, and the new Entanglements. Locks that stood in the way of an overwrite the writer
// agreed to are taken off. The outcome is used up: build a new one rather than committing it twice.
export function commitChapter(project, outcome) {
  const events = project.summary_events ?? { entries: [] };
  const shifts = project.summary_shifts ?? { shifts: [] };
  const history = project.entanglements_history ?? { states: [] };
  const chapters = project.chapters ?? [];
  const locks = (project.locks ?? []).filter((l) => !outcome.unlock.includes(l.id));
  events.entries = [...(events.entries ?? []), outcome.events];
  shifts.shifts = [...(shifts.shifts ?? []), ...outcome.shifts];
  history.states = [...(history.states ?? []), outcome.history];
  Object.assign(project, {
    summary_events: events, summary_shifts: shifts, entanglements_history: history,
    chapters: [...chapters, outcome.chapter], entanglements: outcome.entanglements, locks,
  });
  return project;
}
