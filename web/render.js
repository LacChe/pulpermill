// Draws one card as a form. Only this file touches the DOM. All wording comes from the schema JSON,
// except the few page labels in STRINGS below, which move into the text files when languages are added.
import {
  addItem, blockedValues, canAdd, chooseOneOf, fieldShown, filledPaths, flagsUsed, groupedFields, isFilled, isItemEmpty, itemTitle,
  legalShifts, lookupLabel, modelCheckRequest, oneOfChoice, pickerSources, problemCounts, problemPath, refOptions,
  removeItem, showsOptionalTag, shownProblems, validate,
} from "./logic.js";

export const STRINGS = {
  optional: "Optional",
  tagLive: "Changes as the story runs",
  tagLiveHelp: "What you write is the starting point. The model updates it as chapters are written, and you can edit it between chapters.",
  tagFixed: "Never changes",
  tagFixedHelp: "The model always gets this exactly as written and never changes it during the story.",
  noteLive: "Fields tagged “{tag}” are where things start. The model updates them chapter by chapter, and you can edit them between chapters.",
  noteFixed: "Fields tagged “{tag}” go to the model exactly as written, and it never changes them during the story.",
  why: "Why this matters",
  good: "Works well",
  avoid: "Avoid",
  newItem: "New item",
  remove: "Delete",
  unnamed: "Unnamed",
  missing: "(no longer exists)",
  characters: "Characters",
  clear: "Clear choice",
  setByCode: "Set by the system",
  unsupported: "This field type isn't built yet.",
  blocks: "Stops generating",
  warns: "Worth a look",
  blockOne: "1 problem stops generating",
  blockMany: "{n} problems stop generating",
  warnOne: "1 warning",
  warnMany: "{n} warnings",
  groupCount: "{n} to check",
  clean: "Nothing wrong found on this page.",
  validate: "Validate",
  modelPending: "Checked what the page can check. {n} more checks need the model and will run once it is connected.",
};

const TEXT_INPUTS = new Set(["text", "textarea", "number"]);

// Input types the renderer can draw. The Node test checks that every field on a finished card passes.
export function isSupported(field) {
  if (field.repeat) return (field.item_fields || []).every(isSupported);
  return field.input === "select" || field.input === "select-multiple" || field.input === "checkbox" || TEXT_INPUTS.has(field.input);
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

// ---- Problems ----------------------------------------------------------------

// The empty place under a field (or a list item, or a whole list) where its problems are written. It is found again
// by its path, the same one logic.js gives each problem. It stays hidden while there is nothing in it.
function problemBox(path, ctx) {
  const box = el("div", { class: "problems", "data-problems": path, "aria-live": "polite", hidden: true });
  ctx.boxes?.set(path, box);
  return box;
}

function problemLine(p) {
  return el("div", { class: `problem problem-${p.severity === "block" ? "block" : "warn"}` },
    el("span", { class: "problem-kind", text: p.severity === "block" ? STRINGS.blocks : STRINGS.warns }),
    el("span", { class: "problem-text", text: p.message }),
    p.fix ? el("span", { class: "problem-fix", text: p.fix }) : null);
}

const countText = (one, many, n) => (n === 1 ? one : many.replace("{n}", String(n)));

// ---- Controls --------------------------------------------------------------

// Radio cards. `options` is [{value, label, description?}].
function radioCards(name, label, options, current, onPick) {
  const wrap = el("div", { class: "options", role: "radiogroup", "aria-label": label });
  for (const option of options) {
    const input = el("input", { type: "radio", name, value: option.value });
    input.checked = current === option.value;
    input.addEventListener("change", () => onPick(option.value));
    wrap.append(el("label", { class: "option" }, input,
      el("span", { class: "option-label", text: option.label }),
      option.description ? el("span", { class: "option-description", text: option.description }) : null));
  }
  return wrap;
}

// A value only the system sets (a chapter number, a fingerprint): shown, not edited. A code-filled box that is also
// a picker (the spotlight) stays editable, because the writer may change what the system chose.
function isCodeFilled(field) {
  return field.filled_by === "code" && !field.ref && !field.options;
}

function checkControl(field, values, scope, ctx) {
  const box = el("input", { type: "checkbox", disabled: isCodeFilled(field) });
  box.checked = Boolean(values[field.key]);
  box.addEventListener("change", () => { values[field.key] = box.checked; ctx.changed(); });
  scope.live.push(() => { box.checked = Boolean(values[field.key]); });
  return el("label", { class: "check" }, box, el("span", { text: field.label }));
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
    readonly: isCodeFilled(field),
  });
  control.value = value ?? "";
  control.addEventListener("input", () => {
    onInput(field.input === "number" ? (control.value === "" ? null : Number(control.value)) : control.value);
  });
  return control;
}

