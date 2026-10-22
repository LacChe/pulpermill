// Deterministic page logic, written once and kept free of the DOM so Node can test it.
// Everything here works on plain objects: the schema JSON and the project object.

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
    return Array.isArray(value) ? value.map((v) => resolve(v, key)).join(", ") : resolve(value, key);
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
  return removeItem(project[card.id] ?? [], id);
}

export function findInstance(project, card, id) {
  return (project[card.id] ?? []).find((i) => i.id === id);
}

// What to call one instance in a list of them: its name, or nothing if it has none yet.
export function instanceName(instance) {
  return typeof instance.name === "string" ? instance.name.trim() : "";
}

// A stand-in until the project shell exists: just enough of a project to hold the cards on screen.
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
export function projectFileName(project, fallback = "pulpermill-project") {
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
export function refOptions(project, sources, unnamed = "Unnamed", options = {}) {
  const { where, keep = [] } = options;
  const paidOff = new Set((project.summary_events?.entries ?? []).flatMap((e) => e.paid_off ?? []));
  const landed = new Set((project.summary_events?.entries ?? []).flatMap((e) => e.reveals_landed ?? []));
  const out = [];
  for (const source of sources) {
    for (const item of sourceList(project, source)) {
      if (!keep.includes(item.id)) {
        if (source === "summary_events.entries" && (!isFilled(item.planted) || paidOff.has(item.id))) continue;
        if (where && source === "world.rules" && landed.has(item.id)) continue;
        if (where && !Object.entries(where).every(([key, allowed]) => allowed.includes(item[key]))) continue;
      }
      out.push({ value: item.id, label: entryLabel(item, unnamed), source });
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
export function lookupLabel(project, itemField, value, unnamed = "Unnamed") {
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

// What the Validate button hands to the model checks. The backend call itself comes later; for now this only
// gathers the rules that need the model and a snapshot of the values they judge.
export function modelCheckRequest(card, values) {
  return {
    card: card.id,
    instance: values.id ?? null,
    rules: modelRules(card).map((rule) => ({ id: rule.id, severity: rule.severity, fields: rule.fields ?? [] })),
    values: JSON.parse(JSON.stringify(values)),
  };
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
      if (!def.ref) continue;
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

// A list is too short or too long. Items with nothing typed do not count.
CHECKS.item_count = ({ card, rule, values }) => {
  const { min, max } = rule.params;
  const hits = [];
  for (const key of rule.fields ?? []) {
    const count = (values[key] ?? []).filter((item) => !isItemEmpty(item)).length;
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
      if (found.length) hits.push({ ...place(target, def.key), tokens: { names: [...new Set(found)].join(", ") } });
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
const STOP = new Set("the a an and or but of to in on at for with by from as is are was were be been it its this that these those he she they his her their them then than so not no".split(" "));

function words(text) {
  return new Set((String(text).toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []).filter((w) => w.length > 2 && !STOP.has(w)));
}

export function similarity(a, b) {
  const x = words(a);
  const y = words(b);
  if (x.size < 3 || y.size < 3) return 0;
  let shared = 0;
  for (const w of x) if (y.has(w)) shared++;
  return shared / Math.min(x.size, y.size);
}

// The turn against the turns of earlier beats and against the "changed" lines of written chapters.
CHECKS.similar_to_earlier = ({ card, rule, values, project }) => {
  const changed = (project.summary_events?.entries ?? []).filter((e) => isFilled(e.changed)).map((e) => ({ beat: e.beat, text: e.changed }));
  return targets(card, rule, values)
    .filter((t) => t.item && isFilled(t.item.turn))
    .filter((t) => {
      const earlier = t.list.filter((b) => b !== t.item && isFilled(b.turn) && Number(b.chapter) < Number(t.item.chapter)).map((b) => b.turn);
      const lines = changed.filter((c) => c.beat !== t.item.id).map((c) => c.text);
      return [...earlier, ...lines].some((text) => similarity(t.item.turn, text) >= SIMILARITY_LIMIT);
    })
    .map((t) => place(t, "turn"));
};
