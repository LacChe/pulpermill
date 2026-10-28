// Loads the schema, holds the project in memory and draws the cards built so far.
// The project bar (name, New, Open, Save, unsaved-changes mark, recovery offer) lives here too.
// The tabs show where each card stands; a dropdown picks the character on the Characters card.
import {
  addInstance, ensureCard, findInstance, instanceName, newProject, removeInstance,
  hasUnsavedChanges, projectSnapshot, projectFileName, readProject,
  RECOVERY_KEY, recoveryRecord, readRecovery, worthRecovering, projectStatus,
  noteFor, setNote, setExample, setCardValues,
} from "./logic.js";
import { renderCard, errorText, makeReadOnly, restoreRadioSelections, freezeItems, flagItems, STRINGS as CARD_STRINGS } from "./render.js";
import { cardLocked, lockedByStory, lockedByWriter, setWriterLock, storyStarted } from "./gate.js";
import { ask } from "./dialog.js";
import { untouched } from "./undo.js";
import { createStoryBar } from "./story.js";
import { createPlanPanel } from "./planpanel.js";
import { createGeneratePanel } from "./generatepanel.js";
import { forgetFolds } from "./folds.js";
import { createEndPanel } from "./endpanel.js";
import { createExportPanel } from "./exportpanel.js";
import { createChapterPanel } from "./chapterpanel.js";
import { createImportPanel } from "./importpanel.js";
import { createWelcomeStrip } from "./welcomestrip.js";
import { fileKind } from "./exporting.js";
import { pruneNotes } from "./modelnotes.js";
import { writtenBeatIds, staleBeatIds } from "./plan.js";
import { createMock } from "./mock.js";
import {
  BACKEND_KEY, TOKEN_KEY, createClient, readStoredSetting, parseBackendSetting, settingText, blockedByPage, fillCard, judgeCard,
} from "./client.js";
import { section, fill, msg, joinList, setText, applyStaticText, TEXT_FILE, BOOT_FAILURE } from "./text.js";

const LABELS = section("labels");     // labels.tabNames: a tab holds all of a many-per-project card, so it is named in the plural
const STRINGS = section("app");

const cardsNav = document.getElementById("cards");
const peopleNav = document.getElementById("people");
const main = document.getElementById("card");
const openInput = document.getElementById("open-file");
const importInput = document.getElementById("import-file");
const importButton = document.getElementById("import");
const importNode = document.getElementById("import-panel");
const welcomeNode = document.getElementById("welcome");
const guideButton = document.getElementById("guide");
const titleInput = document.getElementById("title");
const stateNode = document.getElementById("save-state");
const backendInput = document.getElementById("backend");
const tokenInput = document.getElementById("token");
const connectionNode = document.getElementById("connection");
const stopButton = document.getElementById("stop");
const noticeNode = document.getElementById("notice");
const recoveryNode = document.getElementById("recovery");
const storyNode = document.getElementById("story-bar");
const planningColumn = document.querySelector(".planning-column");
const chaptersNav = document.getElementById("chapters");
const workspace = document.getElementById("workspace");
const columnSwitches = [...document.querySelectorAll(".column-switch")];
let schema;
let project;
let client;
let mock;
let storyBar;
let planPanel;
let generatePanel;
let endPanel;
let exportPanel;
let chapterPanel;
let importPanel;
let welcome;
let view = { card: "style", characterId: null, chapter: null };

function syncWorkspaceLayout() {
  const top = workspace.getBoundingClientRect().top;
  workspace.style.setProperty("--workspace-top", `${Math.max(0, top)}px`);
}

function selectColumn(column) {
  workspace.dataset.column = column;
  for (const switchButton of columnSwitches) {
    const selected = switchButton.dataset.column === column;
    switchButton.classList.toggle("active", selected);
    switchButton.setAttribute("aria-pressed", String(selected));
  }

}

for (const switchButton of columnSwitches) switchButton.addEventListener("click", () => selectColumn(switchButton.dataset.column));
selectColumn("cards");
window.addEventListener("resize", syncWorkspaceLayout);
new ResizeObserver(syncWorkspaceLayout).observe(document.body);
new MutationObserver(syncWorkspaceLayout).observe(document.body, {
  subtree: true,
  attributes: true,
  attributeFilter: ["hidden", "class", "style"],
});
syncWorkspaceLayout();

function chapterState() {
  const count = Number(project?.setup?.chapter_count) || 0;
  const written = project?.chapters?.length ?? 0;
  const current = Math.min(written + 1, count);
  if (!count || !storyStarted(project)) return null;
  if (!view.chapter || view.chapter > current || view.chapter < 1) view.chapter = current;
  return { count, written, current };
}

