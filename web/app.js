// Loads the schema, holds the project in memory and draws the cards built so far.
// The project bar (name, New, Open, Save, unsaved-changes mark, recovery offer) lives here too.
// The tabs show where each card stands; a dropdown picks the character on the Characters card.
import {
  addInstance, ensureCard, findInstance, instanceName, newProject, removeInstance,
  hasUnsavedChanges, projectSnapshot, projectFileName, readProject,
  RECOVERY_KEY, recoveryRecord, readRecovery, worthRecovering, projectStatus,
  noteFor, setNote, setExample, setCardValues,
} from "./logic.js";
import { renderCard, errorText, makeReadOnly, freezeItems, STRINGS as CARD_STRINGS } from "./render.js";
import { cardLocked } from "./gate.js";
import { createStoryBar } from "./story.js";
import { createPlanPanel } from "./planpanel.js";
import { createGeneratePanel } from "./generatepanel.js";
import { createEndPanel } from "./endpanel.js";
import { createExportPanel } from "./exportpanel.js";
import { writtenBeatIds } from "./plan.js";
import { createMock } from "./mock.js";
import {
  BACKEND_KEY, createClient, readStoredSetting, parseBackendSetting, settingText, blockedByPage, fillCard, judgeCard,
} from "./client.js";

const LABELS = {
  addCharacter: "Add a character", deleteCharacter: "Delete this character?", remove: "Delete this character",
  unnamed: "Unnamed character", noCharacters: "No characters yet.", character: "Character",
  locked: "locked", lockMark: "🔒",
  tabEmpty: "nothing in it yet", tabStarted: "started", tabReady: "nothing stops generating",
  markBlock: "✕ {n}", markWarn: "△ {n}", markReady: "✓", markStarted: "●",
};
const STRINGS = {
  untitled: "Untitled story",
  clean: "No unsaved changes",
  dirty: "Unsaved changes",
  saved: "Downloaded as {file}. Keep that file: it is your project.",
  opened: "Opened {name}.",
  older: "This project was saved by an older version of Pulpermill. Anything newer than that version is blank.",
  restored: "Restored. It is not saved yet, so save it when you can.",
  unchanged: "Your current project is unchanged.",
  unreadable: "That file could not be read as a project.",
  notProject: "That file is not a Pulpermill project.",
  newer: "That project was saved by a newer version of Pulpermill than this page, so it was not opened. Opening it here could lose parts of it.",
  damaged: "That project is damaged: its {card} card holds something it should not, so it was not opened.",
  confirmNew: "Start a new project? The one you are working on has unsaved changes, and they will be lost.",
  confirmOpen: "Open this file? The project you are working on has unsaved changes, and they will be lost.",
  confirmRestore: "Restore the earlier work? The project you are working on has unsaved changes, and they will be lost.",
  confirmThrowAway: "Throw away the unsaved work from {when}? It cannot be brought back.",
  recoveryFound: "Your last session ended with unsaved work: {what}, from {when}.",
  untitledStory: "an untitled story",
  characterOne: "1 character",
  characterMany: "{n} characters",
  restore: "Restore it",
  throwAway: "Throw it away",
  close: "Close",
  undo: "Undo",
  undone: "Put back what those fields held before the fill.",
  filled: "The model drafted: {fields}. They are marked “Model draft” until you edit them.",
  nothingNew: "The model had nothing new to add to this card.",
  declined: "Nothing was changed.",
  dropped: "The project changed while the model was working, so its answer was thrown away.",
  confirmReplace: "The model’s draft would replace your words in: {fields}. Go ahead? You can undo it afterwards.",
  unmatched: "The model named {names}, but nothing in your cards matches, so those links were left empty.",
  noSource: "Add a note for this card, or an example chapter, first. The model fills a card from one of them.",
  noInstance: "That character isn’t there any more.",
  more: "and {n} more",
  backendBad: "That isn’t an address I can use. Type “mock”, or something like localhost:8000.",
  backendMixed: "This page is served over https, so the browser won’t let it call a plain http address. Use an https address, or open the page from your own computer.",
  whereMock: "the built-in sample model, which writes placeholder text (nothing leaves this page)",
  working: "The model is working…",
  writtenBeat: "This beat was written from. To change the chapter, write it again below.",
  lockedBanner: "This card is locked because the story has started. You can read it, but not change it.",
  connection: { unknown: "Not checked yet", idle: "Ready", busy: "Busy with another job", unreachable: "Can’t reach the model" },
};
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);

