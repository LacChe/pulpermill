// The story bar: where the writer starts the story, and sees which cards are locked.
// Starting is a button press. It runs the code gate first (no model), then asks the model whether the protagonist suits
// the voice (the style-fit check, an opinion the writer may overrule), then locks the five static cards: Style, Characters, World,
// Entanglements and Setup (P0, A12). Once started the bar lists all five as locked and the Outline as open.
import { startGate, lockStaticCards, unlockStaticCards, storyStarted, canUnlock, STATIC_CARDS } from "./gate.js";
import { checkStyleFit } from "./client.js";
import { errorText } from "./render.js";
import { section, fill } from "./text.js";

const LABELS = section("labels");
import { ask } from "./dialog.js";

export const STRINGS = section("story");

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, getProject, client, goTo(cardId, instanceId), changed(), notice(text, kind), redraw()}
export function createStoryBar(root, hooks) {
  let message = null;       // {text, stops} left by the last press, until something changes

  async function press() {
    const { schema, client } = hooks;
    const project = hooks.getProject();
    message = null;
    const gate = startGate(schema, project);
    if (!gate.ok) { message = { text: STRINGS.fixFirst, stops: gate.stops }; draw(); return; }
    if (!project.setup?.protagonist) { hooks.notice(STRINGS.noProtagonist, "notice-bad"); return; }
    draw(true);
    const result = await checkStyleFit(client, schema, project).done;
    if (hooks.getProject() !== project) return;      // another project was opened while the model worked
    if (result.reason) { hooks.notice(STRINGS.noProtagonist, "notice-bad"); draw(); return; }
    if (!result.ok) { hooks.notice(errorText(result.error), result.error.kind === "stopped" ? "" : "notice-bad"); draw(); return; }
    if (!result.fits) {
      const question = result.message ? fill(STRINGS.misfit, { message: result.message }) : STRINGS.misfitBare;
      if (!(await ask(question))) { draw(); return; }
    }
    lockStaticCards(project);
    hooks.notice(STRINGS.begun);
    hooks.changed();
    hooks.redraw();
  }

  async function unlock() {
    if (!(await ask(STRINGS.confirmUnlock))) return;
    unlockStaticCards(hooks.getProject());
    message = null;
    hooks.notice(STRINGS.unlocked);
    hooks.changed();
    hooks.redraw();
  }

  function stopList(stops) {
    const { schema } = hooks;
    return node("ul", { className: "story-stops" }, ...stops.map((stop) => {
      const label = schema.cards[stop.card].label;
      const text = stop.count === 0 ? fill(STRINGS.stopNone, { card: label })
        : stop.name ? fill(STRINGS.stopOne, { card: label, name: stop.name, n: stop.count })
        : fill(STRINGS.stop, { card: label, n: stop.count });
      const go = node("button", { type: "button", textContent: text });
      go.addEventListener("click", () => hooks.goTo(stop.card, stop.id));
      return node("li", {}, go);
    }));
  }

  // The five static cards, each marked locked, and the Outline, marked open.
  function stateList() {
    const { schema } = hooks;
    const row = (id, locked) => node("li", { className: locked ? "story-card is-locked" : "story-card is-open" },
      node("span", { className: "story-mark", textContent: locked ? LABELS.lockMark : LABELS.unlockMark, ariaHidden: "true" }),
      node("span", { className: "story-card-name", textContent: LABELS.tabNames[id] ?? schema.cards[id].label }),
      node("span", { className: "tag", textContent: locked ? STRINGS.lockedTag : STRINGS.openTag }));
    return node("ul", { className: "story-cards" }, ...STATIC_CARDS.map((id) => row(id, true)), row("outline", false));
  }

  function draw(checking = false) {
    const project = hooks.getProject();
    if (!project) return;
    if (storyStarted(project)) {
      const free = canUnlock(project);
      const parts = [node("p", { textContent: free ? STRINGS.started : STRINGS.startedKept }), stateList()];
      if (free) {
        const undo = node("button", { type: "button", textContent: STRINGS.unlock });
        undo.addEventListener("click", unlock);
        parts.push(undo);
      }
      root.className = "story-bar story-started";
      root.replaceChildren(...parts);
      return;
    }
    const begin = node("button", { type: "button", className: "validate", textContent: STRINGS.start, disabled: checking || hooks.client.state.working });
    begin.addEventListener("click", press);
    const parts = [node("p", { textContent: checking ? STRINGS.checking : STRINGS.intro }), begin];
    if (message) parts.push(node("p", { className: "story-fix", textContent: message.text }), stopList(message.stops));
    root.className = "story-bar";
    root.replaceChildren(...parts);
  }

  return { draw: () => draw(false), STATIC_CARDS };
}
