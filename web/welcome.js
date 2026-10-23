// Where the writer is on the way from a blank page to a finished story, worked out from the project alone. No DOM, so Node can
// test it. The welcome strip (welcomestrip.js) draws it; nothing here calls a model or changes the project.
//
// The way has five steps. The first three come one after another, and the first one not yet done is the "next" step. The
// last two (ending the story, and downloading the work) are open once every chapter is written. A step is one of:
//   done   it has been done
//   next   it is the one to do now
//   later  it is not open yet
import { startGate, storyStarted } from "./gate.js";
import { chapterInfo } from "./plan.js";

export const STEP_IDS = ["cards", "start", "chapters", "end", "download"];

// [{id, state, ...}] in the order above. Extra facts, only where they help the strip say something useful:
//   cards     {stop}: the first card (or character) the story cannot start from yet: {card, id, name} or null
//   chapters  {written, count}
export function welcomeSteps(schema, project) {
  const gate = startGate(schema, project);
  const started = storyStarted(project);
  const info = chapterInfo(project);
  const written = info.written;
  const done = {
    cards: started || gate.ok,
    start: started,
    chapters: info.done,
    end: Boolean(project.after_story),
    download: false,
  };
  const open = {
    cards: true,
    start: gate.ok || started,
    chapters: started,
    end: info.done,
    download: written > 0,
  };
  const sequence = ["cards", "start", "chapters"];
  const firstOpen = sequence.find((id) => !done[id]) ?? null;
  const state = (id) => {
    if (done[id]) return "done";
    if (sequence.includes(id)) return id === firstOpen ? "next" : "later";
    return open[id] ? "next" : "later";
  };
  const stop = gate.stops[0] ? { card: gate.stops[0].card, id: gate.stops[0].id, name: gate.stops[0].name } : null;
  return STEP_IDS.map((id) => {
    const step = { id, state: state(id) };
    if (id === "cards") step.stop = stop;
    if (id === "chapters") Object.assign(step, { written, count: info.count });
    return step;
  });
}