const cardsNav = document.getElementById("cards");
const peopleNav = document.getElementById("people");
const main = document.getElementById("card");
const openInput = document.getElementById("open-file");
const titleInput = document.getElementById("title");
const stateNode = document.getElementById("save-state");
const backendInput = document.getElementById("backend");
const connectionNode = document.getElementById("connection");
const stopButton = document.getElementById("stop");
const noticeNode = document.getElementById("notice");
const recoveryNode = document.getElementById("recovery");
const storyNode = document.getElementById("story-bar");
let schema;
let project;
let client;
let mock;
let storyBar;
let planPanel;
let generatePanel;
let endPanel;
let exportPanel;
let view = { card: "style", characterId: null };
// What the writer has visited and whether they pressed Validate, per card (and per character), so it survives
// switching cards. Cleared when another project is opened.
const reviews = new Map();
function reviewFor(key) {
  if (!reviews.has(key)) reviews.set(key, { touched: new Set(), validated: false });
  return reviews.get(key);
}

// Which fields the model has just drafted, per card (and per character), until the writer edits them.
const drafts = new Map();
function draftsFor(key) {
  if (!drafts.has(key)) drafts.set(key, new Set());
  return drafts.get(key);
}

function button(text, onClick, extra = {}) {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = text;
  if (extra.current) node.setAttribute("aria-current", "true");
  if (extra.className) node.className = extra.className;
  node.addEventListener("click", onClick);
  return node;
}

// ---- Keeping track of what is saved ---------------------------------------
// `savedSnapshot` is the project as of the last save or open. Anything different from it is unsaved.
// While the project changes, a safety copy goes into the browser so a closed tab or a crash loses little.
let savedSnapshot = "";
let offerPending = false;   // an earlier session's copy is waiting for a yes or no, so the copy must not be overwritten
let timer = null;

const store = {
  get() { try { return localStorage.getItem(RECOVERY_KEY); } catch { return null; } },
  set(text) { try { localStorage.setItem(RECOVERY_KEY, text); } catch { /* storage is off: the file is still the real save */ } },
  remove() { try { localStorage.removeItem(RECOVERY_KEY); } catch { /* same */ } },
};

const isDirty = () => hasUnsavedChanges(schema, project, savedSnapshot);

function refreshState() {
  clearTimeout(timer);
  timer = null;
  const dirty = isDirty();
  stateNode.textContent = dirty ? STRINGS.dirty : STRINGS.clean;
  stateNode.classList.toggle("is-dirty", dirty);
  document.title = `${dirty ? "● " : ""}${project.title?.trim() || STRINGS.untitled} — Pulpermill`;
  if (offerPending) return;
  if (dirty) store.set(recoveryRecord(schema, project));
  else store.remove();
}

// Called on every edit. Waits a moment so typing does not do the work on every key.
function touchState() {
  clearTimeout(timer);
  timer = setTimeout(refreshState, 400);
}

function replaceProject(next, savedAs = next) {
  next.title = typeof next.title === "string" ? next.title : "";
  project = next;
  reviews.clear();
  drafts.clear();
  planPanel?.reset();
  generatePanel?.reset();
  endPanel?.reset();
  view = { card: "style", characterId: null };
  titleInput.value = project.title;
  savedSnapshot = projectSnapshot(schema, savedAs);
  show();
  refreshState();
}

// ---- Messages ---------------------------------------------------------------
function showNotice(text, kind = "", action = null) {
  const close = button(STRINGS.close, () => { noticeNode.hidden = true; }, { className: "notice-close" });
  const words = document.createElement("span");
  words.textContent = text;
  noticeNode.className = `notice ${kind}`.trim();
  noticeNode.replaceChildren(...[words, action && button(action.label, action.run, { className: "validate" }), close].filter(Boolean));
  noticeNode.hidden = false;
}

