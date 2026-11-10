// The chapter view: shown in the planning column when the writer opens a written chapter's tab. It shows what the chapter was planned
// as (the spotlight tie in words, who was in it, what the protagonist was after and the plan), its text (beside the earlier text
// after a Write again) and what changed in it. Everything shown is this chapter's own. The one thing the writer can do here is
// write this chapter again; the call itself is the generate panel's (hooks.redo).
import { section, fill, joinList } from "./text.js";
import { effectiveProject } from "./effective.js";
import { tieInWords } from "./plan.js";
import { instanceName, stageText } from "./logic.js";
import { chapterNoteFor } from "./modelnotes.js";
import { regenerateGate } from "./generate.js";
import { elapsedTag } from "./elapsed.js";
import { reviewNodes } from "./generatepanel.js";

export const STRINGS = section("app");
const PLAN = section("plan");
const GENERATE = section("generate");

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, client, getProject, redo(project, number, later)}
export function createChapterPanel(hooks) {
  let redoButton = null;
  let stageLine = null;
  let tag = null;                       // the seconds beside the button
  let busy = null;                      // the number of the chapter this panel is writing again

  function refresh() {
    const { working, stage } = hooks.client.state;
    if (redoButton) redoButton.disabled = working;
    if (stageLine) stageLine.textContent = working && busy !== null ? stageText(stage) || GENERATE.working : "";
    tag?.update();
  }

  async function redo(project, number, later) {
    busy = number;
    refresh();
    try { await hooks.redo(project, number, later); } finally { busy = null; refresh(); }
  }

  const paragraphs = (value) => value.split(/\n\s*\n/).map((part) => node("p", { className: "chapter-text", textContent: part.trim() }));

  function draw(container, chapter) {
    redoButton = null;
    stageLine = null;
    tag = null;
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
    const review = written ? chapterNoteFor(project, written.id) : null;
    if (!written?.text) textBody.append(node("p", { className: "help", textContent: STRINGS.chapterNoText }));
    else if (review?.before !== undefined) {
      textBody.append(node("div", { className: "chapter-compare" },
        node("div", {}, node("h5", { textContent: GENERATE.before }), ...paragraphs(review.before)),
        node("div", {}, node("h5", { textContent: GENERATE.after }), ...paragraphs(written.text))));
    } else textBody.append(...paragraphs(written.text));
    const shiftBody = node("div", { className: "chapter-view-body" });
    const shifts = node("details", { className: "chapter-view-section", open: true },
      node("summary", { textContent: STRINGS.chapterShifts }), shiftBody);
    if (review) shiftBody.append(...reviewNodes(review).slice(1));      // the summary above is the heading
    else shiftBody.append(node("p", { className: "help", textContent: STRINGS.chapterNoShifts }));
    panel.append(plan, text, shifts);
    const gate = written ? regenerateGate(hooks.schema, project, chapter) : null;
    if (gate?.ok) {
      redoButton = node("button", { type: "button", className: "validate again", textContent: fill(GENERATE.again, { n: chapter }) });
      redoButton.addEventListener("click", () => redo(project, chapter, gate.later));
      stageLine = node("span", { className: "note", textContent: "" });
      tag = elapsedTag(hooks.client, () => busy === chapter);
      panel.append(node("div", { className: "plan-actions" }, redoButton, tag.node, stageLine));
    } else if (gate?.reason === "outline_locked") {
      panel.append(node("p", { className: "help", textContent: GENERATE.reasonsAgain.outline_locked }));
    }
    container.append(panel);
    refresh();
  }

  return { draw, refresh, reset() { redoButton = null; stageLine = null; tag = null; busy = null; } };
}
