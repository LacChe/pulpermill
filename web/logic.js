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
//   [{field, item?, key?, tokens?}]. Filled in one check at a time.
export const CHECKS = {};

// Code rules whose check is named in the schema but not written yet. A test keeps this list honest:
// every named check has a function here or is listed in PENDING_CHECKS, so none can be forgotten.
export const PENDING_CHECKS = [
  "all_or_none", "exactly_one", "fields_differ", "holding_pairs_allowed", "includes_value", "item_count",
  "legal_shift", "mentions_known_names", "not_already_landed", "paid_off_valid", "pressure_touches_cast",
  "ref_exists", "required_if", "similar_to_earlier",
];

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