function groupLabel(source, ctx) {
  if (source === "characters") return STRINGS.characters;
  const [cardId, key] = source.split(".");
  return ctx.schema?.cards?.[cardId]?.fields?.find((f) => f.key === key)?.label ?? source;
}

// Options for a link field, in the order of its sources, with a heading per source when there are several.
function pickerOptions(field, values, scope, ctx) {
  const sources = pickerSources(field, values, scope.fields, ctx.project, ctx.card);
  const chosen = values[field.key];
  const keep = Array.isArray(chosen) ? chosen : isFilled(chosen) ? [chosen] : [];
  return { sources, entries: refOptions(ctx.project, sources, STRINGS.unnamed, { where: field.ref_where, keep }) };
}

// A dropdown over entries of other cards. Rebuilds itself when a sibling changes.
function pickerControl(field, values, path, ctx, scope) {
  const wrap = el("div", { class: "picker" });
  const select = el("select", { class: "text-control", "aria-label": field.label });
  const none = el("p", { class: "empty", text: field.no_options });
  const note = el("p", { class: "note" });
  const filtered = field.ref_filter_by && field.filtered_note ? el("p", { class: "note", text: field.filtered_note }) : null;
  select.addEventListener("change", () => { values[field.key] = select.value; ctx.changed(); });

  function refresh() {
    const { sources, entries } = pickerOptions(field, values, scope, ctx);
    const blocked = new Set(blockedValues(ctx.card, scope.owner, field, values));
    // A holder that stopped being allowed after the thing changed is cleared, so the box never holds a wrong value.
    if (field.ref_filter_by && isFilled(values[field.key]) && !entries.some((e) => e.value === values[field.key])) {
      values[field.key] = "";
    }
    select.replaceChildren(el("option", { value: "", disabled: field.required !== false, text: field.placeholder || "" }));
    const bySource = new Map();
    for (const entry of entries) {
      if (!bySource.has(entry.source)) bySource.set(entry.source, []);
      bySource.get(entry.source).push(entry);
    }
    for (const [source, group] of bySource) {
      const parent = sources.length > 1 ? el("optgroup", { label: groupLabel(source, ctx) }) : select;
      for (const entry of group) {
        parent.append(el("option", { value: entry.value, text: entry.label, disabled: blocked.has(entry.value) }));
      }
      if (parent !== select) select.append(parent);
    }
    const current = values[field.key];
    if (isFilled(current) && !entries.some((e) => e.value === current)) {
      select.append(el("option", { value: current, text: STRINGS.missing, disabled: true }));
    }
    select.value = isFilled(current) ? current : "";
    select.hidden = entries.length === 0;
    none.hidden = entries.length > 0;
    const anyBlocked = entries.some((e) => blocked.has(e.value));
    // The reason for a greyed-out choice is only worth showing while the writer is looking at the picker.
    note.textContent = anyBlocked && field.disabled_reason ? field.disabled_reason : "";
    note.hidden = !note.textContent || document.activeElement !== select;
  }
  select.addEventListener("focus", () => { note.hidden = !note.textContent; });
  select.addEventListener("blur", () => { note.hidden = true; });
  scope.live.push(refresh);
  wrap.append(select, none, note);
  if (filtered) wrap.append(filtered);
  return wrap;
}

