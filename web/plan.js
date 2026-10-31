// Planning the next chapter: everything the page works out in code, and the request it sends the model. No DOM, so Node can
// test it. The backend is stateless and never applies a shift, so the page works out the effective cards (effective.js),
// picks the spotlight tie and the cast, reduces the lists with seeded random picks (pick.js) and sends the result; the
// model only fills the beat's planner fields (where, when_time, aim, plan).
//
// The chapter is about one tie, the spotlight: code picks one at random and the writer may change it. The cast always holds
// the protagonist and the two characters of that tie (a group is never cast). The beat remembers a hash of what its plan was
// made from, so a later change to those inputs marks the plan stale (it is never replanned by itself).

import { envelope, blankItem, wordsToId, validate, isFilled, settledProject, findInstance, lookupLabel } from "./logic.js";
import { effectiveProject } from "./effective.js";
import { pickMany, rng, projectSeed, PICK_MAX } from "./pick.js";
import { storyStarted, cardLocked } from "./gate.js";
import { watch } from "./undo.js";
import { joinList, msg } from "./text.js";

export const CAST_MAX = 5;               // the beat's cast, protagonist included (the schema's max_selected)

const copyOf = (value) => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)));
const beatsOf = (project) => project.outline?.beats ?? [];
const eventsOf = (project) => project.summary_events?.entries ?? [];
const asList = (value) => (Array.isArray(value) ? value : isFilled(value) ? [value] : []);
const BEAT_FIELD = (schema) => schema.cards.outline.fields.find((f) => f.key === "beats");

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

export const chapterOfBeat = (project, id) => Number(beatsOf(project).find((b) => b.id === id)?.chapter) || null;

const isCharacter = (project, id) => (project.characters ?? []).some((c) => c.id === id);
const groupIds = (project) => new Set((project.world?.powers ?? []).map((g) => g.id));

// ---- The spotlight and the cast ------------------------------------------------

// The tie the chapter is about: one of the ties as they stand going into the chapter (shifts included), picked at random from
// the project and the chapter, so asking again gives the same tie. Null when there is no tie.
export function pickSpotlight(project, chapter) {
  const ties = effectiveProject(project, chapter).entanglements?.ties ?? [];
  if (!ties.length) return null;
  const next = rng(projectSeed(project), chapter, "spotlight");
  return copyOf(ties[Math.floor(next() * ties.length)]);
}

// Who the chapter must have: the protagonist and the characters at the two ends of the spotlight tie (an end that is a group is
// not cast). `project` should be the effective project when the tie may have come from a shift.
export function requiredCast(project, spotlightId) {
  const tie = (project.entanglements?.ties ?? []).find((t) => t.id === spotlightId);
  const ids = [];
  const add = (id) => { if (isFilled(id) && isCharacter(project, id) && !ids.includes(id)) ids.push(id); };
  add(project.setup?.protagonist);
  if (tie) { add(tie.tie_from); add(tie.tie_to); }
  return ids;
}

// Every tie among the cast, every tie between a cast member and a group, and a tie between two groups when one of them touches
// the cast (P0, decision 6). A tie to a character who is not in the cast is not sent.
export function tiesInPlay(project, cast) {
  const people = new Set(asList(cast));
  const groups = groupIds(project);
  const ties = project.entanglements?.ties ?? [];
  const chosen = new Set();
  const touching = new Set();
  for (const t of ties) {
    const from = people.has(t.tie_from);
    const to = people.has(t.tie_to);
    if (from && to) chosen.add(t.id);
    else if (from && groups.has(t.tie_to)) { chosen.add(t.id); touching.add(t.tie_to); }
    else if (to && groups.has(t.tie_from)) { chosen.add(t.id); touching.add(t.tie_from); }
  }
  for (const t of ties) {
    if (groups.has(t.tie_from) && groups.has(t.tie_to) && (touching.has(t.tie_from) || touching.has(t.tie_to))) chosen.add(t.id);
  }
  return ties.filter((t) => chosen.has(t.id)).map(copyOf);
}

