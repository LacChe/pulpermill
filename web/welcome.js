// Where the writer is on the way from a blank page to a finished story, worked out from the project alone. No DOM, so Node can
// test it. The welcome strip (welcomestrip.js) draws it; nothing here calls a model or changes the project.
//
// The way has two phases. Design is the cards. Starting the story moves the writer on to Write: planning and writing the chapters.
// A phase is one of:
//   done   it has been done
//   next   it is the one the writer is in
//   later  it is not open yet
import { startGate, storyStarted, STATIC_CARDS } from "./gate.js";
import { chapterInfo } from "./plan.js";

export const PHASE_IDS = ["design", "write"];

// {phases, cards, stop, canStart, started, written, count, allWritten, finished}
//   phases      [{id, state}] in the order above
//   cards       [{id, ready, stopId}] for the five cards the story starts from: ready means nothing on it stops the story yet;
//               stopId is the character that stops it, for the Characters card
//   stop        the first card (or character) the story cannot start from yet: {card, id, name}, or null
//   canStart    every card is sound and the story has not started
//   written, count   chapters written, and the chapter count the Setup card holds (0 before it is set)
//   allWritten  every chapter is written
//   finished    the story was finished (the after-story copy exists)
export function welcomePhases(schema, project) {
  const gate = startGate(schema, project);
  const started = storyStarted(project);
  const info = chapterInfo(project);
  const phases = [
    { id: "design", state: started ? "done" : "next" },
    { id: "write", state: !started ? "later" : info.done ? "done" : "next" },
  ];
  const cards = STATIC_CARDS.map((id) => {
    const stop = gate.stops.find((s) => s.card === id);
    return { id, ready: !stop, stopId: stop?.id ?? null };
  });
  const first = gate.stops[0];
  return {
    phases, cards,
    stop: first ? { card: first.card, id: first.id, name: first.name } : null,
    canStart: gate.ok && !started,
    started, written: info.written, count: info.count, allWritten: info.done, finished: Boolean(project.after_story),
  };
}
