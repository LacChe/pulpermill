// Loads the schema, holds the project in memory and draws the cards built so far.
// The project bar (name, New, Open, Save, unsaved-changes mark, recovery offer) lives here too.
// The card switcher is a stand-in until the real navigation exists.
import {
  addInstance, ensureCard, findInstance, instanceName, newProject, removeInstance,
  hasUnsavedChanges, projectSnapshot, projectFileName, readProject,
  RECOVERY_KEY, recoveryRecord, readRecovery, worthRecovering,
} from "./logic.js";
import { renderCard } from "./render.js";

const BUILT = ["style", "characters", "world", "entanglements", "setup", "outline"];
const LABELS = { addCharacter: "Add a character", deleteCharacter: "Delete this character?", remove: "Delete", unnamed: "Unnamed character", noCharacters: "No characters yet." };
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
};
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);

const cardsNav = document.getElementById("cards");
const peopleNav = document.getElementById("people");
const main = document.getElementById("card");
const openInput = document.getElementById("open-file");
const titleInput = document.getElementById("title");
const stateNode = document.getElementById("save-state");
const noticeNode = document.getElementById("notice");
const recoveryNode = document.getElementById("recovery");
let schema;
let project;
let view = { card: "style", characterId: null };
// What the writer has visited and whether they pressed Validate, per card (and per character), so it survives
// switching cards. Cleared when another project is opened.
const reviews = new Map();
function reviewFor(key) {
  if (!reviews.has(key)) reviews.set(key, { touched: new Set(), validated: false });
  return reviews.get(key);
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
  view = { card: "style", characterId: null };
  titleInput.value = project.title;
  savedSnapshot = projectSnapshot(schema, savedAs);
  show();
  refreshState();
}

// ---- Messages ---------------------------------------------------------------
function showNotice(text, kind = "") {
  const close = button(STRINGS.close, () => { noticeNode.hidden = true; }, { className: "notice-close" });
  const words = document.createElement("span");
  words.textContent = text;
  noticeNode.className = `notice ${kind}`.trim();
  noticeNode.replaceChildren(words, close);
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

// ---- Cards --------------------------------------------------------------------
function drawNav() {
  cardsNav.replaceChildren(...BUILT.map((id) =>
    button(schema.cards[id].label, () => { view.card = id; show(); }, { current: view.card === id })));

  const card = schema.cards[view.card];
  peopleNav.hidden = !card.many_per_project;
  if (!card.many_per_project) return;
  const list = project[card.id];
  const items = list.map((instance) =>
    button(instanceName(instance) || LABELS.unnamed, () => { view.characterId = instance.id; show(); },
      { current: instance.id === view.characterId }));
  if (!list.length) {
    const note = document.createElement("span");
    note.textContent = LABELS.noCharacters;
    items.push(note);
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
  renderCard(main, card, values, {
    project,
    schema,
    common: schema.common,
    review: reviewFor(`${card.id}:${values.id ?? ""}`),
    onValidate: (request) => { window.pulpermill.lastModelRequest = request; },   // the backend call comes in Phase 7
    changed: () => { if (card.many_per_project) drawNav(); touchState(); },
  });
}

try {
  schema = await (await fetch("data/schema.en.json")).json();
  // Read the earlier copy before anything can tidy it away: a blank, clean project clears the copy it finds.
  const recovered = readRecovery(store.get() ?? "", schema);
  offerPending = worthRecovering(schema, recovered);
  replaceProject(newProject(schema));
  if (offerPending) offerRecovery(recovered);
} catch (error) {
  main.textContent = "The page couldn't load its schema.";
}
window.pulpermill = { get project() { return project; }, get dirty() { return isDirty(); } };   // for looking at the data while testing
