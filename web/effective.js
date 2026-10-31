// The effective state of the cards: the base card plus every shift of the chapters before the one being planned or
// written. This is the only implementation of the overlay (P0, A6): the backend is stateless, never applies a shift, and
// is sent the effective cards in every request. The same code folds the shifts into the cards when the story ends.
// No DOM, so Node can test it. tests/shared/overlay-vectors.json defines what it must do.
//
// A shift entry is {id, beat, card, target, patch}. The chapter of an entry is the number on its beat (the number is stored
// only there). A patch is a partial card in the card's own field keys: a scalar field holds its new value, a list field
// holds a list of operations (add, replace, remove) on items found by id.

import { msg } from "./text.js";

export const SHIFT_CARDS = ["characters", "world", "entanglements"];
export const OPS = ["add", "replace", "remove"];

const copyOf = (value) => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)));
const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

// ---- Applying one patch ----------------------------------------------------------------------

// A copy of `card` with `patch` applied. A scalar field takes the new value. A list field takes its operations in order:
//   add      puts {id, ...values} at the end (an id already in the list is left alone)
//   replace  merges its values into the item with that id, which keeps its other keys and its place
//   remove   takes the item with that id out
// An operation on an id that is not in the list changes nothing and does not stop the rest.
export function applyPatch(card, patch) {
  const out = copyOf(card) ?? {};
  for (const [key, value] of Object.entries(patch ?? {})) {
    if (!Array.isArray(value)) { out[key] = copyOf(value); continue; }
    let list = Array.isArray(out[key]) ? out[key] : [];
    for (const op of value) {
      if (!isObject(op)) continue;
      if (op.op === "add") {
        if (!list.some((item) => item.id === op.id)) list = [...list, { id: op.id, ...copyOf(op.values ?? {}) }];
      } else if (op.op === "replace") {
        list = list.map((item) => (item.id === op.id ? { ...item, ...copyOf(op.values ?? {}) } : item));
      } else if (op.op === "remove") {
        list = list.filter((item) => item.id !== op.id);
      }
    }
    out[key] = list;
  }
  return out;
}

// ---- The overlay -------------------------------------------------------------------------------

const chapterMap = (beats) => (beats instanceof Map ? beats : new Map(Array.isArray(beats) ? beats.map((b) => [b.id, Number(b.chapter)]) : Object.entries(beats ?? {})));

// `base` holds some of {characters: [..], world, entanglements}; the result holds the same ones, with the entries of
// every chapter before `chapter` applied: in chapter order, then in the order the entries are listed. `beats` says each
// beat's chapter: a Map or object of beat id -> number, or the project's list of beats. An entry whose beat is unknown is
// never applied.
export function applyShifts(base, entries, beats, chapter) {
  const out = copyOf(base);
  const chapters = chapterMap(beats);
  const due = (entries ?? [])
    .map((entry, order) => ({ entry, order, at: Number(chapters.get(entry.beat)) }))
    .filter((x) => Number.isFinite(x.at) && x.at < chapter)
    .sort((a, b) => a.at - b.at || a.order - b.order);
  for (const { entry } of due) {
    if (!isObject(entry.patch)) continue;
    if (entry.card === "characters") {
      if (!Array.isArray(out.characters)) continue;
      out.characters = out.characters.map((c) => (c.id === entry.target ? applyPatch(c, entry.patch) : c));
    } else if (entry.card === "world" || entry.card === "entanglements") {
      if (isObject(out[entry.card])) out[entry.card] = applyPatch(out[entry.card], entry.patch);
    }
  }
  return out;
}

// A copy of the project whose Characters, World and Entanglements are what they were going INTO chapter `beforeChapter`.
export function effectiveProject(project, beforeChapter) {
  const copy = copyOf(project);
  const base = {};
  for (const key of SHIFT_CARDS) if (copy[key] !== undefined && copy[key] !== null) base[key] = copy[key];
  Object.assign(copy, applyShifts(base, project.shifts?.entries, project.outline?.beats, beforeChapter));
  return copy;
}

// Every shift applied: the cards as the story left them.
export const foldAll = (project) => effectiveProject(project, Infinity);

// ---- Checking a patch -----------------------------------------------------------------------------
// The same checks as validate_patch in pulpermill/schema/shifts.py, read from web/data/schema.en.json: the vectors in
// tests/shared/overlay-vectors.json (patch_validation) hold both to the same answers. It checks shape only; it does not apply
// the patch, and it does not look for the ids it names.
// Returns a list of {code, field, message}; an empty list means the patch is valid.