// Checkboxes over entries of other cards, for fields that take several. max_selected limits how many.
function multiPickerControl(field, values, path, ctx, scope) {
  const wrap = el("div", { class: "picker" });
  const hint = field.placeholder ? el("p", { class: "note", text: field.placeholder }) : null;
  const list = el("div", { class: "checks" });
  const none = el("p", { class: "empty", text: field.no_options });
  if (!Array.isArray(values[field.key])) values[field.key] = [];

  function refresh() {
    const { sources, entries } = pickerOptions(field, values, scope, ctx);
    const chosen = values[field.key];
    const full = field.max_selected && chosen.length >= field.max_selected;
    list.replaceChildren();
    const bySource = new Map();
    for (const entry of entries) {
      if (!bySource.has(entry.source)) bySource.set(entry.source, []);
      bySource.get(entry.source).push(entry);
    }
    for (const [source, group] of bySource) {
      if (sources.length > 1) list.append(el("div", { class: "check-group", text: groupLabel(source, ctx) }));
      for (const entry of group) {
        const box = el("input", { type: "checkbox", value: entry.value });
        box.checked = chosen.includes(entry.value);
        box.disabled = !box.checked && Boolean(full);
        box.addEventListener("change", () => {
          const next = chosen.filter((id) => id !== entry.value);
          if (box.checked) next.push(entry.value);
          values[field.key] = next;
          ctx.changed();
        });
        list.append(el("label", { class: "check" }, box, el("span", { text: entry.label })));
      }
    }
    list.hidden = entries.length === 0;
    none.hidden = entries.length > 0;
    if (hint) hint.hidden = entries.length === 0;
  }
  scope.live.push(refresh);
  wrap.append(...[hint, list, none].filter(Boolean));
  return wrap;
}

// The either-or switch for a pair like "Pushed by: Someone / A circumstance". Shown before the first field of the pair.
function toggleBlock(group, index, values, path, ctx, scope) {
  const memory = scope.memory;
  const options = group.fields.map((key) => ({ value: key, label: group.options[key] ?? key }));
  const block = el("div", { class: "field toggle" },
    el("div", { class: "field-heading" }, el("span", { class: "field-label", text: group.label })));
  block.append(radioCards(`${path}.oneof${index}`, group.label, options, oneOfChoice(group, index, values, memory), (key) => {
    chooseOneOf(group, index, values, memory, key);
    ctx.changed();
  }));
  return block;
}

// ---- Fields ----------------------------------------------------------------

