// Planning the next chapter: everything the page works out in code, and the requests it sends the model. No DOM, so
// Node can test it. The backend is stateless, so the page works out the deterministic numbers (which chapter, the
// spotlight, the legal shifts, the goal, the open plants, the reveals still available, the use counts, who is on
// stage) and sends them; the model only thinks and fills the beat.
//
// A chapter is planned from the cards as they stand. The beat remembers a hash of the Entanglements it was planned
// from, so a later edit to a live field marks the plan as made from older state (it is never replanned by itself).

import {
  envelope, blankItem, refOptions, resolveFillLinks, validate, legalShifts, instanceName, isFilled, settledProject,
  findInstance,
} from "./logic.js";
import { storyStarted } from "./gate.js";

export const CAST_MAX = 5;               // the beat's cast, protagonist included (the schema's max_selected)
export const SUGGEST_SIZE = 3;           // how many the page suggests: the protagonist and the two least used
export const OFFSTAGE_EVERY = 2;         // an offstage change is due in every 2nd chapter
const REVEALABLE = ["uncommon", "false_belief"];

const copyOf = (value) => JSON.parse(JSON.stringify(value));
const beatsOf = (project) => project.outline?.beats ?? [];
const eventsOf = (project) => project.summary_events?.entries ?? [];
const shiftsOf = (project) => project.summary_shifts?.shifts ?? [];
const asList = (value) => (Array.isArray(value) ? value : isFilled(value) ? [value] : []);

// ---- Where the story stands ---------------------------------------------------

// Chapter numbers come from beats, and a chapter is written when a Chapter points at its beat.
export function writtenBeatIds(project) {
  return new Set((project.chapters ?? []).map((c) => c.beat));
}

// The beats marked as possibly out of step (an earlier chapter was written again after they were planned): a set of ids.
export function staleBeatIds(project) {
  return new Set(beatsOf(project).filter((b) => b.stale === true).map((b) => b.id));
}

// Who is in a beat's cast, as one string that does not depend on the order: for telling whether the cast was changed.
export function castKey(cast) {
  return [...(Array.isArray(cast) ? cast : [])].sort().join("|");
}

export function chapterInfo(project) {
  const written = (project.chapters ?? []).length;
  const count = Number(project.setup?.chapter_count) || 0;
  return { written, next: written + 1, count, done: count > 0 && written >= count };
}

// The unwritten beat for chapter n, if one was planned.
export function beatForChapter(project, chapter) {
  const done = writtenBeatIds(project);
  return beatsOf(project).find((b) => Number(b.chapter) === chapter && !done.has(b.id)) ?? null;
}

const chapterOfBeat = (project, id) => Number(beatsOf(project).find((b) => b.id === id)?.chapter) || null;

// Setup's goal, replaced by each beat whose redefinition actually landed. A landed "achieved" or "abandoned" ends it.
export function currentGoal(project) {
  let goal = isFilled(project.setup?.goal) ? project.setup.goal : null;
  const written = beatsOf(project).filter((b) => writtenBeatIds(project).has(b.id)).sort((a, b) => a.chapter - b.chapter);
  for (const beat of written) {
    if (!eventsOf(project).some((e) => e.beat === beat.id && e.goal_landed)) continue;
    if (beat.goal_change === "redefined") goal = isFilled(beat.goal_now) ? beat.goal_now : goal;
    else if (beat.goal_change === "achieved" || beat.goal_change === "abandoned") return null;
  }
  return goal;
}

// Earlier entries that planted something no later entry has paid off.
export function openPlants(project) {
  const paidOff = new Set(eventsOf(project).flatMap((e) => e.paid_off ?? []));
  return eventsOf(project)
    .filter((e) => isFilled(e.planted) && !paidOff.has(e.id))
    .map((e) => ({ id: e.id, text: e.planted.trim(), chapter: chapterOfBeat(project, e.beat) }))
    .sort((a, b) => (a.chapter ?? 0) - (b.chapter ?? 0));
}

// World rules the story may still bring to light: not common, and not landed in a written chapter.
export function availableReveals(project) {
  const landed = new Set(eventsOf(project).flatMap((e) => e.reveals_landed ?? []));
  return (project.world?.rules ?? [])
    .filter((r) => REVEALABLE.includes(r.status) && !landed.has(r.id) && isFilled(r.statement))
    .map((r) => ({ id: r.id, statement: r.statement.trim(), truth: r.truth ?? "", status: r.status }));
}

