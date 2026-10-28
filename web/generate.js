// Writing a chapter: everything the page works out in code around the one generate call. No DOM, so Node can test it.
//
// The model writes the chapter, then reads it twice (what happened, and how people and their entanglements moved).
// The page then turns the reply into records: it maps names to ids, applies the proposed changes to the live
// Entanglements, finds the changes that would overwrite a locked value, and builds everything the commit needs. Nothing
// here changes the project until commitChapter, which changes all of it at once.

import { envelope, settledProject, wordsToId, isFilled, validate, newId } from "./logic.js";
import { storyStarted, cardLocked } from "./gate.js";
import { watch } from "./undo.js";
import { msg, joinList } from "./text.js";
import {
  chapterInfo, beatForChapter, beatBlockers, castProblem, planIsStale, entanglementsHash, currentGoal, goalArc, openPlants,
  availableReveals, latestShifts, nameMap, fieldDefs, entanglementsFor, castCards, beatInWords, eventsInWords, rotating,
} from "./plan.js";

export const PREVIOUS_ENDING_CHARS = 1500;   // how much of the last chapter's end the model is shown
export const MAX_OPEN_PLANTS = 2;            // the schema's open_plants_max
const STANDINGS = ["knows", "suspects", "misled"];   // the lists on a Knowledge entry; a person is in one of them
export const MAX_SHIFTS = 5;                 // the schema's shifts_per_chapter_max

const copyOf = (value) => JSON.parse(JSON.stringify(value));

// The parts of the project a chapter and its records live in: what an Undo of Generate or Write again puts back.
const CHAPTER_PARTS = ["chapters", "summary_events", "summary_shifts", "entanglements_history", "entanglements", "locks"];
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
  if (held.length) return { ok: false, reason: "entanglements_blocked", problems: held.map((p) => joinList([p.message, p.fix].filter(Boolean), "sentence")) };
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
function worldForWriter(schema, project, names, beat) {
  const w = settledProject(schema, project).world;
  const held = new Map((project.entanglements?.holdings ?? []).map((h) => [h.holdee, names.get(h.held_by) ?? ""]));
  const sent = rotating(project, w, beat);       // the places and things the beat names, then the least used
  return { ...w, places: sent.places, objects: sent.objects.map((o) => ({ ...o, held_by: held.get(o.id) ?? "" })) };
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
    goal_state: goalArc(project).state === "active" ? null : goalArc(project).state,
    cast: castCards(project, beat.cast).map(copyOf),
    world: worldForWriter(schema, project, names, beat),
    entanglements: entanglementsFor(schema, project, beat.cast, names, { allPressures: false, beat }),
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
  if (Array.isArray(value)) return joinList(value.map(one));
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
        if (!found.id) return { why: msg("records.whyMatchesNothing", { words: w }) };
        ids.push(found.id);
      }
      return ids.length ? { value: ids } : { why: msg("records.whyEmptyList") };
    }
    if (typeof words !== "string") return { why: msg("records.whyNotName") };
    const found = wordsToId(project, def.ref, words);
    return found.id ? { value: found.id } : { why: msg(found.several ? "records.whyMatchesSeveral" : "records.whyMatchesNothing", { words }) };
  }
  if (def.options?.length) {
    return def.options.some((o) => o.value === change.value) ? { value: change.value } : { why: msg("records.whyNotChoice", { value: change.value }) };
  }
  // The model sometimes writes "old -> new". The value is only what it reads now: the part after the last arrow.
  const words = typeof change.value === "string" ? change.value.split(/\s*(?:->|→)\s*/).pop().trim() : "";
  return words ? { value: words } : { why: msg("records.whyNoWords") };
}

// Puts a person into one of a Knowledge entry's lists, out of the others. Returns what the entry held before (to put back), and
// clears the belief when no one is misled any more.
function setStanding(entry, status, id) {
  const before = { knows: [...entry.knows], suspects: [...entry.suspects], misled: [...entry.misled], belief: entry.belief ?? "" };
  for (const key of STANDINGS) entry[key] = entry[key].filter((x) => x !== id);
  entry[status].push(id);
  if (!entry.misled.length) entry.belief = "";
  return before;
}

