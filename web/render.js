// Draws one card as a form. Only this file touches the DOM. All wording comes from the schema JSON,
// except the few page labels in STRINGS below, which move into the text files when languages are added.
import {
  addItem, canAdd, groupedFields, isItemEmpty, isVisible, itemTitle, removeItem,
} from "./logic.js";

export const STRINGS = {
  optional: "Optional",
  why: "Why this matters",
  good: "Works well",
  avoid: "Avoid",
  newItem: "New item",
  remove: "Remove",
  unsupported: "This field type isn't built yet.",
};

const TEXT_INPUTS = new Set(["text", "textarea", "number"]);

// Input types the renderer can draw. The Node test checks that every field on a finished card passes.
export function isSupported(field) {
  if (field.repeat) return (field.item_fields || []).every(isSupported);
  return field.input === "select" || TEXT_INPUTS.has(field.input);
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === false || value === undefined || value === null) continue;
    if (name === "class") node.className = value;
    else if (name === "text") node.textContent = value;
    else node.setAttribute(name, value === true ? "" : value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

function examplesBlock(examples) {
  const box = el("div", { class: "examples" });
  for (const [kind, label] of [["good", STRINGS.good], ["avoid", STRINGS.avoid]]) {
    const lines = examples[kind];
    if (!lines || !lines.length) continue;
    const list = el("ul");
    for (const line of lines) list.append(el("li", { text: line }));
    box.append(el("div", { class: `examples-${kind}` }, el("strong", { text: label }), list));
  }
  return box;
}

function whyBlock(why) {
  return el("details", { class: "why" }, el("summary", { text: STRINGS.why }), el("p", { text: why }));
}

function selectControl(path, field, value, onInput) {
  const wrap = el("div", { class: "options", role: "radiogroup", "aria-label": field.label });
  for (const option of field.options || []) {
    const input = el("input", { type: "radio", name: path, value: option.value });
    input.checked = value === option.value;
    input.addEventListener("change", () => onInput(option.value));
    wrap.append(el("label", { class: "option" }, input,
      el("span", { class: "option-label", text: option.label }),
      option.description ? el("span", { class: "option-description", text: option.description }) : null));
  }
  return wrap;
}

function textControl(field, value, onInput) {
  const isArea = field.input === "textarea";
  const control = el(isArea ? "textarea" : "input", {
    class: "text-control",
    placeholder: field.placeholder,
    rows: isArea ? 3 : false,
    type: isArea ? false : field.input === "number" ? "number" : "text",
    step: field.input === "number" ? "1" : false,
    "aria-label": field.label,
  });
  control.value = value ?? "";
  control.addEventListener("input", () => {
    onInput(field.input === "number" ? (control.value === "" ? null : Number(control.value)) : control.value);
  });
  return control;
}

// One field of one object (a card, or one item in a list). `values` is that object; it is changed in place.
function fieldBlock(field, values, path, ctx) {
  const block = el("div", { class: "field", "data-path": path });
  const heading = el("div", { class: "field-heading" }, el("span", { class: "field-label", text: field.label }));
  if (field.required === false) heading.append(el("span", { class: "tag", text: STRINGS.optional }));
  block.append(heading);
  if (field.help) block.append(el("p", { class: "help", text: field.help }));

  if (field.repeat) {
    block.append(listControl(field, values, path, ctx));
    if (field.why) block.append(whyBlock(field.why));
    return block;
  }
  if (!isSupported(field)) {
    block.append(el("p", { class: "unsupported", text: STRINGS.unsupported }));
    return block;
  }

  const onInput = (next) => { values[field.key] = next; ctx.changed(); };
  block.append(field.input === "select"
    ? selectControl(path, field, values[field.key], onInput)
    : textControl(field, values[field.key], onInput));
  if (field.examples) block.append(examplesBlock(field.examples));
  if (field.why) block.append(whyBlock(field.why));
  return block;
}

// Show or hide the fields of one object whose visible_if depends on a sibling.
function applyVisibility(fields, scope, values, prefix) {
  for (const field of fields) {
    if (!field.visible_if) continue;
    const block = scope.querySelector(`[data-path="${CSS.escape(prefix + field.key)}"]`);
    if (block) block.hidden = !isVisible(field, values);
  }
}

// Draws the fields of one object into `body`, wiring conditional fields.
function fieldsInto(body, fields, values, prefix, ctx, scope) {
  for (const field of fields) {
    body.append(fieldBlock(field, values, prefix + field.key, {
      ...ctx,
      changed: () => { applyVisibility(fields, scope, values, prefix); ctx.changed(); },
    }));
  }
}

function itemRow(field, item, list, ctx, redraw) {
  const compact = field.item_fields.length === 1;
  const row = el("div", { class: compact ? "item item-compact" : "item", "data-id": item.id });
  const remove = el("button", { type: "button", class: "remove", text: "×", "aria-label": STRINGS.remove, title: STRINGS.remove });
  remove.addEventListener("click", () => {
    if (!isItemEmpty(item) && field.delete_confirm && !window.confirm(field.delete_confirm)) return;
    removeItem(list, item.id);
    redraw();
    ctx.changed();
  });

  if (compact) {
    const inner = { ...field.item_fields[0], examples: undefined, help: undefined };
    row.append(textControl(inner, item[inner.key], (next) => { item[inner.key] = next; ctx.changed(); }), remove);
    return row;
  }

  const title = el("span", { class: "item-title" });
  const setTitle = () => { title.textContent = itemTitle(field, item, ctx.resolve) || STRINGS.newItem; };
  setTitle();
  row.append(el("div", { class: "item-head" }, title, remove));
  const body = el("div", { class: "item-body" });
  fieldsInto(body, field.item_fields, item, `${field.key}.${item.id}.`, {
    ...ctx, changed: () => { setTitle(); ctx.changed(); },
  }, row);
  row.append(body);
  applyVisibility(field.item_fields, row, item, `${field.key}.${item.id}.`);
  return row;
}

function listControl(field, values, path, ctx) {
  const list = values[field.key];
  const wrap = el("div", { class: "list" });
  const rows = el("div", { class: "items" });
  const empty = el("p", { class: "empty", text: field.empty });
  const add = el("button", { type: "button", class: "add", text: field.add });
  const limit = el("p", { class: "limit" });

  function redraw() {
    rows.replaceChildren(...list.map((item) => itemRow(field, item, list, ctx, redraw)));
    empty.hidden = list.length > 0;
    const full = !canAdd(field, list);
    add.disabled = full;
    limit.hidden = !full;
    limit.textContent = full && ctx.common?.too_many
      ? ctx.common.too_many.message.replace("{label}", field.label).replace("{max}", String(field.max_items))
      : "";
  }
  add.addEventListener("click", () => { if (addItem(field, list)) { redraw(); ctx.changed(); } });

  wrap.append(rows, empty, add, limit);
  // A list of one-box items shows the examples once, under the list, instead of under every row.
  const only = field.item_fields.length === 1 ? field.item_fields[0] : null;
  if (only && only.examples) wrap.append(examplesBlock(only.examples));
  redraw();
  return wrap;
}

// `values` is the one object the card edits (a card held once, or one character). It is changed in place.
// ctx: { common, resolve, changed }
export function renderCard(root, card, values, ctx) {
  root.replaceChildren();
  const section = el("section", { class: "card", "data-card": card.id },
    el("h2", { text: card.label }),
    el("p", { class: "summary", text: card.summary }));
  const resolve = ctx.resolve || ((value) => String(value));
  const inner = { ...ctx, resolve };

  for (const { group, fields } of groupedFields(card)) {
    const body = el("div", { class: "group-body" });
    fieldsInto(body, fields, values, "", inner, section);
    if (!group) { section.append(body); continue; }
    section.append(el("details", { class: "group", open: !group.collapsed },
      el("summary", {}, el("span", { class: "group-label", text: group.label }),
        group.help ? el("span", { class: "group-help", text: group.help }) : null),
      body));
  }
  root.append(section);
  applyVisibility(card.fields, section, values, "");
}