// ---- Use counts and the cast ---------------------------------------------------
// Place and character counts come from planned beats (the beat chose them for its chapter). Behavior and thing counts
// come from what the Events passes saw. `except` leaves out the chapter being planned, so replanning it does not count itself.

export function useCounts(project, except = null) {
  const counts = { characters: {}, places: {}, lastSeen: {}, behaviors: {}, things: {} };
  const bump = (bucket, id) => { if (id) counts[bucket][id] = (counts[bucket][id] ?? 0) + 1; };
  for (const beat of beatsOf(project)) {
    if (except !== null && Number(beat.chapter) === except) continue;
    for (const id of asList(beat.cast)) {
      bump("characters", id);
      counts.lastSeen[id] = Math.max(counts.lastSeen[id] ?? 0, Number(beat.chapter) || 0);
    }
    bump("places", beat.where);
  }
  for (const entry of eventsOf(project)) {
    for (const id of asList(entry.behaviors_seen)) bump("behaviors", id);
    for (const id of asList(entry.things_seen)) bump("things", id);
  }
  return counts;
}

// Every character as a choice for the cast, with how much they have been used, and a suggestion: the protagonist and
// the least-used others (fewest chapters, then the longest since they last appeared). {id, name, uses, last, protagonist, suggested}
export function castChoices(project, chapter) {
  const counts = useCounts(project, chapter);
  const lead = project.setup?.protagonist;
  const all = (project.characters ?? []).map((c, order) => ({
    id: c.id, name: instanceName(c), uses: counts.characters[c.id] ?? 0, last: counts.lastSeen[c.id] ?? null, protagonist: c.id === lead, order,
  }));
  const others = all.filter((c) => !c.protagonist)
    .sort((a, b) => a.uses - b.uses || (a.last ?? 0) - (b.last ?? 0) || a.order - b.order)
    .slice(0, Math.max(0, SUGGEST_SIZE - 1));
  const suggested = new Set([...all.filter((c) => c.protagonist), ...others].map((c) => c.id));
  return all.map(({ order, ...c }) => ({ ...c, suggested: suggested.has(c.id) }));
}

export const suggestedCast = (project, chapter) => castChoices(project, chapter).filter((c) => c.suggested).map((c) => c.id);

// Whether a cast can be used: the protagonist is in, there are at most CAST_MAX, and everyone exists.
export function castProblem(project, castIds) {
  const ids = asList(castIds);
  if (!ids.length) return "empty";
  if (ids.length > CAST_MAX) return "too_many";
  if (!ids.includes(project.setup?.protagonist)) return "no_protagonist";
  if (ids.some((id) => !findInstance(project, { id: "characters", many_per_project: true }, id))) return "unknown";
  return null;
}

// ---- The spotlight and the shifts ------------------------------------------------

// The pressure this chapter is about: always one that involves someone on stage, the least-spotlit first (ties go to the
// one listed first). With none involving the cast, the least-spotlit overall; the beat's own rule then warns about it.
export function pickSpotlight(project, castIds, except = null) {
  const pressures = project.entanglements?.pressures ?? [];
  if (!pressures.length) return null;
  const used = {};
  for (const beat of beatsOf(project)) if (except === null || Number(beat.chapter) !== except) used[beat.spotlight] = (used[beat.spotlight] ?? 0) + 1;
  const involves = (p) => [p.source_agent, ...asList(p.bears_on)].some((id) => asList(castIds).includes(id));
  const pool = pressures.filter(involves);
  return (pool.length ? pool : pressures)
    .map((p, order) => ({ p, order }))
    .sort((a, b) => (used[a.p.id] ?? 0) - (used[b.p.id] ?? 0) || a.order - b.order)[0].p;
}

// The shifts the chapter may take, from the earlier beats' pacing.
export function shiftsForChapter(project, chapter) {
  return legalShifts(beatsOf(project).filter((b) => Number(b.chapter) !== chapter), { chapter });
}

export function offstageDue(chapter) {
  return chapter > 1 && chapter % OFFSTAGE_EVERY === 0;
}

