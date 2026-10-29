// Planning the next chapter: everything the page works out in code, and the requests it sends the model. No DOM, so
// Node can test it. The backend is stateless, so the page works out the deterministic numbers (which chapter, the
// spotlight, the legal shifts, the goal, the open plants, the reveals still available, the use counts, who is on
// stage) and sends them; the model only thinks and fills the beat.
//
// A chapter is planned from the cards as they stand. The beat remembers a hash of the Entanglements it was planned
// from, so a later edit to a live field marks the plan as made from older state (it is never replanned by itself).

import {
  envelope, blankItem, refOptions, plantLabels, resolveFillLinks, validate, legalShifts, instanceName, isFilled, settledProject,
  findInstance, similarity, SIMILARITY_LIMIT,
} from "./logic.js";
import { storyStarted, cardLocked } from "./gate.js";
import { joinList, msg } from "./text.js";
import { usageOf, writtenChapters, choose, plannedIds, beatWords, mentions } from "./usage.js";

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

// ---- The goal arc ----------------------------------------------------------------------------
// The story has one goal from Setup (the story's goal) and the goal the chapters are pursuing now, which starts as the same
// words. A landed `redefined` beat replaces the current goal. A landed `achieved` or `abandoned` beat ends it, and what happens
// next depends on how much story is left: with two or more chapters after it, the story is not over, it needs a new goal (the next
// plan must redefine one, growing from the win or the failure); with fewer, the story winds down. Planned is not done: only a
// change the Events pass confirmed counts.
//   {story, goal, goals, since, state: "active" | "needs_goal" | "ended", lastEnd: {kind, goal} | null}
//   goals  every goal the story has had, in order, the current one last
//   since  the first chapter that pursued the current goal
export const GOAL_NEEDED_LEFT = 2;       // chapters that must remain after a goal ends for the story to need a new one

export function goalArc(project) {
  const count = Number(project.setup?.chapter_count) || 0;
  const story = isFilled(project.setup?.goal) ? project.setup.goal.trim() : null;
  const arc = { story, goal: story, goals: story ? [story] : [], since: 1, state: "active", lastEnd: null };
  const written = beatsOf(project).filter((b) => writtenBeatIds(project).has(b.id)).sort((a, b) => a.chapter - b.chapter);
  for (const beat of written) {
    if (!eventsOf(project).some((e) => e.beat === beat.id && e.goal_landed)) continue;
    const chapter = Number(beat.chapter) || 0;
    if (beat.goal_change === "redefined" && isFilled(beat.goal_now)) {
      arc.goal = beat.goal_now.trim();
      arc.goals.push(arc.goal);
      arc.since = chapter + 1;
      arc.state = "active";
      arc.lastEnd = null;
    } else if (beat.goal_change === "achieved" || beat.goal_change === "abandoned") {
      arc.lastEnd = { kind: beat.goal_change, goal: arc.goal };
      arc.state = count && count - chapter >= GOAL_NEEDED_LEFT ? "needs_goal" : "ended";
      arc.goal = null;
    }
  }
  return arc;
}

// Setup's goal, replaced by each landed redefinition; none once a goal ended (while the story needs a new one, or winds down).
export const currentGoal = (project) => goalArc(project).goal;

// How the goal stands for the chapter about to be planned, and what is worth doing with it. `due` is advice, never a rule:
//   set      the last goal ended and the story goes on: this chapter must start a new one
//   settle   the last chapter: the story's goal should end, won or lost
//   return   the chapter before the last, away from the story's goal: turn back toward it
//   stale    a goal that is not the story's has stood for half the story or more: end it or reshape it
//   twist    the middle of the story, with the goal unchanged so far: room for one turn
//   null     leave the goal alone unless the chapter's turn truly ends or reshapes it
export const GOAL_STALE_SHARE = 0.5;

