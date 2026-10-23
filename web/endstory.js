// The end of the story: after the last chapter the model updates Characters and World from what the records say happened.
// The page works out what to send, keeps what must not change, and stores the result as the after-story copy. The
// originals stay as they are. No DOM, so Node can test it.
//
// What the page insists on:
//   - every character comes back with the id it was sent, none missing and none new (otherwise the reply is refused);
//   - the fixed fields (name, age, sex, appearance) are put back as they were;
//   - a list item that comes back with an id the page knows keeps it, a new item gets a new id, and an item the model left
//     out stays as it was (the model may add to the world and change it, it does not delete);
//   - anything that does not fit a field (wrong kind, not one of the choices) is dropped and the field keeps its old value.

import { envelope, settledProject, isFilled, itemTitle, newId, validate, instanceName } from "./logic.js";
import { chapterInfo, eventsInWords, nameMap } from "./plan.js";

const copyOf = (value) => JSON.parse(JSON.stringify(value));

// {ok} or {ok: false, reason}: not_done (a chapter is still to write).
export function endGate(project) {
  const info = chapterInfo(project);
  if (!info.done) return { ok: false, reason: "not_done" };
  return { ok: true, replaces: Boolean(project.after_story) };
}

// What the model reads: the cards as they are, and the records in words (never the chapter text).
export function endStoryRequest(schema, project) {
  const settled = settledProject(schema, project);
  const names = nameMap(project);
  const beats = project.outline?.beats ?? [];
  const chapterOf = (id) => Number(beats.find((b) => b.id === id)?.chapter) || 0;
  const shifts = (project.summary_shifts?.shifts ?? [])
    .map((s) => ({ chapter: chapterOf(s.beat), character: names.get(s.character) ?? s.character,
      ...Object.fromEntries(["believes", "fears", "wants", "refuses", "decided"].filter((k) => isFilled(s[k])).map((k) => [k, s[k]])) }))
    .sort((a, b) => a.chapter - b.chapter);
  return {
    ...envelope(schema, project, "end_story"),
    style: copyOf(settled.style),
    setup: copyOf(settled.setup),
    characters: copyOf(settled.characters),
    world: copyOf(settled.world),
    events: eventsInWords(project),
    shifts,
  };
}

// ---- Taking the reply in ----------------------------------------------------------------

const kindOk = (field, value) => {
  if (field.input === "select-multiple") return Array.isArray(value) && value.every((v) => typeof v === "string");
  if (field.input === "number") return value === null || typeof value === "number";
  if (field.input === "checkbox") return typeof value === "boolean";
  if (field.options?.length) return typeof value === "string" && (value === "" || field.options.some((o) => o.value === value));
  return typeof value === "string";
};

// One set of fields: the model's value where it fits, the old one where it does not. `fixedBack` collects the fixed fields
// the model changed, `dropped` the keys that did not fit.
function landFields(fields, was, given, taken, track) {
  const out = { ...was };
  for (const field of fields) {
    if (!(field.key in given)) continue;
    const value = given[field.key];
    if (field.fixed) {
      if (JSON.stringify(value) !== JSON.stringify(was[field.key])) track.forced.push(field.key);
      continue;
    }
    if (field.repeat) {
      if (!Array.isArray(value) || !value.every((i) => i && typeof i === "object" && !Array.isArray(i))) { track.dropped.push(field.key); continue; }
      const old = was[field.key] ?? [];
      const ids = new Map(old.map((i) => [i.id, i]));
      const seen = new Set();
      const items = value.map((item) => {
        const before = ids.get(item.id);
        const id = before && !seen.has(item.id) ? item.id : newId(taken);
        seen.add(id);
        taken.push(id);
        return { ...landFields(field.item_fields ?? [], before ?? {}, item, taken, { forced: [], dropped: track.dropped }), id };
      });
      for (const left of old) if (!seen.has(left.id)) items.push(left);      // left out: stays as it was
      out[field.key] = items;
    } else if (kindOk(field, value)) {
      out[field.key] = value;
    } else {
      track.dropped.push(field.key);
    }
  }
  return out;
}

