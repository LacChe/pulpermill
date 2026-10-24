// The end-of-story panel: shown on the Outline card under the generate panel. Once every chapter is written, one button asks
// the model to update the characters and the world from what the records say happened. The result is stored at once as the
// after-story copy (the originals are never touched) with an Undo, and the panel lists what changed. Nothing here calls the model
// except that one button.
import { endStory } from "./client.js";
import { endGate, afterStoryChanges, afterStoryProblems, afterStoryStale, afterStoryView, chaptersFingerprint } from "./endstory.js";
import { endNoteFor, setEndNote, setEndProblems, copyEndNote, putEndNote } from "./modelnotes.js";
import { renderCard } from "./render.js";
import { instanceName } from "./logic.js";
import { section, fill, joinList } from "./text.js";

export const STRINGS = section("end");
const copy = (value) => JSON.parse(JSON.stringify(value));

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, client, getProject, backendWhere, changed(), redraw(), notice(text, kind, action), errorText(error)}
export function createEndPanel(hooks) {
  let button = null;
  let mine = false;
  let status = null;
  let reviews = new Map();              // per card in the copy: what the writer has visited, kept across redraws like the cards' own

  function refresh() {
    const { working } = hooks.client.state;
    if (button) button.disabled = working;
    if (status) status.textContent = working && mine ? STRINGS.working : "";
  }

  async function press(project, replaces) {
    if (replaces && !window.confirm(STRINGS.confirmAgain)) return;
    mine = true;
    refresh();
    const result = await endStory(hooks.client, hooks.schema, project).done;
    mine = false;
    if (hooks.getProject() !== project) return;
    if (result.reason) { hooks.notice(STRINGS.reasons[result.reason] ?? result.reason, "notice-bad"); hooks.redraw(); return; }
    if (!result.ok) { hooks.notice(hooks.errorText(result.error), result.error.kind === "stopped" ? "" : "notice-bad"); refresh(); return; }
    const previous = project.after_story ? copy(project.after_story) : null;
    const previousNote = copyEndNote(project);
    project.after_story = result.after;
    reviews = new Map();
    setEndNote(project, {
      forced: result.forced, dropped: result.dropped, problems: afterStoryProblems(hooks.schema, project, result.after),
      madeFrom: chaptersFingerprint(project),
    });
    hooks.notice(STRINGS.done, "", {
      label: STRINGS.undo,
      run: () => {
        if (hooks.getProject() !== project) return;
        if (previous) project.after_story = previous; else delete project.after_story;
        putEndNote(project, previousNote);
        hooks.changed();
        hooks.redraw();
        hooks.notice(STRINGS.undone);
      },
    });
    hooks.changed();
    hooks.redraw();
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
      parts.push(node("ul", { className: "after-changes" }, ...changes.map((c) => node("li", {
        textContent: c.kind === "added"
          ? fill(STRINGS.added, { who: who(c), label: c.label, after: c.after })
          : fill(STRINGS.changed, { who: who(c), label: c.label, before: c.before || "–", after: c.after || "–" }),
      }))));
    }
    if (note?.forced.length) {
      const what = joinList(note.forced.map((f) => fill(STRINGS.forcedOf, { fields: joinList(f.fields), character: f.character })), "semicolon");
      parts.push(node("p", { className: "help", textContent: fill(STRINGS.kept, { what }) }));
    }
    if (note?.dropped.length) parts.push(node("p", { className: "help", textContent: fill(STRINGS.dropped, { fields: joinList(note.dropped) }) }));
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
    ];
    const body = node("div", { className: "after-edit-body" }, node("p", { className: "help", textContent: STRINGS.editHelp }));
    for (const [label, cardId, values, key] of sections) {
      if (!values) continue;
      if (!reviews.has(key)) reviews.set(key, { touched: new Set(), validated: false });
      const holder = node("div", { className: "after-edit-card" });
      const inside = node("details", { className: "after-edit-item" }, node("summary", { textContent: label }), holder);
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
    return node("details", { className: "after-edit" }, node("summary", { textContent: STRINGS.editTitle }), body);
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
    status = null;
    if (!project) return;
    const panel = node("section", { className: "end-panel" }, node("h3", { textContent: STRINGS.title }));
    (container.querySelector(".generate-panel")?.after(panel) ?? container.append(panel));
    const gate = endGate(project);
    if (!gate.ok) { panel.append(node("p", { className: "help", textContent: STRINGS.notDone })); return; }
    panel.append(node("p", { className: "help", textContent: STRINGS.help }));
    button = node("button", { type: "button", className: "validate", textContent: gate.replaces ? STRINGS.buttonAgain : STRINGS.button });
    button.addEventListener("click", () => press(project, gate.replaces));
    status = node("span", { className: "note", textContent: "" });
    panel.append(node("div", { className: "plan-actions" }, button, status),
      node("p", { className: "note", textContent: fill(STRINGS.sends, { where: hooks.backendWhere() }) }));
    if (project.after_story) panel.append(review(project));
    refresh();
  }

  return { draw, refresh, reset() { button = null; status = null; mine = false; reviews = new Map(); } };
}