function failureText(read) {
  const text = {
    unreadable: STRINGS.unreadable,
    not_project: STRINGS.notProject,
    newer: STRINGS.newer,
    damaged: fill(STRINGS.damaged, { card: schema.cards[read.card]?.label ?? read.card }),
  }[read.reason] ?? STRINGS.unreadable;
  return `${text} ${STRINGS.unchanged}`;
}

// ---- New, Open, Save ----------------------------------------------------------
function save() {
  if (!schema) return;
  const text = projectSnapshot(schema, project);
  const file = projectFileName(project);
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  link.download = file;
  link.click();
  URL.revokeObjectURL(link.href);
  savedSnapshot = text;
  refreshState();
  showNotice(fill(STRINGS.saved, { file }));
}

function startNew() {
  if (!schema) return;
  if (isDirty() && !window.confirm(STRINGS.confirmNew)) return;
  noticeNode.hidden = true;
  replaceProject(newProject(schema));
}

document.getElementById("save").addEventListener("click", save);
document.getElementById("new").addEventListener("click", startNew);
document.getElementById("open").addEventListener("click", () => { if (schema) openInput.click(); });

openInput.addEventListener("change", async () => {
  const file = openInput.files[0];
  openInput.value = "";
  if (!file) return;
  let text;
  try {
    text = await file.text();
  } catch {
    showNotice(`${STRINGS.unreadable} ${STRINGS.unchanged}`, "notice-bad");
    return;
  }
  const read = readProject(text, schema);
  if (!read.ok) { showNotice(failureText(read), "notice-bad"); return; }
  if (isDirty() && !window.confirm(STRINGS.confirmOpen)) return;
  replaceProject(read.project);
  showNotice(`${fill(STRINGS.opened, { name: file.name })}${read.older ? ` ${STRINGS.older}` : ""}`);
});

titleInput.addEventListener("input", () => {
  if (!project) return;
  project.title = titleInput.value;
  touchState();
});

// Ctrl+S or Cmd+S saves, as in any editor.
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    save();
  }
});

// Leaving with unsaved work asks first, and the safety copy is brought up to date either way.
window.addEventListener("beforeunload", (event) => {
  if (!schema) return;
  refreshState();
  if (isDirty()) { event.preventDefault(); event.returnValue = ""; }
});
document.addEventListener("visibilitychange", () => {
  if (schema && document.visibilityState === "hidden") refreshState();
});

// ---- Work left over from an earlier session ------------------------------------
const when = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

function offerRecovery(recovered) {
  offerPending = true;
  const what = [
    recovered.title ? `“${recovered.title}”` : STRINGS.untitledStory,
    recovered.characters === 1 ? STRINGS.characterOne : recovered.characters > 1 ? fill(STRINGS.characterMany, { n: recovered.characters }) : "",
  ].filter(Boolean).join(", ");
  const words = document.createElement("span");
  words.textContent = fill(STRINGS.recoveryFound, { what, when: when(recovered.savedAt) });
  const resolve = () => { offerPending = false; recoveryNode.hidden = true; recoveryNode.replaceChildren(); };
  const restore = button(STRINGS.restore, () => {
    if (isDirty() && !window.confirm(STRINGS.confirmRestore)) return;
    resolve();
    replaceProject(recovered.project, newProject(schema));   // saved as "blank", so it counts as unsaved until saved
    showNotice(STRINGS.restored);
  }, { className: "validate" });
  const discard = button(STRINGS.throwAway, () => {
    if (!window.confirm(fill(STRINGS.confirmThrowAway, { when: when(recovered.savedAt) }))) return;
    store.remove();
    resolve();
    refreshState();
  });
  recoveryNode.replaceChildren(words, restore, discard);
  recoveryNode.hidden = false;
}

// ---- The model backend ----------------------------------------------------------
// "mock" is the built-in sample model, so the page works with nothing running. Anything else is an address.
const backendWhere = () => (client.state.setting.kind === "mock" ? STRINGS.whereMock : settingText(client.state.setting));