// The words for each problem, by key (every message is in the text bundle).
const PATCH_TEXT = {
  operation: "patch.operation",
  unknownCard: "patch.unknownCard",
  notObject: "patch.notObject",
  emptyPatch: "patch.emptyPatch",
  unknownField: "patch.unknownField",
  fixedField: "patch.fixedField",
  notList: "patch.notList",
  emptyList: "patch.emptyList",
  opNotObject: "patch.opNotObject",
  opUnknown: "patch.opUnknown",
  opExtra: "patch.opExtra",
  missingId: "patch.missingId",
  needsValues: "patch.needsValues",
  emptyValues: "patch.emptyValues",
  unknownItemField: "patch.unknownItemField",
  identityField: "patch.identityField",
  missingValue: "patch.missingValue",
  badType: "patch.badType",
  badOption: "patch.badOption",
};

const problem = (code, field, key, params = {}) => ({ code, field, message: msg(PATCH_TEXT[key], params) });

const cardFields = (schema, cardId) => schema.cards?.[cardId]?.fields ?? [];

function valueOk(def, value) {
  if (def.options?.length) return typeof value === "string" ? (def.options.some((o) => o.value === value) ? null : "bad_option") : "bad_type";
  if (value === null && def.required === false) return null;
  switch (def.input) {
    case "number": return typeof value === "number" && Number.isInteger(value) ? null : "bad_type";
    case "checkbox": return typeof value === "boolean" ? null : "bad_type";
    case "select-multiple": return Array.isArray(value) && value.every((v) => typeof v === "string") ? null : "bad_type";
    default: return typeof value === "string" ? null : "bad_type";
  }
}

function valueProblem(def, path, value, where = "") {
  const bad = valueOk(def, value);
  if (!bad) return null;
  const options = (def.options ?? []).map((o) => o.value).join(", ");
  return problem(bad, path, bad === "bad_option" ? "badOption" : "badType", { where, key: path, options, got: String(value) });
}

function operationProblems(key, def, index, op) {
  const where = msg(PATCH_TEXT.operation, { n: index + 1, key });
  if (!isObject(op)) return [problem("bad_operation", key, "opNotObject", { where })];
  if (!OPS.includes(op.op)) return [problem("bad_operation", key, "opUnknown", { where })];
  const out = [];
  const allowed = op.op === "remove" ? ["op", "id"] : ["op", "id", "values"];
  const extra = Object.keys(op).filter((k) => !allowed.includes(k)).sort();
  if (extra.length) out.push(problem("bad_operation", key, "opExtra", { where, op: op.op, extra: extra.join(", ") }));
  if (typeof op.id !== "string" || !op.id.trim()) out.push(problem("missing_id", key, "missingId", { where, op: op.op }));
  if (op.op === "remove") return out;
  if (!isObject(op.values)) return [...out, problem("bad_operation", key, "needsValues", { where, op: op.op })];
  const items = def.item_fields ?? [];
  if (op.op === "replace" && !Object.keys(op.values).length) out.push(problem("empty_values", key, "emptyValues", { where }));
  for (const [name, value] of Object.entries(op.values)) {
    const path = `${key}.${name}`;
    const item = items.find((f) => f.key === name);
    if (!item) out.push(problem("unknown_item_field", path, "unknownItemField", { where, name, key }));
    else if (op.op === "replace" && (item.identity || item.fixed)) out.push(problem("identity_field", path, "identityField", { where, name }));
    else { const p = valueProblem(item, path, value, where); if (p) out.push(p); }
  }
  if (op.op === "add") {
    for (const item of items) {
      if (item.required !== false && !(item.key in op.values)) out.push(problem("missing_value", `${key}.${item.key}`, "missingValue", { where, name: item.key }));
    }
  }
  return out;
}

export function validatePatch(schema, cardId, patch) {
  if (!SHIFT_CARDS.includes(cardId)) return [problem("unknown_card", "", "unknownCard", { card: cardId, cards: SHIFT_CARDS.join(", ") })];
  if (!isObject(patch)) return [problem("bad_type", "", "notObject")];
  if (!Object.keys(patch).length) return [problem("empty_patch", "", "emptyPatch")];
  const fields = cardFields(schema, cardId);
  const out = [];
  for (const [key, value] of Object.entries(patch)) {
    const def = fields.find((f) => f.key === key);
    if (key === "id" || !def) { out.push(problem("unknown_field", key, "unknownField", { key, card: cardId })); continue; }
    if (def.fixed) { out.push(problem("fixed_field", key, "fixedField", { key })); continue; }
    if (!def.repeat) { const p = valueProblem(def, key, value); if (p) out.push(p); continue; }
    if (!Array.isArray(value)) out.push(problem("bad_type", key, "notList", { key }));
    else if (!value.length) out.push(problem("empty_list", key, "emptyList", { key }));
    else value.forEach((op, i) => out.push(...operationProblems(key, def, i, op)));
  }
  return out;
}
