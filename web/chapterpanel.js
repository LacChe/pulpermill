import { section, fill } from "./text.js";
import { planNoteFor } from "./modelnotes.js";

export const STRINGS = section("app");

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

export function createChapterPanel(hooks) {
  function draw(container, chapter) {
    const project = hooks.getProject();
    if (!project) return;
    const beat = (project.outline?.beats ?? []).find((entry) => Number(entry.chapter) === chapter);
    const written = (project.chapters ?? []).find((entry) => {
      const source = (project.outline?.beats ?? []).find((candidate) => candidate.id === entry.beat);
      return Number(source?.chapter) === chapter;
    });
    const panel = node("section", { className: "chapter-view" },
      node("h3", { textContent: fill(STRINGS.chapterTab, { n: chapter }) }));
    const planBody = node("div", { className: "chapter-view-body" });
    const plan = node("details", { className: "chapter-view-section", open: true },
      node("summary", { textContent: STRINGS.chapterPlan }), planBody);
    const thought = beat ? planNoteFor(project, beat.id) : null;
    if (!thought?.thinking) {
      planBody.append(node("p", { className: "help", textContent: STRINGS.chapterNoPlan }));
    } else {
      planBody.append(node("p", { className: "chapter-text", textContent: thought.thinking }));
    }
    const textBody = node("div", { className: "chapter-view-body" });
    const text = node("details", { className: "chapter-view-section", open: true },
      node("summary", { textContent: STRINGS.chapterText }), textBody);
    if (!written?.text) textBody.append(node("p", { className: "help", textContent: STRINGS.chapterNoText }));
    else textBody.append(...written.text.split(/\n\s*\n/).map((part) => node("p", { className: "chapter-text", textContent: part.trim() })));
    panel.append(plan, text);
    container.append(panel);
  }

  return { draw };
}