// One field of one object (a card, or one item in a list). `values` is that object; it is changed in place.
function fieldBlock(field, values, path, ctx, scope) {
  const block = el("div", { class: "field", "data-path": path });
  const heading = el("div", { class: "field-heading" }, el("span", { class: "field-label", text: field.label }));
  if (showsOptionalTag(scope.owner, field)) heading.append(el("span", { class: "tag", text: STRINGS.optional }));
  if (field.changes) heading.append(el("span", { class: "tag tag-live", text: STRINGS.tagLive, title: STRINGS.tagLiveHelp }));
  if (field.fixed) heading.append(el("span", { class: "tag tag-fixed", text: STRINGS.tagFixed, title: STRINGS.tagFixedHelp }));
  block.append(heading);
  if (field.help) block.append(el("p", { class: "help", text: field.help }));

  if (field.repeat) {
    block.append(listControl(field, values, path, ctx), problemBox(path, ctx));
    if (field.why) block.append(whyBlock(field.why));
    return block;
  }
  if (!isSupported(field)) {
    block.append(el("p", { class: "unsupported", text: STRINGS.unsupported }));
    return block;
  }

  const onInput = (next) => { values[field.key] = next; ctx.changed(); };
  if (field.input === "select" && field.ref) block.append(pickerControl(field, values, path, ctx, scope));
  else if (field.input === "select-multiple") block.append(multiPickerControl(field, values, path, ctx, scope));
  else if (field.input === "checkbox") {
    heading.hidden = true;
    block.append(checkControl(field, values, scope, ctx));
    // A flag the system sets is only worth showing when it is on.
    if (isCodeFilled(field)) scope.live.push(() => { if (!values[field.key]) block.hidden = true; });
  } else if (field.input === "select") {
    let sync = () => {};
    const cards = radioCards(path, field.label, field.options || [], values[field.key], (next) => { onInput(next); sync(); });
    block.append(cards);
    if (field.limited_by === "code" && field.key === "shift" && ctx.list) {
      // Pacing: the choices the earlier chapters leave open. A choice already made stays selectable so it can be seen and fixed.
      const reason = el("p", { class: "note" });
      const update = () => {
        const legal = legalShifts(ctx.list, values);
        let any = false;
        for (const input of cards.querySelectorAll("input")) {
          input.disabled = !legal.includes(input.value) && values[field.key] !== input.value;
          any = any || !legal.includes(input.value);
        }
        reason.textContent = any ? field.disabled_reason : "";
        reason.hidden = !any;
      };
      // One chapter's shift limits the next ones, so every beat's choices follow a change in any beat.
      scope.live.push(update);
      ctx.siblings?.add(update);
      block.append(reason);
    }
    if (field.required === false) {
      const clear = el("button", { type: "button", class: "clear", text: STRINGS.clear });
      sync = () => { clear.hidden = !isFilled(values[field.key]); };
      clear.addEventListener("click", () => {
        for (const input of cards.querySelectorAll("input")) input.checked = false;
        onInput("");
        sync();
      });
      sync();
      block.append(clear);
    }
  }
  else {
    const control = textControl(field, values[field.key], onInput);
    // A value cleared elsewhere (an either-or switch) must show as cleared if the box comes back.
    scope.live.push(() => { const v = values[field.key] ?? ""; if (control.value !== String(v)) control.value = v; });
    block.append(control);
  }
  block.append(problemBox(path, ctx));
  if (field.examples) block.append(examplesBlock(field.examples));
  if (field.why) block.append(whyBlock(field.why));
  return block;
}

// Draws the fields of one object into `body`. Conditional fields, either-or fields and pickers that depend on
// a sibling are brought up to date after every change in this object.
function fieldsInto(body, fields, values, prefix, ctx, owner) {
  const scope = { fields, owner, live: [], memory: memoryFor(values) };
  const blocks = new Map();
  const refresh = () => {
    for (const field of fields) {
      const block = blocks.get(field.key);
      if (block) block.hidden = !fieldShown(owner, field, values, scope.memory);
    }
    for (const fn of scope.live) fn();
  };
  const inner = {
    ...ctx,
    changed: () => { refresh(); ctx.changed(); },
  };
  const groups = owner?.one_of ?? [];
  for (const field of fields) {
    const index = groups.findIndex((g) => g.fields[0] === field.key);
    if (index >= 0) body.append(toggleBlock(groups[index], index, values, prefix + "oneof", inner, scope));
    const block = fieldBlock(field, values, prefix + field.key, inner, scope);
    blocks.set(field.key, block);
    body.append(block);
  }
  refresh();
}

const memories = new WeakMap();
function memoryFor(values) {
  if (!memories.has(values)) memories.set(values, {});
  return memories.get(values);
}

// ---- Lists -----------------------------------------------------------------