// A Knowledge entry made before this build, or typed by hand, may lack a list: every entry reads as all three.
const wholeEntry = (entry) => { for (const key of STANDINGS) entry[key] = Array.isArray(entry[key]) ? entry[key] : []; return entry; };

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
    if (!item) { drop(msg("records.whyNoEntry")); continue; }
    if (!def?.changes) { drop(msg("records.whyNoChange")); continue; }
    const covering = locks.filter((l) => lockCovers(l, change));
    if (change.section === "knowledge" && STANDINGS.includes(change.field)) {
      // The value is the one person who now stands that way; the entry moves them out of its other lists.
      wholeEntry(item);
      const who = wordsToId(project, ["characters", "world.powers"], Array.isArray(change.value) ? change.value[0] : change.value);
      if (!who.id) { drop(msg(who.several ? "records.whyMatchesSeveral" : "records.whyMatchesNothing", { words: String(change.value) })); continue; }
      if (item[change.field].includes(who.id)) continue;                                  // already so
      if (covering.length && !overwriteLocked) { drop(msg("records.whyLocked")); continue; }
      const was = [...item[change.field]];
      const restore = setStanding(item, change.field, who.id);
      applied.push({
        section: change.section, item: change.item, field: change.field, label: def.label ?? def.key, was, now: [...item[change.field]],
        from: show(def, was, names), to: show(def, item[change.field], names), restore, locks: covering.map((l) => l.id),
      });
      continue;
    }
    const got = resolveChangeValue(def, change, project);
    if (got.why) { drop(got.why); continue; }
    if (JSON.stringify(item[change.field]) === JSON.stringify(got.value)) continue;       // no change at all
    if (covering.length && !overwriteLocked) { drop(msg("records.whyLocked")); continue; }
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
      if (a.restore) Object.assign(section, a.restore); else section[a.field] = a.was;
      dropped.push({ section: a.section, item: a.item, field: a.field, value: a.to, why: msg("records.whyBreaksRule", { why }) });
    }
  }
  const kept = applied.filter((a) => !fresh.some((p) => p.item === a.item));
  return { entanglements: next, applied: kept, dropped, locked: kept.filter((a) => a.locks.length) };
}

// New Knowledge the model proposed: someone came to know, suspect or be misled about something. One proposal is one person. A person
// is added to the entry about the same thing when there is one (moved, if they stood another way), and the first proposal about a
// new thing makes its entry, which the next proposals about it join. Each is checked or left out with its reason: the person must be
// found, and if a character must be in this chapter; exactly one of a World rule or a fact; and a lock on the whole Knowledge list
// or card asks first, like any locked value. There is no limit on how many. Returns {applied, dropped}; applied entries read like
// changes (label, from, to) so the review lists them with the rest.
const entryWords = (project, k) => (k.rule ? (project.world?.rules ?? []).find((r) => r.id === k.rule)?.statement : k.fact) ?? "";

