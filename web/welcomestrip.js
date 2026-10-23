// The welcome strip: a short guide above the cards for someone who has never used the page. Words only. It says what the page
// does, shows the way from a blank page to a finished story with the step to do now marked, and says what to know about the
// model and the project file. It can be hidden, and the choice is remembered in this browser (and only there). It never calls
// the model and never changes the project.
import { welcomeSteps } from "./welcome.js";

export const HIDE_KEY = "pulpermill.welcome.hidden";

export const STRINGS = {
  title: "Welcome to Pulpermill",
  intro: "You write the story. The model drafts the parts you ask it for, and you decide what stays.",
  way: "The way from a blank page to a finished story",
  steps: {
    cards: {
      title: "Fill in the cards",
      detail: "Style, Characters, World, Entanglements and Setup describe your story. Fill them in yourself, or write a note on a card and press Fill to have the model draft it. Start with whichever you know best.",
    },
    start: {
      title: "Start the story",
      detail: "When the cards have nothing that stops the story, press Start the story. That locks Style, Characters, World and Setup, so every chapter is written from the same foundations.",
    },
    chapters: {
      title: "Plan and write each chapter",
      detail: "On the Outline card the model plans a chapter, you change the plan as you like, and then the model writes it. Plans and rewrites can be undone.",
    },
    end: {
      title: "End the story (optional)",
      detail: "The model updates the characters and the world to show how the story changed them. The result is a separate copy you can edit. Your cards stay as they are.",
    },
    download: {
      title: "Download your work",
      detail: "At the bottom of the Outline card, Export gives you the story as a text file and your cards as files you can bring into another project.",
    },
  },
  cardsGo: "Next: {card}",
  cardsGoPerson: "Next: {card}, {name}",
  noCharacter: "Add a character",
  chaptersCount: "{written} of {count} written",
  chaptersOnly: "{written} written",
  states: { done: "done", next: "do this now", later: "later" },
  know: "Good to know",
  knowItems: [
    "Nothing happens by itself. The model works only when you press a button, one job at a time, and Stop ends it.",
    "What the model writes is shown to you and can be changed. Its drafts are marked until you edit them.",
    "Save downloads your project as a file. That file is your story and your cards, so keep it somewhere safe. This page keeps only a short-term safety copy in this browser.",
    "Until you give a model connection, the page uses a built-in sample model that writes placeholder text, so you can try everything first.",
  ],
  hide: "Hide this guide",
};
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => values[key]);

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

const remembered = {
  get() { try { return localStorage.getItem(HIDE_KEY) === "1"; } catch { return false; } },
  set(hidden) { try { if (hidden) localStorage.setItem(HIDE_KEY, "1"); else localStorage.removeItem(HIDE_KEY); } catch { /* the choice is just not remembered */ } },
};

// hooks: {schema, getProject, goTo(cardId, instanceId), shownChanged(isShown)}. `root` is the element the strip is drawn into. Returns {draw, toggle, isHidden}.
export function createWelcomeStrip(root, hooks) {
  let hidden = remembered.get();
  let knowOpen = false;                 // kept across redraws, so reading it is not interrupted

  function draw() {
    const project = hooks.getProject();
    hooks.shownChanged?.(!hidden);
    root.hidden = hidden || !project;
    if (root.hidden) { root.replaceChildren(); return; }
    const steps = welcomeSteps(hooks.schema, project);
    const hide = node("button", { type: "button", className: "welcome-hide", textContent: STRINGS.hide });
    hide.addEventListener("click", () => { hidden = true; remembered.set(true); draw(); });

    const list = node("ol", { className: "welcome-steps" });
    for (const step of steps) {
      const words = STRINGS.steps[step.id];
      const parts = [node("span", { className: "welcome-step-title", textContent: words.title }), node("span", { className: `tag welcome-state welcome-${step.state}`, textContent: STRINGS.states[step.state] })];
      if (step.id === "chapters" && step.written) {
        parts.push(node("span", { className: "note", textContent: fill(step.count ? STRINGS.chaptersCount : STRINGS.chaptersOnly, { written: step.written, count: step.count }) }));
      }
      const item = node("li", { className: `welcome-step welcome-step-${step.state}` }, node("div", { className: "welcome-step-head" }, ...parts));
      if (step.state === "next") {
        item.append(node("p", { className: "help", textContent: words.detail }));
        const go = goButton(step, project);
        if (go) item.append(go);
      }
      list.append(item);
    }

    const know = node("details", { className: "welcome-know", open: knowOpen }, node("summary", { textContent: STRINGS.know }),
      node("ul", {}, ...STRINGS.knowItems.map((text) => node("li", { textContent: text }))));
    know.addEventListener("toggle", () => { knowOpen = know.open; });
    root.replaceChildren(node("div", { className: "welcome-head" }, node("h2", { textContent: STRINGS.title }), hide),
      node("p", { className: "welcome-intro", textContent: STRINGS.intro }), node("h3", { textContent: STRINGS.way }), list, know);
  }

  // A button that takes the writer to where the next step is done.
  function goButton(step, project) {
    let label = null;
    let target = null;
    if (step.id === "cards" && step.stop) {
      const card = hooks.schema.cards[step.stop.card];
      if (step.stop.card === "characters" && !step.stop.id && !(project.characters ?? []).length) label = STRINGS.noCharacter;
      else label = step.stop.name ? fill(STRINGS.cardsGoPerson, { card: card.label, name: step.stop.name }) : fill(STRINGS.cardsGo, { card: card.label });
      target = [step.stop.card, step.stop.id];
    } else if (step.id === "chapters" || step.id === "end" || step.id === "download") {
      label = hooks.schema.cards.outline.label;
      target = ["outline", null];
    }
    if (!label) return null;
    const go = node("button", { type: "button", className: "welcome-go", textContent: label });
    go.addEventListener("click", () => hooks.goTo(target[0], target[1]));
    return go;
  }

  // The Guide button in the header: shows the strip again, or hides it.
  function toggle() {
    hidden = !hidden;
    remembered.set(hidden);
    draw();
    return !hidden;
  }

  return { draw, toggle, isHidden: () => hidden };
}
