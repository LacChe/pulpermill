// Loads the schema, holds the project in memory and draws the cards built so far.
// The card switcher and the Open and Save buttons are stand-ins until the project shell exists.
import {
  addInstance, ensureCard, findInstance, instanceName, newProject, removeInstance,
} from "./logic.js";
import { renderCard } from "./render.js";

const BUILT = ["style", "characters", "world"];
const LABELS = { addCharacter: "Add a character", deleteCharacter: "Delete this character?", remove: "Delete", unnamed: "Unnamed character", noCharacters: "No characters yet." };

const cardsNav = document.getElementById("cards");
const peopleNav = document.getElementById("people");
const main = document.getElementById("card");
const openInput = document.getElementById("open-file");
let schema;
let project;
let view = { card: "style", characterId: null };

function button(text, onClick, extra = {}) {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = text;
  if (extra.current) node.setAttribute("aria-current", "true");
  if (extra.className) node.className = extra.className;
  node.addEventListener("click", onClick);
  return node;
}

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
  }, { className: "add" }));
  if (view.characterId) {
    items.push(button(LABELS.remove, () => {
      if (!window.confirm(LABELS.deleteCharacter)) return;
      removeInstance(project, card, view.characterId);
      view.characterId = project[card.id][0]?.id ?? null;
      show();
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
    common: schema.common,
    changed: () => { if (card.many_per_project) drawNav(); },
  });
}

document.getElementById("save").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "pulpermill-project.json";
  link.click();
  URL.revokeObjectURL(link.href);
});

document.getElementById("open").addEventListener("click", () => openInput.click());
openInput.addEventListener("change", async () => {
  const file = openInput.files[0];
  if (!file) return;
  try {
    project = JSON.parse(await file.text());
    view.characterId = null;
    show();
  } catch (error) {
    main.replaceChildren(Object.assign(document.createElement("p"), {
      className: "unsupported", textContent: "That file couldn't be read as a project.",
    }));
  }
  openInput.value = "";
});

try {
  schema = await (await fetch("data/schema.en.json")).json();
  project = newProject(schema);
  show();
} catch (error) {
  main.textContent = "The page couldn't load its schema.";
}
window.pulpermill = { get project() { return project; } };   // for looking at the data while testing
