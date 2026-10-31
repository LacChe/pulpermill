// The end of the story: after the last chapter the page folds every shift into the cards, with no model call (P0, A9). The
// result is stored as the after-story copy (Style, Characters, World and the final Entanglements), and the originals stay as
// they are. No DOM, so Node can test it.

import { settledProject, isFilled, validate, instanceName, lookupLabel } from "./logic.js";
import { foldAll } from "./effective.js";
import { chapterInfo } from "./plan.js";
import { msg, joinList } from "./text.js";

const copyOf = (value) => JSON.parse(JSON.stringify(value));

// {ok} or {ok: false, reason}: not_done (a chapter is still to write).
export function endGate(project) {
  const info = chapterInfo(project);
  if (!info.done) return { ok: false, reason: "not_done" };
  return { ok: true, replaces: Boolean(project.after_story) };
}

// The after-story copy: the cards as the story left them. Style is copied as it is; Characters, World and Entanglements are the base
// cards with every shift applied, so every original id is kept. {ok: true, after} or {ok: false, reason}.
export function makeAfterStory(project) {
  const gate = endGate(project);
  if (!gate.ok) return gate;
  const folded = foldAll(project);
  return { ok: true, after: { style: copyOf(project.style ?? {}), characters: folded.characters ?? [], world: folded.world ?? {}, entanglements: folded.entanglements ?? {} } };
}

// ---- What changed, for the review ---------------------------------------------------------------

const words = (value) => (Array.isArray(value) ? joinList(value) : value === null || value === undefined ? "" : String(value));

// A list item in a few words: its first two filled values, links by the name they point at.
function titleOf(view, field, item) {
  const parts = (field.item_fields ?? []).filter((d) => isFilled(item[d.key])).slice(0, 2)
    .map((d) => (d.ref ? lookupLabel(view, d, item[d.key]) : words(item[d.key])));
  return parts.join(" · ") || msg("endstory.untitled");
}

// The differences between the cards now and the after-story copy, in words:
//   [{card, who, field, label, kind: "changed"|"added"|"removed", before, after}]
export function afterStoryChanges(schema, project, after) {
  const settled = settledProject(schema, project);
  const view = settledProject(schema, { ...project, characters: after.characters, world: after.world, entanglements: after.entanglements });   // the copy, settled the same way
  after = { characters: view.characters, world: view.world, entanglements: view.entanglements };
  const out = [];
  const compare = (card, who, fields, was, now) => {
    for (const field of fields) {
      if (field.repeat) {
        const old = new Map((was[field.key] ?? []).map((i) => [i.id, i]));
        const kept = new Set();
        for (const item of now[field.key] ?? []) {
          const before = old.get(item.id);
          kept.add(item.id);
          const title = titleOf(view, field, item);
          if (!before) out.push({ card, who, field: field.key, label: field.label, kind: "added", before: "", after: title });
          else if (JSON.stringify(before) !== JSON.stringify(item)) {
            for (const d of (field.item_fields ?? []).filter((x) => JSON.stringify(before[x.key]) !== JSON.stringify(item[x.key]))) {
              out.push({ card, who, field: field.key, label: msg("endstory.partOf", { field: field.label, title, part: d.label ?? d.key }), kind: "changed", before: words(before[d.key]), after: words(item[d.key]) });
            }
          }
        }
        for (const [id, item] of old) if (!kept.has(id)) out.push({ card, who, field: field.key, label: field.label, kind: "removed", before: titleOf(settled, field, item), after: "" });
      } else if (JSON.stringify(was[field.key]) !== JSON.stringify(now[field.key])) {
        out.push({ card, who, field: field.key, label: field.label ?? field.key, kind: "changed", before: words(was[field.key]), after: words(now[field.key]) });
      }
    }
  };
  for (const now of after.characters) {
    const was = settled.characters.find((c) => c.id === now.id);
    if (was) compare("characters", instanceName(now), schema.cards.characters.fields, was, now);
  }
  compare("world", settled.world.name ?? "", schema.cards.world.fields, settled.world, after.world);
  compare("entanglements", schema.cards.entanglements.label, schema.cards.entanglements.fields, settled.entanglements, after.entanglements);
  return out;
}

// ---- Editing the copy, and knowing when it is out of date -----------------------------------------

// A short fingerprint (8 hex digits, FNV-1a) of what the copy was made from: every written chapter and the records of what
// happened and what changed. A chapter written again changes the records even when its words come out the same; undoing that
// puts the fingerprint back. The order things are stored in does not matter.
export function chaptersFingerprint(project) {
  const byId = (list) => [...(list ?? [])].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const text = JSON.stringify([
    byId(project.chapters).map((c) => [c.id, c.text ?? ""]),
    byId(project.summary_events?.entries),
    byId(project.shifts?.entries),
  ]);
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) { hash ^= text.charCodeAt(i); hash = Math.imul(hash, 0x01000193) >>> 0; }
  return hash.toString(16).padStart(8, "0");
}

// True when the copy was made from chapters that have since been written again. A copy with no fingerprint is never called out of date.
export function afterStoryStale(project) {
  const made = project.end_note?.made_from;
  if (!project.after_story || typeof made !== "string" || !made) return false;
  return made !== chaptersFingerprint(project);
}

// The project as the copy's cards should see it while the writer edits them: the same project, with the copy's cards in place of the
// originals. The copy's own objects are shared, not duplicated, so editing a form edits the copy.
export function afterStoryView(schema, project) {
  return { ...settledProject(schema, project), style: project.after_story.style, characters: project.after_story.characters, world: project.after_story.world, entanglements: project.after_story.entanglements };
}

// Block problems in the copy, counted, so the review can say the copy is not as clean as the original.
export function afterStoryProblems(schema, project, after) {
  const settled = { ...settledProject(schema, project), characters: after.characters, world: after.world, entanglements: after.entanglements };
  let count = 0;
  const blocking = (card, values) => validate(schema.cards[card], values, settled, schema.common).problems.filter((p) => p.severity === "block").length;
  for (const c of after.characters) count += blocking("characters", c);
  count += blocking("world", after.world);
  count += blocking("entanglements", after.entanglements);
  return count;
}
