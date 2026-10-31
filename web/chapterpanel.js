// The chapter view: shown in the planning column when the writer opens a written chapter's tab. It shows what the chapter was planned
// as (the spotlight tie in words, who was in it, what the protagonist was after and the plan) and its text. Read-only.
import { section, fill, joinList } from "./text.js";
import { effectiveProject } from "./effective.js";
import { tieInWords } from "./plan.js";
import { instanceName } from "./logic.js";
import { chapterNoteFor } from "./modelnotes.js";
import { reviewNodes } from "./generatepanel.js";

export const STRINGS = section("app");
const PLAN = section("plan");

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, getProject}
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
    if (!beat || !(beat.aim || beat.plan)) {
      planBody.append(node("p", { className: "help", textContent: STRINGS.chapterNoPlan }));
    } else {
      const eff = effectiveProject(project, chapter);
      const aimLabel = hooks.schema.cards.outline.fields.find((f) => f.key === "beats").item_fields.find((f) => f.key === "aim").label;
      const tie = (eff.entanglements?.ties ?? []).find((t) => t.id === beat.spotlight);
      const who = (beat.cast ?? []).map((id) => (eff.characters ?? []).find((c) => c.id === id)).filter(Boolean).map((c) => instanceName(c) || PLAN.unnamed);
      const rows = [
        [PLAN.spotlight, tie ? tieInWords(hooks.schema, eff, tie).text : ""],
        [PLAN.castTitle, joinList(who)],
        [aimLabel, beat.aim ?? ""],
      ].filter(([, value]) => value);
      planBody.append(node("dl", { className: "plan-facts" }, ...rows.flatMap(([term, value]) => [node("dt", { textContent: term }), node("dd", { textContent: value })])));
      if (beat.plan) planBody.append(...beat.plan.split(/\n\s*\n/).map((part) => node("p", { className: "chapter-text", textContent: part.trim() })));
    }
    const textBody = node("div", { className: "chapter-view-body" });
    const text = node("details", { className: "chapter-view-section", open: true },
      node("summary", { textContent: STRINGS.chapterText }), textBody);
    if (!written?.text) textBody.append(node("p", { className: "help", textContent: STRINGS.chapterNoText }));
    else textBody.append(...written.text.split(/\n\s*\n/).map((part) => node("p", { className: "chapter-text", textContent: part.trim() })));
    const shiftBody = node("div", { className: "chapter-view-body" });
    const shifts = node("details", { className: "chapter-view-section", open: true },
      node("summary", { textContent: STRINGS.chapterShifts }), shiftBody);
    const review = written ? chapterNoteFor(project, written.id) : null;
    if (review) shiftBody.append(...reviewNodes(review).slice(1));      // the summary above is the heading
    else shiftBody.append(node("p", { className: "help", textContent: STRINGS.chapterNoShifts }));
    panel.append(plan, text, shifts);
    container.append(panel);
  }

  return { draw };
}
