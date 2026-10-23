// Getting the story out: the chapters as one markdown file, and each portable card as its own JSON file. No DOM, so Node can
// test it. (The project file is the Save button's.)
//
// A card file looks like this, and readCardFile reads it back:
//   { "pulpermill_card": "characters", "schema_version": 1, "values": { ...the card's fields, ids included... } }
// Only the portable cards go out: Style, each Character, and World. The others (Entanglements, Setup, Outline) point at ids
// in this one story, so they mean nothing in another. When the story has an after-story copy, its cards go out too, named
// "after-story".
//
// Bringing a card file in (planImport, applyImport) is the other way round, and only into a card that is not locked. A
// character comes in as a new character or in place of one the writer already has; Style and World replace the card.
// planImport changes nothing: it says what would happen, so the page can show it first. applyImport does it and hands back an undo.

import {
  settledProject, instanceName, blankCard, blankItem, newId, isFilled, sameValue, ensureCard, findInstance, removeInstance, setCardValues,
} from "./logic.js";
import { cardLocked } from "./gate.js";
import { chapterInfo } from "./plan.js";

export const CARD_FILE_KEY = "pulpermill_card";
export const PORTABLE = ["style", "characters", "world"];

const slug = (text, fallback) => String(text ?? "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 40).replace(/-+$/g, "") || fallback;

// The story: the title, then every written chapter in order.
export function storyMarkdown(project) {
  const beats = project.outline?.beats ?? [];
  const number = (c) => Number(beats.find((b) => b.id === c.beat)?.chapter) || 0;
  const chapters = [...(project.chapters ?? [])].sort((a, b) => number(a) - number(b));
  const title = String(project.title ?? "").trim() || "Untitled story";
  return `${[`# ${title}`, ...chapters.map((c) => `## Chapter ${number(c)}\n\n${c.text.trim()}`)].join("\n\n")}\n`;
}

export function storyFileName(project) {
  return `${slug(project.title, "untitled")}-story.md`;
}

// One card as the text of a file.
export function cardFileText(schema, cardId, values) {
  return `${JSON.stringify({ [CARD_FILE_KEY]: cardId, schema_version: schema.schema_version, values }, null, 2)}\n`;
}

// Every card file the project can give: [{name, label, text}].
export function cardFiles(schema, project) {
  const settled = settledProject(schema, project);
  const base = slug(project.title, "untitled");
  const files = [];
  const add = (prefix, label, cardId, values, part) => files.push({
    name: `${base}${prefix ? `-${prefix}` : ""}${part}.json`, label, text: cardFileText(schema, cardId, values),
  });
  const set = (prefix, labelPrefix, cards) => {
    add(prefix, `${labelPrefix}${schema.cards.style.label}`, "style", cards.style, "-style");
    cards.characters.forEach((c, at) => {
      const name = instanceName(c);
      add(prefix, `${labelPrefix}${name || `Character ${at + 1}`}`, "characters", c, `-character-${at + 1}-${slug(name, "unnamed")}`);
    });
    add(prefix, `${labelPrefix}${schema.cards.world.label}`, "world", cards.world, "-world");
  };
  set("", "", settled);
  if (project.after_story) set("after-story", "After the story: ", { style: project.after_story.style, characters: project.after_story.characters, world: project.after_story.world });
  return files;
}

// What the story export offers right now: {chapters, total}.
export function storyCounts(project) {
  const info = chapterInfo(project);
  return { chapters: info.written, total: info.count };
}

// ---- Reading a card file back ------------------------------------------------------------------
const isObject = (v) => v && typeof v === "object" && !Array.isArray(v);

// What kind of file this is, so each button can say where a wrong file belongs: "card", "project", "other" or "unreadable".
export function fileKind(text) {
  let data;
  try { data = JSON.parse(String(text).replace(/^\uFEFF/, "")); } catch { return "unreadable"; }
  if (!isObject(data)) return "other";
  if (typeof data[CARD_FILE_KEY] === "string") return "card";
  return Number.isInteger(data.schema_version) ? "project" : "other";
}

// Is this one value the right kind for its field? A choice must be one of the field's options when the field lists them
// (a choice that points at other cards has no fixed list, so only its kind is checked).
function fits(field, value) {
  const options = (field.options ?? []).map((o) => o.value);
  switch (field.input) {
    case "select-multiple": return Array.isArray(value) && value.every((v) => typeof v === "string" && (!options.length || options.includes(v)));
    case "number": return value === null || (typeof value === "number" && Number.isFinite(value));
    case "checkbox": return typeof value === "boolean";
    case "select": return typeof value === "string" && (value === "" || !options.length || options.includes(value));
    default: return typeof value === "string";
  }
}

// One list item with only the parts that fit; `bad` names the parts left out.
function cleanItem(field, item) {
  const defs = new Map((field.item_fields ?? []).map((f) => [f.key, f]));
  const out = {};
  const bad = [];
  for (const [key, value] of Object.entries(item)) {
    if (key === "id") { if (typeof value === "string" && value) out.id = value; continue; }
    if (defs.has(key) && fits(defs.get(key), value)) out[key] = value; else bad.push(key);
  }
  return { out, bad };
}

// {ok: true, card, values, ignored: [keys]} or {ok: false, reason}: unreadable, not_card_file, unknown_card, not_portable, newer, damaged.
// Only keys the card has are kept (ignored lists the rest); a value of the wrong kind is ignored too, and so is a part of a
// list item that does not fit (the rest of the item stays). A character file gives one character.
export function readCardFile(text, schema) {
  let data;
  try { data = JSON.parse(String(text).replace(/^\uFEFF/, "")); } catch { return { ok: false, reason: "unreadable" }; }
  if (!isObject(data) || typeof data[CARD_FILE_KEY] !== "string" || !isObject(data.values)) return { ok: false, reason: "not_card_file" };
  const card = schema.cards[data[CARD_FILE_KEY]];
  if (!card) return { ok: false, reason: "unknown_card" };
  if (!PORTABLE.includes(card.id)) return { ok: false, reason: "not_portable" };
  if (Number.isInteger(data.schema_version) && data.schema_version > schema.schema_version) return { ok: false, reason: "newer" };
  if (!card.fields.length) return { ok: false, reason: "damaged" };
  const values = {};
  const ignored = [];
  for (const [key, value] of Object.entries(data.values)) {
    if (key === "id") { if (typeof value === "string" && value) values.id = value; continue; }
    const field = card.fields.find((f) => f.key === key);
    if (!field) { ignored.push(key); continue; }
    if (field.repeat) {
      if (!Array.isArray(value) || !value.every(isObject)) { ignored.push(key); continue; }
      const items = value.map((item) => cleanItem(field, item));
      values[key] = items.map((i) => i.out);
      if (items.some((i) => i.bad.length)) ignored.push(key);
    } else if (fits(field, value)) values[key] = value;
    else ignored.push(key);
  }
  return { ok: true, card: card.id, values, ignored };
}

// ---- Bringing a card in ------------------------------------------------------------------------
const copy = (value) => JSON.parse(JSON.stringify(value));

// Links from other cards into the world's places, things, groups and rules that a replaced world would leave pointing at
// nothing: {count, cards: [labels]}, or null when none. A link to something the new world also holds (same id) stays good.
export function linksLost(schema, project, nextWorld) {
  const gone = new Map();
  for (const key of ["places", "objects", "powers", "rules"]) {
    const after = new Set((nextWorld[key] ?? []).map((i) => i.id));
    gone.set(`world.${key}`, new Set((project.world?.[key] ?? []).map((i) => i.id).filter((id) => !after.has(id))));
  }
  let count = 0;
  const cards = new Set();
  const look = (cardId, def, value) => {
    for (const one of Array.isArray(value) ? value : [value]) {
      if (isFilled(one) && def.ref.some((source) => gone.get(source)?.has(one))) { count += 1; cards.add(schema.cards[cardId].label); }
    }
  };
  for (const cardId of Object.keys(schema.cards)) {
    if (cardId === "world") continue;
    const card = schema.cards[cardId];
    for (const holder of card.many_per_project ? project[cardId] ?? [] : [project[cardId] ?? {}]) {
      for (const field of card.fields) {
        if (field.repeat) {
          for (const item of holder[field.key] ?? []) for (const def of field.item_fields ?? []) if (def.ref) look(cardId, def, item[def.key]);
        } else if (field.ref) look(cardId, field, holder[field.key]);
      }
    }
  }
  return count ? { count, cards: [...cards] } : null;
}

// What bringing this card file in would do, without doing it. `read` is what readCardFile gave.
// choice (Characters only): {mode: "add"} (the default) or {mode: "replace", id} for one of the writer's characters.
// {ok: false, reason: "locked" | "no_target"} or
//   {ok: true, card, mode, targetId, id, name, next, replaced, filled, ignored, lost}
//   next      the card's values as they would be (a copy); for a new character it carries the id it would get
//   replaced  labels of the fields where the writer has words that would change (including ones the file leaves blank)
//   filled    labels of the fields that are empty now and would get words
//   ignored   labels of what in the file did not fit and was left out
//   lost      for a replaced World: {count, cards} of links that would point at nothing, else null
// A character's id from the file is kept unless someone here already has it; list items keep their ids unless two share one.
export function planImport(schema, project, read, choice = {}) {
  const card = schema.cards[read.card];
  if (cardLocked(project, card.id)) return { ok: false, reason: "locked", card: card.id };
  const label = (key) => card.fields.find((f) => f.key === key)?.label ?? key;
  let mode = "replace";
  let target = null;
  let id = null;
  let current;
  if (card.many_per_project) {
    const list = project[card.id] ?? [];
    if (choice.mode === "replace") {
      target = list.find((i) => i.id === choice.id);
      if (!target) return { ok: false, reason: "no_target", card: card.id };
      current = target;
    } else {
      mode = "add";
      current = blankCard(card);
      const taken = list.map((i) => i.id);
      id = read.values.id && !taken.includes(read.values.id) ? read.values.id : newId(taken);
    }
  } else {
    current = { ...blankCard(card), ...(project[card.id] ?? {}) };
  }
  const next = copy(current);
  for (const field of card.fields) {
    if (!(field.key in read.values)) continue;
    next[field.key] = field.repeat
      ? read.values[field.key].reduce((items, item) => {
        const keep = typeof item.id === "string" && item.id && !items.some((i) => i.id === item.id);
        items.push({ ...blankItem(field), ...item, id: keep ? item.id : newId(items.map((i) => i.id)) });
        return items;
      }, [])
      : read.values[field.key];
  }
  if (mode === "add") next.id = id;
  const replaced = card.fields.filter((f) => isFilled(current[f.key]) && !sameValue(f, current[f.key], next[f.key])).map((f) => f.label);
  const filled = card.fields.filter((f) => !isFilled(current[f.key]) && isFilled(next[f.key])).map((f) => f.label);
  return {
    ok: true, card: card.id, mode, targetId: target?.id ?? null, id, name: card.many_per_project ? instanceName(next) : "",
    next, replaced, filled, ignored: [...new Set(read.ignored.map(label))],
    lost: card.id === "world" ? linksLost(schema, project, next) : null,
  };
}

// Does what planImport said. Returns {instanceId, keys, undo}: instanceId is the character it landed on (null for Style and
// World), keys are the fields it wrote, and undo puts back exactly what this import changed (for a new character, takes it out again).
export function applyImport(schema, project, plan) {
  const card = schema.cards[plan.card];
  if (plan.mode === "add") {
    const list = ensureCard(project, card);
    list.push(copy(plan.next));
    return { instanceId: plan.id, keys: card.fields.map((f) => f.key), undo: () => removeInstance(project, card, plan.id) };
  }
  const held = ensureCard(project, card);   // fills any field the project has not drawn yet, so every value can be compared and put back
  const target = card.many_per_project ? findInstance(project, card, plan.targetId) : held;
  const keys = card.fields.filter((f) => !sameValue(f, target[f.key], plan.next[f.key])).map((f) => f.key);
  const before = Object.fromEntries(keys.map((key) => [key, copy(target[key])]));
  setCardValues(card, target, Object.fromEntries(keys.map((key) => [key, plan.next[key]])));
  const where = () => (card.many_per_project ? findInstance(project, card, plan.targetId) : project[card.id]);
  return { instanceId: card.many_per_project ? plan.targetId : null, keys, undo: () => { const now = where(); if (now) setCardValues(card, now, before); } };
}
