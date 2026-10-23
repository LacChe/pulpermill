// The generate panel: shown on the Outline card under the plan panel. One button asks the model to write the planned
// chapter; the page then applies the result and commits it as one unit. The panel also lists the written chapters and, for
// the chapter just made, what changed in the Entanglements and what the page noticed. Nothing here calls the model except
// that one button. Stopping is the Stop button the page already has: a stopped or failed chapter leaves nothing behind.
import { generateChapter, regenerateChapter } from "./client.js";
import { generateGate, applyGenerated, commitChapter, regenerateGate, applyRegenerated, commitRegenerated } from "./generate.js";
import { chapterInfo } from "./plan.js";

export const STRINGS = {
  title: "Write the chapter",
  chapterOf: "Chapter {n} of {total}",
  chapterOnly: "Chapter {n}",
  button: "Write chapter {n} with the model",
  working: "The model is working…",
  stages: { write: "The model is writing the chapter…", events: "The model is noting what happened…", shifts: "The model is noting how people changed…" },
  sends: "Pressing the button sends the cast, the cards in play, the beat and the summaries of earlier chapters to {where}. Nothing is saved unless the whole chapter comes back.",
  reasons: {
    not_started: "Start the story first (the bar above).",
    done: "Every chapter is written. Use the end-of-story step when you are ready.",
    no_beat: "Plan the chapter first (the panel above).",
    cast_empty: "The beat has no cast.", cast_too_many: "The beat has too many people in its cast.",
    cast_no_protagonist: "The protagonist has to be in the beat's cast.", cast_unknown: "Someone in the beat's cast is not there any more.",
    beat_blocked: "The beat has problems that stop generating. Fix them first:",
    entanglements_blocked: "Entanglements has problems that stop generating. Fix them first:",
    changed: "The Entanglements or the beat were edited while the model was writing, so the chapter was thrown away. Press the button again.",
  },
  stale: "This plan was made from older Entanglements. Write the chapter anyway? (Cancel, then plan it again, to use the new state.)",
  locked: "The model wants to change values that are locked:\n{list}\n\nOK unlocks them and overwrites them. Cancel keeps them as they are, and the chapter is saved without those changes.",
  done: "Chapter {n} is written and saved.",
  droppedLocked: "Chapter {n} is written and saved. The locked values were left as they were.",
  chapters: "Written chapters",
  noChapters: "No chapter yet.",
  chapterTitle: "Chapter {n}",
  changes: "What changed in Entanglements",
  noChanges: "Nothing in Entanglements changed.",
  change: "{field}: {from} → {to}",
  noticed: "What the page noticed",
  again: "Write chapter {n} again",
  againConfirm: "Write chapter {n} again?\n\nThe Entanglements go back to what this chapter was first written from, and what the model makes now replaces the Entanglements as they are. This chapter's text, events and shifts are replaced. {later}You can undo it afterwards.",
  againLater: "The {k} later chapter(s) stay as they are, and their beats are marked stale. ",
  againDone: "Chapter {n} is written again.",
  undo: "Undo", undone: "Put chapter {n} back as it was.",
  before: "Before", after: "After",
  noChapterGate: "This chapter cannot be written again:",
  reasonsAgain: { no_chapter: "There is no such chapter.", no_snapshot: "The Entanglements it was written from were not kept." },
};
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, client, getProject, backendWhere, changed(), redraw(), notice(text, kind), errorText(error)}
export function createGeneratePanel(hooks) {
  const reviews = new Map();            // chapter id -> {applied, warnings}; only kept while the page is open
  let button = null;
  let stageLine = null;
  let againButtons = [];
  let mine = false;                     // this panel pressed the button and is waiting

  function refresh() {
    const { working, stage } = hooks.client.state;
    for (const b of againButtons) b.disabled = working;
    if (button) button.disabled = working || button.dataset.blocked === "true";
    if (stageLine) stageLine.textContent = working && mine ? STRINGS.stages[stage] ?? STRINGS.working : "";
  }

  async function press(project) {
    const gate = generateGate(hooks.schema, project);
    if (!gate.ok) return;
    if (gate.stale && !window.confirm(STRINGS.stale)) return;
    mine = true;
    refresh();
    const result = await generateChapter(hooks.client, hooks.schema, project).done;
    mine = false;
    if (hooks.getProject() !== project) return;          // another project was opened while the model worked
    if (result.reason) { hooks.notice(STRINGS.reasons[result.reason] ?? result.reason, "notice-bad"); hooks.redraw(); return; }
    if (!result.ok) { hooks.notice(hooks.errorText(result.error), result.error.kind === "stopped" ? "" : "notice-bad"); refresh(); return; }

    let outcome = result.outcome;
    let leftLocked = false;
    if (outcome.changes.locked.length) {
      const list = outcome.changes.locked.map((a) => `• ${a.label}: ${a.from} → ${a.to}`).join("\n");
      if (!window.confirm(fill(STRINGS.locked, { list }))) {
        outcome = applyGenerated(hooks.schema, project, result.beat, result.read, { overwriteLocked: false });
        leftLocked = true;
      }
    }
    const n = Number(result.beat.chapter);
    commitChapter(project, outcome);
    reviews.set(outcome.chapter.id, { applied: outcome.changes.applied, warnings: outcome.warnings });
    hooks.notice(fill(leftLocked ? STRINGS.droppedLocked : STRINGS.done, { n }), "");
    hooks.changed();
    hooks.redraw();
  }

  async function again(project, number, later) {
    if (!window.confirm(fill(STRINGS.againConfirm, { n: number, later: later ? fill(STRINGS.againLater, { k: later }) : "" }))) return;
    mine = true;
    refresh();
    const result = await regenerateChapter(hooks.client, hooks.schema, project, number).done;
    mine = false;
    if (hooks.getProject() !== project) return;
    if (result.reason) {
      const why = STRINGS.reasonsAgain[result.reason] ?? STRINGS.reasons[result.reason] ?? result.reason;
      hooks.notice([why, ...(result.problems ?? [])].join(" "), "notice-bad");
      hooks.redraw();
      return;
    }
    if (!result.ok) { hooks.notice(hooks.errorText(result.error), result.error.kind === "stopped" ? "" : "notice-bad"); refresh(); return; }
    let outcome = result.outcome;
    if (outcome.changes.locked.length) {
      const list = outcome.changes.locked.map((a) => `• ${a.label}: ${a.from} → ${a.to}`).join("\n");
      if (!window.confirm(fill(STRINGS.locked, { list }))) outcome = applyRegenerated(hooks.schema, project, result.ctx, result.read, { overwriteLocked: false });
    }
    const { undo } = commitRegenerated(project, outcome);
    const earlier = reviews.get(outcome.chapter.id);
    reviews.set(outcome.chapter.id, { applied: outcome.changes.applied, warnings: outcome.warnings, before: outcome.before });
    hooks.notice(fill(STRINGS.againDone, { n: number }), "", {
      label: STRINGS.undo,
      run: () => {
        if (hooks.getProject() !== project) return;
        undo();
        if (earlier) reviews.set(outcome.chapter.id, earlier); else reviews.delete(outcome.chapter.id);
        hooks.changed();
        hooks.redraw();
        hooks.notice(fill(STRINGS.undone, { n: number }));
      },
    });
    hooks.changed();
    hooks.redraw();
  }

  function chapterList(project) {
    const written = project.chapters ?? [];
    const box = node("div", { className: "chapter-list" }, node("h4", { textContent: STRINGS.chapters }));
    if (!written.length) { box.append(node("p", { className: "help", textContent: STRINGS.noChapters })); return box; }
    const numberOf = (c) => Number((project.outline?.beats ?? []).find((b) => b.id === c.beat)?.chapter) || 0;
    const ordered = [...written].sort((a, b) => numberOf(a) - numberOf(b));
    ordered.forEach((c, at) => {
      const parts = [node("summary", { textContent: fill(STRINGS.chapterTitle, { n: numberOf(c) }) })];
      const paragraphs = (text) => text.split(/\n\s*\n/).map((paragraph) => node("p", { className: "chapter-text", textContent: paragraph.trim() }));
      const review = reviews.get(c.id);
      if (review?.before !== undefined) {
        parts.push(node("div", { className: "chapter-compare" },
          node("div", {}, node("h5", { textContent: STRINGS.before }), ...paragraphs(review.before)),
          node("div", {}, node("h5", { textContent: STRINGS.after }), ...paragraphs(c.text))));
      } else {
        parts.push(...paragraphs(c.text));
      }
      if (review) {
        parts.push(node("h5", { textContent: STRINGS.changes }));
        parts.push(review.applied.length
          ? node("ul", { className: "chapter-changes" }, ...review.applied.map((a) => node("li", { textContent: fill(STRINGS.change, { field: a.label, from: a.from || "–", to: a.to || "–" }) })))
          : node("p", { className: "help", textContent: STRINGS.noChanges }));
        if (review.warnings.length) {
          parts.push(node("h5", { textContent: STRINGS.noticed }));
          parts.push(node("ul", { className: "chapter-warnings" }, ...review.warnings.map((w) => node("li", { textContent: w.text }))));
        }
      }
      const gate = regenerateGate(hooks.schema, project, numberOf(c));
      if (gate.ok) {
        const redo = node("button", { type: "button", className: "validate again", textContent: fill(STRINGS.again, { n: numberOf(c) }) });
        redo.addEventListener("click", () => again(project, numberOf(c), gate.later));
        parts.push(node("div", { className: "plan-actions" }, redo));
        againButtons.push(redo);
      }
      box.append(node("details", { className: "chapter", open: at === ordered.length - 1 }, ...parts));
    });
    return box;
  }

  // Draws the panel into the Outline card, under the plan panel.
  function draw(container) {
    const project = hooks.getProject();
    button = null;
    stageLine = null;
    againButtons = [];
    if (!project) return;
    const panel = node("section", { className: "generate-panel" }, node("h3", { textContent: STRINGS.title }));
    (container.querySelector(".plan-panel")?.after(panel) ?? container.prepend(panel));
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
      panel.append(node("div", { className: "plan-actions" }, button, stageLine),
        node("p", { className: "note", textContent: fill(STRINGS.sends, { where: hooks.backendWhere() }) }));
    }
    panel.append(chapterList(project));
    refresh();
  }

  return { draw, refresh, reset() { reviews.clear(); button = null; stageLine = null; mine = false; } };
}