// ---- The stale-plan hash ------------------------------------------------------------

function hashText(text) {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, "0");
}

// A short fingerprint of the Entanglements as they stand (blank fields filled in, so a visit alone changes nothing).
export function entanglementsHash(schema, project) {
  return hashText(JSON.stringify(settledProject(schema, project).entanglements));
}

// The plan was made from Entanglements that have changed since.
export function planIsStale(schema, project, beat) {
  return Boolean(beat?.planned_from) && beat.planned_from !== entanglementsHash(schema, project);
}

// ---- Can a chapter be planned? -------------------------------------------------------

// {ok, chapter} or {ok: false, reason}: not_started, done, no_pressure, cast (with `why`).
export function planGate(project, castIds) {
  if (!storyStarted(project)) return { ok: false, reason: "not_started" };
  const info = chapterInfo(project);
  if (info.done) return { ok: false, reason: "done" };
  if (!(project.entanglements?.pressures ?? []).length) return { ok: false, reason: "no_pressure" };
  const why = castProblem(project, castIds);
  if (why) return { ok: false, reason: "cast", why };
  return { ok: true, chapter: info.next };
}

// ---- What the model is sent ------------------------------------------------------------
// Links become names (the model never sees an id except on an item it may change later), and each request carries only the
// cast and what is in play.

const NAMED_SOURCES = ["characters", "world.places", "world.objects", "world.powers", "world.rules"];

export function nameMap(project) {
  const names = new Map(refOptions(project, NAMED_SOURCES, "").map((o) => [o.value, o.label || "(unnamed)"]));
  for (const e of eventsOf(project)) if (isFilled(e.planted)) names.set(e.id, e.planted.trim());   // a payoff names the plant it resolves
  return names;
}

// An item with every link field turned into a name (or a list of names). Its own id stays.
export function named(defs, item, names) {
  const out = { ...item };
  for (const def of defs) {
    if (!def.ref || !(def.key in item)) continue;
    const value = item[def.key];
    out[def.key] = Array.isArray(value) ? value.map((id) => names.get(id) ?? id) : isFilled(value) ? names.get(value) ?? value : value;
  }
  return out;
}

export function fieldDefs(schema, cardId, listKey) {
  return schema.cards[cardId].fields.find((f) => f.key === listKey)?.item_fields ?? [];
}

export const castCards = (project, castIds) => asList(castIds).map((id) => (project.characters ?? []).find((c) => c.id === id)).filter(Boolean);

// The Entanglements the cast can see: ties they hold, what they hold, what they know, and (for the planner) every pressure.
export function entanglementsFor(schema, project, castIds, names, { allPressures }) {
  const cast = asList(castIds);
  const e = settledProject(schema, project).entanglements;
  const out = (key, items) => items.map((i) => named(fieldDefs(schema, "entanglements", key), i, names));
  const touchesCast = (p) => [p.source_agent, ...asList(p.bears_on)].some((id) => cast.includes(id));
  return {
    ties: out("ties", e.ties.filter((t) => cast.includes(t.tie_from))),
    holdings: out("holdings", e.holdings.filter((h) => cast.includes(h.held_by))),
    knowledge: out("knowledge", e.knowledge.filter((k) => cast.includes(k.person))),
    pressures: out("pressures", allPressures ? e.pressures : e.pressures.filter(touchesCast)),
  };
}

const withCounts = (items, counts) => items.map((i) => ({ ...i, uses: counts[i.id] ?? 0 }));

function worldFor(schema, project, castIds, names) {
  const w = settledProject(schema, project).world;
  const counts = useCounts(project, null);
  const held = new Map((project.entanglements?.holdings ?? []).map((h) => [h.holdee, names.get(h.held_by) ?? ""]));
  return {
    name: w.name, era_and_technology: w.era_and_technology, everyday_life: w.everyday_life,
    places: withCounts(w.places, counts.places),
    objects: withCounts(w.objects, counts.things).map((o) => ({ ...o, held_by: held.get(o.id) ?? "" })),
    powers: w.powers,
    rules: w.rules,
  };
}

export function beatInWords(schema, project, beat, names) {
  const defs = schema.cards.outline.fields.find((f) => f.key === "beats").item_fields;
  const out = named(defs, beat, names);
  const pressure = (project.entanglements?.pressures ?? []).find((p) => p.id === beat.spotlight);
  out.spotlight = pressure?.what ?? "";
  delete out.planned_from; delete out.stale;
  return out;
}

