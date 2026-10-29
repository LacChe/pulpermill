// Deterministic page logic, written once and kept free of the DOM so Node can test it.
// Everything here works on plain objects: the schema JSON and the project object.

import { msg, joinList } from "./text.js";

// A value counts as filled when the writer has put something in it.
export function isFilled(value) {
  if (value === undefined || value === null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

// visible_if is {siblingKey: "filled" | optionValue | [optionValues]}. Every entry must hold.
// A field without visible_if is always shown. `values` holds the sibling values.
export function isVisible(field, values) {
  const cond = field.visible_if;
  if (!cond) return true;
  return Object.entries(cond).every(([key, want]) => {
    const have = values[key];
    if (want === "filled") return isFilled(have);
    if (Array.isArray(want)) return want.includes(have);
    return have === want;
  });
}

// ---- Ids ----------------------------------------------------------------

// Eight hex characters, like the ids the schema makes. `taken` is a list of ids already in use.
export function newId(taken = [], random = Math.random) {
  const used = new Set(taken);
  for (;;) {
    let id = "";
    for (let i = 0; i < 8; i++) id += Math.floor(random() * 16).toString(16);
    if (!used.has(id)) return id;
  }
}

// ---- Blank values -------------------------------------------------------

// The empty value a field starts with when a project has nothing for it yet.
export function blankValue(field) {
  if (field.repeat) return [];
  switch (field.input) {
    case "select-multiple": return [];
    case "checkbox": return field.default ?? false;
    case "number": return null;
    default: return field.default ?? "";
  }
}

function blankFields(fields) {
  const values = {};
  for (const field of fields) values[field.key] = blankValue(field);
  return values;
}

export function blankCard(card) {
  return blankFields(card.fields);
}

export function blankItem(field, taken = []) {
  return { id: newId(taken), ...blankFields(field.item_fields || []) };
}

// ---- Layout -------------------------------------------------------------

// Fields grouped in the card's group order. A field whose group is missing from the card is kept
// in a trailing group with `group: null`, so nothing silently disappears.
export function groupedFields(card) {
  const known = new Set(card.groups.map((g) => g.id));
  const out = card.groups.map((group) => ({
    group,
    fields: card.fields.filter((f) => f.group === group.id),
  }));
  const loose = card.fields.filter((f) => !known.has(f.group));
  if (loose.length) out.push({ group: null, fields: loose });
  return out.filter((entry) => entry.fields.length > 0);
}

export function optionByValue(field, value) {
  return (field.options || []).find((o) => o.value === value);
}

// ---- Repeating lists ----------------------------------------------------

// Lists are capped unless the field says `uncapped`. A field with no max_items has no cap.
export function canAdd(field, list) {
  if (field.uncapped) return true;
  if (field.max_items === undefined || field.max_items === null) return true;
  return list.length < field.max_items;
}

export function addItem(field, list) {
  if (!canAdd(field, list)) return null;
  const item = blankItem(field, list.map((i) => i.id));
  // A beat added by hand takes the next chapter number, so the system-set number is never left empty.
  if ((field.item_fields || []).some((f) => f.key === "chapter" && f.filled_by === "code")) {
    item.chapter = Math.max(0, ...list.map((i) => Number(i.chapter) || 0)) + 1;
  }
  list.push(item);
  return item;
}

export function removeItem(list, id) {
  const index = list.findIndex((item) => item.id === id);
  if (index >= 0) list.splice(index, 1);
  return list;
}

// True when nothing has been typed into the item, so deleting it needs no confirmation.
export function isItemEmpty(item) {
  return Object.entries(item).every(([key, value]) => key === "id" || !isFilled(value));
}

// Fill "{token}" slots from a values object. `resolve(value, key)` turns a stored value into text
// (it is how a link id becomes a name). Returns "" when no slot had a value, so the caller can
// show a fallback; a slot that is empty while others are filled shows as "…" unless it is in `skip`.
export function fillTemplate(template, values, resolve = (value) => String(value), skip = []) {
  let any = false;
  const text = template.replace(/\{(\w+)\}/g, (_, key) => {
    if (skip.includes(key)) return "";
    const value = values[key];
    if (!isFilled(value)) return "…";
    any = true;
    return Array.isArray(value) ? joinList(value.map((v) => resolve(v, key))) : resolve(value, key);
  });
  return any ? text : "";
}

// `lookup(itemField, value)` turns a stored value into words (see lookupLabel); without it values show as stored.
export function itemTitle(field, item, lookup) {
  if (!field.item_title) return "";
  const resolve = lookup
    ? (value, key) => lookup((field.item_fields || []).find((f) => f.key === key), value)
    : (value) => String(value);
  // In an either-or pair, a half with nothing in it is left out of the title instead of showing as "…".
  const skip = [];
  for (const group of field.one_of ?? []) {
    skip.push(...group.fields.filter((key) => !isFilled(item[key])));
  }
  return fillTemplate(field.item_title, item, resolve, skip).trim();
}

// ---- Cards held once or many times per project --------------------------

// Fill in any key the saved values do not have yet. Never overwrites a value that is there.
function fillBlanks(fields, current) {
  const merged = { ...blankFields(fields), ...current };
  for (const field of fields) {
    if (field.repeat && field.item_fields) {
      merged[field.key] = (merged[field.key] || []).map((item) => ({ ...blankFields(field.item_fields), ...item }));
    }
  }
  return merged;
}

// A card the project holds once lives at project[cardId]; a card held many times is a list there.
export function ensureCard(project, card) {
  if (card.many_per_project) {
    project[card.id] = (project[card.id] ?? []).map((instance) => fillBlanks(card.fields, instance));
    return project[card.id];
  }
  project[card.id] = fillBlanks(card.fields, project[card.id] ?? {});
  return project[card.id];
}

export function addInstance(project, card) {
  const list = project[card.id] ?? (project[card.id] = []);
  const instance = { id: newId(list.map((i) => i.id)), ...blankCard(card) };
  list.push(instance);
  return instance;
}

export function removeInstance(project, card, id) {
  // A note about a character goes with the character, so no note is left pointing at someone who is gone.
  if (card.id === "characters" && project.card_notes) {
    project.card_notes = project.card_notes.filter((n) => !(n.card === "characters" && n.character === id));
    if (!project.card_notes.length) delete project.card_notes;
  }
  return removeItem(project[card.id] ?? [], id);
}

// ---- The writer's notes for the model -------------------------------------
// A note describes one card (for Characters, one character) in the writer's own words, and the example chapter is
// shared by every card. Both are kept on the project, and both are left out of it when blank, so an untouched box
// is not a change.

export function noteFor(project, cardId, instanceId = null) {
  const note = (project.card_notes ?? []).find((n) => n.card === cardId && (cardId !== "characters" || n.character === instanceId));
  return note?.text ?? "";
}

export function setNote(project, cardId, instanceId, text) {
  const notes = project.card_notes ?? [];
  const same = (n) => n.card === cardId && (cardId !== "characters" || n.character === instanceId);
  const kept = notes.filter((n) => !same(n));
  if (String(text ?? "").trim()) {
    const existing = notes.find(same);
    const note = existing ?? { id: newId(notes.map((n) => n.id)), card: cardId, ...(cardId === "characters" ? { character: instanceId } : {}) };
    kept.push({ ...note, text });
  }
  if (kept.length) project.card_notes = kept;
  else delete project.card_notes;
}

export function setExample(project, text) {
  if (String(text ?? "").trim()) project.example_chapter = text;
  else delete project.example_chapter;
}

export function findInstance(project, card, id) {
  return (project[card.id] ?? []).find((i) => i.id === id);
}

// What to call one instance in a list of them: its name, or nothing if it has none yet.
export function instanceName(instance) {
  return typeof instance.name === "string" ? instance.name.trim() : "";
}

// A blank project: a title and the schema version. The cards fill themselves in as they are shown.
export function newProject(schema) {
  return { title: "", schema_version: schema.schema_version };
}

// ---- Saving, opening and the recovery copy -------------------------------
// The saved file is the project itself, with nothing wrapped around it, so the backend reads the same thing.
// This section has no page code: it only turns a project into text and text back into a project.
const copyOf = (value) => JSON.parse(JSON.stringify(value));

// The project with every card filled out to its full shape. Visiting a card fills in blank fields, so two
// projects that differ only in blanks the page has not drawn yet are the same project once settled.
export function settledProject(schema, project) {
  const settled = copyOf(project);
  for (const id of schema.order) ensureCard(settled, schema.cards[id]);
  return settled;
}

// The text of a project, used both to compare ("has anything changed since the last save?") and to save.
export function projectSnapshot(schema, project) {
  return JSON.stringify(settledProject(schema, project), null, 2) + "\n";
}

export function hasUnsavedChanges(schema, project, savedSnapshot) {
  return projectSnapshot(schema, project) !== savedSnapshot;
}

// The file name to offer when saving: the project's title, or a plain default when it has none yet.
export function projectFileName(project, fallback = msg("files.project")) {
  const slug = String(project.title ?? "").toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 60).replace(/-+$/g, "");
  return `${slug || fallback}.json`;
}

// Turn the text of a file into a project, or say why not. The reasons are codes; the page words them.
//   unreadable   not JSON at all
//   not_project  JSON, but not a Pulpermill project (no schema_version)
//   newer        saved by a newer version of the page than this one
//   damaged      a card holds the wrong kind of thing (`card` names it)
// An older file still opens, and comes back with `older: true` so the page can say so.
export function readProject(text, schema) {
  let data;
  try {
    data = JSON.parse(String(text).replace(/^﻿/, ""));
  } catch {
    return { ok: false, reason: "unreadable" };
  }
  if (!data || typeof data !== "object" || Array.isArray(data) || !Number.isInteger(data.schema_version)) {
    return { ok: false, reason: "not_project" };
  }
  if (data.schema_version > schema.schema_version) return { ok: false, reason: "newer" };
  for (const id of schema.order) {
    const card = schema.cards[id];
    const held = data[id];
    if (held === undefined || held === null) continue;
    const isObject = (v) => v && typeof v === "object" && !Array.isArray(v);
    const fine = card.many_per_project ? Array.isArray(held) && held.every(isObject) : isObject(held);
    if (!fine) return { ok: false, reason: "damaged", card: id };
  }
  return { ok: true, project: data, older: data.schema_version < schema.schema_version };
}

// The safety copy kept in the browser while the writer works. The file stays the real save.
export const RECOVERY_KEY = "pulpermill-recovery";

export function recoveryRecord(schema, project, now = new Date()) {
  return JSON.stringify({
    schema_version: schema.schema_version,
    saved_at: now.toISOString(),
    project: settledProject(schema, project),
  });
}

// What the browser kept, or null if it is missing, damaged or from a newer page.
export function readRecovery(text, schema) {
  let record;
  try {
    record = JSON.parse(text);
  } catch {
    return null;
  }
  if (!record || typeof record.saved_at !== "string" || !record.project) return null;
  const read = readProject(JSON.stringify(record.project), schema);
  if (!read.ok) return null;
  return {
    project: read.project,
    savedAt: record.saved_at,
    title: typeof read.project.title === "string" ? read.project.title : "",
    characters: (read.project.characters ?? []).length,
  };
}

// Only offer the copy back if it holds something. A copy of a blank project is not worth interrupting for.
export function worthRecovering(schema, recovered) {
  return Boolean(recovered) &&
    projectSnapshot(schema, recovered.project) !== projectSnapshot(schema, newProject(schema));
}

// ---- Links to other cards ------------------------------------------------
// A field with `ref` picks from lists elsewhere in the project. A source is "characters" or "<card>.<list>".
const NAME_KEYS = ["name", "statement", "term", "what", "planted"];

function sourceList(project, source) {
  if (source === "characters") return project.characters ?? [];
  const [cardId, key] = source.split(".");
  return project[cardId]?.[key] ?? [];
}

// A plant is named by its words, and two chapters can plant the same words. Past the first, the label carries the chapter,
// so a payoff names exactly one plant and the page and the model agree on which.
export function plantLabels(project) {
  const beats = project.outline?.beats ?? [];
  const chapterOf = (id) => beats.find((b) => b.id === id)?.chapter;
  const planted = (project.summary_events?.entries ?? []).filter((e) => isFilled(e.planted))
    .sort((a, b) => (Number(chapterOf(a.beat)) || 0) - (Number(chapterOf(b.beat)) || 0));
  const seen = new Map();
  const out = new Map();
  for (const e of planted) {
    const words = e.planted.trim();
    const key = words.replace(/\s+/g, " ").toLowerCase();
    const n = (seen.get(key) ?? 0) + 1;
    seen.set(key, n);
    out.set(e.id, n === 1 ? words : `${words.replace(/[.!?]+$/, "")} (chapter ${chapterOf(e.beat) ?? "?"})`);
  }
  return out;
}

function entryLabel(item, unnamed) {
  for (const key of NAME_KEYS) {
    if (typeof item[key] === "string" && item[key].trim()) return item[key].trim();
  }
  return unnamed;
}

// Every entry of the given sources as {value: id, label, source}. `unnamed` is shown for entries with no name yet.
// `options.where` ({key: [values]}) keeps only entries whose key holds one of the values (ref_where).
// `options.keep` lists ids that stay in the list even when the filters would drop them, so a saved choice is not lost.
// Two sources are narrowed by what the story has already done:
//   summary_events.entries  only entries that planted something and have not been paid off yet (an open plant)
//   world.rules, when a filter is given  rules that have not already come to light (reveals_landed)
export function refOptions(project, sources, unnamed = msg("common.unnamed"), options = {}) {
  const { where, keep = [] } = options;
  const paidOff = new Set((project.summary_events?.entries ?? []).flatMap((e) => e.paid_off ?? []));
  const landed = new Set((project.summary_events?.entries ?? []).flatMap((e) => e.reveals_landed ?? []));
  const labels = sources.includes("summary_events.entries") ? plantLabels(project) : new Map();
  const out = [];
  for (const source of sources) {
    for (const item of sourceList(project, source)) {
      if (!keep.includes(item.id)) {
        if (source === "summary_events.entries" && (!isFilled(item.planted) || paidOff.has(item.id))) continue;
        if (where && source === "world.rules" && landed.has(item.id)) continue;
        if (where && !Object.entries(where).every(([key, allowed]) => allowed.includes(item[key]))) continue;
      }
      out.push({ value: item.id, label: source === "summary_events.entries" && labels.has(item.id) ? labels.get(item.id) : entryLabel(item, unnamed), source });
    }
  }
  return out;
}

export function sourceOfId(project, sources, id) {
  return sources.find((source) => sourceList(project, source).some((item) => item.id === id)) ?? null;
}

// The sources a picker may list right now. A filtered picker (ref_filter_by) follows another field in the
// same item: what may hold a thing depends on what kind of thing it is (the card's holding_pairs table).
export function pickerSources(field, values, siblings, project, card) {
  if (!field.ref_filter_by) return field.ref;
  const other = siblings.find((f) => f.key === field.ref_filter_by);
  const kind = other ? sourceOfId(project, other.ref ?? [], values[other.key]) : null;
  if (!kind) return field.ref;
  const allowed = card.holding_pairs?.[kind] ?? [];
  return field.ref.filter((source) => allowed.includes(source));
}

// Values a picker must not offer because a "fields_differ" rule needs them to be different from a sibling.
// Example: a tie may not point at itself, so each end disables the other end's choice.
export function blockedValues(card, listField, field, values) {
  const blocked = [];
  for (const rule of card.rules ?? []) {
    if (rule.check !== "fields_differ") continue;
    if (!(rule.fields ?? []).includes(listField?.key)) continue;
    const pair = rule.params?.fields ?? [];
    if (!pair.includes(field.key)) continue;
    for (const key of pair) if (key !== field.key && isFilled(values[key])) blocked.push(values[key]);
  }
  return blocked;
}

// The words for a stored value, for titles: an option's label, a linked entry's name, or the value itself.
export function lookupLabel(project, itemField, value, unnamed = msg("common.unnamed")) {
  if (itemField?.options) return itemField.options.find((o) => o.value === value)?.label ?? String(value);
  if (itemField?.ref) return refOptions(project, itemField.ref, unnamed).find((o) => o.value === value)?.label ?? String(value);
  return String(value);
}

// ---- Either-or fields ----------------------------------------------------
// A list can declare `one_of: [{fields: [a, b], label, options: {a, b}}]`: exactly one of the two is filled in.
// The choice is the field that has a value, or, before anything is typed, what the writer last picked.
export function oneOfChoice(group, index, values, memory) {
  return group.fields.find((key) => isFilled(values[key])) ?? memory[index] ?? null;
}

// Switching clears the other field, so only one of them ever holds a value.
export function chooseOneOf(group, index, values, memory, key) {
  for (const other of group.fields) if (other !== key) values[other] = "";
  memory[index] = key;
}

export function fieldShown(owner, field, values, memory) {
  if (!isVisible(field, values)) return false;
  for (const [index, group] of (owner?.one_of ?? []).entries()) {
    if (group.fields.includes(field.key)) return oneOfChoice(group, index, values, memory) === field.key;
  }
  return true;
}

export function inOneOf(owner, field) {
  return (owner?.one_of ?? []).some((group) => group.fields.includes(field.key));
}

// "Optional" is only honest for a field that is never required: not part of an either-or, not shown only
// under a condition (those are required whenever they show).
export function showsOptionalTag(owner, field) {
  return field.required === false && !field.visible_if && !inOneOf(owner, field);
}

// ---- Validation ----------------------------------------------------------
// Two kinds of rule come with every card. A "code" rule has a named `check` that the page can run itself, the
// moment the writer leaves a field. A "model" rule (needs_model) is a judgement the page cannot make; those run
// only when the writer presses Validate, through the backend. This file runs the code rules and the common
// field checks (empty, not a listed choice, too many); it never judges wording.
//
// A problem is {rule, kind, severity, field, item, key, message, fix}:
//   field  the card's own field (a list's key, for a problem inside one of its items)
//   item   the id of the list item, or null
//   key    the field inside that item, or null
// Blocking problems only stop generating; the writer can always keep editing and saving a draft.

export function ruleKind(rule) {
  return rule.needs_model ? "model" : "code";
}

export function modelRules(card) {
  return (card.rules ?? []).filter((rule) => ruleKind(rule) === "model");
}

// check name -> function({rule, card, values, project}) returning the places that break the rule:
//   [{field, item?, key?, tokens?}].
export const CHECKS = {};

// Checks named in the schema that this page does not run yet. Empty means every code rule is written. A test keeps
// this honest: every named check has a function in CHECKS or is listed here, so a new rule cannot be forgotten.
export const PENDING_CHECKS = [];

function fillTokens(text, tokens) {
  return (text ?? "").replace(/\{(\w+)\}/g, (whole, key) => (key in tokens ? String(tokens[key]) : whole));
}

function problem(card, rule, hit, extra = {}) {
  return {
    rule: rule.id,
    kind: ruleKind(rule),
    severity: rule.severity,
    field: hit.field,
    item: hit.item ?? null,
    key: hit.key ?? null,
    message: fillTokens(rule.message, { ...extra, ...(hit.tokens ?? {}) }),
    fix: fillTokens(rule.fix, { ...extra, ...(hit.tokens ?? {}) }),
  };
}

function commonProblem(common, kind, hit, label, extra = {}) {
  const text = common?.[kind] ?? {};
  const tokens = { label, ...extra };
  return {
    rule: kind, kind: "code", severity: "block", field: hit.field, item: hit.item ?? null, key: hit.key ?? null,
    message: fillTokens(text.message, tokens), fix: fillTokens(text.fix, tokens),
  };
}

// The checks every field gets without a rule: required and empty, a value that is not one of the options, too many.
function fieldProblems(field, values, scope, common, out) {
  const hit = scope.item ? { field: scope.field, item: scope.item, key: field.key } : { field: field.key, item: null, key: null };
  const value = values[field.key];
  if (!isVisible(field, values)) return;
  if (field.repeat) {
    if (field.required && !isFilled(value)) out.push(commonProblem(common, "missing", { field: field.key }, field.label));
    if (!field.uncapped && field.max_items != null && (value ?? []).length > field.max_items) {
      out.push(commonProblem(common, "too_many", { field: field.key }, field.label, { max: field.max_items }));
    }
    for (const item of value ?? []) {
      for (const sub of field.item_fields ?? []) {
        fieldProblems(sub, item, { field: field.key, item: item.id, group: field }, common, out);
      }
    }
    return;
  }
  const inOne = (scope.group?.one_of ?? []).some((g) => g.fields.includes(field.key));
  if (field.required && !isFilled(value) && !inOne) out.push(commonProblem(common, "missing", hit, field.label));
  if (field.options && isFilled(value)) {
    const wanted = Array.isArray(value) ? value : [value];
    if (wanted.some((v) => !field.options.some((o) => o.value === v))) out.push(commonProblem(common, "not_allowed", hit, field.label));
  }
  if (field.max_selected && Array.isArray(value) && value.length > field.max_selected) {
    out.push(commonProblem(common, "too_many", hit, field.label, { max: field.max_selected }));
  }
}

// All code problems for one card. `values` is the card's values (one instance for a card held many times).
// Returns {problems, unchecked}: unchecked names the code rules this page cannot run yet.
export function validate(card, values, project, common = {}) {
  const problems = [];
  const unchecked = [];
  for (const field of card.fields) fieldProblems(field, values, { field: null, item: null }, common, problems);
  for (const rule of card.rules ?? []) {
    if (ruleKind(rule) !== "code") continue;
    const check = CHECKS[rule.check];
    if (!check) { unchecked.push(rule.id); continue; }
    for (const hit of check({ rule, card, values, project })) problems.push(problem(card, rule, hit));
  }
  return { problems, unchecked };
}

// The problems that belong to one field (or one field of one item), for showing under it.
export function problemsFor(problems, field, item = null, key = null) {
  return problems.filter((p) => p.field === field && p.item === item && p.key === key);
}

// ---- Showing problems ----------------------------------------------------------
// A problem is shown under its field only once the writer has been there: they left the field, or it already had
// something in it when the card was drawn (a saved project). A blank, untouched card shows nothing. Pressing Validate
// shows everything. Nothing here ever stops editing; blocking problems only stop generating.

// Where a problem sits on the page: "protagonist", "beats" (a whole list), "beats.<item>" or "beats.<item>.<key>".
export function problemPath(p) {
  if (p.item && p.key) return `${p.field}.${p.item}.${p.key}`;
  if (p.item) return `${p.field}.${p.item}`;
  return p.field;
}

// An unticked box is not "something typed".
const hasContent = (value) => isFilled(value) && value !== false;

// The paths of everything that has something in it: fields, lists, list items and the fields inside them.
export function filledPaths(card, values) {
  const out = new Set();
  for (const field of card.fields) {
    const value = values[field.key];
    if (!hasContent(value)) continue;
    out.add(field.key);
    if (!field.repeat) continue;
    for (const item of value) {
      const subs = (field.item_fields ?? []).filter((sub) => hasContent(item[sub.key]));
      if (!subs.length) continue;
      out.add(`${field.key}.${item.id}`);
      for (const sub of subs) out.add(`${field.key}.${item.id}.${sub.key}`);
    }
  }
  return out;
}

// The places the writer may have been when a problem should appear: the field it sits on, and the other fields its
// rule looks at. "Pushed by: someone" filled in but "next move" empty is shown once the writer leaves "someone".
export function problemTriggers(card, p) {
  const out = [problemPath(p)];
  const rule = (card.rules ?? []).find((r) => r.id === p.rule);
  if (!rule) return out;
  const params = rule.params ?? {};
  const keys = [...(params.fields ?? []), params.field, params.when_present].filter((key) => typeof key === "string");
  const prefix = p.item ? `${p.field}.${p.item}.` : "";
  for (const key of keys) out.push(prefix + key);
  return out;
}

// `review` is {touched: Set of paths, validated: boolean}.
export function shownProblems(card, problems, review) {
  if (review.validated) return problems;
  return problems.filter((p) => problemTriggers(card, p).some((path) => review.touched.has(path)));
}

export function problemCounts(problems) {
  const block = problems.filter((p) => p.severity === "block").length;
  return { block, warn: problems.length - block };
}

// ---- What a tab or a dropdown entry says about a card ---------------------------
// One status per card (or per character):
//   started  something is written in it
//   ready    started, and nothing in it blocks generating. This looks at every problem, shown or not, so a tick
//            is never given to a card that still has a required field the writer has not reached.
//   block, warn  the problems the writer has already been shown (the same rule as under the fields), so a tab never
//                nags about a part of the card the writer has not touched.
export function cardStatus(card, values, project, common, review) {
  const filled = filledPaths(card, values);
  const { problems } = validate(card, values, project, common);
  const seen = { validated: review.validated, touched: new Set([...review.touched, ...filled]) };
  const counts = problemCounts(shownProblems(card, problems, seen));
  const started = filled.size > 0;
  return { started, ready: started && !problems.some((p) => p.severity === "block"), ...counts };
}

// Several statuses (every character) as one. A card held many times is ready only when each one is.
export function combineStatus(list) {
  return {
    started: list.some((s) => s.started),
    ready: list.length > 0 && list.every((s) => s.ready),
    block: list.reduce((sum, s) => sum + s.block, 0),
    warn: list.reduce((sum, s) => sum + s.warn, 0),
  };
}

// The status of every card, and of every character. `reviewOf(key)` gives the review state kept for
// "<card id>:<instance id or empty>", as the page does.
export function projectStatus(schema, project, reviewOf) {
  const settled = settledProject(schema, project);
  const cards = {};
  const instances = {};
  for (const id of schema.order) {
    const card = schema.cards[id];
    const list = card.many_per_project ? settled[id] : [settled[id]];
    const each = list.map((values) => ({
      id: values.id ?? null,
      status: cardStatus(card, values, settled, schema.common, reviewOf(`${id}:${values.id ?? ""}`)),
    }));
    if (card.many_per_project) instances[id] = each;
    cards[id] = combineStatus(each.map((e) => e.status));
  }
  return { cards, instances };
}

// ---- Fixed and live fields ---------------------------------------------------------
// The schema flags some fields: `fixed` (always sent to the model exactly as written, never changed in the story) and
// `changes` (a live field: what the writer enters is the starting point, and the model updates it chapter by chapter).
// The page tags those fields, and explains the tags only on a card that actually has them.
export function flagsUsed(card) {
  const used = { fixed: false, changes: false };
  const walk = (fields) => {
    for (const field of fields) {
      if (field.fixed) used.fixed = true;
      if (field.changes) used.changes = true;
      walk(field.item_fields ?? []);
    }
  };
  walk(card.fields);
  return used;
}

// ---- The backend contract ---------------------------------------------------
// What the page sends to the backend and what it accepts back. Pure: nothing here sends anything, so the mock,
// the real backend and the tests all speak the same shapes.
//
// Two rules the page keeps, whatever the call:
//   1. A model is only ever asked after the writer presses a button. Never on typing, never on leaving a field.
//   2. Code checks run when the writer leaves a field (or presses Validate). Never per keystroke.
//
// Transport: GET {base}/status, and POST {base}/{call} with a JSON body for the others. The backend is stateless,
// so every request carries everything the call needs.
//   Every request: {call, schema_version, language, ...}. `language` is the project's output language.
//   Every reply:   {ok: true, ...} or {ok: false, error: {kind, detail?}}.
//
//   status     GET. Reply {ok, state: "idle" | "busy"}.
//   fill       Fill one card from the writer's note and/or the example chapter.
//              Request {card, instance, note, example_chapter, values, related}. Reply {ok, values}. `values` is
//              the card's fields by key. A field that links to another card's entry is named in words; the page
//              turns the words into ids.
//   judge      The model-judged rules for one card. Request {card, instance, rules: [{id, fields}], values,
//              related}. Reply {ok, results: [{rule, hits: [{field, item?, key?}]}]}. A rule with no hits passed.
//   style_fit  Does the protagonist's personality allow the chosen person, tense and voice? Request {style,
//              protagonist}. Reply {ok, fits, message}.
//
//   offstage   Plan, only when due: what do background groups and places do? Reply {ok, did, reach}.
//   plan       Think, then fill the beat. Reply {ok, thinking, beat}. The beat is by field key, links in words.
//   generate   Write the chapter, then the Events pass, then the Shifts pass. Reply {ok, chapter_text, events,
//              shifts, changes}. All or nothing: the page commits the chapter and its records as one unit.
//   end_story  Update Characters and World from the records. Reply {ok, characters, world}.
//   The page works out everything deterministic (spotlight, legal shifts, open plants, goal, which cards are in
//   play) and sends it; the backend renders prose and runs the model. Progress is not streamed: while a long call
//   runs the page asks `status`, which may name the stage ({state: "busy", stage: "write"}).
//
//   `related` holds the cards this card reads (schema `reads`), by card id: the few cards that matter to it,
//   never the whole project.

export const FILLABLE = ["style", "characters", "world", "entanglements", "setup"];

// Errors from the backend: busy (try again when idle), bad_request (the page sent something wrong),
// bad_output (the model's answer did not fit the shape; the backend already retried), too_long (the context does
// not fit the model), stopped (the writer pressed Stop), server (anything else), unauthorized (the token is missing or wrong).
// Made by the page itself: unreachable (nothing answered), timeout (no answer in time).
export const ERROR_KINDS = ["busy", "bad_request", "bad_output", "too_long", "stopped", "server", "unauthorized", "unreachable", "timeout"];

// The calls that take long enough to show progress for, and the stages a busy backend may name.
export const STORY_CALLS = ["offstage", "plan", "generate", "end_story"];
export const STAGES = ["offstage", "think", "beat", "retry", "write", "events", "shifts", "update"];

export function envelope(schema, project, call) {
  return { call, schema_version: schema.schema_version, language: project.output_language || schema.lang };
}

// The cards `card` reads, copied, by card id. A card held many times is a list.
export function relatedCards(schema, project, card) {
  const related = {};
  for (const id of card.reads ?? []) {
    if (schema.cards[id] && project[id] !== undefined) related[id] = copyOf(project[id]);
  }
  return related;
}

// A reply that failed: the same shape whether the backend sent it or the page made it.
export function failure(kind, detail = "") {
  return { ok: false, error: { kind: ERROR_KINDS.includes(kind) ? kind : "server", detail: String(detail ?? "") } };
}

// The envelope check shared by every reply. Returns the reply when it is {ok: true}, else a failure.
export function readReply(reply) {
  if (reply === null || typeof reply !== "object" || Array.isArray(reply)) return failure("bad_output", "The reply is not an object.");
  if (reply.ok === false) return failure(reply.error?.kind, reply.error?.detail);
  if (reply.ok !== true) return failure("bad_output", "The reply does not say whether it worked.");
  return reply;
}

export function readStatus(reply) {
  const checked = readReply(reply);
  if (!checked.ok) return checked;
  if (checked.state !== "idle" && checked.state !== "busy") return failure("bad_output", "The state is neither idle nor busy.");
  const stage = STAGES.includes(checked.stage) ? checked.stage : null;
  return stage && checked.state === "busy" ? { ok: true, state: checked.state, stage } : { ok: true, state: checked.state };
}

// Fill: {ok: true, request} or {ok: false, reason}. The model may only fill a card when there is something to fill it
// from: the example chapter, or a note for that card (for a character, a note about that character).
export function fillRequest(schema, project, cardId, instanceId = null) {
  const card = schema.cards[cardId];
  if (!card) return { ok: false, reason: "unknown_card" };
  if (!FILLABLE.includes(cardId)) return { ok: false, reason: "not_fillable" };
  let values;
  if (card.many_per_project) {
    values = findInstance(project, card, instanceId);
    if (!values) return { ok: false, reason: "no_instance" };
  } else {
    values = project[cardId] ?? blankCard(card);
  }
  const note = (project.card_notes ?? []).find((n) => n.card === cardId && (!card.many_per_project || n.character === instanceId));
  const noteText = isFilled(note?.text?.trim()) ? note.text : null;
  const example = isFilled(project.example_chapter?.trim()) ? project.example_chapter : null;
  if (!noteText && !example) return { ok: false, reason: "no_source" };
  return {
    ok: true,
    request: {
      ...envelope(schema, project, "fill"),
      card: cardId, instance: card.many_per_project ? instanceId : null,
      note: noteText, example_chapter: example,
      values: copyOf(values), related: relatedCards(schema, project, card),
    },
  };
}

// Fill reply: the card's fields by key. Keys the card does not have are set aside and named, not kept.
// A value of the wrong kind (a list where text goes, text where a list goes) is a shape failure.
export function readFillReply(card, reply) {
  const checked = readReply(reply);
  if (!checked.ok) return checked;
  const given = checked.values;
  if (given === null || typeof given !== "object" || Array.isArray(given)) return failure("bad_output", "The reply has no values.");
  const known = new Map(card.fields.map((f) => [f.key, f]));
  const values = {};
  const ignored = [];
  for (const [key, value] of Object.entries(given)) {
    const field = known.get(key);
    if (!field) {
      ignored.push(key);
    } else if (!rightKind(field, value)) {
      return failure("bad_output", `The value for ${key} is the wrong kind of thing.`);
    } else {
      values[key] = field.repeat ? oneEach(field, value) : value;
    }
  }
  return { ok: true, values, ignored };
}

// An either-or pair ("a world rule or a fact of your own") holds one value. The model is asked for one, but if it gives both,
// the first of the pair as the card declares it is kept and the other is dropped, so the page never holds a hidden second value.
export function oneEach(field, items) {
  const groups = field.one_of ?? [];
  if (!groups.length) return items;
  return items.map((item) => {
    const out = { ...item };
    for (const group of groups) {
      const first = group.fields.find((key) => isFilled(out[key]));
      if (first) for (const key of group.fields) if (key !== first) delete out[key];
    }
    return out;
  });
}

const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const isPlain = (v) => v === null || ["string", "number", "boolean"].includes(typeof v);

// A single value (not a list of items) is the right kind when it is text, a number or a tick box, or, for a
// multiple choice, a list of those. A list field holds objects whose own values follow the same rule.
function rightValue(field, value) {
  return field.input === "select-multiple" ? Array.isArray(value) && value.every(isPlain) : isPlain(value);
}

function rightKind(field, value) {
  if (!field.repeat) return rightValue(field, value);
  if (!Array.isArray(value)) return false;
  const defs = new Map((field.item_fields ?? []).map((f) => [f.key, f]));
  return value.every((item) => isObject(item) && Object.entries(item).every(([key, v]) => !defs.has(key) || rightValue(defs.get(key), v)));
}

// ---- Landing a fill ------------------------------------------------------
// The model names what a link points at in words ("Suvi", "the Salt Guild"). The page turns the words into ids here,
// once, so the same code runs in the page and in Node. Words that match nothing, or match two entries, are left empty
// and reported, never guessed.

const squash = (text) => String(text ?? "").trim().replace(/\s+/g, " ").toLowerCase();

// One word or phrase -> an id: {id} when exactly one entry has that name (or the text already is an id),
// {none: true} or {several: true} otherwise.
export function wordsToId(project, sources, words) {
  const options = refOptions(project, sources, "");
  const text = String(words ?? "").trim();
  const byId = options.find((o) => o.value === text);
  if (byId) return { id: byId.value };
  const want = squash(text);
  const hits = options.filter((o) => o.label && squash(o.label) === want);
  if (hits.length === 1) return { id: hits[0].value };
  return hits.length ? { several: true } : { none: true };
}

function resolveValue(project, field, value, where, unresolved) {
  if (!field.ref || !isFilled(value)) return value;
  const one = (words) => {
    const found = wordsToId(project, field.ref, words);
    if (found.id) return found.id;
    unresolved.push({ ...where, words: String(words), why: found.several ? "several" : "none" });
    return null;
  };
  if (Array.isArray(value)) return value.map(one).filter((id) => id !== null);
  return one(value) ?? "";
}

// The fill's values with every link turned into an id. Returns {values, unresolved: [{field, item?, key?, words, why}]}.
export function resolveFillLinks(card, values, project) {
  const unresolved = [];
  const out = {};
  for (const field of card.fields) {
    if (!(field.key in values)) continue;
    const value = values[field.key];
    if (field.repeat) {
      out[field.key] = (value ?? []).map((item, index) => {
        const resolved = { ...item };
        for (const def of field.item_fields ?? []) {
          if (def.key in item) resolved[def.key] = resolveValue(project, def, item[def.key], { field: field.key, index, key: def.key }, unresolved);
        }
        return resolved;
      });
    } else {
      out[field.key] = resolveValue(project, field, value, { field: field.key }, unresolved);
    }
  }
  return { values: out, unresolved };
}

const withoutIds = (list) => JSON.stringify((list ?? []).map(({ id, ...rest }) => rest));
export const sameValue = (field, a, b) => (field.repeat ? withoutIds(a) === withoutIds(b) : JSON.stringify(a) === JSON.stringify(b));

// What the card holds right now that a fill could replace: the keys of the fields with something in them.
export function filledFieldKeys(card, values) {
  return card.fields.filter((field) => isFilled(values[field.key])).map((field) => field.key);
}

// Work out what a fill would do to a card, without doing it.
//   current  the card's values now (one character's, for Characters)
//   reply    the values from readFillReply
// Only a field the model gave something for can change; an empty answer never wipes what the writer wrote.
// Every new list item gets a fresh id. Returns
//   {ok, next, before, filled, replaced, unchanged, unresolved, ignored}
//   next       the card's values as they would be after the fill (a copy)
//   before     a copy of the values as they are now, kept so Undo can put them back
//   filled     keys that were empty and now have the model's words
//   replaced   keys that had the writer's words and would change (the page asks before this happens)
//   unchanged  keys the model gave back exactly as they were
//   unresolved links the model named that match nothing here (see resolveFillLinks)
export function planFill(card, current, reply, project) {
  const before = copyOf(current);
  const next = copyOf(current);
  const { values, unresolved } = resolveFillLinks(card, reply.values, project);
  const filled = [];
  const replaced = [];
  const unchanged = [];
  const taken = [];
  for (const field of card.fields) {
    if (!(field.key in values) || !isFilled(values[field.key])) continue;
    let value = values[field.key];
    if (field.repeat) {
      value = value.map((item) => {
        const fresh = { ...blankFields(field.item_fields ?? []), id: newId(taken) };
        taken.push(fresh.id);
        for (const def of field.item_fields ?? []) if (def.key in item) fresh[def.key] = item[def.key];
        return fresh;
      });
    }
    if (sameValue(field, current[field.key], value)) unchanged.push(field.key);
    else {
      (isFilled(current[field.key]) ? replaced : filled).push(field.key);
      next[field.key] = value;
    }
  }
  return { ok: true, next, before, filled, replaced, unchanged, unresolved, ignored: reply.ignored ?? [] };
}

// Put values into a card's values object in place, so whatever holds that object sees the change (used for the fill
// and for Undo). Only the keys the card has are written; the instance id is never touched.
export function setCardValues(card, target, values) {
  for (const field of card.fields) if (field.key in values) target[field.key] = copyOf(values[field.key]);
  return target;
}

// The model-judged rules for one card. `ruleIds` narrows which to ask about (all of them when left out).
export function judgeRequest(schema, project, cardId, values, ruleIds = null) {
  const card = schema.cards[cardId];
  const rules = modelRules(card).filter((rule) => !ruleIds || ruleIds.includes(rule.id));
  return {
    ...envelope(schema, project, "judge"),
    card: cardId, instance: values.id ?? null,
    rules: rules.map((rule) => ({ id: rule.id, fields: rule.fields ?? [] })),
    values: copyOf(values), related: relatedCards(schema, project, card),
  };
}

// Judge reply -> {ok, problems, answered, missing}. Each hit becomes a problem like the code checks make, so the page
// shows it the same way. A rule the model did not answer is `missing`, never counted as passed. A hit that names a
// field the card does not have is a shape failure. A hit on a list item that is gone falls back to the whole field.
export function readJudgeReply(card, values, sentRuleIds, reply) {
  const checked = readReply(reply);
  if (!checked.ok) return checked;
  if (!Array.isArray(checked.results)) return failure("bad_output", "The reply has no results.");
  const problems = [];
  const answered = [];
  for (const result of checked.results) {
    const rule = modelRules(card).find((r) => r.id === result?.rule);
    if (!rule || !sentRuleIds.includes(rule.id) || answered.includes(rule.id)) continue;
    if (!Array.isArray(result.hits)) return failure("bad_output", `The answer for ${rule.id} has no hits list.`);
    for (const hit of result.hits) {
      const field = card.fields.find((f) => f.key === hit?.field);
      if (!field) return failure("bad_output", `The answer for ${rule.id} names a field the card does not have.`);
      const there = hit.item && (values[field.key] ?? []).some((i) => i.id === hit.item);
      problems.push(problem(card, rule, there ? { field: field.key, item: hit.item, key: hit.key ?? null } : { field: field.key }));
    }
    answered.push(rule.id);
  }
  return { ok: true, problems, answered, missing: sentRuleIds.filter((id) => !answered.includes(id)) };
}

// Style fit: the style card against the protagonist Setup chose. Needs both.
export function styleFitRequest(schema, project) {
  const protagonistId = project.setup?.protagonist;
  const protagonist = findInstance(project, schema.cards.characters, protagonistId);
  if (!protagonist) return { ok: false, reason: "no_protagonist" };
  return {
    ok: true,
    request: { ...envelope(schema, project, "style_fit"), style: copyOf(project.style ?? {}), protagonist: copyOf(protagonist) },
  };
}

export function readStyleFitReply(reply) {
  const checked = readReply(reply);
  if (!checked.ok) return checked;
  if (typeof checked.fits !== "boolean") return failure("bad_output", "The reply does not say whether the style fits.");
  return { ok: true, fits: checked.fits, message: typeof checked.message === "string" ? checked.message : "" };
}

// ---- The story calls: replies -----------------------------------------------
// Shape only. Links in these replies are words (names, or the wording the page sent); the steps that use each reply
// turn them into ids, the way the fill does. A reply whose shape is wrong is a bad_output and changes nothing.

const isText = (value) => typeof value === "string";
const isOptionalText = (value) => value === undefined || value === null || typeof value === "string";
const isTextList = (value) => Array.isArray(value) && value.every(isText);
const bad = (detail) => failure("bad_output", detail);

export function readOffstageReply(reply) {
  const checked = readReply(reply);
  if (!checked.ok) return checked;
  if (!isText(checked.did) || !isText(checked.reach)) return bad("The offstage move needs words for what happened and how it reaches the protagonist.");
  if (!checked.did.trim() || !checked.reach.trim()) return bad("The offstage move is missing one of its two parts.");
  return { ok: true, did: checked.did.trim(), reach: checked.reach.trim() };
}

export function readPlanReply(reply) {
  const checked = readReply(reply);
  if (!checked.ok) return checked;
  if (!isText(checked.thinking)) return bad("The plan has no thinking text.");
  if (!isObject(checked.beat)) return bad("The plan has no beat.");
  return { ok: true, thinking: checked.thinking, beat: checked.beat };
}

const SHIFT_TEXT = ["believes", "fears", "wants", "refuses", "decided"];
const CHANGE_SECTIONS = ["ties", "holdings", "knowledge", "pressures"];
export const KNOWLEDGE_STATUSES = ["knows", "suspects", "misled"];
export const GOAL_CHANGES = ["achieved", "redefined", "abandoned"];

export function readGenerateReply(reply) {
  const checked = readReply(reply);
  if (!checked.ok) return checked;
  if (!isText(checked.chapter_text) || !checked.chapter_text.trim()) return bad("The chapter text is empty.");
  const e = checked.events;
  if (!isObject(e) || !isText(e.happened) || !e.happened.trim()) return bad("The chapter's events are missing.");
  if (!isOptionalText(e.changed) || !isOptionalText(e.planted)) return bad("The chapter's events have text of the wrong kind.");
  const lists = ["paid_off", "reveals_landed", "behaviors_seen", "things_seen"];
  for (const key of lists) if (e[key] !== undefined && !isTextList(e[key])) return bad(`The events' ${key} is not a list of names.`);
  if (!GOAL_CHANGES.includes(e.goal_change) || !isText(e.goal_now) || !e.goal_now.trim()) return bad("The chapter's events do not say how the goal ended up.");
  if (!Array.isArray(checked.shifts)) return bad("The chapter's shifts are missing.");
  const shifts = [];
  for (const shift of checked.shifts) {
    if (!isObject(shift) || !isText(shift.character) || !shift.character.trim()) return bad("A shift does not say who moved.");
    for (const key of SHIFT_TEXT) if (!isOptionalText(shift[key])) return bad(`A shift's ${key} is not text.`);
    shifts.push({ character: shift.character.trim(), ...Object.fromEntries(SHIFT_TEXT.filter((k) => isText(shift[k]) && shift[k].trim()).map((k) => [k, shift[k].trim()])) });
  }
  if (!Array.isArray(checked.changes)) return bad("The proposed changes are missing.");
  for (const change of checked.changes) {
    if (!isObject(change) || !CHANGE_SECTIONS.includes(change.section) || !isText(change.item) || !isText(change.field) || !("value" in change)) {
      return bad("A proposed change does not say what to change.");
    }
  }
  // New Knowledge entries are optional. Each says who, how they stand, and which rule or fact (the page checks the rest).
  const proposed = checked.new_knowledge ?? [];
  if (!Array.isArray(proposed)) return bad("The new knowledge entries are not a list.");
  const newKnowledge = [];
  for (const entry of proposed) {
    if (!isObject(entry) || !isText(entry.person) || !entry.person.trim() || !KNOWLEDGE_STATUSES.includes(entry.status)) return bad("A new knowledge entry does not say who or how they stand.");
    if (!isOptionalText(entry.rule) || !isOptionalText(entry.fact) || !isOptionalText(entry.belief) || !isOptionalText(entry.entry)) return bad("A new knowledge entry's rule, fact, belief or entry is not text.");
    newKnowledge.push({ person: entry.person.trim(), status: entry.status, rule: entry.rule?.trim() || null, fact: entry.fact?.trim() || null, belief: entry.belief?.trim() || null, entry: entry.entry?.trim() || null });
  }
  // Which entanglements (ids the page sent) the chapter showed. Optional.
  const shown = checked.shown ?? [];
  if (!isTextList(shown)) return bad("The shown entanglements are not a list of ids.");
  const events = {
    happened: e.happened.trim(), changed: e.changed?.trim() || null, planted: e.planted?.trim() || null,
    goal_change: e.goal_change, goal_now: e.goal_now.trim(),
  };
  for (const key of lists) events[key] = e[key] ?? [];
  return { ok: true, chapter_text: checked.chapter_text, events, shifts, changes: checked.changes.map((c) => ({ section: c.section, item: c.item, field: c.field, value: c.value })), new_knowledge: newKnowledge, shown };
}

export function readEndStoryReply(reply) {
  const checked = readReply(reply);
  if (!checked.ok) return checked;
  if (!Array.isArray(checked.characters) || !checked.characters.every((c) => isObject(c) && isText(c.id))) {
    return bad("The updated characters must each carry the id they were sent with.");
  }
  if (!isObject(checked.world)) return bad("The updated world is missing.");
  return { ok: true, characters: checked.characters, world: checked.world };
}

// ---- The code checks -------------------------------------------------------
// Each takes {rule, card, values, project} and returns where the rule is broken: [{field, item?, key?, tokens?}].

// Every item of the list fields a rule names, as {field, item (the object), fields (its field definitions)}.
// A rule that names a plain field (not a list) gets the card's own values.
function targets(card, rule, values) {
  const out = [];
  for (const key of rule.fields ?? []) {
    const field = card.fields.find((f) => f.key === key);
    if (!field) continue;
    if (field.repeat) for (const item of values[key] ?? []) out.push({ field: key, item, defs: field.item_fields ?? [], list: values[key] });
    else out.push({ field: key, item: null, defs: [field], list: null, own: values });
  }
  return out;
}

const place = (target, key) => (target.item ? { field: target.field, item: target.item.id, key } : { field: key, item: null, key: null });
const valueOf = (target, key) => (target.item ?? target.own)[key];
const asList = (value) => (Array.isArray(value) ? value : isFilled(value) ? [value] : []);

// {key: value | [values] | "filled"} holds for these values (the same meaning as visible_if).
function conditionHolds(cond, values) {
  return isVisible({ visible_if: cond }, values);
}

// A link must still point at something that exists. Which fields hold links is read from each field's `ref`.
CHECKS.ref_exists = ({ card, rule, values, project }) => {
  const hits = [];
  for (const target of targets(card, rule, values)) {
    for (const def of target.defs) {
      if (!def.ref || (rule.params?.skip ?? []).includes(def.key)) continue;
      const have = new Set(refOptions(project, def.ref).map((o) => o.value));
      if (asList(valueOf(target, def.key)).some((id) => !have.has(id))) hits.push(place(target, def.key));
    }
  }
  return hits;
};

// Exactly one of two fields is filled. Reported on the first.
CHECKS.exactly_one = ({ card, rule, values }) => {
  const [a, b] = rule.params.fields;
  const hits = [];
  for (const target of targets(card, rule, values)) {
    const count = [a, b].filter((key) => isFilled(valueOf(target, key))).length;
    if (count !== 1) hits.push(place(target, a));
  }
  return hits;
};

// Both fields filled or both empty.
CHECKS.all_or_none = ({ card, rule, values }) => {
  const [a, b] = rule.params.fields;
  const hits = [];
  for (const target of targets(card, rule, values)) {
    const filledA = isFilled(valueOf(target, a));
    const filledB = isFilled(valueOf(target, b));
    if (filledA !== filledB) hits.push(place(target, filledA ? b : a));
  }
  return hits;
};

// At least one of the named list fields has something in it. Reported on the first.
CHECKS.any_filled = ({ card, rule, values }) => {
  const hits = [];
  for (const target of targets(card, rule, values)) {
    if (!rule.params.fields.some((key) => isFilled(valueOf(target, key)))) hits.push(place(target, rule.params.fields[0]));
  }
  return hits;
};

// No value is in more than one of the named list fields. Reported on the second list that repeats a value.
CHECKS.disjoint_lists = ({ card, rule, values }) => {
  const hits = [];
  for (const target of targets(card, rule, values)) {
    const seen = new Set();
    for (const key of rule.params.fields) {
      const own = Array.isArray(valueOf(target, key)) ? valueOf(target, key) : [];
      if (own.some((v) => seen.has(v))) { hits.push(place(target, key)); break; }
      own.forEach((v) => seen.add(v));
    }
  }
  return hits;
};

CHECKS.fields_differ = ({ card, rule, values }) => {
  const [a, b] = rule.params.fields;
  const hits = [];
  for (const target of targets(card, rule, values)) {
    const x = valueOf(target, a);
    if (isFilled(x) && x === valueOf(target, b)) hits.push(place(target, b));
  }
  return hits;
};

// A holder must be a kind the held thing allows (the card's holding_pairs table).
CHECKS.holding_pairs_allowed = ({ card, rule, values, project }) => {
  const hits = [];
  for (const target of targets(card, rule, values)) {
    const thing = target.defs.find((d) => d.ref_filter_by == null && d.ref && d.key === "holdee");
    const holder = target.defs.find((d) => d.ref_filter_by);
    if (!thing || !holder) continue;
    const kind = sourceOfId(project, thing.ref, target.item[thing.key]);
    // The holder may be a kind the picker would not offer (a thing), so look it up across every kind of holdable thing too.
    const holderKind = sourceOfId(project, [...new Set([...holder.ref, ...Object.keys(card.holding_pairs ?? {})])], target.item[holder.key]);
    if (kind && holderKind && !(card.holding_pairs?.[kind] ?? []).includes(holderKind)) hits.push(place(target, holder.key));
  }
  return hits;
};

// A list is too short or too long. Items with nothing typed do not count, and neither does an item that holds every value of
// params.skip ({field: value}: a resolved pressure is not an active one).
CHECKS.item_count = ({ card, rule, values }) => {
  const { min, max, skip } = rule.params;
  const skipped = (item) => Boolean(skip) && Object.entries(skip).every(([k, v]) => item?.[k] === v);
  const hits = [];
  for (const key of rule.fields ?? []) {
    const count = (values[key] ?? []).filter((item) => !isItemEmpty(item) && !skipped(item)).length;
    if ((min != null && count < min) || (max != null && count > max)) hits.push({ field: key });
  }
  return hits;
};

// params: {field, when: cond} | {field, when_present: key} | {field, unless: cond}. Items only.
CHECKS.required_if = ({ card, rule, values }) => {
  const { field, when, when_present: present, unless } = rule.params;
  const hits = [];
  for (const target of targets(card, rule, values)) {
    if (!target.item) continue;
    let needed = true;
    if (when) needed = needed && conditionHolds(when, target.item);
    if (present) needed = needed && isFilled(target.item[present]);
    if (unless) needed = needed && !conditionHolds(unless, target.item);
    if (needed && !isFilled(target.item[field])) hits.push(place(target, field));
  }
  return hits;
};

// The protagonist from Setup is on stage in every beat that has a cast. With no protagonist yet, nothing to check.
CHECKS.includes_value = ({ card, rule, values, project }) => {
  const [cardId, key] = rule.params.value_from.split(".");
  const wanted = project[cardId]?.[key];
  if (!isFilled(wanted)) return [];
  return targets(card, rule, values)
    .filter((t) => t.item && isFilled(t.item[rule.params.field]) && !asList(t.item[rule.params.field]).includes(wanted))
    .map((t) => place(t, rule.params.field));
};

// Pacing, from the earlier beats only: at most two Harder in a row, and never two Easier in a row. A beat with no
// shift chosen breaks a run, and so does a missing chapter number. legalShifts is also what the page uses to grey out choices.
export const MAX_HARDER_IN_A_ROW = 2;
export const MAX_EASIER_IN_A_ROW = 1;

function shiftRun(beats, chapter, value) {
  const byChapter = new Map(beats.map((b) => [Number(b.chapter), b.shift]));
  let run = 0;
  for (let n = Number(chapter) - 1; n >= 1 && byChapter.get(n) === value; n--) run++;
  return run;
}

export function legalShifts(beats, beat) {
  if (!isFilled(beat.chapter)) return ["harder", "easier"];
  const others = beats.filter((b) => b !== beat);
  return ["harder", "easier"].filter((value) =>
    shiftRun(others, beat.chapter, value) < (value === "harder" ? MAX_HARDER_IN_A_ROW : MAX_EASIER_IN_A_ROW));
}

CHECKS.legal_shift = ({ card, rule, values }) =>
  targets(card, rule, values)
    .filter((t) => t.item && isFilled(t.item.shift) && !legalShifts(t.list, t.item).includes(t.item.shift))
    .map((t) => place(t, "shift"));

// Names of the characters and of the world's places, things and groups, to spot a card that names them when it should not.
function knownNames(project, sources, skipId) {
  return refOptions(project, sources, "")
    .filter((o) => o.label && o.label.length > 1 && o.value !== skipId)
    .map((o) => o.label);
}

function mentions(text, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (/[\u3040-\u30ff\u3400-\u9fff]/.test(name)) return text.toLowerCase().includes(name.toLowerCase());
  return new RegExp(`(?<![\\p{L}\\p{N}])${escaped}(?![\\p{L}\\p{N}])`, "iu").test(text);
}

// Which context names a rule looks for: character_names, world_names. A character's own name is not counted against it.
CHECKS.mentions_known_names = ({ card, rule, values, project }) => {
  const sources = [];
  if (rule.context?.includes("character_names")) sources.push("characters");
  if (rule.context?.includes("world_names")) sources.push("world.places", "world.objects", "world.powers");
  const names = knownNames(project, sources, card.many_per_project ? values.id : null);
  const hits = [];
  for (const target of targets(card, rule, values)) {
    for (const def of target.defs) {
      if (def.input !== "text" && def.input !== "textarea") continue;
      const text = valueOf(target, def.key);
      if (typeof text !== "string" || !text.trim()) continue;
      const found = names.filter((name) => mentions(text, name));
      if (found.length) hits.push({ ...place(target, def.key), tokens: { names: joinList([...new Set(found)]) } });
    }
  }
  return hits;
};

// A reveal that already came to light in another chapter cannot be planned again. This beat's own chapter does not count,
// because writing it again replaces that record.
CHECKS.not_already_landed = ({ card, rule, values, project }) => {
  const field = rule.params.field;
  return targets(card, rule, values)
    .filter((t) => t.item && isFilled(t.item[field]) &&
      (project.summary_events?.entries ?? []).some((e) => e.beat !== t.item.id && (e.reveals_landed ?? []).includes(t.item[field])))
    .map((t) => place(t, field));
};

// A payoff must point at an earlier chapter's plant that nothing else has paid off.
CHECKS.paid_off_valid = ({ card, rule, values, project }) => {
  const field = rule.params.field;
  const entries = project.summary_events?.entries ?? [];
  const hits = [];
  for (const t of targets(card, rule, values)) {
    if (!t.item) continue;
    const bad = asList(t.item[field]).some((id) => {
      const entry = entries.find((e) => e.id === id);
      if (!entry || !isFilled(entry.planted)) return true;
      if (entries.some((e) => e.beat !== t.item.id && (e.paid_off ?? []).includes(id))) return true;
      const planted = (t.list ?? []).find((b) => b.id === entry.beat);
      return Boolean(planted && isFilled(planted.chapter) && isFilled(t.item.chapter) && Number(planted.chapter) >= Number(t.item.chapter));
    });
    if (bad) hits.push(place(t, field));
  }
  return hits;
};

// The spotlighted pressure must involve someone on stage: its agent, or something it bears on.
CHECKS.pressure_touches_cast = ({ card, rule, values, project }) => {
  const { field, cast } = rule.params;
  const pressures = project.entanglements?.pressures ?? [];
  const hits = [];
  for (const t of targets(card, rule, values)) {
    const pressure = t.item && pressures.find((p) => p.id === t.item[field]);
    const onStage = asList(t.item?.[cast]);
    if (!pressure || !onStage.length) continue;
    const involved = [pressure.source_agent, ...asList(pressure.bears_on)].filter(isFilled);
    if (!involved.some((id) => onStage.includes(id))) hits.push(place(t, field));
  }
  return hits;
};

// Two lines are "too similar" when most of their meaningful words are shared. A rough measure, tuned by this one number.
export const SIMILARITY_LIMIT = 0.6;
// The little words that carry no meaning in the page's language ("the", "and"), read from the text bundle.
let stopSet = null;
function stopWords() {
  const text = msg("language.stopWords");
  if (stopSet?.text !== text) stopSet = { text, set: new Set(text.split(" ")) };
  return stopSet.set;
}

function words(text) {
  const stop = stopWords();
  return new Set((String(text).toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []).filter((w) => w.length > 2 && !stop.has(w)));
}

export function similarity(a, b) {
  const x = words(a);
  const y = words(b);
  if (x.size < 3 || y.size < 3) return 0;
  let shared = 0;
  for (const w of x) if (y.has(w)) shared++;
  return shared / Math.min(x.size, y.size);
}

// The aim (params.field) against the aims of earlier beats and against the "changed" lines of written chapters.
CHECKS.similar_to_earlier = ({ card, rule, values, project }) => {
  const key = rule.params?.field ?? "collision_goal";
  const changed = (project.summary_events?.entries ?? []).filter((e) => isFilled(e.changed)).map((e) => ({ beat: e.beat, text: e.changed }));
  return targets(card, rule, values)
    .filter((t) => t.item && isFilled(t.item[key]))
    .filter((t) => {
      const earlier = t.list.filter((b) => b !== t.item && isFilled(b[key]) && Number(b.chapter) < Number(t.item.chapter)).map((b) => b[key]);
      const lines = changed.filter((c) => c.beat !== t.item.id).map((c) => c.text);
      return [...earlier, ...lines].some((text) => similarity(t.item[key], text) >= SIMILARITY_LIMIT);
    })
    .map((t) => place(t, key));
};