function itemRow(field, item, list, ctx, redraw) {
  const compact = field.item_fields.length === 1;
  const itemPath = `${field.key}.${item.id}`;
  const row = el("div", { class: compact ? "item item-compact" : "item", "data-id": item.id, "data-path": itemPath });
  const remove = el("button", { type: "button", class: "remove", text: "×", "aria-label": STRINGS.remove, title: STRINGS.remove });
  remove.addEventListener("click", () => {
    if (!isItemEmpty(item) && field.delete_confirm && !window.confirm(field.delete_confirm)) return;
    removeItem(list, item.id);
    redraw();
    ctx.changed();
  });

  if (compact) {
    const inner = { ...field.item_fields[0], examples: undefined, help: undefined };
    const control = textControl(inner, item[inner.key], (next) => { item[inner.key] = next; ctx.changed(); });
    control.setAttribute("data-path", `${itemPath}.${inner.key}`);   // so leaving the box counts as visiting that field
    row.append(control, remove);
    return row;
  }

  const title = el("span", { class: "item-title" });
  const setTitle = () => { title.textContent = itemTitle(field, item, ctx.lookup) || STRINGS.newItem; };
  setTitle();
  row.append(el("div", { class: "item-head" }, title, remove), problemBox(itemPath, ctx));
  const body = el("div", { class: "item-body" });
  row.append(body);
  fieldsInto(body, field.item_fields, item, `${field.key}.${item.id}.`, {
    ...ctx, list, changed: () => { setTitle(); for (const fn of ctx.siblings ?? []) fn(); ctx.changed(); },
  }, field);
  return row;
}

