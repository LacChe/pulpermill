// The plan panel: shown at the top of the Outline card. The chapter is about one tie (the spotlight): code picks it at random, and
// the writer may pick another. The cast always holds the protagonist and the characters at the two ends of that tie, and the writer
// may add others up to CAST_MAX. The panel shows what will be sent (the spotlight and the ties among the cast), and one button asks
// the model to plan the chapter; the beat lands in the Outline below, where it can be edited like any other. Nothing here calls the
// model except that one button. The rules and the picks are worked out in plan.js; this file only draws them.
import { storyStarted, cardLocked } from "./gate.js";
import { planChapter } from "./client.js";
import {
  CAST_MAX, castKey, chapterInfo, beatForChapter, newBeat, requiredCast, tiesInPlay, tieInWords, withSpotlight, castProblem,
  planIsStale, commitPlan,
} from "./plan.js";
import { effectiveProject } from "./effective.js";
import { stageText, instanceName } from "./logic.js";
import { section, fill, msg, joinList } from "./text.js";
import { ask } from "./dialog.js";
import { elapsedTag } from "./elapsed.js";

export const STRINGS = section("plan");

// The Outline rule whose wording explains each way a cast can be wrong (P1 wrote them; the panel does not word them again).
const CAST_RULES = { no_protagonist: "cast_has_protagonist", spotlight_pair: "spotlight_pair_in_cast" };

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, client, getProject, backendWhere, changed(), redraw(), notice(text, kind, action), errorText(error)}
export function createPlanPanel(hooks) {
  let draft = null;                     // {project, chapter, beat}: the beat for the next chapter until it is planned (nothing is added to the Outline before)
  let button = null;
  let stageLine = null;
  let mine = false;                     // this panel pressed the button and is waiting
  let tag = null;                       // the seconds beside the button
  let shownIn = null;                   // the card the panel was last drawn into, so it can be drawn again alone
  let shownKey = null;                  // what the panel was drawn from, so a change made in the Outline form is noticed

  // The beat the panel works on: the planned one in the Outline, or a draft made when there is none yet.
  function working(project, chapter) {
    const existing = beatForChapter(project, chapter);
    if (existing) return { beat: existing, existing };
    if (!draft || draft.project !== project || draft.chapter !== chapter) draft = { project, chapter, beat: newBeat(hooks.schema, project, chapter) };
    return { beat: draft.beat, existing: null };
  }

  const keyOf = (beat, stale) => `${beat.spotlight}|${castKey(beat.cast)}|${stale}`;

  // Run when the writer leaves a field: if the beat's Spotlight or Cast was changed in the Outline form, draws the panel again
  // (the panel only, so the form keeps its place).
  function sync() {
    const project = hooks.getProject();
    const panel = shownIn?.querySelector(".plan-panel");
    if (!project || !panel || shownKey === null) return;
    const info = chapterInfo(project);
    const existing = beatForChapter(project, info.next);
    if (!existing || keyOf(existing, planIsStale(project, existing)) === shownKey) return;
    panel.remove();
    draw(shownIn);
  }

  function refresh() {
    const { working: busy, stage } = hooks.client.state;
    if (button) button.disabled = busy || button.dataset.blocked === "true";
    if (stageLine) stageLine.textContent = busy && mine ? stageText(stage) || STRINGS.working : "";
    tag?.update();
  }

  // Changes the beat's spotlight and cast: in the Outline when the beat is planned (the form below then shows it), else in the draft.
  function setBeat(project, chapter, change) {
    const { beat, existing } = working(project, chapter);
    Object.assign(beat, change);
    if (existing) hooks.changed();
    hooks.redraw();
  }

  async function press(project, chapter) {
    const { beat, existing } = working(project, chapter);
    if (existing?.plan && !(await ask(STRINGS.confirmReplan))) return;
    hooks.notice(STRINGS.working);
    const call = planChapter(hooks.client, hooks.schema, project, beat);
    mine = true;
    refresh();
    const result = await call.done;
    mine = false;
    refresh();
    if (hooks.getProject() !== project) return;          // another project was opened while the model worked
    if (result.reason) {
      const text = STRINGS.reasons[result.reason] ?? result.reason;
      hooks.notice(fill(text, { max: CAST_MAX }), "notice-bad");
      return;
    }
    if (!result.ok) { hooks.notice(hooks.errorText(result.error), result.error.kind === "stopped" ? "" : "notice-bad"); return; }

    const placed = commitPlan(project, result.beat);
    draft = null;
    const parts = [fill(STRINGS.planned, { n: result.beat.chapter })];
    if (result.retried) parts.push(STRINGS.retried);
    if (result.blockers.length) parts.push(fill(STRINGS.stillBlocks, { n: result.blockers.length }));
    const words = [...new Set(result.unresolved.map((u) => u.words))];
    if (words.length) parts.push(fill(STRINGS.unmatched, { names: joinList(words.map((w) => msg("common.quoted", { text: w }))) }));
    if (result.dropped.length) parts.push(fill(STRINGS.dropped, { fields: joinList(result.dropped) }));
    for (const warning of result.warnings ?? []) parts.push(warning);
    hooks.notice(joinList(parts, "sentence"), result.blockers.length ? "notice-bad" : "", {
      label: STRINGS.undo,
      run: () => {
        if (hooks.getProject() !== project) return;
        if (!placed.undo()) { hooks.notice(STRINGS.undoBlocked, "notice-bad"); return; }   // the plan was changed since
        hooks.changed();
        hooks.redraw();
        hooks.notice(STRINGS.undone);
      },
    });
    hooks.changed();
    hooks.redraw();
  }

  // Draws the panel into the planning column.
  function draw(container) {
    const project = hooks.getProject();
    button = null;
    stageLine = null;
    tag = null;
    shownIn = container;
    shownKey = null;
    if (!project) return;
    const panel = node("section", { className: "plan-panel" }, node("h3", { textContent: STRINGS.title }));
    container.append(panel);
    if (!storyStarted(project)) { panel.append(node("p", { className: "help", textContent: STRINGS.notStarted })); return; }
    const info = chapterInfo(project);
    if (info.done) { panel.append(node("p", { className: "help", textContent: STRINGS.allDone })); return; }
    if (cardLocked(project, "outline")) { panel.append(node("p", { className: "help", textContent: STRINGS.reasons.outline_locked })); return; }
    const chapter = info.next;
    const eff = effectiveProject(project, chapter);
    const allTies = eff.entanglements?.ties ?? [];
    if (!allTies.length) { panel.append(node("p", { className: "help", textContent: STRINGS.noTies })); return; }

    const { beat, existing } = working(project, chapter);
    const stale = Boolean(existing && planIsStale(project, existing));
    shownKey = keyOf(beat, stale);
    panel.append(node("p", { className: "plan-chapter", textContent: fill(info.count ? STRINGS.chapterOf : STRINGS.chapterOnly, { n: chapter, total: info.count }) }));
    if (stale) panel.append(node("p", { className: "plan-stale", textContent: STRINGS.stale }));

    // The spotlight: the tie in words, and a list of every tie to pick another from.
    const picker = node("select", { className: "text-control", id: "plan-spotlight" },
      ...(allTies.some((t) => t.id === beat.spotlight) ? [] : [node("option", { value: "", textContent: STRINGS.spotlightPick, selected: true })]),
      ...allTies.map((t) => node("option", { value: t.id, textContent: tieInWords(hooks.schema, eff, t).text, selected: t.id === beat.spotlight })));
    picker.addEventListener("change", () => setBeat(project, chapter, withSpotlight(project, beat, picker.value)));
    const spot = allTies.find((t) => t.id === beat.spotlight);
    panel.append(node("fieldset", { className: "plan-spotlight-box" }, node("legend", { textContent: STRINGS.spotlight }),
      node("p", { className: "help", textContent: STRINGS.spotlightHelp }),
      node("p", { className: "plan-tie", textContent: spot ? tieInWords(hooks.schema, eff, spot).text : STRINGS.spotlightNone }),
      node("label", { className: "plan-pick", htmlFor: "plan-spotlight", textContent: STRINGS.spotlightChange }), picker));

    // The cast: the required members are in and marked; the writer adds others up to CAST_MAX.
    const required = requiredCast(eff, beat.spotlight);
    const protagonist = eff.setup?.protagonist;
    const chosen = new Set([...required, ...(beat.cast ?? [])]);
    const list = node("div", { className: "plan-cast" });
    const boxes = [];
    const setCast = () => setBeat(project, chapter, { cast: [...required, ...[...chosen].filter((id) => !required.includes(id))] });
    for (const c of eff.characters ?? []) {
      const must = required.includes(c.id);
      const box = node("input", { type: "checkbox", checked: chosen.has(c.id), disabled: must });
      box.addEventListener("change", () => { if (box.checked) chosen.add(c.id); else chosen.delete(c.id); setCast(); });
      boxes.push([box, c.id]);
      const why = !must ? null : c.id === protagonist ? STRINGS.protagonist : STRINGS.inSpotlight;
      list.append(node("label", { className: "plan-person" }, box, node("span", { className: "plan-name", textContent: instanceName(c) || STRINGS.unnamed }),
        ...(why ? [node("span", { className: "tag", textContent: why })] : [])));
    }
    for (const [box, id] of boxes) if (!chosen.has(id) && chosen.size >= CAST_MAX) box.disabled = true;
    const problem = castProblem(eff, beat.cast, beat.spotlight);
    const status = node("p", { className: "problem-count has-block", hidden: !problem });
    if (problem) {
      const rule = hooks.schema.cards.outline.rules.find((r) => r.id === CAST_RULES[problem]);
      status.textContent = rule ? joinList([rule.message, rule.fix], "sentence") : fill(STRINGS.reasons[`cast_${problem}`], { max: CAST_MAX });
    }
    panel.append(node("fieldset", { className: "plan-cast-box" }, node("legend", { textContent: STRINGS.castTitle }),
      node("p", { className: "help", textContent: fill(STRINGS.castHelp, { max: CAST_MAX }) }), list), status);

    // What will be sent: the ties among the cast and between the cast and a group.
    const sent = tiesInPlay(eff, beat.cast);
    panel.append(node("div", { className: "plan-facts-box" }, node("h4", { textContent: STRINGS.tiesSent }),
      sent.length ? node("ul", { className: "plan-ties" }, ...sent.map((t) => node("li", { textContent: tieInWords(hooks.schema, eff, t).text })))
        : node("p", { className: "help", textContent: STRINGS.tiesNone })));

    button = node("button", { type: "button", className: "validate", textContent: fill(existing?.plan ? STRINGS.again : STRINGS.button, { n: chapter }) });
    button.dataset.blocked = String(Boolean(problem));
    button.addEventListener("click", () => press(project, chapter));
    tag = elapsedTag(hooks.client, () => mine);
    stageLine = node("span", { className: "note", textContent: "" });
    panel.append(node("div", { className: "plan-actions" }, button, tag.node, stageLine),
      node("p", { className: "note", textContent: fill(STRINGS.sends, { where: hooks.backendWhere() }) }));
    refresh();
  }

  return { draw, refresh, sync, reset() { draft = null; button = null; stageLine = null; tag = null; mine = false; shownIn = null; shownKey = null; } };
}