function drawConnection() {
  const { working, connection } = client.state;
  stopButton.hidden = !working;
  connectionNode.textContent = working ? STRINGS.working : STRINGS.connection[connection];
  connectionNode.dataset.state = working ? "busy" : connection;
}

function chooseBackend(text) {
  const parsed = parseBackendSetting(text);
  const keep = () => { backendInput.value = settingText(client.state.setting); };
  if (!parsed.ok) { showNotice(STRINGS.backendBad, "notice-bad"); keep(); return; }
  if (blockedByPage(parsed, location.protocol)) { showNotice(STRINGS.backendMixed, "notice-bad"); keep(); return; }
  try { localStorage.setItem(BACKEND_KEY, settingText(parsed)); } catch { /* the choice is just not remembered */ }
  client.setSetting(parsed);
  keep();
  client.checkStatus();
  show();
}

backendInput.addEventListener("change", () => chooseBackend(backendInput.value));
document.getElementById("check").addEventListener("click", () => client.checkStatus());
stopButton.addEventListener("click", () => client.stop());

// ---- Filling a card ---------------------------------------------------------------
// The writer presses the button; the model answers; nothing changes until the page has the whole answer. If the answer
// would replace words the writer wrote, the page asks first, and afterwards Undo puts those fields back.
const sameView = (card, instanceId) => view.card === card.id && (!card.many_per_project || view.characterId === instanceId);
const copy = (value) => JSON.parse(JSON.stringify(value));

function listOf(labels) {
  return labels.length > 6 ? `${labels.slice(0, 6).join(", ")} ${fill(STRINGS.more, { n: labels.length - 6 })}` : labels.join(", ");
}

async function runFill(card, shown) {
  if (cardLocked(project, card.id)) return;
  const here = project;
  const instanceId = card.many_per_project ? shown.id : null;
  const result = await fillCard(client, schema, project, card.id, instanceId).done;
  const targetNow = () => (card.many_per_project ? findInstance(project, card, instanceId) : project[card.id]);
  if (project !== here || !targetNow()) { showNotice(STRINGS.dropped); return; }
  if (result.reason) {
    showNotice(result.reason === "no_instance" ? STRINGS.noInstance : STRINGS.noSource, "notice-bad");
    return;
  }
  if (!result.ok) { showNotice(errorText(result.error), result.error.kind === "stopped" ? "" : "notice-bad"); return; }

  const label = (key) => card.fields.find((f) => f.key === key)?.label ?? key;
  if (result.replaced.length && !window.confirm(fill(STRINGS.confirmReplace, { fields: listOf(result.replaced.map(label)) }))) {
    showNotice(STRINGS.declined);
    return;
  }
  const keys = [...result.filled, ...result.replaced];
  const unmatched = [...new Set(result.unresolved.map((u) => u.words))];
  const extra = unmatched.length ? ` ${fill(STRINGS.unmatched, { names: unmatched.map((n) => `“${n}”`).join(", ") })}` : "";
  if (!keys.length) { showNotice(`${STRINGS.nothingNew}${extra}`); return; }

  // Only the fields the model drafted are written, and what they held a moment ago is what Undo puts back. Anything
  // else the writer typed while waiting is left alone.
  const target = targetNow();
  const before = Object.fromEntries(keys.map((key) => [key, copy(target[key])]));
  setCardValues(card, target, Object.fromEntries(keys.map((key) => [key, result.next[key]])));
  const marked = draftsFor(`${card.id}:${target.id ?? ""}`);
  for (const key of keys) marked.add(key);
  if (sameView(card, instanceId)) show();
  touchState();

  showNotice(`${fill(STRINGS.filled, { fields: listOf(keys.map(label)) })}${extra}`, "", {
    label: STRINGS.undo,
    run: () => {
      const now = project === here ? targetNow() : null;
      if (!now) return;
      setCardValues(card, now, before);
      for (const key of keys) marked.delete(key);
      if (sameView(card, instanceId)) show();
      touchState();
      showNotice(STRINGS.undone);
    },
  });
}

// ---- Navigation ---------------------------------------------------------------
const countWords = (one, many, n) => (n === 1 ? one : many.replace("{n}", String(n)));