function addKnowledge(schema, project, next, proposals, cast, { overwriteLocked }) {
  const applied = [];
  const dropped = [];
  const names = nameMap(project);
  const defs = fieldDefs(schema, "entanglements", "knowledge");
  const label = msg("records.newKnowledge");
  const covering = (project.locks ?? []).filter((l) => lockCovers(l, { section: "knowledge" }));
  const list = next.knowledge ?? (next.knowledge = []);
  const taken = ["ties", "holdings", "knowledge", "pressures"].flatMap((k) => (next[k] ?? []).map((i) => i.id));
  const people = new Set((project.characters ?? []).map((c) => c.id));
  const madeHere = new Map();      // entry id -> the applied record that shows it
  const standing = (entry) => STANDINGS.filter((k) => entry[k].length).map((k) => `${defs.find((d) => d.key === k)?.label ?? k}: ${joinList(entry[k].map((id) => names.get(id) ?? id))}`).join("; ");
  for (const p of proposals) {
    if (!p.entry && !p.rule && !p.fact) continue;      // an empty proposal says nothing, so it is not worth a warning
    const target = p.entry ? list.find((k) => k.id === p.entry) : null;
    const what = p.entry ? (target ? entryWords(project, target) : "") : (p.rule ?? p.fact ?? "");
    const drop = (why) => dropped.push({ section: "knowledge", field: label, value: `${p.person}: ${what}`, why });
    const who = wordsToId(project, ["characters", "world.powers"], p.person);
    if (!who.id) { drop(msg(who.several ? "records.whyMatchesSeveral" : "records.whyMatchesNothing", { words: p.person })); continue; }
    if (people.has(who.id) && !cast.includes(who.id)) { drop(msg("records.notInChapter", { name: p.person })); continue; }
    if (p.entry && !target) { drop(msg("records.whyMatchesNothing", { words: p.entry })); continue; }
    if (!p.entry && Boolean(p.rule) === Boolean(p.fact)) { drop(msg("records.knowledgeOneFact")); continue; }
    let ruleId = "";
    if (p.rule) {
      const found = wordsToId(project, ["world.rules"], p.rule);
      if (!found.id) { drop(msg(found.several ? "records.whyMatchesSeveral" : "records.whyMatchesNothing", { words: p.rule })); continue; }
      ruleId = found.id;
    }
    const same = target ?? list.find((k) => (ruleId ? k.rule === ruleId : squash(k.fact) === squash(p.fact)));
    if (same) {
      wholeEntry(same);
      if (same[p.status].includes(who.id)) continue;                                      // already so
      const here = madeHere.get(same.id);
      if (!here && covering.length && !overwriteLocked) { drop(msg("records.whyLocked")); continue; }
      const was = [...same[p.status]];
      const restore = setStanding(same, p.status, who.id);
      if (p.status === "misled" && p.belief && !same.belief) same.belief = p.belief;
      if (here) {                                                                         // joins the entry this reply made
        here.to = msg("records.newKnowledgeTo", { what, standing: standing(same) });
        continue;
      }
      const def = defs.find((d) => d.key === p.status);
      applied.push({
        section: "knowledge", item: same.id, field: p.status, label: def?.label ?? p.status, was, now: [...same[p.status]],
        from: show(def, was, names), to: show(def, same[p.status], names), restore, locks: covering.map((l) => l.id),
      });
      continue;
    }
    if (covering.length && !overwriteLocked) { drop(msg("records.whyLocked")); continue; }
    const entry = { rule: ruleId, fact: ruleId ? "" : p.fact, knows: [], suspects: [], misled: [], belief: p.status === "misled" ? (p.belief ?? "") : "", id: newId(taken) };
    entry[p.status].push(who.id);
    taken.push(entry.id);
    list.push(entry);
    const record = {
      section: "knowledge", item: entry.id, field: "entry", label, was: null, now: entry, added: true,
      from: "", to: msg("records.newKnowledgeTo", { what, standing: standing(entry) }), locks: covering.map((l) => l.id),
    };
    madeHere.set(entry.id, record);
    applied.push(record);
  }
  return { applied, dropped };
}

