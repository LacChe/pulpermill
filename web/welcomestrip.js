// The welcome strip: a short guide above the cards for someone who has never used the page. Words only. It says what the page does,
// in two phases (Design the cards, then Write the chapters) with the one the writer is in open, and it says so when the page is
// using the built-in sample model. Once a chapter is written it shrinks to one line. It can be hidden, and the choice is remembered
// in this browser (and only there). It never calls the model and never changes the project.
import { welcomePhases } from "./welcome.js";
import { section, fill } from "./text.js";

export const HIDE_KEY = "pulpermill.welcome.hidden";

export const STRINGS = section("welcome");

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

const remembered = {
  get() { try { return localStorage.getItem(HIDE_KEY) === "1"; } catch { return false; } },
  set(hidden) { try { if (hidden) localStorage.setItem(HIDE_KEY, "1"); else localStorage.removeItem(HIDE_KEY); } catch { /* the choice is just not remembered */ } },
};

// hooks: {schema, getProject, usingSample(), goTo(cardId, instanceId), goToWrite(), shownChanged(isShown)}. `root` is the element the
// strip is drawn into. Returns {draw, toggle, isHidden}.
export function createWelcomeStrip(root, hooks) {
  let hidden = remembered.get();
  let full = false;                    // the writer asked for the whole guide after it shrank

  const goWrite = (label) => {
    const go = node("button", { type: "button", className: "welcome-go", textContent: label });
    go.addEventListener("click", () => hooks.goToWrite());
    return go;
  };

  // The button that takes the writer to where the next step is done.
  function designGo(facts) {
    if (facts.canStart) return goWrite(STRINGS.startGo);
    const stop = facts.stop;
    if (!stop) return null;
    const card = hooks.schema.cards[stop.card];
    const project = hooks.getProject();
    const label = stop.card === "characters" && !stop.id && !(project.characters ?? []).length ? STRINGS.noCharacter
      : stop.name ? fill(STRINGS.cardsGoPerson, { card: card.label, name: stop.name }) : fill(STRINGS.cardsGo, { card: card.label });
    const go = node("button", { type: "button", className: "welcome-go", textContent: label });
    go.addEventListener("click", () => hooks.goTo(stop.card, stop.id));
    return go;
  }

  // The five cards as small buttons, each saying whether anything on it still stops the story.
  function cardChips(facts) {
    const items = facts.cards.map((card) => {
      const name = hooks.schema.cards[card.id].label;
      const chip = node("button", { type: "button", className: `welcome-card ${card.ready ? "welcome-card-ready" : "welcome-card-fix"}` },
        node("span", { className: "welcome-card-head" }, node("span", { className: "welcome-card-name", textContent: name }),
          node("span", { className: "tag", textContent: card.ready ? STRINGS.cardReady : STRINGS.cardFix })),
        node("span", { className: "note", textContent: STRINGS.cards[card.id] }));
      chip.addEventListener("click", () => hooks.goTo(card.id, card.stopId));
      return node("li", {}, chip);
    });
    return node("ul", { className: "welcome-cards" }, ...items);
  }

  function designBody(facts) {
    const body = [node("p", { className: "help", textContent: STRINGS.design.detail }), cardChips(facts),
      node("p", { className: "help", textContent: STRINGS.design.hinge })];
    const go = designGo(facts);
    if (go) body.push(go);
    return body;
  }

  function writeBody(facts) {
    const body = [node("p", { className: "help", textContent: STRINGS.write.detail }),
      node("p", { className: "welcome-way" }, node("strong", { textContent: `${STRINGS.write.allLead} ` }), STRINGS.write.allText),
      node("p", { className: "welcome-way" }, node("strong", { textContent: `${STRINGS.write.eachLead} ` }), STRINGS.write.eachText),
      node("p", { className: "help", textContent: STRINGS.write.fixed })];
    if (facts.allWritten) body.push(node("p", { className: "help", textContent: STRINGS.write.finished }));
    else body.push(goWrite(STRINGS.writeGo));
    return body;
  }

  function draw() {
    const project = hooks.getProject();
    hooks.shownChanged?.(!hidden);
    root.hidden = hidden || !project;
    if (root.hidden) { root.replaceChildren(); return; }
    const facts = welcomePhases(hooks.schema, project);
    const hide = node("button", { type: "button", className: "welcome-hide", textContent: STRINGS.hide });
    hide.addEventListener("click", () => { hidden = true; remembered.set(true); draw(); });
    const head = node("div", { className: "welcome-head" }, node("h2", { textContent: STRINGS.title }), hide);
    const sample = hooks.usingSample?.() ? node("p", { className: "welcome-sample", textContent: STRINGS.sample }) : null;

    // Once a chapter is written the writer knows the page: one line, with the way back to the whole guide.
    if (facts.started && facts.written > 0 && !full) {
      const line = facts.allWritten ? STRINGS.compactDone : fill(STRINGS.compact, { n: facts.written + 1, count: facts.count });
      const more = node("button", { type: "button", className: "welcome-more", textContent: STRINGS.showFull });
      more.addEventListener("click", () => { full = true; draw(); });
      root.replaceChildren(head, ...(sample ? [sample] : []), node("div", { className: "welcome-line" }, node("span", { textContent: line }),
        ...(facts.allWritten ? [] : [goWrite(STRINGS.writeGo)]), more));
      return;
    }

    const list = node("ol", { className: "welcome-phases" });
    for (const phase of facts.phases) {
      const words = STRINGS[phase.id];
      const item = node("li", { className: `welcome-phase welcome-phase-${phase.state}` }, node("div", { className: "welcome-phase-head" },
        node("span", { className: "welcome-phase-title", textContent: words.title }),
        node("span", { className: `tag welcome-state welcome-${phase.state}`, textContent: STRINGS.states[phase.state] })));
      if (phase.state === "next" || (phase.id === "write" && phase.state === "done")) item.append(...(phase.id === "design" ? designBody(facts) : writeBody(facts)));
      list.append(item);
    }
    const parts = [head, ...(sample ? [sample] : []), node("p", { className: "welcome-intro", textContent: STRINGS.intro }), list,
      node("p", { className: "note", textContent: STRINGS.save })];
    if (full && facts.started && facts.written > 0) {
      const less = node("button", { type: "button", className: "welcome-more", textContent: STRINGS.showLess });
      less.addEventListener("click", () => { full = false; draw(); });
      parts.push(less);
    }
    root.replaceChildren(...parts);
  }

  // The Guide button in the header: shows the strip again, or hides it.
  function toggle() {
    hidden = !hidden;
    remembered.set(hidden);
    if (!hidden) full = true;            // asking for the guide means the whole guide
    draw();
    return !hidden;
  }

  return { draw, toggle, isHidden: () => hidden };
}
