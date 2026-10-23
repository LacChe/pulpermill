// Getting the story out: the chapters as one markdown file, and each portable card as its own JSON file. No DOM, so Node can
// test it. (The project file is the Save button's.)
//
// A card file looks like this, and readCardFile reads it back:
//   { "pulpermill_card": "characters", "schema_version": 1, "values": { ...the card's fields, ids included... } }
// Only the portable cards go out: Style, each Character, and World. The others (Entanglements, Setup, Outline) point at ids
// in this one story, so they mean nothing in another. When the story has an after-story copy, its cards go out too, named
// "after-story".

import { settledProject, instanceName } from "./logic.js";
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
// {ok: true, card, values, ignored: [keys]} or {ok: false, reason}: unreadable, not_card_file, unknown_card, not_portable, newer, damaged.
// Only keys the card has are kept (ignored lists the rest); a value of the wrong kind is ignored too. A character file gives one character.
export function readCardFile(text, schema) {
  let data;
  try { data = JSON.parse(String(text).replace(/^﻿/, "")); } catch { return { ok: false, reason: "unreadable" }; }
  const isObject = (v) => v && typeof v === "object" && !Array.isArray(v);
  if (!isObject(data) || typeof data[CARD_FILE_KEY] !== "string" || !isObject(data.values)) return { ok: false, reason: "not_card_file" };
  const card = schema.cards[data[CARD_FILE_KEY]];
  if (!card) return { ok: false, reason: "unknown_card" };
  if (!PORTABLE.includes(card.id)) return { ok: false, reason: "not_portable" };
  if (Number.isInteger(data.schema_version) && data.schema_version > schema.schema_version) return { ok: false, reason: "newer" };
  const values = {};
  const ignored = [];
  const known = new Set(card.fields.map((f) => f.key));
  for (const [key, value] of Object.entries(data.values)) {
    if (key === "id") { if (typeof value === "string") values.id = value; continue; }
    const field = card.fields.find((f) => f.key === key);
    const fine = field && (field.repeat ? Array.isArray(value) && value.every(isObject)
      : field.input === "select-multiple" ? Array.isArray(value)
      : field.input === "number" ? value === null || typeof value === "number"
      : field.input === "checkbox" ? typeof value === "boolean" : typeof value === "string");
    if (fine) values[key] = value; else ignored.push(key);
  }
  if (!known.size) return { ok: false, reason: "damaged" };
  return { ok: true, card: card.id, values, ignored };
}
