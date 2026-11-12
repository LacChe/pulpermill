// The generate panel: shown on the Outline card under the plan panel. One button asks the model to write the planned
// chapter; the page then applies the result and commits it as one unit. Nothing here calls the model except that one button
// and `again`, which the chapter's own tab (chapterpanel.js) runs from its Write again button: shifts are edited by writing the
// chapter again. The panel shows nothing about chapters already written; each chapter's tab shows its own.
// Stopping is the Stop button the page already has: a stopped or failed chapter leaves nothing behind.
import { generateChapter, regenerateChapter } from "./client.js";
import { generateGate, applyGenerated, commitChapter, applyRegenerated, commitRegenerated } from "./generate.js";
import { chapterInfo, beatForChapter, requiredCast, tiesInPlay, tieInWords } from "./plan.js";
import { effectiveProject } from "./effective.js";
import { instanceName } from "./logic.js";
import { setChapterNote, copyNote, putNote } from "./modelnotes.js";
import { section, fill, joinList } from "./text.js";
import { ask } from "./dialog.js";
import { elapsedTag } from "./elapsed.js";
import { removeNote } from "./modelnotes.js";
import { callsModel } from "./busy.js";

export const STRINGS = section("generate");
const PLAN = section("plan");           // the words for the cast and the ties, which the plan panel used to show

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

// Who is in the chapter and the ties that will be sent with it, read-only: what the writer is sent, shown once the chapter has a plan (so the
// spotlight is the planner's pick and the cast is the one the plan was made for). A change is made in the Outline form, then planned again.
function sentNodes(project, hooks) {
  const info = chapterInfo(project);
  const beat = beatForChapter(project, info.next);
  if (!beat) return [];
  const eff = effectiveProject(project, info.next);
  const must = requiredCast(eff, beat.spotlight);
  const protagonist = eff.setup?.protagonist;
  const people = (beat.cast ?? []).map((id) => (eff.characters ?? []).find((c) => c.id === id)).filter(Boolean);
  const sent = tiesInPlay(eff, beat.cast);
  return [node("fieldset", { className: "plan-cast-box" }, node("legend", { textContent: PLAN.castTitle }),
    node("p", { className: "help", textContent: PLAN.castSent }),
    node("div", { className: "plan-cast" }, ...people.map((c) => node("p", { className: "plan-person" },
      node("span", { className: "plan-name", textContent: instanceName(c) || PLAN.unnamed }),
      ...(must.includes(c.id) ? [node("span", { className: "tag", textContent: c.id === protagonist ? PLAN.protagonist : PLAN.inSpotlight })] : [])))),
    node("h4", { textContent: PLAN.tiesSent }),
    sent.length ? node("ul", { className: "plan-ties" }, ...sent.map((t) => node("li", { textContent: tieInWords(hooks.schema, eff, t).text })))
      : node("p", { className: "help", textContent: PLAN.tiesNone }))];
}

// hooks: {schema, client, getProject, backendWhere, changed(), redraw(), notice(text, kind), errorText(error)}
export function createGeneratePanel(hooks) {
  let button = null;
  let tag = null;                       // the seconds beside the button
  let mine = false;                     // this panel pressed the button and is waiting

  function refresh() {
    if (button) button.disabled = button.dataset.blocked === "true";
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
    land(project, result);
  }

  // What a chapter call's result does to the page: the failure said in words, or the chapter committed with its notice and Undo. Also how
  // a chapter collected after a reload lands (collect.js), so the two read the same.
  function land(project, result) {
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
      button = callsModel(node("button", { type: "button", className: "validate", textContent: fill(STRINGS.button, { n: info.next }) }));
      button.addEventListener("click", () => press(project));
      tag = elapsedTag(hooks.client, () => mine);
      panel.append(node("div", { className: "plan-actions" }, button, tag.node),
        node("p", { className: "note", textContent: fill(STRINGS.sends, { where: hooks.backendWhere() }) }), ...sentNodes(project, hooks));
    }
    refresh();
  }

  return { draw, refresh, again, land, reset() { button = null; tag = null; mine = false; } };
}