// The ids the model said the chapter showed that are live entanglements here (anything else is left out), each once.
function shownIds(project, shown) {
  const live = new Set(["ties", "holdings", "knowledge", "pressures"].flatMap((k) => (project.entanglements?.[k] ?? []).map((i) => i.id)));
  return [...new Set(asList(shown))].filter((id) => live.has(id));
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
    if (!found.id) warnings.push({ kind: "unmatched", text: msg(found.several ? "records.unmatchedSeveral" : "records.unmatchedNone", { what, words }) });
    return found.id ?? null;
  };
  const plants = openPlants(project);
  const paid = [];
  for (const words of e.paid_off) {
    const plant = plants.find((p) => squash(p.text) === squash(words));
    if (plant) { if (!paid.includes(plant.id)) paid.push(plant.id); } else warnings.push({ kind: "unmatched", text: msg("records.payoffNotOpen", { words }) });
  }
  const availableIds = new Set(availableReveals(project).map((r) => r.id));
  const reveals = e.reveals_landed.map((w) => link(["world.rules"], w, msg("records.whatReveal"))).filter((id) => {
    if (id && !availableIds.has(id)) warnings.push({ kind: "unmatched", text: msg("records.revealAgain") });
    return id && availableIds.has(id);
  });
  const behaviors = [];
  for (const w of e.behaviors_seen) {
    const found = behaviorMatch(project, cast, w);
    if (found.id) behaviors.push(found.id); else warnings.push({ kind: "unmatched", text: msg(found.several ? "records.behaviorSeveral" : "records.behaviorNone", { words: w }) });
  }
  const things = e.things_seen.map((w) => link(["world.objects"], w, msg("records.whatThing"))).filter(Boolean);

  // A chapter plants at most one thing, and at most two plants stay open at once.
  // Only the plant the beat planned can land. Anything else the extractor wrote is not a plant, so a chapter cannot
  // plant the same words twice by echoing the open list.
  let planted = isFilled(beat.plant) && squash(e.planted) === squash(beat.plant) ? beat.plant.trim() : null;
  if (planted && plants.some((p) => squash(p.text) === squash(planted))) planted = null;
  if (planted && plants.length - paid.length >= MAX_OPEN_PLANTS) {
    warnings.push({ kind: "plant", text: msg("records.plantsFull", { planted }) });
    planted = null;
  }
  const event = {
    id: fresh(), beat: beat.id, happened: e.happened, changed: e.changed ?? "", planted: planted ?? "",
    paid_off: paid, reveals_landed: reveals, behaviors_seen: behaviors, things_seen: things, goal_landed: e.goal_landed,
    entanglements_shown: shownIds(project, read.shown),
  };
  if (beat.goal_change && !e.goal_landed) warnings.push({ kind: "goal", text: msg("records.goalPending") });
  if (beat.reveal_rule && !reveals.includes(beat.reveal_rule)) warnings.push({ kind: "reveal", text: msg("records.revealStillAvailable") });

  // Who moved: only people in the chapter, once each.
  const shifts = [];
  for (const s of read.shifts) {
    const id = link(["characters"], s.character, msg("records.whatCharacter"));
    if (!id) continue;
    if (!cast.includes(id)) { warnings.push({ kind: "unmatched", text: msg("records.notInChapter", { name: s.character }) }); continue; }
    if (shifts.some((x) => x.character === id)) { warnings.push({ kind: "unmatched", text: msg("records.shiftTwice", { name: s.character }) }); continue; }
    if (shifts.length >= MAX_SHIFTS) continue;
    const { character, ...texts } = s;
    shifts.push({ id: fresh(), beat: beat.id, character: id, ...texts });
  }

  const changes = applyChanges(schema, project, read.changes, { overwriteLocked });
  const added = addKnowledge(schema, project, changes.entanglements, read.new_knowledge ?? [], cast, { overwriteLocked });
  changes.applied.push(...added.applied);
  changes.dropped.push(...added.dropped);
  changes.locked.push(...added.applied.filter((a) => a.locks.length));
  if (reveals.length && !changes.applied.some((a) => a.section === "knowledge")) {
    warnings.push({ kind: "knowledge", text: msg("records.knowledgeUnchanged") });
  }
  for (const d of changes.dropped) warnings.push({ kind: "dropped", text: msg("records.changeLeftOut", { field: d.field, why: d.why }) });

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
// Returns {project, undo}: undo takes the chapter and everything with it out again and answers true, or answers false and
// changes nothing when any of those parts has been changed since.
export function commitChapter(project, outcome) {
  const undo = watch(project, CHAPTER_PARTS);
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
  undo.settle();
  return { project, undo: () => undo.undo() };
}

// ---- Writing a chapter again ---------------------------------------------------------------------
// Regenerating chapter N goes back to the state N was first written from: the Entanglements as the history kept them, and
// only the records of the chapters before it. It reuses N's beat. The old chapter stays in the project until the new one
// commits (a failed or stopped call changes nothing), and later chapters stay where they are, with their beats marked stale.

const chapterNumber = (project, beatId) => Number((project.outline?.beats ?? []).find((b) => b.id === beatId)?.chapter) || 0;

// The project as it stood when chapter `number` was about to be written: no chapter or record from `number` on, and the
// Entanglements that chapter was written from.
export function projectBefore(project, number) {
  const trial = copyOf(project);
  const early = (x) => chapterNumber(project, x.beat) < number;
  trial.chapters = (project.chapters ?? []).filter(early).map(copyOf);
  trial.summary_events = { ...(project.summary_events ?? {}), entries: (project.summary_events?.entries ?? []).filter(early).map(copyOf) };
  trial.summary_shifts = { ...(project.summary_shifts ?? {}), shifts: (project.summary_shifts?.shifts ?? []).filter(early).map(copyOf) };
  trial.entanglements_history = { ...(project.entanglements_history ?? {}), states: (project.entanglements_history?.states ?? []).filter(early).map(copyOf) };
  const snapshot = (project.entanglements_history?.states ?? []).find((s) => chapterNumber(project, s.beat) === number);
  if (snapshot) trial.entanglements = copyOf(snapshot.state);
  return trial;
}