// The groups that appear at the end of a tie in play.
export function groupsInPlay(project, cast) {
  const groups = groupIds(project);
  const ends = new Set(tiesInPlay(project, cast).flatMap((t) => [t.tie_from, t.tie_to]).filter((id) => groups.has(id)));
  return (project.world?.powers ?? []).filter((g) => ends.has(g.id)).map(copyOf);
}

// What the cast, and the groups in play, hold.
export function holdingsInPlay(project, cast) {
  const holders = new Set([...asList(cast), ...groupsInPlay(project, cast).map((g) => g.id)]);
  return (project.entanglements?.holdings ?? []).filter((h) => holders.has(h.held_by)).map(copyOf);
}

// A new beat for a chapter: the code's fields are set, the spotlight is picked, and the cast starts as the required cast. The
// planner's fields are blank. `chapter` defaults to the next one to write.
export function newBeat(schema, project, chapter = chapterInfo(project).next) {
  const taken = beatsOf(project).map((b) => b.id);
  const eff = effectiveProject(project, chapter);
  const tie = pickSpotlight(project, chapter);
  return { ...blankItem(BEAT_FIELD(schema), taken), chapter, stale: false, cast: requiredCast(eff, tie?.id), spotlight: tie?.id ?? "", planned_from: null };
}

// The unwritten beat for the next chapter, made and put in the Outline when there is none yet. Returns it.
export function ensureBeat(schema, project) {
  const chapter = chapterInfo(project).next;
  const existing = beatForChapter(project, chapter);
  if (existing) return existing;
  const beat = newBeat(schema, project, chapter);
  placeBeat(project, beat);
  return beat;
}

// Whether a cast can be used: the protagonist is in, there are at most CAST_MAX, everyone exists, and (when the spotlight is
// given) both characters of the spotlight tie are in. Returns null, or why not: empty, too_many, no_protagonist, unknown, spotlight_pair.
export function castProblem(project, castIds, spotlightId = null) {
  const ids = asList(castIds);
  if (!ids.length) return "empty";
  if (ids.length > CAST_MAX) return "too_many";
  if (!ids.includes(project.setup?.protagonist)) return "no_protagonist";
  if (ids.some((id) => !findInstance(project, { id: "characters", many_per_project: true }, id))) return "unknown";
  if (spotlightId && requiredCast({ ...project, setup: { ...project.setup, protagonist: null } }, spotlightId).some((id) => !ids.includes(id))) return "spotlight_pair";
  return null;
}

// The spotlight changed to another tie: the beat's new spotlight and cast. The cast keeps everyone the writer added, drops the two
// characters the old tie required (unless the new tie needs them too) and gains the characters the new tie requires. The protagonist
// stays. The required members come first, and the cast never goes over CAST_MAX (it is the extras that are cut). Used by the plan
// panel's picker; `project` is any project, the effective cards are worked out here.
export function withSpotlight(project, beat, spotlightId) {
  const eff = effectiveProject(project, Number(beat.chapter));
  const before = requiredCast(eff, beat.spotlight);
  const extras = asList(beat.cast).filter((id) => !before.includes(id));
  const required = requiredCast(eff, spotlightId);
  const cast = [...required, ...extras.filter((id) => !required.includes(id))].slice(0, Math.max(CAST_MAX, required.length));
  return { spotlight: spotlightId, cast };
}

// A tie in words, for the plan panel: "Suvi and Ola, mother (edge: to care for him)". Ends are named by their cards, a group by its
// name. Returns {from, to, bond, edge, text}. `project` should be the effective project, so a tie a shift made reads right.
export function tieInWords(schema, project, tie) {
  const defs = schema.cards.entanglements.fields.find((f) => f.key === "ties").item_fields;
  const end = (key) => lookupLabel(project, defs.find((d) => d.key === key), tie[key]);
  const out = { from: end("tie_from"), to: end("tie_to"), bond: tie.bond ?? "", edge: tie.edge ?? "" };
  return { ...out, text: msg(out.edge ? "plan.tieWords" : "plan.tieWordsNoEdge", out) };
}

// ---- What the model is sent ------------------------------------------------------------

const placeName = (project, id) => (project.world?.places ?? []).find((p) => p.id === id)?.name ?? "";

