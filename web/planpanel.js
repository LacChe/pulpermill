// The plan panel: shown at the top of the Outline card. The writer picks who is in the chapter, sees what the plan starts
// from (worked out in plan.js), and presses a button; the model thinks and fills the beat, and the beat lands in the
// outline below, where it can be edited like any other. Nothing here calls the model except that one button.
import { storyStarted } from "./gate.js";
import { planChapter } from "./client.js";
import { planNoteFor, setPlanNote, copyNote, putNote, removeNote } from "./modelnotes.js";
import {
  CAST_MAX, castKey, chapterInfo, beatForChapter, castChoices, suggestedCast, castProblem, pickSpotlight, shiftsForChapter, currentGoal,
  openPlants, availableReveals, offstageDue, planIsStale, placeBeat,
} from "./plan.js";

export const STRINGS = {
  title: "Plan the next chapter",
  chapterOf: "Chapter {n} of {total}",
  chapterOnly: "Chapter {n}",
  notStarted: "Start the story first (the bar above). The plan is made from the cards as they will be locked.",
  allDone: "Every chapter is written. Use the end-of-story step when you are ready.",
  noPressure: "Entanglements has no pressure yet, so there is nothing to spotlight. Add one first.",
  castTitle: "Who is in this chapter",
  castHelp: "The protagonist is always in, and up to {max} people can be. The people used least so far are suggested, so everyone gets time.",
  protagonist: "Protagonist, always in",
  suggested: "Suggested",
  usedNone: "not in a chapter yet",
  usedOne: "in 1 chapter, last in chapter {last}",
  usedMany: "in {n} chapters, last in chapter {last}",
  startsFrom: "What the plan starts from",
  spotlight: "Spotlight",
  spotlightNone: "no pressure",
  shifts: "Shift allowed",
  shiftWords: { harder: "harder", easier: "easier" },
  goal: "Current goal",
  goalNone: "none: the goal has ended, so the story winds down",
  plants: "Open plants",
  plantsNone: "none",
  reveals: "Reveals still available",
  offstage: "Offstage change",
  offstageYes: "due: the model first decides what the background groups and places do",
  offstageNo: "not this chapter",
  button: "Plan chapter {n} with the model",
  again: "Plan chapter {n} again",
  working: "The model is planning…",
  sends: "Pressing the button sends the cast, the cards in play and the summaries of earlier chapters to {where}.",
  planned: "Chapter {n} is planned. The beat is below: edit anything you like.",
  retried: "The first try broke a rule, so the model tried again.",
  stillBlocks: "It still has {n} problem(s) that stop generating. They are marked on the beat.",
  unmatched: "The model named {names}, but nothing in your cards matches, so those links were left empty.",
  dropped: "The model gave something that is not a choice here ({fields}), so it was left empty.",
  undo: "Undo",
  undone: "Put the plan back as it was.",
  confirmReplan: "Plan this chapter again? The beat you have now will be replaced. You can undo it afterwards.",
  stale: "The Entanglements have changed since this was planned. Plan it again to use the new state, or write the beat on as it is.",
  thought: "How the model thought about this chapter",
  thoughtKept: "This is kept with your project, and replaced when you plan the chapter again.",
  reasons: {
    not_started: "Start the story first.", done: "Every chapter is written.", no_pressure: "Entanglements has no pressure yet.",
    cast_empty: "Pick who is in the chapter.", cast_too_many: "A chapter has at most {max} people.",
    cast_no_protagonist: "The protagonist has to be in the chapter.", cast_unknown: "Someone in the cast is not there any more.",
  },
};
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);
const copy = (value) => JSON.parse(JSON.stringify(value));

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, client, getProject, backendWhere, changed(), redraw(), notice(text, kind, action), errorText(error)}
export function createPlanPanel(hooks) {
  let selection = null;                 // {project, chapter, ids}: who is ticked, per project and chapter
  let button = null;
  let shownIn = null;                   // the card the panel was last drawn into, so it can be drawn again alone

  // The ticks follow the plan's own Cast field: while the field is as it was, the writer's ticks stand; when it changes (by hand,
  // by an undo, by a new plan) the ticks are taken from it again.
  function chosen(project, chapter, existing) {
    const synced = castKey(existing?.cast);
    if (selection && selection.project === project && selection.chapter === chapter && selection.synced === synced) return selection;
    selection = { project, chapter, synced, ids: new Set(existing?.cast?.length ? existing.cast : suggestedCast(project, chapter)) };
    return selection;
  }

  // Run when the writer leaves a field: if the plan's Cast was changed, draws the panel again (the panel only, so the form keeps its place).
  function sync() {
    const project = hooks.getProject();
    const panel = shownIn?.querySelector(".plan-panel");
    if (!project || !panel || !selection || selection.project !== project) return;
    const existing = beatForChapter(project, selection.chapter);
    if (castKey(existing?.cast) === selection.synced) return;
    panel.remove();
    draw(shownIn);
  }

  const usedText = (c) => (c.uses === 0 ? STRINGS.usedNone : fill(c.uses === 1 ? STRINGS.usedOne : STRINGS.usedMany, { n: c.uses, last: c.last ?? "?" }));

  function refresh() {
    if (!button) return;
    const working = hooks.client.state.working;
    button.disabled = working || button.dataset.blocked === "true";
  }

  function facts(project, ids, chapter) {
    const spotlight = pickSpotlight(project, ids, chapter);
    const goal = currentGoal(project);
    const rows = [
      [STRINGS.spotlight, spotlight?.what ? (spotlight.what.length > 140 ? `${spotlight.what.slice(0, 140)}…` : spotlight.what) : STRINGS.spotlightNone],
      [STRINGS.shifts, shiftsForChapter(project, chapter).map((s) => STRINGS.shiftWords[s]).join(", ")],
      [STRINGS.goal, goal ?? STRINGS.goalNone],
      [STRINGS.plants, String(openPlants(project).length || STRINGS.plantsNone)],
      [STRINGS.reveals, String(availableReveals(project).length)],
      [STRINGS.offstage, offstageDue(chapter) ? STRINGS.offstageYes : STRINGS.offstageNo],
    ];
    return node("dl", { className: "plan-facts" }, ...rows.flatMap(([term, value]) => [node("dt", { textContent: term }), node("dd", { textContent: value })]));
  }

  async function press(project, existing, ids) {
    if (existing && !window.confirm(STRINGS.confirmReplan)) return;
    hooks.notice(STRINGS.working);
    const call = planChapter(hooks.client, hooks.schema, project, [...ids]);
    const result = await call.done;
    if (hooks.getProject() !== project) return;          // another project was opened while the model worked
    if (result.reason) {
      const text = STRINGS.reasons[result.reason] ?? result.reason;
      hooks.notice(fill(text, { max: CAST_MAX }), "notice-bad");
      return;
    }
    if (!result.ok) { hooks.notice(hooks.errorText(result.error), result.error.kind === "stopped" ? "" : "notice-bad"); return; }

    const previous = result.replaces ? copy(result.replaces) : null;
    const previousThought = previous ? copyNote(project, "plan", previous.id) : null;
    placeBeat(project, result.beat);
    setPlanNote(project, result.beat.id, { thinking: result.thinking, retried: result.retried });
    const parts = [fill(STRINGS.planned, { n: result.beat.chapter })];
    if (result.retried) parts.push(STRINGS.retried);
    if (result.blockers.length) parts.push(fill(STRINGS.stillBlocks, { n: result.blockers.length }));
    const words = [...new Set(result.unresolved.map((u) => u.words))];
    if (words.length) parts.push(fill(STRINGS.unmatched, { names: words.map((w) => `“${w}”`).join(", ") }));
    if (result.dropped.length) parts.push(fill(STRINGS.dropped, { fields: result.dropped.join(", ") }));
    hooks.notice(parts.join(" "), result.blockers.length ? "notice-bad" : "", {
      label: STRINGS.undo,
      run: () => {
        if (hooks.getProject() !== project) return;
        if (previous) {
          placeBeat(project, previous);
          putNote(project, "plan", previous.id, previousThought);
        } else {
          project.outline.beats = project.outline.beats.filter((b) => b.id !== result.beat.id);
          removeNote(project, "plan", result.beat.id);
        }
        hooks.changed();
        hooks.redraw();
        hooks.notice(STRINGS.undone);
      },
    });
    hooks.changed();
    hooks.redraw();
  }

  // Draws the panel into the Outline card, under its summary line.
  function draw(container) {
    const project = hooks.getProject();
    button = null;
    shownIn = container;
    if (!project) return;
    const panel = node("section", { className: "plan-panel" }, node("h3", { textContent: STRINGS.title }));
    (container.querySelector(".summary")?.after(panel) ?? container.prepend(panel));
    if (!storyStarted(project)) { panel.append(node("p", { className: "help", textContent: STRINGS.notStarted })); return; }
    const info = chapterInfo(project);
    if (info.done) { panel.append(node("p", { className: "help", textContent: STRINGS.allDone })); return; }
    if (!(project.entanglements?.pressures ?? []).length) { panel.append(node("p", { className: "help", textContent: STRINGS.noPressure })); return; }

    const existing = beatForChapter(project, info.next);
    const pick = chosen(project, info.next, existing);
    panel.append(node("p", { className: "plan-chapter", textContent: fill(info.count ? STRINGS.chapterOf : STRINGS.chapterOnly, { n: info.next, total: info.count }) }));
    if (existing && planIsStale(hooks.schema, project, existing)) panel.append(node("p", { className: "plan-stale", textContent: STRINGS.stale }));

    const factsBox = node("div", { className: "plan-facts-box" });
    const status = node("p", { className: "problem-count has-block", hidden: true });
    const startable = () => {
      const why = castProblem(project, [...pick.ids]);
      status.hidden = !why;
      status.textContent = why ? fill(STRINGS.reasons[`cast_${why}`], { max: CAST_MAX }) : "";
      if (button) { button.dataset.blocked = String(Boolean(why)); refresh(); }
    };
    const drawFacts = () => factsBox.replaceChildren(node("h4", { textContent: STRINGS.startsFrom }), facts(project, [...pick.ids], info.next));

    const choices = castChoices(project, info.next);
    const list = node("div", { className: "plan-cast" });
    const boxes = [];
    for (const c of choices) {
      const box = node("input", { type: "checkbox", checked: pick.ids.has(c.id) || c.protagonist, disabled: c.protagonist });
      if (c.protagonist) pick.ids.add(c.id);
      box.addEventListener("change", () => {
        if (box.checked) pick.ids.add(c.id); else pick.ids.delete(c.id);
        for (const [other, id] of boxes) other.disabled = id !== project.setup?.protagonist && !pick.ids.has(id) && pick.ids.size >= CAST_MAX;
        drawFacts();
        startable();
      });
      boxes.push([box, c.id]);
      const tags = [c.protagonist ? STRINGS.protagonist : null, c.suggested && !c.protagonist ? STRINGS.suggested : null].filter(Boolean);
      list.append(node("label", { className: "plan-person" }, box, node("span", { className: "plan-name", textContent: c.name || "Unnamed" }),
        node("span", { className: "plan-used", textContent: usedText(c) }),
        ...tags.map((t) => node("span", { className: "tag", textContent: t }))));
    }
    panel.append(node("fieldset", { className: "plan-cast-box" }, node("legend", { textContent: STRINGS.castTitle }),
      node("p", { className: "help", textContent: fill(STRINGS.castHelp, { max: CAST_MAX }) }), list), status, factsBox);
    drawFacts();

    button = node("button", { type: "button", className: "validate", textContent: fill(existing ? STRINGS.again : STRINGS.button, { n: info.next }) });
    button.addEventListener("click", () => press(project, existing, pick.ids));
    panel.append(node("div", { className: "plan-actions" }, button,
      node("span", { className: "note", textContent: fill(STRINGS.sends, { where: hooks.backendWhere() }) })));
    startable();

    const thought = existing ? planNoteFor(project, existing.id) : null;
    if (thought) {
      const lines = [node("p", { className: "plan-thinking", textContent: thought.thinking }), node("p", { className: "help", textContent: STRINGS.thoughtKept })];
      if (thought.retried) lines.unshift(node("p", { className: "help", textContent: STRINGS.retried }));
      panel.append(node("details", { className: "plan-thought", open: true }, node("summary", { textContent: STRINGS.thought }), ...lines));
    }
  }

  return { draw, refresh, sync, reset() { selection = null; button = null; shownIn = null; } };
}