export function goalDue(project, chapter) {
  const arc = goalArc(project);
  const count = Number(project.setup?.chapter_count) || 0;
  if (arc.state === "needs_goal") return { arc, due: "set", age: 0 };
  if (arc.state === "ended") return { arc, due: null, age: 0 };
  const age = Math.max(0, chapter - arc.since);
  const away = arc.goal !== arc.story;
  if (count && chapter >= count) return { arc, due: "settle", age };
  if (count && chapter === count - 1 && away) return { arc, due: "return", age };
  if (away && count && age >= Math.ceil(count * GOAL_STALE_SHARE)) return { arc, due: "stale", age };
  if (count && chapter === Math.ceil(count / 2) && arc.goals.length < 2) return { arc, due: "twist", age };
  return { arc, due: null, age };
}

// Directions a new goal could take, from the cards, so the next goal does not have to come out of the last one. Up to `size`
// of different kinds, with the kind to start from moving on each chapter, so the story is offered a different door each time:
//   pressure    the pressure that has had the least attention, and what its agent means to do next
//   truth       a hidden truth still waiting to come to light
//   want        something one of the people on stage wants, rotating through them
//   tie         what one person on stage wants from, or hides from, someone else
//   disruption  the break that began the story, while the story is young enough to be dealing with it
// A direction too close to a goal the story already had is left out. [{kind, text}]
export function goalDirections(project, castIds, chapter, names = nameMap(project), size = 3) {
  const arc = goalArc(project);
  const count = Number(project.setup?.chapter_count) || 0;
  const cast = castCards(project, castIds);
  const found = [];
  const due = duePressure(project, chapter);
  if (due?.what) found.push({ kind: "pressure", text: due.next_move ? `${due.what.replace(/[.!?]+$/, "")}. ${due.next_move}` : due.what });
  const truths = availableReveals(project);
  if (truths.length) found.push({ kind: "truth", text: truths[(chapter - 1) % truths.length].statement });
  const wants = cast.flatMap((c) => (c.wants ?? []).filter((w) => isFilled(w.text)).map((w) => `${instanceName(c)} wants to ${w.text.replace(/^to\s+/i, "")}`));
  if (wants.length) found.push({ kind: "want", text: wants[(chapter - 1) % wants.length] });
  const ties = (project.entanglements?.ties ?? []).filter((x) => asList(castIds).includes(x.tie_from) && isFilled(x.edge));
  if (ties.length) {
    const x = ties[(chapter - 1) % ties.length];
    found.push({ kind: "tie", text: `${names.get(x.tie_from) ?? "Someone"} and ${names.get(x.tie_to) ?? "someone"}: ${x.edge}` });
  }
  if (isFilled(project.setup?.disruption) && (!count || chapter <= Math.ceil((count * 2) / 3))) found.push({ kind: "disruption", text: project.setup.disruption.trim() });
  const fresh = found.filter((d) => !arc.goals.some((g) => similarity(d.text, g) >= SIMILARITY_LIMIT));
  const start = fresh.length ? (chapter - 1) % fresh.length : 0;
  return [...fresh.slice(start), ...fresh.slice(0, start)].slice(0, size);
}

// What the page says about a planned beat's goal, in the writer's words. Advice only: none of it stops anything.
export function goalWarnings(project, beat, chapter = Number(beat?.chapter) || chapterInfo(project).next) {
  const { arc, due } = goalDue(project, chapter);
  const count = Number(project.setup?.chapter_count) || 0;
  const out = [];
  const earlierBeats = beatsOf(project).filter((b) => b.id !== beat.id && Number(b.chapter) < chapter);
  const change = beat.goal_change || "";
  if (arc.state === "needs_goal" && !(change === "redefined" && isFilled(beat.goal_now))) out.push(msg("plan.goalWarn.needed"));
  if (change === "redefined" && isFilled(beat.goal_now) && arc.goals.some((g) => similarity(beat.goal_now, g) >= SIMILARITY_LIMIT)) out.push(msg("plan.goalWarn.repeats"));
  if (isFilled(beat.collision_goal) && earlierBeats.some((b) => isFilled(b.collision_goal) && similarity(beat.collision_goal, b.collision_goal) >= SIMILARITY_LIMIT)) out.push(msg("plan.goalWarn.aimRepeats"));
  if (due === "stale" && !change) out.push(msg("plan.goalWarn.stale", { n: Math.max(0, chapter - arc.since) }));
  if (change === "achieved" && arc.goal === arc.story && count && count - chapter >= 3) out.push(msg("plan.goalWarn.early", { n: count - chapter }));
  if (due === "settle" && change !== "achieved" && change !== "abandoned") out.push(msg("plan.goalWarn.unsettled"));
  return out;
}