// A beat in words, the way the writer reads it: its place by name, and no ids or code fields.
export function beatInWords(project, beat) {
  return { where: placeName(project, beat.where), when_time: beat.when_time ?? "", aim: beat.aim ?? "", plan: beat.plan ?? "" };
}

// Earlier beats in words for the planner: chapter, where, when, aim and plan.
export function earlierBeats(project, chapter) {
  return beatsOf(project).filter((b) => Number(b.chapter) < chapter).sort((a, b) => a.chapter - b.chapter)
    .map((b) => ({ chapter: Number(b.chapter), where: placeName(project, b.where), when: b.when_time ?? "", aim: b.aim ?? "", plan: b.plan ?? "" }));
}

// Earlier Events entries in words: chapter, what happened and what changed.
export function eventsInWords(project, upTo = Infinity) {
  return eventsOf(project)
    .map((e) => ({ chapter: chapterOfBeat(project, e.beat), happened: e.happened, changed: e.changed ?? "" }))
    .filter((e) => e.chapter !== null && e.chapter <= upTo)
    .sort((a, b) => a.chapter - b.chapter);
}

// What the cast, the world and their entanglements look like to the model: the effective cards (`project` is an effective
// project) reduced to what the scene needs, with every list cut to at most PICK_MAX by seeded picks. Always kept: the cast's own
// cards, the beat's `where`, and the places and objects held by the cast or the groups in play.   {cast, world, ties, holdings}
export function scene(project, chapter, castIds, { where = null } = {}) {
  const seed = projectSeed(project);
  const cast = asList(castIds);
  const holdings = holdingsInPlay(project, cast);
  const held = holdings.map((h) => h.holdee);
  const pick = (salt, items, must = []) => pickMany(items, PICK_MAX, rng(seed, chapter, salt), { must });
  const w = project.world ?? {};
  const people = cast.map((id) => (project.characters ?? []).find((c) => c.id === id)).filter(Boolean).map((c) => {
    const out = copyOf(c);
    if (Array.isArray(out.behaviors)) out.behaviors = pick(`behaviors:${c.id}`, out.behaviors);
    return out;
  });
  return {
    cast: people,
    world: {
      ...copyOf(w),
      places: pick("places", copyOf(w.places ?? []), [where, ...held]),
      objects: pick("objects", copyOf(w.objects ?? []), held),
      powers: groupsInPlay(project, cast),
      rules: pick("rules", copyOf(w.rules ?? [])),
      terms: pick("terms", copyOf(w.terms ?? [])),
    },
    ties: tiesInPlay(project, cast),
    holdings,
  };
}

// ---- The stale-plan hash ------------------------------------------------------------

export function hashText(text) {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, "0");
}

// A short fingerprint of what a plan is made from: the spotlight, the effective cast cards, the ties in play and the picks (the
// lists are cut by the same seeded picks the request uses, without the place the plan itself chose).
export function planInputsHash(project, beat) {
  const chapter = Number(beat.chapter);
  return hashText(JSON.stringify([beat.spotlight ?? "", scene(effectiveProject(project, chapter), chapter, beat.cast)]));
}

// The plan was made from inputs that have changed since.
export function planIsStale(project, beat) {
  return Boolean(beat?.planned_from) && beat.planned_from !== planInputsHash(project, beat);
}

// ---- Can a chapter be planned? -------------------------------------------------------

// {ok, chapter} or {ok: false, reason}: not_started, outline_locked, done, no_tie, cast (with `why`).
export function planGate(project, beat) {
  if (!storyStarted(project)) return { ok: false, reason: "not_started" };
  if (cardLocked(project, "outline")) return { ok: false, reason: "outline_locked" };    // planning writes into the Outline card
  const info = chapterInfo(project);
  if (info.done) return { ok: false, reason: "done" };
  const chapter = Number(beat?.chapter) || info.next;
  const eff = effectiveProject(project, chapter);
  if (!(eff.entanglements?.ties ?? []).some((t) => t.id === beat?.spotlight)) return { ok: false, reason: "no_tie" };
  const why = castProblem(eff, beat.cast, beat.spotlight);
  if (why) return { ok: false, reason: "cast", why };
  return { ok: true, chapter };
}

