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

export function blankCard(card) {
  const values = {};
  for (const field of card.fields) values[field.key] = blankValue(field);
  return values;
}

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

// The project is the saved file. A one-per-project card lives at project[cardId].
export function cardValues(project, cardId) {
  return project[cardId] ?? {};
}

// Add blanks for any key the project does not have yet. Never overwrites a value that is there.
export function ensureCard(project, card) {
  const current = project[card.id] ?? {};
  const merged = { ...blankCard(card), ...current };
  project[card.id] = merged;
  return merged;
}

export function setField(project, cardId, key, value) {
  if (project[cardId] === undefined) project[cardId] = {};
  project[cardId][key] = value;
  return project;
}

// A stand-in until the project shell exists: just enough of a project to hold the cards on screen.
export function newProject(schema) {
  return { title: "", schema_version: schema.schema_version };
}
