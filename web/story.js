// The story bar: where the writer starts the story, and sees that the static cards are locked.
// Starting is a button press. It runs the code gate first (no model), then asks the model whether the protagonist suits
// the voice (the style-fit check, an opinion the writer may overrule), then locks Style, Characters, World and Setup.
import { startGate, lockStaticCards, unlockStaticCards, storyStarted, canUnlock, STATIC_CARDS } from "./gate.js";
import { checkStyleFit } from "./client.js";
import { errorText } from "./render.js";

export const STRINGS = {
  intro: "When your cards are ready, start the story. That locks Style, Characters, World and Setup, so they stay as you wrote them while chapters are written. Entanglements and each chapter’s plan stay editable.",
  start: "Start the story",
  checking: "The model is checking that the protagonist suits the voice…",
  fixFirst: "Fix these first. The story can’t start while a card has problems that stop generating.",
  stop: "{card}: {n} to fix",
  stopOne: "{card}, {name}: {n} to fix",
  stopNone: "{card}: add at least one character",
  noProtagonist: "Setup needs a protagonist before the model can check the voice.",
  misfit: "The model thinks the protagonist may not suit the voice you chose:\n\n{message}\n\nStart the story anyway?",
  misfitBare: "The model thinks the protagonist may not suit the voice you chose. Start the story anyway?",
  started: "The story has started. Style, Characters, World and Setup are locked: you can read them, but not change them.",
  startedKept: "The story has started. Style, Characters, World and Setup stay locked for the rest of the story, because chapters are written from them.",
  unlock: "Unlock the cards",
  confirmUnlock: "Unlock Style, Characters, World and Setup so you can edit them? You will need to start the story again.",
  unlocked: "The cards are unlocked. Start the story again when you are ready.",
  begun: "The story has started. Style, Characters, World and Setup are now locked.",
};
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);

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
      const ask = result.message ? fill(STRINGS.misfit, { message: result.message }) : STRINGS.misfitBare;
      if (!window.confirm(ask)) { draw(); return; }
    }
    lockStaticCards(project);
    hooks.notice(STRINGS.begun);
    hooks.changed();
    hooks.redraw();
  }

  function unlock() {
    if (!window.confirm(STRINGS.confirmUnlock)) return;
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

  function draw(checking = false) {
    const project = hooks.getProject();
    if (!project) return;
    if (storyStarted(project)) {
      const free = canUnlock(project);
      const parts = [node("p", { textContent: free ? STRINGS.started : STRINGS.startedKept })];
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