// Earlier entries that planted something no later entry has paid off.
export function openPlants(project) {
  const paidOff = new Set(eventsOf(project).flatMap((e) => e.paid_off ?? []));
  const labels = plantLabels(project);
  return eventsOf(project)
    .filter((e) => isFilled(e.planted) && !paidOff.has(e.id))
    .map((e) => ({ id: e.id, text: labels.get(e.id) ?? e.planted.trim(), chapter: chapterOfBeat(project, e.beat) }))
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
// A value is used in a chapter only when it appears in that chapter's written text (see usage.js); a beat that planned it but has
// not been written, or a chapter that never names it, uses nothing up. `except` leaves out the chapter being planned or written
// again, so replanning it does not count itself.

export function useCounts(project, except = null) {
  const used = usageOf(project, except);
  const counts = { characters: {}, places: {}, lastSeen: {}, behaviors: {}, things: {}, used };
  const take = (bucket, list) => { for (const x of list ?? []) if (used[x.id]) counts[bucket][x.id] = used[x.id].uses; };
  take("characters", project.characters);
  take("places", project.world?.places);
  take("things", project.world?.objects);
  take("behaviors", (project.characters ?? []).flatMap((c) => c.behaviors ?? []));
  for (const c of project.characters ?? []) if (used[c.id]) counts.lastSeen[c.id] = used[c.id].last;
  return counts;
}

// How often each pressure has had a chapter: one the chapter showed (see usage.js) or one the chapter's beat put in the
// spotlight, once per chapter. A spotlight counts even when its agent stayed off stage and the chapter never showed it, so
// the rotation always moves on. `except` leaves out the chapter being planned.
function spotlightUse(project, except = null) {
  const used = usageOf(project, except);
  const count = Object.fromEntries((project.entanglements?.pressures ?? []).map((p) => [p.id, used[p.id]?.uses ?? 0]));
  const shown = {};
  for (const c of writtenChapters(project)) {
    if (except !== null && c.n === except) continue;
    const id = c.beat?.spotlight;
    if (id in count && !asList(c.events?.entanglements_shown).includes(id)) shown[id] = (shown[id] ?? 0) + 1;
  }
  for (const id of Object.keys(shown)) count[id] += shown[id];
  return count;
}

// The pressure that has had the least attention so far (ties go to the one listed first), or null when there is none.
// It is the one the next chapter should turn on, so the people in it are the ones worth having on stage.
export function duePressure(project, except = null) {
  const pressures = project.entanglements?.pressures ?? [];
  if (!pressures.length) return null;
  const used = spotlightUse(project, except);
  return pressures.map((p, order) => ({ p, order }))
    .sort((a, b) => (used[a.p.id] ?? 0) - (used[b.p.id] ?? 0) || a.order - b.order)[0].p;
}

// Every character as a choice for the cast, with how much they have been used, and a suggestion: the protagonist and
// two others. The others are the people in the pressure that has had the least attention (see duePressure) first, then the
// least-used (fewest chapters, then the longest since they last appeared). It is only a suggestion: the ticks start there and
// the writer changes them freely. Plain code, no model. {id, name, uses, last, protagonist, inPressure, suggested}
export function castChoices(project, chapter) {
  const counts = useCounts(project, chapter);
  const lead = project.setup?.protagonist;
  const due = duePressure(project, chapter);
  const inDue = new Set(due ? [due.source_agent, ...asList(due.bears_on)].filter(Boolean) : []);
  const all = (project.characters ?? []).map((c, order) => ({
    id: c.id, name: instanceName(c), uses: counts.characters[c.id] ?? 0, last: counts.lastSeen[c.id] ?? null, protagonist: c.id === lead,
    inPressure: inDue.has(c.id), order,
  }));
  const others = all.filter((c) => !c.protagonist)
    .sort((a, b) => Number(b.inPressure) - Number(a.inPressure) || a.uses - b.uses || (a.last ?? 0) - (b.last ?? 0) || a.order - b.order)
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
  const used = spotlightUse(project, except);
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
  if (cardLocked(project, "outline")) return { ok: false, reason: "outline_locked" };    // planning writes into the Outline card
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
  const labels = plantLabels(project);
  for (const e of eventsOf(project)) if (isFilled(e.planted)) names.set(e.id, labels.get(e.id) ?? e.planted.trim());   // a payoff names the plant it resolves
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

// The Entanglements the cast can see: ties they hold, what they hold, what they know, and (for the planner) every pressure. Each
// kind is cut to the few least used (usage.js), with everything the beat names kept. `beat` is the chapter's beat when there is
// one; for the planner it is only the pressure in focus.
export function entanglementsFor(schema, project, castIds, names, { allPressures, beat = null }) {
  const cast = asList(castIds);
  const e = settledProject(schema, project).entanglements;
  const used = usageOf(project);
  const nameOfId = (id) => names.get(id) ?? "";
  const planned = (items, label, extra = () => false) => new Set(items.filter((i) => plannedIds(beat, [i], label).size || extra(i)).map((i) => i.id));
  const pick = (key, items, label, extra, near) => choose(items, used, { planned: planned(items, label, extra), near })
    .map((i) => named(fieldDefs(schema, "entanglements", key), i, names));
  const touchesCast = (p) => [p.source_agent, ...asList(p.bears_on)].some((id) => cast.includes(id));
  const standing = (k) => [...asList(k.knows), ...asList(k.suspects), ...asList(k.misled)];
  const words = beatWords(beat);
  const placesAndThings = [...(project.world?.places ?? []), ...(project.world?.objects ?? [])];
  const thingName = (id) => placesAndThings.find((x) => x.id === id)?.name;
  return {
    ties: pick("ties", e.ties.filter((t) => cast.includes(t.tie_from)), () => "", (t) => cast.includes(t.tie_to)),
    holdings: pick("holdings", e.holdings.filter((h) => cast.includes(h.held_by)), () => "", (h) => Boolean(words) && mentions(words, thingName(h.holdee))),
    knowledge: pick("knowledge", e.knowledge.filter((k) => standing(k).some((id) => cast.includes(id))),
      () => "", (k) => (k.rule && k.rule === beat?.reveal_rule) || (Boolean(words) && mentions(words, k.rule ? (project.world?.rules ?? []).find((r) => r.id === k.rule)?.statement : k.fact)),
      (k) => standing(k).filter((id) => cast.includes(id)).length),
    pressures: pick("pressures", allPressures ? e.pressures : e.pressures.filter(touchesCast), () => "", () => false),
  };
}

const withCounts = (items, counts) => items.map((i) => ({ ...i, uses: counts[i.id] ?? 0 }));

// The places and things a request carries: the beat's own, then the least used, five in all (usage.js).
export function rotating(project, w, beat = null, except = null) {
  const used = usageOf(project, except);
  const cast = new Set(asList(beat?.cast));
  const held = new Map((project.entanglements?.holdings ?? []).map((h) => [h.holdee, h.held_by]));
  return {
    places: choose(w.places, used, { planned: plannedIds(beat, w.places, (p) => p.name) }),
    objects: choose(w.objects, used, { planned: plannedIds(beat, w.objects, (o) => o.name), near: (o) => Number(cast.has(held.get(o.id))) }),
  };
}

function worldFor(schema, project, castIds, names) {
  const w = settledProject(schema, project).world;
  const counts = useCounts(project, chapterInfo(project).next);
  const held = new Map((project.entanglements?.holdings ?? []).map((h) => [h.holdee, names.get(h.held_by) ?? ""]));
  const sent = rotating(project, w, null, chapterInfo(project).next);
  return {
    name: w.name, era_and_technology: w.era_and_technology, everyday_life: w.everyday_life,
    places: withCounts(sent.places, counts.places),
    objects: withCounts(sent.objects, counts.things).map((o) => ({ ...o, held_by: held.get(o.id) ?? "" })),
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
    world: { powers: w.powers, places: withCounts(rotating(project, w, null, chapter).places, counts.places) },
    entanglements: {
      ties: out("ties", choose(e.ties.filter((t) => touches(t.tie_from, t.tie_to)), counts.used)),
      holdings: out("holdings", choose(e.holdings.filter((h) => touches(h.held_by)), counts.used)),
      pressures: out("pressures", choose(e.pressures.filter((p) => touches(p.source_agent, asList(p.bears_on))), counts.used)),
    },
    latest_events: last,
    earlier_offstage: beatsOf(project).filter((b) => Number(b.chapter) < chapter && String(b.offstage_did ?? "").trim() !== "")
      .sort((a, b) => Number(a.chapter) - Number(b.chapter)).map((b) => ({ chapter: Number(b.chapter), did: b.offstage_did })),
  };
}

// What the planner is told about the goal: the current goal (none while a new one is needed, or once the story winds down), the
// state, the story's own goal when the chapters have moved off it, and the goal arc's advice for this chapter.
function goalFields(project, chapter, castIds, names) {
  const { arc, due, age } = goalDue(project, chapter);
  const advice = ["set", "stale", "twist"].includes(due);
  return {
    goal: arc.goal,
    goal_state: arc.state === "active" ? null : arc.state,
    story_goal: arc.story && arc.goal !== arc.story ? arc.story : null,
    goal_plan: {
      state: arc.state, due, age, since: arc.since,
      earlier_goals: arc.goals.filter((g) => g !== arc.goal),
      last_end: arc.lastEnd,
      directions: advice ? goalDirections(project, castIds, chapter, names) : [],
    },
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
    ...goalFields(project, chapter, castIds, names),
    cast: castCards(project, castIds).map(copyOf),
    world: worldFor(schema, project, castIds, names),
    entanglements: entanglementsFor(schema, project, castIds, names, { allPressures: true, beat: { spotlight: spotlight?.id, cast: castIds } }),
    spotlight: spotlight ? named(defs, spotlight, names) : {},
    legal_shifts: shiftsForChapter(project, chapter),
    open_plants: openPlants(project).map(({ text, chapter: c }) => ({ text, chapter: c })),
    available_reveals: availableReveals(project).map(({ statement, truth, status }) => ({ statement, truth, status })),
    use_counts: {
      characters: characters.map((c) => ({ name: instanceName(c), uses: counts.characters[c.id] ?? 0, last: counts.lastSeen[c.id] ?? null })),
      places: rotating(project, settledProject(schema, project).world, null, chapter).places.map((p) => ({ name: p.name, uses: counts.places[p.id] ?? 0 })),
      behaviors: characters.flatMap((c) => (c.behaviors ?? []).map((b) => ({ character: instanceName(c), state: b.state, uses: counts.behaviors[b.id] ?? 0 }))),
      things: rotating(project, settledProject(schema, project).world, null, chapter).objects.map((o) => ({ name: o.name, uses: counts.things[o.id] ?? 0 })),
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
  // A plant the story already has open is not new. Keep the beat's payoff for it, but plant nothing.
  if (isFilled(beat.plant)) {
    const same = (a, b) => String(a).trim().replace(/\s+/g, " ").toLowerCase().replace(/[.!?]+$/, "") === String(b).trim().replace(/\s+/g, " ").toLowerCase().replace(/[.!?]+$/, "");
    const known = (project.summary_events?.entries ?? []).some((e) => isFilled(e.planted) && same(e.planted, beat.plant));
    if (known) { dropped.push("plant"); beat.plant = ""; }
  }
  if (Array.isArray(beat.payoff)) beat.payoff = [...new Set(beat.payoff)];   // the same plant named twice pays it once
  if (existing) beat.id = existing.id;
  const spotlight = pickSpotlight(project, castIds, info.next);
  Object.assign(beat, {
    chapter: info.next, stale: false, cast: asList(castIds).slice(), spotlight: spotlight?.id ?? "",
    planned_from: entanglementsHash(schema, project),
    offstage_did: offstage?.did ?? "", offstage_reach: offstage?.reach ?? "",
  });
  if (info.next === 1) beat.when_gap = "";
  return { beat, unresolved, dropped, warnings: goalWarnings(project, beat, info.next) };
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
    .map((p) => joinList([p.message, p.fix].filter(Boolean), "sentence"));
}