function drawChapterNav() {
  const state = chapterState();
  chaptersNav.hidden = !state;
  if (!state) { chaptersNav.replaceChildren(); return; }
  chaptersNav.replaceChildren(...Array.from({ length: state.count }, (_, index) => {
    const number = index + 1;
    const written = number <= state.written;
    const available = number <= state.current;
    const node = button(fill(STRINGS.chapterTab, { n: number }), () => {
      view.chapter = number;
      show();
    }, { current: view.chapter === number });
    node.disabled = !available;
    node.title = available ? (written ? STRINGS.chapterWritten : STRINGS.chapterCurrent) : STRINGS.chapterFuture;
    node.classList.add(written ? "chapter-written" : "chapter-current");
    return node;
  }));
}
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
  document.title = fill(STRINGS.documentTitle, { mark: dirty ? STRINGS.dirtyMark : "", title: project.title?.trim() || STRINGS.untitled });
  if (offerPending) return;
  if (dirty) store.set(recoveryRecord(schema, project));
  else store.remove();
}

// Called on every edit. Waits a moment so typing does not do the work on every key.
function touchState() {
  if (project) pruneNotes(project);     // a note about a beat or chapter that is gone has nothing to point at
  clearTimeout(timer);
  timer = setTimeout(refreshState, 400);
}

function replaceProject(next, savedAs = next) {
  next.title = typeof next.title === "string" ? next.title : "";
  project = next;
  reviews.clear();
  drafts.clear();
  forgetFolds();
  planPanel?.reset();
  generatePanel?.reset();
  endPanel?.reset();
  importPanel?.reset();
  view = { card: "style", characterId: null, chapter: null };
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
  return joinList([text, STRINGS.unchanged], "sentence");
}