// The model's reply (checked by readEndStoryReply) as the after-story copy:
//   {ok: true, after: {style, characters, world}, forced: [{character, fields}], dropped: [key]}
// or a bad_output failure when the characters do not come back as they were sent.
export function landEndStory(schema, project, read) {
  const settled = settledProject(schema, project);
  const sent = settled.characters.map((c) => c.id);
  const got = read.characters.map((c) => c.id);
  const same = sent.length === got.length && sent.every((id) => got.includes(id)) && new Set(got).size === got.length;
  if (!same) return { ok: false, error: { kind: "bad_output", detail: "The updated characters must be the same people, each with the id it was sent with." } };
  const taken = [];
  const forced = [];
  const dropped = [];
  const characters = settled.characters.map((was) => {
    const track = { forced: [], dropped };
    const next = landFields(schema.cards.characters.fields, was, read.characters.find((c) => c.id === was.id), taken, track);
    if (track.forced.length) forced.push({ character: instanceName(was), fields: track.forced });
    next.id = was.id;
    return next;
  });
  const world = landFields(schema.cards.world.fields, settled.world, read.world, taken, { forced: [], dropped });
  if (settled.world.id) world.id = settled.world.id;
  return { ok: true, after: { style: copyOf(settled.style), characters, world }, forced, dropped: [...new Set(dropped)] };
}

// ---- What changed, for the review ---------------------------------------------------------------

const titleOf = (field, item) => itemTitle(field, item) || ["name", "state", "statement", "term"].map((k) => item[k]).find(isFilled) || "(untitled)";
const words = (value) => (Array.isArray(value) ? value.join(", ") : value === null || value === undefined ? "" : String(value));

// The differences between the cards now and the after-story copy, in words:
//   [{card: "characters"|"world", who, field, label, kind: "changed"|"added", before, after}]
export function afterStoryChanges(schema, project, after) {
  const settled = settledProject(schema, project);
  const out = [];
  const compare = (card, who, fields, was, now) => {
    for (const field of fields) {
      if (field.repeat) {
        const old = new Map((was[field.key] ?? []).map((i) => [i.id, i]));
        for (const item of now[field.key] ?? []) {
          const before = old.get(item.id);
          const title = titleOf(field, item);
          if (!before) out.push({ card, who, field: field.key, label: field.label, kind: "added", before: "", after: title });
          else if (JSON.stringify(before) !== JSON.stringify(item)) {
            const keys = (field.item_fields ?? []).filter((d) => JSON.stringify(before[d.key]) !== JSON.stringify(item[d.key]));
            for (const d of keys) out.push({ card, who, field: field.key, label: `${field.label}, ${title}: ${d.label ?? d.key}`, kind: "changed", before: words(before[d.key]), after: words(item[d.key]) });
          }
        }
      } else if (JSON.stringify(was[field.key]) !== JSON.stringify(now[field.key])) {
        out.push({ card, who, field: field.key, label: field.label ?? field.key, kind: "changed", before: words(was[field.key]), after: words(now[field.key]) });
      }
    }
  };
  for (const now of after.characters) {
    compare("characters", instanceName(now), schema.cards.characters.fields, settled.characters.find((c) => c.id === now.id), now);
  }
  compare("world", settled.world.name ?? "", schema.cards.world.fields, settled.world, after.world);
  return out;
}

// ---- Editing the copy, and knowing when it is out of date -----------------------------------------

// A short fingerprint (8 hex digits, FNV-1a) of what the model read at the end: every written chapter, and the records of what
// happened and how people changed. A chapter written again changes the records even when its words come out the same; undoing
// that puts the fingerprint back. The order things are stored in does not matter.
export function chaptersFingerprint(project) {
  const byId = (list) => [...(list ?? [])].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const text = JSON.stringify([
    byId(project.chapters).map((c) => [c.id, c.text ?? ""]),
    byId(project.summary_events?.entries),
    byId(project.summary_shifts?.shifts),
  ]);
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) { hash ^= text.charCodeAt(i); hash = Math.imul(hash, 0x01000193) >>> 0; }
  return hash.toString(16).padStart(8, "0");
}

// True when the copy was made from chapters that have since been written again. A copy with no fingerprint (made before this was
// kept) is never called out of date, since nothing says it is.
export function afterStoryStale(project) {
  const made = project.end_note?.made_from;
  if (!project.after_story || typeof made !== "string" || !made) return false;
  return made !== chaptersFingerprint(project);
}

// The project as the copy's cards should see it while the writer edits them: the same project, with the copy's style,
// characters and world in place of the originals. The copy's own objects are shared, not duplicated, so editing a form edits the copy.
export function afterStoryView(schema, project) {
  return { ...settledProject(schema, project), style: project.after_story.style, characters: project.after_story.characters, world: project.after_story.world };
}

// Block problems in the copy, counted per card, so the review can say the copy is not as clean as the original.
export function afterStoryProblems(schema, project, after) {
  const settled = { ...settledProject(schema, project), characters: after.characters, world: after.world };
  let count = 0;
  for (const c of after.characters) count += validate(schema.cards.characters, c, settled, schema.common).problems.filter((p) => p.severity === "block").length;
  count += validate(schema.cards.world, after.world, settled, schema.common).problems.filter((p) => p.severity === "block").length;
  return count;
}
