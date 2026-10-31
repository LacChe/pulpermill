// The end-of-story panel: shown on the Outline card under the generate panel. Once every chapter is written, one button finishes the
// story. There is no model call: the page folds every shift into the cards (endstory.js) and keeps the result as the after-story copy
// (Style, Characters, World and Entanglements; the originals are never touched) with an Undo. The panel lists what changed in
// Characters, World and Entanglements in words, the problems the copy has, and says when the copy may be out of date.
import { endGate, makeAfterStory, afterStoryChanges, afterStoryProblems, afterStoryStale, afterStoryView, chaptersFingerprint } from "./endstory.js";
import { endNoteFor, setEndNote, setEndProblems } from "./modelnotes.js";
import { watch } from "./undo.js";
import { renderCard } from "./render.js";
import { instanceName } from "./logic.js";
import { section, fill } from "./text.js";
import { ask } from "./dialog.js";
import { remember } from "./folds.js";

export const STRINGS = section("end");

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, client, getProject, changed(), redraw(), notice(text, kind, action)}
export function createEndPanel(hooks) {
  let button = null;
  let reviews = new Map();              // per card in the copy: what the writer has visited, kept across redraws like the cards' own

  function refresh() {
    if (button) button.disabled = hooks.client.state.working;      // one job at a time, though this one needs no model
  }

  function press(project, replaces) {
    return (async () => {
      if (replaces && !(await ask(STRINGS.confirmAgain))) return;
      const made = makeAfterStory(project);
      if (!made.ok) { hooks.notice(STRINGS.reasons[made.reason] ?? made.reason, "notice-bad"); hooks.redraw(); return; }
      const undo = watch(project, ["after_story", "end_note"]);
      project.after_story = made.after;
      reviews = new Map();
      setEndNote(project, { problems: afterStoryProblems(hooks.schema, project, made.after), madeFrom: chaptersFingerprint(project) });
      undo.settle();
      hooks.notice(STRINGS.done, "", {
        label: STRINGS.undo,
        run: () => {
          if (hooks.getProject() !== project) return;
          if (!undo.undo()) { hooks.notice(STRINGS.undoBlocked, "notice-bad"); return; }
          hooks.changed();
          hooks.redraw();
          hooks.notice(STRINGS.undone);
        },
      });
      hooks.changed();
      hooks.redraw();
    })();
  }

  // What the review says, drawn into `box`. Called when the panel is drawn and again when the writer leaves a field of the copy.
  function drawReview(project, box) {
    const note = endNoteFor(project);
    const parts = [node("h4", { textContent: STRINGS.changes })];
    if (afterStoryStale(project)) parts.push(node("p", { className: "plan-stale after-stale", textContent: STRINGS.stale }));
    const changes = afterStoryChanges(hooks.schema, project, project.after_story);
    if (!changes.length) parts.push(node("p", { className: "help", textContent: STRINGS.noChanges }));
    else {
      const who = (c) => (c.card === "world" ? STRINGS.worldWho : c.who);
      const line = (c) => (c.kind === "added" ? fill(STRINGS.added, { who: who(c), label: c.label, after: c.after })
        : c.kind === "removed" ? fill(STRINGS.removed, { who: who(c), label: c.label, before: c.before })
        : fill(STRINGS.changed, { who: who(c), label: c.label, before: c.before || "–", after: c.after || "–" }));
      parts.push(node("ul", { className: "after-changes" }, ...changes.map((c) => node("li", { textContent: line(c) }))));
    }
    if (note?.problems) parts.push(node("p", { className: "help", textContent: fill(STRINGS.problems, { n: note.problems }) }));
    box.replaceChildren(...parts);
  }

  // The copy's cards as forms, the same ones as on the card tabs but with no Fill and no model check. They edit the copy in
  // place. The review above is brought up to date when the writer leaves a field, never on each keystroke.
  function editor(project, summary) {
    const after = project.after_story;
    const view = afterStoryView(hooks.schema, project);
    const sections = [
      [STRINGS.editStyle, "style", after.style, "style"],
      ...after.characters.map((c) => [fill(STRINGS.editPerson, { name: instanceName(c) || STRINGS.unnamed }), "characters", c, `characters:${c.id}`]),
      [STRINGS.editWorld, "world", after.world, "world"],
      [STRINGS.editEntanglements, "entanglements", after.entanglements, "entanglements"],
    ];
    const body = node("div", { className: "after-edit-body" }, node("p", { className: "help", textContent: STRINGS.editHelp }));
    for (const [label, cardId, values, key] of sections) {
      if (!values) continue;
      if (!reviews.has(key)) reviews.set(key, { touched: new Set(), validated: false });
      const holder = node("div", { className: "after-edit-card" });
      const inside = node("details", { className: "after-edit-item" }, node("summary", { textContent: label }), holder);
      remember(inside, `after-edit:${label}`, inside.open);
      renderCard(holder, hooks.schema.cards[cardId], values, {
        project: view, schema: hooks.schema, common: hooks.schema.common, review: reviews.get(key),
        changed: () => hooks.changed(),
      });
      body.append(inside);
    }
    body.addEventListener("focusout", () => {
      setTimeout(() => {
        if (hooks.getProject() !== project || project.after_story !== after) return;
        setEndProblems(project, afterStoryProblems(hooks.schema, project, after));
        drawReview(project, summary);
      }, 0);
    });
    const outer = node("details", { className: "after-edit" }, node("summary", { textContent: STRINGS.editTitle }), body);
    remember(outer, "after-edit", outer.open);
    return outer;
  }

  function review(project) {
    const box = node("div", { className: "after-story" });
    const summary = node("div", { className: "after-summary" });
    drawReview(project, summary);
    box.append(summary, editor(project, summary));
    return box;
  }

  function draw(container) {
    const project = hooks.getProject();
    button = null;
    if (!project) return;
    const panel = node("section", { className: "end-panel" }, node("h3", { textContent: STRINGS.title }));
    container.append(panel);
    const gate = endGate(project);
    if (!gate.ok) { panel.append(node("p", { className: "help", textContent: STRINGS.notDone })); return; }
    panel.append(node("p", { className: "help", textContent: STRINGS.help }));
    button = node("button", { type: "button", className: "validate", textContent: gate.replaces ? STRINGS.buttonAgain : STRINGS.button });
    button.addEventListener("click", () => press(project, gate.replaces));
    panel.append(node("div", { className: "plan-actions" }, button));
    if (project.after_story) panel.append(review(project));
    refresh();
  }

  return { draw, refresh, reset() { button = null; reviews = new Map(); } };
}