// ---- New, Open, Save ----------------------------------------------------------
function save() {
  if (!schema) return;
  pruneNotes(project);     // a note about a beat the writer deleted has nothing to point at
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

async function startNew() {
  if (!schema) return;
  if (isDirty() && !(await ask(STRINGS.confirmNew))) return;
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
    showNotice(joinList([STRINGS.unreadable, STRINGS.unchanged], "sentence"), "notice-bad");
    return;
  }
  // A card file has a schema_version too, so it would read as a project: ask what it is first.
  if (fileKind(text) === "card") { showNotice(joinList([STRINGS.isCard, STRINGS.unchanged], "sentence"), "notice-bad"); return; }
  const read = readProject(text, schema);
  if (!read.ok) { showNotice(failureText(read), "notice-bad"); return; }
  if (isDirty() && !(await ask(STRINGS.confirmOpen))) return;
  replaceProject(read.project);
  showNotice(joinList([fill(STRINGS.opened, { name: file.name }), ...(read.older ? [STRINGS.older] : [])], "sentence"));
});
// Import card: pick a card file; the import panel says what it would do and changes nothing until the writer says so.
importButton.addEventListener("click", () => { if (schema) importInput.click(); });
guideButton.addEventListener("click", () => welcome?.toggle());
importInput.addEventListener("change", async () => {
  const files = [...importInput.files];
  importInput.value = "";
  if (!files.length) return;
  const entries = [];
  for (const file of files) {
    try { entries.push({ file: file.name, text: await file.text() }); }
    catch { entries.push({ file: file.name, text: "", readError: true }); }
  }
  noticeNode.hidden = true;
  importPanel.start(entries);
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
  const what = joinList([
    recovered.title ? msg("common.quoted", { text: recovered.title }) : STRINGS.untitledStory,
    recovered.characters === 1 ? STRINGS.characterOne : recovered.characters > 1 ? fill(STRINGS.characterMany, { n: recovered.characters }) : "",
  ].filter(Boolean));
  const words = document.createElement("span");
  words.textContent = fill(STRINGS.recoveryFound, { what, when: when(recovered.savedAt) });
  const resolve = () => { offerPending = false; recoveryNode.hidden = true; recoveryNode.replaceChildren(); };
  const restore = button(STRINGS.restore, async () => {
    if (isDirty() && !(await ask(STRINGS.confirmRestore))) return;
    resolve();
    replaceProject(recovered.project, newProject(schema));   // saved as "blank", so it counts as unsaved until saved
    showNotice(STRINGS.restored);
  }, { className: "validate" });
  const discard = button(STRINGS.throwAway, async () => {
    if (!(await ask(fill(STRINGS.confirmThrowAway, { when: when(recovered.savedAt) })))) return;
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
  importButton.disabled = working;     // one job at a time: a card is not brought in while the model is working
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
tokenInput.addEventListener("change", () => {
  const token = tokenInput.value.trim();
  try { if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY); } catch { /* not remembered */ }
  client.setToken(token);
  client.checkStatus();
});
document.getElementById("check").addEventListener("click", () => client.checkStatus());
stopButton.addEventListener("click", () => client.stop());

// ---- Filling a card ---------------------------------------------------------------
// The writer presses the button; the model answers; nothing changes until the page has the whole answer. If the answer
// would replace words the writer wrote, the page asks first, and afterwards Undo puts those fields back.
const sameView = (card, instanceId) => view.card === card.id && (!card.many_per_project || view.characterId === instanceId);
const copy = (value) => JSON.parse(JSON.stringify(value));

function listOf(labels) {
  return labels.length > 6 ? fill(STRINGS.more, { list: joinList(labels.slice(0, 6)), n: labels.length - 6 }) : joinList(labels);
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
  if (result.replaced.length && !(await ask(fill(STRINGS.confirmReplace, { fields: listOf(result.replaced.map(label)) })))) {
    showNotice(STRINGS.declined);
    return;
  }
  const keys = [...result.filled, ...result.replaced];
  const unmatched = [...new Set(result.unresolved.map((u) => u.words))];
  const extra = unmatched.length ? fill(STRINGS.unmatched, { names: joinList(unmatched.map((n) => msg("common.quoted", { text: n }))) }) : "";
  if (!keys.length) { showNotice(joinList([STRINGS.nothingNew, extra].filter(Boolean), "sentence")); return; }

  // Only the fields the model drafted are written, and what they held a moment ago is what Undo puts back. Anything
  // else the writer typed while waiting is left alone.
  const target = targetNow();
  const before = Object.fromEntries(keys.map((key) => [key, copy(target[key])]));
  setCardValues(card, target, Object.fromEntries(keys.map((key) => [key, result.next[key]])));
  const wrote = Object.fromEntries(keys.map((key) => [key, copy(target[key])]));
  const marked = draftsFor(`${card.id}:${target.id ?? ""}`);
  for (const key of keys) marked.add(key);
  if (sameView(card, instanceId)) show();
  touchState();

  showNotice(joinList([fill(STRINGS.filled, { fields: listOf(keys.map(label)) }), extra].filter(Boolean), "sentence"), "", {
    label: STRINGS.undo,
    run: () => {
      const now = project === here ? targetNow() : null;
      if (!now) return;
      // A field the writer has edited since keeps their edit.
      const back = untouched(now, wrote, keys);
      if (!back.length) { showNotice(STRINGS.undoBlocked, "notice-bad"); return; }
      setCardValues(card, now, Object.fromEntries(back.map((key) => [key, before[key]])));
      for (const key of back) marked.delete(key);
      if (sameView(card, instanceId)) show();
      touchState();
      const skipped = keys.filter((key) => !back.includes(key));
      showNotice(skipped.length ? fill(STRINGS.undonePartly, { fields: listOf(skipped.map(label)) }) : STRINGS.undone);
    },
  });
}

// The lock button at the top of every card. The writer's lock is theirs to put on and take off. While the story's own lock is
// on a card, the story bar is where it comes off, so the button is not offered.
function drawLockButton(card) {
  if (lockedByStory(project, card.id)) return;
  const on = lockedByWriter(project, card.id);
  const label = on ? STRINGS.unlockCard : STRINGS.lockCard;
  const toggle = button(on ? LABELS.unlockMark : LABELS.lockMark, () => {
    setWriterLock(project, card.id, !on);
    show();
    touchState();
  }, { className: "lock-toggle" });
  toggle.setAttribute("aria-label", label);
  toggle.title = on ? STRINGS.unlockCardHelp : STRINGS.lockCardHelp;
  toggle.setAttribute("aria-pressed", String(on));
  const bar = Object.assign(document.createElement("div"), { className: "lock-bar" });
  bar.append(toggle);
  main.querySelector(".card-title-row")?.prepend(bar);
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
  return joinList(parts);
}

const tabName = (id) => LABELS.tabNames[id] ?? schema.cards[id].label;

function optionText(name, status) {
  const marks = markNodes(status).map((node) => node.textContent);
  return [name || LABELS.unnamed, ...marks].join("  ");
}

// Brings every tab and every character entry up to date without rebuilding them, so focus stays where it is.
function updateMarks() {
  if (!schema || !project) return;
  welcome?.draw();
  planPanel?.sync();
  const { cards, instances } = projectStatus(schema, project, reviewFor);
  for (const node of cardsNav.querySelectorAll("[data-card]")) {
    const status = cards[node.dataset.card];
    node.querySelector(".tab-marks").replaceChildren(...markNodes(status));
    const words = cardLocked(project, node.dataset.card) ? fill(LABELS.statusLocked, { words: statusWords(status), locked: LABELS.locked }) : statusWords(status);
    node.setAttribute("aria-label", fill(LABELS.tabAria, { name: tabName(node.dataset.card), words }));
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
      Object.assign(document.createElement("span"), { className: "tab-label", textContent: tabName(id) }),
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
  items.push(button(LABELS.addCharacter, () => {
    view.characterId = addInstance(project, card).id;
    show();
    touchState();
  }, { className: "add" }));
  if (view.characterId) {
    items.push(button(LABELS.remove, async () => {
      if (!(await ask(LABELS.deleteCharacter))) return;
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
  planningColumn.querySelectorAll(".plan-panel, .generate-panel, .end-panel, .export-panel, .chapter-view").forEach((panel) => panel.remove());
  let values;
  if (card.many_per_project) {
    if (!findInstance(project, card, view.characterId)) view.characterId = held[0]?.id ?? null;
    values = findInstance(project, card, view.characterId);
  } else {
    values = held;
  }
  drawNav();
  drawChapterNav();
  if (values) {
    const key = `${card.id}:${values.id ?? ""}`;
    const instanceId = card.many_per_project ? values.id : null;
    main.classList.remove("locked");
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
    if (cardLocked(project, card.id)) makeReadOnly(main, lockedByStory(project, card.id) ? STRINGS.lockedBanner : STRINGS.writerLockedBanner);
    drawLockButton(card);
  } else main.replaceChildren();
  if (card.id === "outline" && values) {
    flagItems(main, staleBeatIds(project), STRINGS.staleBeat);
    freezeItems(main, writtenBeatIds(project), STRINGS.writtenBeat);
  }
  const chapter = chapterState();
  if (chapter && view.chapter <= chapter.written) {
    chapterPanel?.draw(planningColumn, view.chapter);
  } else {
    planPanel?.draw(planningColumn);
    generatePanel?.draw(planningColumn);
    endPanel?.draw(planningColumn);
    exportPanel?.draw(planningColumn);
  }
  planningColumn.prepend(storyNode);
  storyBar?.draw();
  welcome?.draw();
  restoreRadioSelections(main);
}

try {
  setText(await (await fetch(TEXT_FILE)).json());
  applyStaticText(document);
  schema = await (await fetch("data/schema.en.json")).json();
  let stored = null;
  try { stored = localStorage.getItem(BACKEND_KEY); } catch { /* no storage: the built-in model is used */ }
  let setting = readStoredSetting(stored);
  if (blockedByPage(setting, location.protocol)) setting = { ok: true, kind: "mock" };
  mock = createMock(schema, { delay: 700 });
  let token = "";
  try { token = localStorage.getItem(TOKEN_KEY) ?? ""; } catch { /* no storage: no token */ }
  client = createClient({ setting, token, mock });
  backendInput.value = settingText(setting);
  tokenInput.value = token;
  storyBar = createStoryBar(storyNode, {
    schema, client, getProject: () => project,
    goTo: (cardId, instanceId) => {     view = { card: cardId, characterId: instanceId, chapter: view.chapter }; show(); },
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
  welcome = createWelcomeStrip(welcomeNode, {
    schema, getProject: () => project,
    goTo: (cardId, instanceId) => { view = { card: cardId, characterId: instanceId, chapter: view.chapter }; show(); },
    shownChanged: (shown) => guideButton.setAttribute("aria-expanded", String(shown)),
  });
  exportPanel = createExportPanel({ schema, getProject: () => project });
  importPanel = createImportPanel(importNode, {
    schema, client, getProject: () => project,
    goTo: (cardId, instanceId) => { view = { card: cardId, characterId: instanceId, chapter: view.chapter }; show(); },
    forget: (cardId, instanceId, keys) => { const marked = draftsFor(`${cardId}:${instanceId ?? ""}`); for (const key of keys) marked.delete(key); },
    changed: () => touchState(), redraw: () => show(),
    notice: (text, kind, action) => showNotice(text, kind, action),
  });
  endPanel = createEndPanel({
    schema, client, getProject: () => project, backendWhere, errorText,
    changed: () => touchState(), redraw: () => show(),
    notice: (text, kind, action) => showNotice(text, kind, action),
  });
  chapterPanel = createChapterPanel({ schema, getProject: () => project });
  client.onChange(() => { drawConnection(); storyBar.draw(); planPanel.refresh(); generatePanel.refresh(); endPanel.refresh(); importPanel.refresh(); });
  drawConnection();
  // Read the earlier copy before anything can tidy it away: a blank, clean project clears the copy it finds.
  const recovered = readRecovery(store.get() ?? "", schema);
  offerPending = worthRecovering(schema, recovered);
  replaceProject(newProject(schema));
  if (offerPending) offerRecovery(recovered);
  client.checkStatus();   // only asks whether the backend is free; no model runs
} catch (error) {
  main.textContent = BOOT_FAILURE;
}
window.pulpermill = {
  get project() { return project; }, get dirty() { return isDirty(); }, get client() { return client; }, get mock() { return mock; },
};   // for looking at the data while testing
