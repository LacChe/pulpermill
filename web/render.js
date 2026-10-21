// Draws one card as a form. Only this file touches the DOM. All wording comes from the schema JSON,
// except the few page labels in STRINGS below, which move into the text files when languages are added.
import { cardValues, groupedFields, isVisible } from "./logic.js";

export const STRINGS = {
  optional: "Optional",
  why: "Why this matters",
  good: "Works well",
  avoid: "Avoid",
  unsupported: "This field type isn't built yet.",
};

// Input types the renderer can draw. The Node test checks that every field on a finished card is in here.
export const SUPPORTED_INPUTS = new Set(["select", "text", "textarea"]);

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

function selectControl(cardId, field, value, onInput) {
  const wrap = el("div", { class: "options", role: "radiogroup", "aria-label": field.label });
  for (const option of field.options || []) {
    const input = el("input", { type: "radio", name: `${cardId}.${field.key}`, value: option.value });
    input.checked = value === option.value;
    input.addEventListener("change", () => onInput(option.value));
    const label = el("label", { class: "option" }, input,
      el("span", { class: "option-label", text: option.label }),
      option.description ? el("span", { class: "option-description", text: option.description }) : null);
    wrap.append(label);
  }
  return wrap;
}

function textControl(field, value, onInput) {
  const tag = field.input === "textarea" ? "textarea" : "input";
  const control = el(tag, {
    class: "text-control",
    placeholder: field.placeholder,
    rows: tag === "textarea" ? 3 : false,
    type: tag === "input" ? "text" : false,
  });
  control.value = value ?? "";
  control.addEventListener("input", () => onInput(control.value));
  return control;
}

function fieldBlock(card, field, project, onChange) {
  const block = el("div", { class: "field", "data-key": field.key });
  const heading = el("div", { class: "field-heading" }, el("span", { class: "field-label", text: field.label }));
  if (field.required === false) heading.append(el("span", { class: "tag", text: STRINGS.optional }));
  block.append(heading);
  if (field.help) block.append(el("p", { class: "help", text: field.help }));

  if (!SUPPORTED_INPUTS.has(field.input)) {
    block.append(el("p", { class: "unsupported", text: STRINGS.unsupported }));
    return block;
  }

  const value = cardValues(project, card.id)[field.key];
  const onInput = (next) => onChange(field.key, next);
  block.append(field.input === "select"
    ? selectControl(card.id, field, value, onInput)
    : textControl(field, value, onInput));

  if (field.examples) block.append(examplesBlock(field.examples));
  if (field.why) {
    block.append(el("details", { class: "why" },
      el("summary", { text: STRINGS.why }), el("p", { text: field.why })));
  }
  return block;
}

// Show or hide fields whose visible_if depends on a sibling that just changed.
function applyVisibility(card, root, project) {
  const values = cardValues(project, card.id);
  for (const field of card.fields) {
    if (!field.visible_if) continue;
    const block = root.querySelector(`[data-key="${field.key}"]`);
    if (block) block.hidden = !isVisible(field, values);
  }
}

export function renderCard(root, card, project, onChange) {
  root.replaceChildren();
  const section = el("section", { class: "card", "data-card": card.id },
    el("h2", { text: card.label }),
    el("p", { class: "summary", text: card.summary }));

  for (const { group, fields } of groupedFields(card)) {
    const body = el("div", { class: "group-body" });
    for (const field of fields) {
      body.append(fieldBlock(card, field, project, (key, value) => {
        onChange(card.id, key, value);
        applyVisibility(card, section, project);
      }));
    }
    if (!group) { section.append(body); continue; }
    const details = el("details", { class: "group", open: !group.collapsed },
      el("summary", {}, el("span", { class: "group-label", text: group.label }),
        group.help ? el("span", { class: "group-help", text: group.help }) : null),
      body);
    section.append(details);
  }
  root.append(section);
  applyVisibility(card, section, project);
}