function listControl(field, values, path, ctx) {
  const list = values[field.key];
  const wrap = el("div", { class: "list" });
  const rows = el("div", { class: "items" });
  const empty = el("p", { class: "empty", text: field.empty });
  const add = el("button", { type: "button", class: "add", text: field.add });
  const limit = el("p", { class: "limit" });

  const siblings = new Set();
  const rowCtx = { ...ctx, siblings };
  function redraw() {
    siblings.clear();
    rows.replaceChildren(...list.map((item) => itemRow(field, item, list, rowCtx, redraw)));
    for (const fn of siblings) fn();
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
// ctx: { project, schema, card, common, changed, review?, onValidate? }
//   review      {touched: Set of paths, validated: boolean}. The page keeps one per card, so coming back to a card
//               still shows what was found. Without one, the card starts fresh.
//   onValidate  called with the model-check request when the writer presses Validate.
//   reviewChanged  called whenever what the card shows may have changed (an edit, leaving a field, Validate), so
//               the page can bring the tabs up to date.
// Problems never stop editing: nothing here disables a control.
export function renderCard(root, card, values, ctx) {
  root.replaceChildren();
  const project = ctx.project ?? {};
  const review = ctx.review ?? { touched: new Set(), validated: false };
  // Whatever is already written counts as visited, so a saved project shows its problems at once.
  for (const path of filledPaths(card, values)) review.touched.add(path);

  const boxes = new Map();          // path -> the place under that field where its problems are written
  const groupViews = new Map();     // group id -> {details, badge}
  const groupOf = (p) => card.fields.find((f) => f.key === p.field)?.group;
  const count = el("p", { class: "problem-count", role: "status", hidden: true });
  const status = el("p", { class: "note validate-status", role: "status" });
  let warned = false;

  // The box a problem is written into: its own field, else its list item, else its list. A field that is hidden
  // (the other half of an either-or) hands its problem to the item, so a problem is never left unseen.
  function boxFor(p) {
    for (const path of [problemPath(p), p.item ? `${p.field}.${p.item}` : null, p.item ? p.field : null]) {
      const box = path && boxes.get(path);
      if (box && box.isConnected && !box.parentElement.closest("[hidden]")) return box;
    }
    return null;
  }

  // Writes every problem that may be shown into its place, and updates the counts. Returns [{p, box}].
  function update() {
    const { problems, unchecked } = validate(card, values, project, ctx.common);
    if (unchecked.length && !warned) { warned = true; console.warn("Rules this page cannot run yet:", unchecked); }
    for (const box of boxes.values()) if (!box.hidden) { box.replaceChildren(); box.hidden = true; }
    const placed = [];
    for (const p of shownProblems(card, problems, review)) {
      const box = boxFor(p);
      if (!box) continue;
      box.append(problemLine(p));
      box.hidden = false;
      placed.push({ p, box });
    }
    const { block, warn } = problemCounts(placed.map((x) => x.p));
    const parts = [];
    if (block) parts.push(countText(STRINGS.blockOne, STRINGS.blockMany, block));
    if (warn) parts.push(countText(STRINGS.warnOne, STRINGS.warnMany, warn));
    count.textContent = parts.length ? parts.join(" · ") : review.validated ? STRINGS.clean : "";
    count.hidden = !count.textContent;
    count.className = `problem-count${block ? " has-block" : warn ? " has-warn" : ""}`;
    for (const [id, view] of groupViews) {
      const mine = placed.filter((x) => groupOf(x.p) === id).map((x) => x.p);
      view.badge.textContent = mine.length ? STRINGS.groupCount.replace("{n}", String(mine.length)) : "";
      view.badge.hidden = mine.length === 0;
      view.badge.className = `group-count ${mine.some((p) => p.severity === "block") ? "has-block" : "has-warn"}`;
    }
    ctx.reviewChanged?.();
    return placed;
  }

  const inner = {
    ...ctx,
    card,
    project,
    boxes,
    changed: () => { ctx.changed?.(); update(); },
    lookup: (itemField, value) => lookupLabel(project, itemField, value, STRINGS.unnamed),
  };

  // One line saying what the "changes" and "never changes" tags mean, only on a card that has them.
  const used = flagsUsed(card);
  const noteText = [
    used.changes ? STRINGS.noteLive.replace("{tag}", STRINGS.tagLive) : "",
    used.fixed ? STRINGS.noteFixed.replace("{tag}", STRINGS.tagFixed) : "",
  ].filter(Boolean).join(" ");

  const section = el("section", { class: "card", "data-card": card.id },
    el("h2", { text: card.label }),
    el("p", { class: "summary", text: card.summary }),
    noteText ? el("p", { class: "flag-note", text: noteText }) : null,
    count);

  for (const { group, fields } of groupedFields(card)) {
    const body = el("div", { class: "group-body" });
    fieldsInto(body, fields, values, "", inner, null);
    if (!group) { section.append(body); continue; }
    const badge = el("span", { class: "group-count", hidden: true });
    const details = el("details", { class: "group", open: !group.collapsed },
      el("summary", {}, el("span", { class: "group-label", text: group.label }),
        group.help ? el("span", { class: "group-help", text: group.help }) : null, badge),
      body);
    groupViews.set(group.id, { details, badge });
    section.append(details);
  }

  // Validate: show everything the page can check, hand the model rules on, and bring the first problem into view.
  const validateButton = el("button", { type: "button", class: "validate", text: STRINGS.validate });
  validateButton.addEventListener("click", () => {
    review.validated = true;
    const placed = update();
    for (const [id, view] of groupViews) if (placed.some((x) => groupOf(x.p) === id)) view.details.open = true;
    const request = modelCheckRequest(card, values);
    ctx.onValidate?.(request);
    status.textContent = request.rules.length ? STRINGS.modelPending.replace("{n}", String(request.rules.length)) : "";
    placed[0]?.box.scrollIntoView({ block: "center", behavior: "smooth" });
  });
  section.append(el("div", { class: "validate-bar" }, validateButton, status));

  // A problem appears when the writer leaves a field. Leaving a box can shift the page under the mouse, so while a
  // pointer is still down the update waits for it to be released, or the click that caused the move could miss.
  let pointerDown = false;
  let deferred = false;
  section.addEventListener("pointerdown", () => {
    pointerDown = true;
    document.addEventListener("pointerup", () => {
      pointerDown = false;
      if (deferred) { deferred = false; setTimeout(update, 0); }
    }, { once: true, capture: true });
  }, true);
  section.addEventListener("focusout", (event) => {
    let added = false;
    for (let node = event.target.closest?.("[data-path]"); node; node = node.parentElement?.closest("[data-path]")) {
      if (!review.touched.has(node.dataset.path)) { review.touched.add(node.dataset.path); added = true; }
    }
    if (!added) return;
    if (pointerDown) deferred = true;
    else update();
  });

  root.append(section);
  update();
}