// {ok, number, beat, trial, later} or {ok: false, reason}: not_started, outline_locked, no_chapter, no_snapshot, cast_<why>, beat_blocked (with `problems`).
// `later` is how many chapters come after this one.
export function regenerateGate(schema, project, number) {
  if (!storyStarted(project)) return { ok: false, reason: "not_started" };
  if (cardLocked(project, "outline")) return { ok: false, reason: "outline_locked" };    // it marks the later beats stale
  const written = project.chapters ?? [];
  const chapter = written.find((c) => chapterNumber(project, c.beat) === number);
  if (!chapter) return { ok: false, reason: "no_chapter" };
  if (!(project.entanglements_history?.states ?? []).some((s) => s.beat === chapter.beat)) return { ok: false, reason: "no_snapshot" };
  const trial = projectBefore(project, number);
  const beat = trial.outline.beats.find((b) => b.id === chapter.beat);
  const why = castProblem(project, beat.cast);
  if (why) return { ok: false, reason: `cast_${why}` };
  const problems = beatBlockers(schema, trial, beat);
  if (problems.length) return { ok: false, reason: "beat_blocked", problems };
  return { ok: true, number, beat, trial, chapter, later: written.length - number };
}

// What the page checks when the model answers: nothing the new chapter depends on was edited meanwhile.
export function regenerateKey(schema, project, number) {
  const chapter = (project.chapters ?? []).find((c) => chapterNumber(project, c.beat) === number);
  return JSON.stringify([entanglementsHash(schema, project), project.outline?.beats ?? [], (project.chapters ?? []).map((c) => c.id), chapter?.text ?? null]);
}

// The records of a regenerated chapter, from the model's reply. The chapter, its events and its history keep their ids (later
// records point at them); the shifts get new ones. Warns about what later chapters still lean on.
export function applyRegenerated(schema, project, ctx, read, { overwriteLocked = true } = {}) {
  const { trial, beat, number } = ctx;
  const out = applyGenerated(schema, trial, beat, read, { overwriteLocked });
  const old = {
    chapter: (project.chapters ?? []).find((c) => c.beat === beat.id),
    events: (project.summary_events?.entries ?? []).find((e) => e.beat === beat.id),
    history: (project.entanglements_history?.states ?? []).find((s) => s.beat === beat.id),
  };
  out.chapter.id = old.chapter.id;
  out.events.id = old.events.id;
  out.history.id = old.history.id;
  const taken = [...(project.summary_shifts?.shifts ?? []).map((s) => s.id), ...(project.chapters ?? []).map((c) => c.id),
    ...(project.summary_events?.entries ?? []).map((e) => e.id), ...(project.entanglements_history?.states ?? []).map((s) => s.id)];
  for (const s of out.shifts) { s.id = newId(taken); taken.push(s.id); }
  out.before = old.chapter.text;
  // Later chapters were written from the old version.
  const lateEvents = (project.summary_events?.entries ?? []).filter((e) => chapterNumber(project, e.beat) > number);
  if (lateEvents.some((e) => (e.paid_off ?? []).includes(out.events.id)) && !out.events.planted) {
    out.warnings.push({ kind: "later", text: msg("records.laterNoPlant") });
  }
  if (project.chapters.length > number) {
    out.warnings.push({ kind: "later", text: msg("records.laterStale", { n: project.chapters.length - number }) });
  }
  return out;
}

// Replaces chapter N's text, events, shifts and history with the new ones, sets the Entanglements to the new result and
// marks every later beat stale, all at once. Returns an undo that puts everything back as it was, unless the writer has changed
// any of it since.
export function commitRegenerated(project, outcome) {
  const undo = watch(project, [...CHAPTER_PARTS, "outline"]);
  const beat = outcome.chapter.beat;
  const number = chapterNumber(project, beat);
  const stale = (project.outline.beats ?? []).map((b) => (Number(b.chapter) > number ? { ...b, stale: true } : b));
  Object.assign(project, {
    chapters: project.chapters.map((c) => (c.beat === beat ? outcome.chapter : c)),
    summary_events: { ...project.summary_events, entries: project.summary_events.entries.map((e) => (e.beat === beat ? outcome.events : e)) },
    summary_shifts: { ...project.summary_shifts, shifts: [...project.summary_shifts.shifts.filter((s) => s.beat !== beat), ...outcome.shifts] },
    entanglements_history: { ...project.entanglements_history, states: project.entanglements_history.states.map((s) => (s.beat === beat ? outcome.history : s)) },
    entanglements: outcome.entanglements,
    outline: { ...project.outline, beats: stale },
    locks: (project.locks ?? []).filter((l) => !outcome.unlock.includes(l.id)),
  });
  undo.settle();
  return { undo: () => undo.undo() };      // true, or false (and nothing changed) when any of those parts was changed since
}