// What a status says, as small marks (for the eye) and as words (for the tooltip and screen readers).
function markNodes(status) {
  const marks = [];
  const add = (cls, text) => marks.push(Object.assign(document.createElement("span"), { className: `mark ${cls}`, textContent: text }));
  if (status.block) add("mark-block", fill(LABELS.markBlock, { n: status.block }));
  if (status.warn) add("mark-warn", fill(LABELS.markWarn, { n: status.warn }));
  if (!status.block && !status.warn) {
    if (status.ready) add("mark-ready", LABELS.markReady);
    else if (status.started) add("mark-started", LABELS.markStarted);
  }
  return marks;
}

function statusWords(status) {
  const parts = [];
  if (status.block) parts.push(countWords(CARD_STRINGS.blockOne, CARD_STRINGS.blockMany, status.block));
  if (status.warn) parts.push(countWords(CARD_STRINGS.warnOne, CARD_STRINGS.warnMany, status.warn));
  if (!parts.length) parts.push(status.ready ? LABELS.tabReady : status.started ? LABELS.tabStarted : LABELS.tabEmpty);
  return parts.join(", ");
}

function optionText(name, status) {
  const marks = markNodes(status).map((node) => node.textContent);
  return [name || LABELS.unnamed, ...marks].join("  ");
}

// Brings every tab and every character entry up to date without rebuilding them, so focus stays where it is.
function updateMarks() {
  if (!schema || !project) return;
  const { cards, instances } = projectStatus(schema, project, reviewFor);
  for (const node of cardsNav.querySelectorAll("[data-card]")) {
    const status = cards[node.dataset.card];
    node.querySelector(".tab-marks").replaceChildren(...markNodes(status));
    const words = cardLocked(project, node.dataset.card) ? `${statusWords(status)}, ${LABELS.locked}` : statusWords(status);
    node.setAttribute("aria-label", `${schema.cards[node.dataset.card].label}: ${words}`);
    node.title = words;
  }
  const select = peopleNav.querySelector("select");
  if (!select) return;
  const byId = new Map((instances.characters ?? []).map((entry) => [entry.id, entry.status]));
  for (const option of select.options) {
    const instance = findInstance(project, schema.cards.characters, option.value);
    if (instance && byId.has(option.value)) option.textContent = optionText(instanceName(instance), byId.get(option.value));
  }
}

function drawNav() {
  cardsNav.replaceChildren(...schema.order.map((id) => {
    const node = button("", () => { view.card = id; show(); }, { current: view.card === id });
    node.dataset.card = id;
    node.append(
      Object.assign(document.createElement("span"), { className: "tab-label", textContent: schema.cards[id].label }),
      Object.assign(document.createElement("span"), { className: "tab-marks" }),
      ...(cardLocked(project, id) ? [Object.assign(document.createElement("span"), { className: "tab-lock", textContent: LABELS.lockMark, title: LABELS.locked })] : []));
    return node;
  }));

  const card = schema.cards[view.card];
  peopleNav.hidden = !card.many_per_project;
  if (!card.many_per_project) return;
  const list = project[card.id];
  const items = [];
  if (list.length) {
    const select = document.createElement("select");
    select.className = "text-control character-select";
    select.id = "character-select";
    for (const instance of list) {
      select.append(Object.assign(document.createElement("option"), {
        value: instance.id, textContent: instanceName(instance) || LABELS.unnamed, selected: instance.id === view.characterId,
      }));
    }
    select.addEventListener("change", () => { view.characterId = select.value; show(); });
    items.push(Object.assign(document.createElement("label"), { className: "people-label", htmlFor: "character-select", textContent: LABELS.character }), select);
  } else {
    items.push(Object.assign(document.createElement("span"), { textContent: LABELS.noCharacters }));
  }
  items.push(button(`+ ${LABELS.addCharacter}`, () => {
    view.characterId = addInstance(project, card).id;
    show();
    touchState();
  }, { className: "add" }));
  if (view.characterId) {
    items.push(button(LABELS.remove, () => {
      if (!window.confirm(LABELS.deleteCharacter)) return;
      removeInstance(project, card, view.characterId);
      view.characterId = project[card.id][0]?.id ?? null;
      show();
      touchState();
    }, { className: "remove-person" }));
  }
  peopleNav.replaceChildren(...items);
  if (cardLocked(project, card.id)) for (const node of peopleNav.querySelectorAll(".add, .remove-person")) node.disabled = true;
}