// ---- The plan request --------------------------------------------------------------------

// Plan chapter `beat.chapter`. `beat` holds the spotlight and the cast (the page's own picks, which the writer may have changed).
// `retry` is {beat, problems} when the first try was refused by the Outline's block rules.
export function planRequest(schema, project, beat, { retry = null } = {}) {
  const chapter = Number(beat.chapter);
  const eff = effectiveProject(project, chapter);
  const request = {
    ...envelope(schema, project, "plan"),
    chapter, chapter_count: chapterInfo(project).count,
    style: copyOf(eff.style ?? {}),
    setup: copyOf(eff.setup ?? {}),
    protagonist: eff.setup?.protagonist ?? "",
    ...scene(eff, chapter, beat.cast),
    spotlight: beat.spotlight,
    earlier_beats: earlierBeats(eff, chapter),
    earlier_events: eventsInWords(eff, chapter - 1),
  };
  if (retry) request.retry = { beat: copyOf(retry.beat), problems: [...retry.problems] };
  return request;
}

// ---- Landing the beat ------------------------------------------------------------------------

// The model's beat (links in words) as the beat with ids: {beat, unresolved, dropped, warnings}.
//   beat        `existing` with its planner fields replaced; the code and human fields (id, chapter, cast, spotlight) are kept and
//               planned_from is the hash of what this plan was made from
//   unresolved  links that matched nothing or two entries (left empty): [{field, key, words, why}]
//   dropped     keys the model gave that were not usable (not a planner field, or text of the wrong kind)
export function landBeat(schema, project, existing, reply) {
  const chapter = Number(existing.chapter);
  const eff = effectiveProject(project, chapter);
  const planner = BEAT_FIELD(schema).item_fields.filter((f) => f.filled_by === "planner");
  const given = reply.beat ?? {};
  const beat = copyOf(existing);
  const unresolved = [];
  const dropped = Object.keys(given).filter((key) => !planner.some((f) => f.key === key));
  for (const def of planner) {
    if (!(def.key in given)) continue;
    const value = given[def.key];
    if (typeof value !== "string") { dropped.push(def.key); continue; }
    if (def.ref) {
      const found = wordsToId(eff, def.ref, value);
      if (!found.id) { unresolved.push({ field: "beats", key: def.key, words: value, why: found.several ? "several" : "none" }); beat[def.key] = ""; continue; }
      beat[def.key] = found.id;
    } else {
      beat[def.key] = value.trim();
    }
  }
  Object.assign(beat, { chapter, stale: false });
  beat.planned_from = planInputsHash(project, beat);
  return { beat, unresolved, dropped, warnings: [] };
}

// Puts the beat into the outline: replaces the beat with the same id, or adds it. Returns what it replaced.
export function placeBeat(project, beat) {
  const outline = project.outline ?? (project.outline = { beats: [] });
  const beats = outline.beats ?? (outline.beats = []);
  const at = beats.findIndex((b) => b.id === beat.id);
  if (at >= 0) { const was = beats[at]; beats[at] = beat; return was; }
  beats.push(beat);
  return null;
}

// Lands a plan: puts the beat in the Outline as one commit. Returns {undo}: it puts the Outline back as it was and answers true, or
// answers false and changes nothing when the Outline was edited since.
export function commitPlan(project, beat) {
  const undo = watch(project, ["outline"]);
  placeBeat(project, beat);
  undo.settle();
  return { undo: () => undo.undo() };
}

// The blocking problems the Outline card's own rules find in one beat, as the words the writer would read. This is what the
// retry sends back to the model, and what stops Generate when the second attempt still fails. The beat is checked against the
// cards as they stood going into its chapter.
export function beatBlockers(schema, project, beat) {
  const trial = effectiveProject(project, Number(beat.chapter));
  placeBeat(trial, copyOf(beat));
  const settled = settledProject(schema, trial);
  return validate(schema.cards.outline, settled.outline, settled, schema.common)
    .problems.filter((p) => p.severity === "block" && p.item === beat.id)
    .map((p) => joinList([p.message, p.fix].filter(Boolean), "sentence"));
}
