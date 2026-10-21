// Loads the schema, holds the project in memory and draws the Style card.
// The Open and Save buttons are a stand-in until the project shell exists.
import { ensureCard, newProject, setField } from "./logic.js";
import { renderCard } from "./render.js";

const main = document.getElementById("card");
const openInput = document.getElementById("open-file");
let schema;
let project;

function show() {
  const card = schema.cards.style;
  ensureCard(project, card);
  renderCard(main, card, project, (cardId, key, value) => setField(project, cardId, key, value));
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
