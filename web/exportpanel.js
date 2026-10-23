// The export panel: shown at the bottom of the Outline card. The story as one markdown file, each portable card as its own
// JSON file, and a pointer to Save for the project file. Nothing here calls the model.
import { storyMarkdown, storyFileName, cardFiles, storyCounts } from "./exporting.js";

export const STRINGS = {
  title: "Export",
  story: "The story",
  storyHelp: "Every written chapter in one markdown file ({n} of {total} written).",
  storyHelpNoTotal: "Every written chapter in one markdown file ({n} written).",
  storyNone: "Nothing to export yet: no chapter is written.",
  storyButton: "Download the story (.md)",
  cards: "The cards",
  cardsHelp: "Style, each character and the world, each as its own JSON file, so they can be used in another story. The other cards belong to this story only.",
  download: "Download",
  downloadAll: "Download all the card files",
  project: "The project",
  projectHelp: "Use Save at the top. The project file holds everything, and opening it brings the story back as it was.",
};
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// Hands the browser a file. The page works from a file name and text, so there is nothing to keep.
export function download(name, text, type) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([text], { type }));
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

// hooks: {schema, getProject}
export function createExportPanel(hooks) {
  function draw(container) {
    const project = hooks.getProject();
    if (!project) return;
    const panel = node("section", { className: "export-panel" }, node("h3", { textContent: STRINGS.title }));
    (container.querySelector(".end-panel")?.after(panel) ?? container.append(panel));

    const { chapters, total } = storyCounts(project);
    panel.append(node("h4", { textContent: STRINGS.story }));
    if (!chapters) panel.append(node("p", { className: "help", textContent: STRINGS.storyNone }));
    else {
      panel.append(node("p", { className: "help", textContent: fill(total ? STRINGS.storyHelp : STRINGS.storyHelpNoTotal, { n: chapters, total }) }));
      const get = node("button", { type: "button", className: "validate", textContent: STRINGS.storyButton });
      get.addEventListener("click", () => download(storyFileName(project), storyMarkdown(project), "text/markdown"));
      panel.append(node("div", { className: "plan-actions" }, get));
    }

    const files = cardFiles(hooks.schema, project);
    panel.append(node("h4", { textContent: STRINGS.cards }), node("p", { className: "help", textContent: STRINGS.cardsHelp }));
    const rows = files.map((f) => {
      const get = node("button", { type: "button", textContent: STRINGS.download });
      get.addEventListener("click", () => download(f.name, f.text, "application/json"));
      return node("li", {}, node("span", { className: "export-label", textContent: f.label }), node("span", { className: "note", textContent: f.name }), get);
    });
    panel.append(node("ul", { className: "export-files" }, ...rows));
    const all = node("button", { type: "button", className: "validate", textContent: STRINGS.downloadAll });
    all.addEventListener("click", () => files.forEach((f, at) => setTimeout(() => download(f.name, f.text, "application/json"), at * 300)));
    panel.append(node("div", { className: "plan-actions" }, all),
      node("h4", { textContent: STRINGS.project }), node("p", { className: "help", textContent: STRINGS.projectHelp }));
  }
  return { draw };
}
