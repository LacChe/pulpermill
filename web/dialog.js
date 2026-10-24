// An in-page question: ask(message) shows a dialog over the page and answers true (Continue) or false (Cancel, Escape, or a click
// outside). It replaces the browser's own confirm box, whose look and words the page cannot control. All words come from the
// bundle (section "dialog"); the question itself is passed in already worded.
//
// One question at a time: asking while one is open waits for the first to be answered.

import { section } from "./text.js";

const STRINGS = section("dialog");

let waiting = Promise.resolve();

export function ask(message) {
  const turn = waiting.then(() => show(message));
  waiting = turn.catch(() => {});
  return turn;
}

function show(message) {
  return new Promise((resolve) => {
    const box = document.createElement("dialog");
    box.className = "ask";
    const words = document.createElement("p");
    words.className = "ask-words";
    words.textContent = message;
    const row = document.createElement("div");
    row.className = "ask-buttons";
    const no = Object.assign(document.createElement("button"), { type: "button", textContent: STRINGS.cancel });
    const yes = Object.assign(document.createElement("button"), { type: "button", textContent: STRINGS.ok, className: "validate" });
    row.append(no, yes);
    box.append(words, row);

    let answer = false;
    yes.addEventListener("click", () => { answer = true; box.close(); });
    no.addEventListener("click", () => box.close());
    // A click on the backdrop lands on the dialog itself, not on anything inside it.
    box.addEventListener("click", (event) => { if (event.target === box) box.close(); });
    box.addEventListener("close", () => { box.remove(); resolve(answer); });   // Escape closes it too, as a Cancel

    document.body.append(box);
    box.showModal();
    no.focus();      // the safe answer is the one Enter gives
  });
}