function show() {
  const card = schema.cards[view.card];
  const held = ensureCard(project, card);
  let values;
  if (card.many_per_project) {
    if (!findInstance(project, card, view.characterId)) view.characterId = held[0]?.id ?? null;
    values = findInstance(project, card, view.characterId);
  } else {
    values = held;
  }
  drawNav();
  if (!values) { main.replaceChildren(); return; }
  const key = `${card.id}:${values.id ?? ""}`;
  const instanceId = card.many_per_project ? values.id : null;
  renderCard(main, card, values, {
    project,
    schema,
    common: schema.common,
    review: reviewFor(key),
    drafts: draftsFor(key),
    judge: () => judgeCard(client, schema, project, card.id, values),
    onFill: () => runFill(card, values),
    notes: { get: () => noteFor(project, card.id, instanceId), set: (text) => { setNote(project, card.id, instanceId, text); touchState(); } },
    example: { get: () => project.example_chapter ?? "", set: (text) => { setExample(project, text); touchState(); } },
    backendWhere,
    changed: touchState,
    reviewChanged: updateMarks,
  });
  if (cardLocked(project, card.id)) makeReadOnly(main, STRINGS.lockedBanner);
  if (card.id === "outline") {
    freezeItems(main, writtenBeatIds(project), STRINGS.writtenBeat);
    planPanel?.draw(main);
    generatePanel?.draw(main);
    endPanel?.draw(main);
    exportPanel?.draw(main);
  }
  storyBar?.draw();
}

try {
  schema = await (await fetch("data/schema.en.json")).json();
  let stored = null;
  try { stored = localStorage.getItem(BACKEND_KEY); } catch { /* no storage: the built-in model is used */ }
  let setting = readStoredSetting(stored);
  if (blockedByPage(setting, location.protocol)) setting = { ok: true, kind: "mock" };
  mock = createMock(schema, { delay: 700 });
  client = createClient({ setting, mock });
  backendInput.value = settingText(setting);
  storyBar = createStoryBar(storyNode, {
    schema, client, getProject: () => project,
    goTo: (cardId, instanceId) => { view = { card: cardId, characterId: instanceId }; show(); },
    changed: () => touchState(),
    notice: (text, kind) => showNotice(text, kind),
    redraw: () => show(),
  });
  planPanel = createPlanPanel({
    schema, client, getProject: () => project, backendWhere, errorText,
    changed: () => touchState(), redraw: () => show(),
    notice: (text, kind, action) => showNotice(text, kind, action),
  });
  generatePanel = createGeneratePanel({
    schema, client, getProject: () => project, backendWhere, errorText,
    changed: () => touchState(), redraw: () => show(),
    notice: (text, kind, action) => showNotice(text, kind, action),
  });
  exportPanel = createExportPanel({ schema, getProject: () => project });
  endPanel = createEndPanel({
    schema, client, getProject: () => project, backendWhere, errorText,
    changed: () => touchState(), redraw: () => show(),
    notice: (text, kind, action) => showNotice(text, kind, action),
  });
  client.onChange(() => { drawConnection(); storyBar.draw(); planPanel.refresh(); generatePanel.refresh(); endPanel.refresh(); });
  drawConnection();
  // Read the earlier copy before anything can tidy it away: a blank, clean project clears the copy it finds.
  const recovered = readRecovery(store.get() ?? "", schema);
  offerPending = worthRecovering(schema, recovered);
  replaceProject(newProject(schema));
  if (offerPending) offerRecovery(recovered);
  client.checkStatus();   // only asks whether the backend is free; no model runs
} catch (error) {
  main.textContent = "The page couldn't load its schema.";
}
window.pulpermill = {
  get project() { return project; }, get dirty() { return isDirty(); }, get client() { return client; }, get mock() { return mock; },
};   // for looking at the data while testing
