// The generate panel: shown on the Outline card under the plan panel. One button asks the model to write the planned
// chapter; the page then applies the result and commits it as one unit. Nothing here calls the model except that one button
// and `again`, which the chapter's own tab (chapterpanel.js) runs from its Write again button: shifts are edited by writing the
// chapter again. The panel shows nothing about chapters already written; each chapter's tab shows its own.
// Stopping is the Stop button the page already has: a stopped or failed chapter leaves nothing behind.
import { generateChapter, regenerateChapter } from "./client.js";
import { generateGate, applyGenerated, commitChapter, applyRegenerated, commitRegenerated } from "./generate.js";
import { chapterInfo } from "./plan.js";
import { setChapterNote, copyNote, putNote } from "./modelnotes.js";
import { stageText } from "./logic.js";
import { section, fill, joinList } from "./text.js";
import { ask } from "./dialog.js";
import { elapsedTag } from "./elapsed.js";
import { removeNote } from "./modelnotes.js";

export const STRINGS = section("generate");

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// What a chapter's note says, read-only: the shifts that were applied (who or what, which field, before and after), and what was left
// out or noticed, each with its reason. Drawn in the chapter's own view.
export function reviewNodes(review) {
  const parts = [node("h5", { textContent: STRINGS.changes })];
  parts.push(review.changes.length
    ? node("ul", { className: "chapter-changes" }, ...review.changes.map((a) => node("li", { textContent: fill(STRINGS.change, { field: a.label, from: a.before || "–", to: a.after || "–" }) })))
    : node("p", { className: "help", textContent: STRINGS.noChanges }));
  if (review.warnings.length) {
    parts.push(node("h5", { textContent: STRINGS.noticed }));
    parts.push(node("ul", { className: "chapter-warnings" }, ...review.warnings.map((w) => node("li", { textContent: w.text }))));
  }
  return parts;
}

// hooks: {schema, client, getProject, backendWhere, changed(), redraw(), notice(text, kind), errorText(error)}
export function createGeneratePanel(hooks) {
  let button = null;
  let stageLine = null;
  let tag = null;                       // the seconds beside the button
  let mine = false;                     // this panel pressed the button and is waiting

  function refresh() {
    const { working, stage } = hooks.client.state;
    if (button) button.disabled = working || button.dataset.blocked === "true";
    if (stageLine) stageLine.textContent = working && mine ? stageText(stage) || STRINGS.working : "";
    tag?.update();
  }

  async function press(project) {
    const gate = generateGate(hooks.schema, project);
    if (!gate.ok) return;
    if (gate.stale && !(await ask(STRINGS.stale))) return;
    mine = true;
    refresh();
    const result = await generateChapter(hooks.client, hooks.schema, project).done;
    mine = false;
    if (hooks.getProject() !== project) return;          // another project was opened while the model worked
    if (result.reason) { hooks.notice(STRINGS.reasons[result.reason] ?? result.reason, "notice-bad"); hooks.redraw(); return; }
    if (!result.ok) { hooks.notice(hooks.errorText(result.error), result.error.kind === "stopped" ? "" : "notice-bad"); refresh(); return; }

    const outcome = result.outcome;
    const n = Number(result.beat.chapter);
    const { undo } = commitChapter(project, outcome);
    setChapterNote(project, outcome.chapter.id, { changes: outcome.changes, warnings: outcome.warnings });
    hooks.notice(joinList([fill(STRINGS.done, { n }), result.edited ? STRINGS.editedMeanwhile : ""].filter(Boolean), "sentence"), result.edited ? "notice-bad" : "", {
      label: STRINGS.undo,
      run: () => {
        if (hooks.getProject() !== project) return;
        if (!undo()) { hooks.notice(fill(STRINGS.undoBlocked, { n }), "notice-bad"); return; }
        removeNote(project, "chapter", outcome.chapter.id);
        hooks.changed();
        hooks.redraw();
        hooks.notice(fill(STRINGS.undoneGenerate, { n }));
      },
    });
    hooks.changed();
    hooks.redraw();
  }

  async function again(project, number, later) {
    if (!(await ask(fill(STRINGS.againConfirm, { n: number, later: later ? fill(STRINGS.againLater, { k: later }) : "" })))) return;
    mine = true;
    refresh();
    const result = await regenerateChapter(hooks.client, hooks.schema, project, number).done;
    mine = false;
    if (hooks.getProject() !== project) return;
    if (result.reason) {
      const why = STRINGS.reasonsAgain[result.reason] ?? STRINGS.reasons[result.reason] ?? result.reason;
      hooks.notice(joinList([why, ...(result.problems ?? [])], "sentence"), "notice-bad");
      hooks.redraw();
      return;
    }
    if (!result.ok) { hooks.notice(hooks.errorText(result.error), result.error.kind === "stopped" ? "" : "notice-bad"); refresh(); return; }
    const outcome = result.outcome;
    const { undo } = commitRegenerated(project, outcome);
    const earlier = copyNote(project, "chapter", outcome.chapter.id);
    setChapterNote(project, outcome.chapter.id, { changes: outcome.changes, warnings: outcome.warnings, before: outcome.before });
    hooks.notice(joinList([fill(STRINGS.againDone, { n: number }), result.edited ? STRINGS.editedMeanwhile : ""].filter(Boolean), "sentence"), result.edited ? "notice-bad" : "", {
      label: STRINGS.undo,
      run: () => {
        if (hooks.getProject() !== project) return;
        if (!undo()) { hooks.notice(fill(STRINGS.undoBlocked, { n: number }), "notice-bad"); return; }
        putNote(project, "chapter", outcome.chapter.id, earlier);
        hooks.changed();
        hooks.redraw();
        hooks.notice(fill(STRINGS.undone, { n: number }));
      },
    });
    hooks.changed();
    hooks.redraw();
  }

  // Draws the panel into the planning column, under the plan panel.
  function draw(container) {
    const project = hooks.getProject();
    button = null;
    stageLine = null;
    tag = null;
    if (!project) return;
    const panel = node("section", { className: "generate-panel" }, node("h3", { textContent: STRINGS.title }));
    container.append(panel);
    const gate = generateGate(hooks.schema, project);
    const info = chapterInfo(project);
    if (gate.ok || gate.reason.startsWith("cast_") || gate.reason.endsWith("_blocked")) {
      panel.append(node("p", { className: "plan-chapter", textContent: fill(info.count ? STRINGS.chapterOf : STRINGS.chapterOnly, { n: info.next, total: info.count }) }));
    }
    if (!gate.ok) {
      panel.append(node("p", { className: "help", textContent: STRINGS.reasons[gate.reason] }));
      if (gate.problems) panel.append(node("ul", { className: "chapter-warnings" }, ...gate.problems.map((p) => node("li", { textContent: p }))));
    } else {
      button = node("button", { type: "button", className: "validate", textContent: fill(STRINGS.button, { n: info.next }) });
      button.addEventListener("click", () => press(project));
      stageLine = node("span", { className: "note", textContent: "" });
      tag = elapsedTag(hooks.client, () => mine);
      panel.append(node("div", { className: "plan-actions" }, button, tag.node, stageLine),
        node("p", { className: "note", textContent: fill(STRINGS.sends, { where: hooks.backendWhere() }) }));
    }
    refresh();
  }

  return { draw, refresh, again, reset() { button = null; stageLine = null; tag = null; mine = false; } };
}