export function eventsInWords(project, upTo = Infinity) {
  return eventsOf(project)
    .map((e) => ({ chapter: chapterOfBeat(project, e.beat), happened: e.happened, changed: e.changed ?? "", planted: e.planted ?? "" }))
    .filter((e) => e.chapter !== null && e.chapter <= upTo)
    .sort((a, b) => a.chapter - b.chapter);
}

// The latest value of each shift field for each cast member, the way the writer's own prompt shows "where they stand now".
export function latestShifts(project, castIds, names = nameMap(project)) {
  const cast = asList(castIds);
  const rows = shiftsOf(project).map((s) => ({ s, chapter: chapterOfBeat(project, s.beat) ?? 0 })).sort((a, b) => a.chapter - b.chapter);
  const out = [];
  for (const id of cast) {
    const standing = { character: names.get(id) ?? id };
    for (const { s } of rows) {
      if (s.character !== id) continue;
      for (const key of ["believes", "fears", "wants", "refuses", "decided"]) if (isFilled(s[key])) standing[key] = s[key];
    }
    if (Object.keys(standing).length > 1) out.push(standing);
  }
  return out;
}

// Offstage: what do the background groups and places do this chapter? Only the groups, places and what touches them.
export function offstageRequest(schema, project, castIds) {
  const chapter = chapterInfo(project).next;
  const names = nameMap(project);
  const e = settledProject(schema, project).entanglements;
  const w = settledProject(schema, project).world;
  const background = new Set([...w.powers, ...w.places].map((x) => x.id));
  const touches = (...ids) => ids.flat().some((id) => background.has(id));
  const out = (key, items) => items.map((i) => named(fieldDefs(schema, "entanglements", key), i, names));
  const counts = useCounts(project, chapter);
  const last = eventsInWords(project).at(-1) ?? null;
  return {
    ...envelope(schema, project, "offstage"),
    chapter, chapter_count: chapterInfo(project).count,
    cast: castCards(project, castIds).map(copyOf),
    world: { powers: w.powers, places: withCounts(w.places, counts.places) },
    entanglements: {
      ties: out("ties", e.ties.filter((t) => touches(t.tie_from, t.tie_to))),
      holdings: out("holdings", e.holdings.filter((h) => touches(h.held_by))),
      pressures: out("pressures", e.pressures.filter((p) => touches(p.source_agent, asList(p.bears_on)))),
    },
    latest_events: last,
  };
}

// The plan: think, then fill the beat. `offstage` is {did, reach} from an offstage call, `retry` {thinking, beat, problems}.
export function planRequest(schema, project, castIds, { offstage = null, retry = null } = {}) {
  const info = chapterInfo(project);
  const chapter = info.next;
  const names = nameMap(project);
  const spotlight = pickSpotlight(project, castIds, chapter);
  const counts = useCounts(project, chapter);
  const defs = fieldDefs(schema, "entanglements", "pressures");
  const earlier = beatsOf(project).filter((b) => Number(b.chapter) < chapter).sort((a, b) => a.chapter - b.chapter);
  const asPerson = (id) => names.get(id) ?? id;
  const characters = (project.characters ?? []);
  return {
    ...envelope(schema, project, "plan"),
    chapter, chapter_count: info.count,
    style: copyOf(settledProject(schema, project).style),
    setup: { ...copyOf(settledProject(schema, project).setup), protagonist: asPerson(project.setup?.protagonist) },
    goal: currentGoal(project),
    cast: castCards(project, castIds).map(copyOf),
    world: worldFor(schema, project, castIds, names),
    entanglements: entanglementsFor(schema, project, castIds, names, { allPressures: true }),
    spotlight: spotlight ? named(defs, spotlight, names) : {},
    legal_shifts: shiftsForChapter(project, chapter),
    open_plants: openPlants(project).map(({ text, chapter: c }) => ({ text, chapter: c })),
    available_reveals: availableReveals(project).map(({ statement, truth, status }) => ({ statement, truth, status })),
    use_counts: {
      characters: characters.map((c) => ({ name: instanceName(c), uses: counts.characters[c.id] ?? 0, last: counts.lastSeen[c.id] ?? null })),
      places: (project.world?.places ?? []).map((p) => ({ name: p.name, uses: counts.places[p.id] ?? 0 })),
      behaviors: characters.flatMap((c) => (c.behaviors ?? []).map((b) => ({ character: instanceName(c), state: b.state, uses: counts.behaviors[b.id] ?? 0 }))),
      things: (project.world?.objects ?? []).map((o) => ({ name: o.name, uses: counts.things[o.id] ?? 0 })),
    },
    earlier_beats: earlier.map((b) => beatInWords(schema, project, b, names)),
    earlier_events: eventsInWords(project, chapter - 1),
    latest_shifts: latestShifts(project, castIds, names),
    offstage: offstage ? { did: offstage.did, reach: offstage.reach } : null,
    retry: retry ? { thinking: retry.thinking, beat: copyOf(retry.beat), problems: [...retry.problems] } : null,
  };
}

// ---- Landing the beat ------------------------------------------------------------------------

const BEAT_FIELD = (schema) => schema.cards.outline.fields.find((f) => f.key === "beats");

// The model's beat (links in words) as a beat item with ids: {beat, unresolved, dropped}.
//   unresolved  links that matched nothing or two entries (left empty), as resolveFillLinks reports them
//   dropped     keys the model gave that were not usable (a shift that is neither harder nor easier, and so on)
// The code-filled fields (chapter, cast, spotlight, planned_from, the offstage move) are set here, never by the model.
export function landBeat(schema, project, castIds, reply, { offstage = null, existing = null } = {}) {
  const field = BEAT_FIELD(schema);
  const info = chapterInfo(project);
  const planner = field.item_fields.filter((f) => f.filled_by === "planner" && !["offstage_did", "offstage_reach"].includes(f.key));
  const given = {};
  const dropped = [];
  for (const def of planner) {
    const value = reply.beat?.[def.key];
    if (!isFilled(value)) continue;
    if (def.options?.length && !def.options.some((o) => o.value === value)) { dropped.push(def.key); continue; }
    given[def.key] = value;
  }
  const { values, unresolved } = resolveFillLinks({ fields: [{ ...field, item_fields: planner }] }, { beats: [given] }, project);
  const beat = { ...blankItem(field, (beatsOf(project)).map((b) => b.id)), ...(values.beats?.[0] ?? {}) };
  // A reveal must be one the page offered. A common or already-landed rule is not.
  if (beat.reveal_rule && !availableReveals(project).some((r) => r.id === beat.reveal_rule)) {
    unresolved.push({ field: "beats", key: "reveal_rule", words: given.reveal_rule, why: "none" });
    beat.reveal_rule = "";
  }
  if (existing) beat.id = existing.id;
  const spotlight = pickSpotlight(project, castIds, info.next);
  Object.assign(beat, {
    chapter: info.next, stale: false, cast: asList(castIds).slice(), spotlight: spotlight?.id ?? "",
    planned_from: entanglementsHash(schema, project),
    offstage_did: offstage?.did ?? "", offstage_reach: offstage?.reach ?? "",
  });
  if (info.next === 1) beat.when_gap = "";
  return { beat, unresolved, dropped };
}

// Puts the beat into the outline: replaces the unwritten beat for the same chapter, or adds it. Returns what it replaced.
export function placeBeat(project, beat) {
  const outline = project.outline ?? (project.outline = { beats: [] });
  const beats = outline.beats ?? (outline.beats = []);
  const at = beats.findIndex((b) => b.id === beat.id);
  if (at >= 0) { const was = beats[at]; beats[at] = beat; return was; }
  beats.push(beat);
  return null;
}

// The blocking problems the Outline card's own rules find in one beat, as the words the writer would read. This is what
// the retry sends back to the model, and what stops Generate when the second attempt still fails.
export function beatBlockers(schema, project, beat) {
  const trial = copyOf(project);
  placeBeat(trial, copyOf(beat));
  const settled = settledProject(schema, trial);
  return validate(schema.cards.outline, settled.outline, settled, schema.common)
    .problems.filter((p) => p.severity === "block" && p.item === beat.id)
    .map((p) => [p.message, p.fix].filter(Boolean).join(" "));
}

