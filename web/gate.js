// The story-start gate and the card locks. No DOM, so Node can test it.
//
// Starting the story locks Style, Characters, World and Setup: from then on only the live fields of Entanglements and
// each chapter's plan change. A lock is an entry in the project's `locks` list, so the project file says what is
// locked and the backend reads the same thing. A card is locked by a lock that names the card and nothing narrower.
//
// Two kinds of whole-card lock, told apart by `by`: the story's own (no `by`), which starting the story sets on the four
// static cards, and the writer's (`by: "writer"`), which the lock button on any of the six cards sets so nothing is changed
// by accident. Either one makes the card read-only. The story has started when all four static cards carry the story's lock,
// so locking cards by hand never starts it.
//
// Before the lock, the gate asks two things. The first is code: every card must be free of blocking problems.
// The second is the model's (the style-fit check, in client.js), and it is only an opinion: the writer can go on anyway.

import { newId, settledProject, validate, instanceName } from "./logic.js";

// Fixed once the story starts.
export const STATIC_CARDS = ["style", "characters", "world", "setup"];
// Every card the gate checks. Entanglements stays editable, but it has to be sound when the story starts.
export const GATE_CARDS = ["style", "characters", "world", "entanglements", "setup"];

export const WRITER = "writer";

const wholeCard = (lock, cardId) => lock.card === cardId && !lock.owner && !lock.field && !lock.item && !lock.part;
const storyLock = (lock, cardId) => wholeCard(lock, cardId) && lock.by !== WRITER;
const writerLock = (lock, cardId) => wholeCard(lock, cardId) && lock.by === WRITER;

// Locked by anyone: the story or the writer.
export function cardLocked(project, cardId) {
  return (project.locks ?? []).some((lock) => wholeCard(lock, cardId));
}

export const lockedByStory = (project, cardId) => (project.locks ?? []).some((lock) => storyLock(lock, cardId));
export const lockedByWriter = (project, cardId) => (project.locks ?? []).some((lock) => writerLock(lock, cardId));

export function storyStarted(project) {
  return STATIC_CARDS.every((id) => lockedByStory(project, id));
}

// The writer's lock button: locks a card, or takes the writer's own lock off it. Never touches the story's lock.
export function setWriterLock(project, cardId, on) {
  const locks = project.locks ?? (project.locks = []);
  if (on) {
    if (!lockedByWriter(project, cardId)) locks.push({ id: newId(locks.map((l) => l.id)), card: cardId, by: WRITER });
  } else {
    project.locks = locks.filter((lock) => !writerLock(lock, cardId));
  }
  return project;
}

// Adds the story's lock to each static card that has none. Locks the writer set by hand stay as they are.
export function lockStaticCards(project) {
  const locks = project.locks ?? (project.locks = []);
  for (const card of STATIC_CARDS) {
    if (!lockedByStory(project, card)) locks.push({ id: newId(locks.map((l) => l.id)), card });
  }
  return project;
}

// Takes the story's locks off the static cards. Locks the writer set (whole-card or narrower) stay.
export function unlockStaticCards(project) {
  project.locks = (project.locks ?? []).filter((lock) => !STATIC_CARDS.some((card) => storyLock(lock, card)));
  return project;
}

// Unlocking is for before the first chapter. Once a chapter is written it was written from these cards.
export function canUnlock(project) {
  return (project.chapters ?? []).length === 0;
}

// Can the story start? {ok, stops}. Each stop is one card (or one character) that still has blocking problems:
// {card, id, name, count, problems: [{message, fix}]}. A project with no characters stops on Characters with no problems
// listed, since there is nothing to fix there but to add one.
export function startGate(schema, project) {
  const settled = settledProject(schema, project);
  const stops = [];
  for (const cardId of GATE_CARDS) {
    const card = schema.cards[cardId];
    const list = card.many_per_project ? settled[cardId] : [settled[cardId]];
    if (card.many_per_project && !list.length) stops.push({ card: cardId, id: null, name: null, count: 0, problems: [] });
    for (const values of list) {
      const blocking = validate(card, values, settled, schema.common).problems.filter((p) => p.severity === "block");
      if (!blocking.length) continue;
      stops.push({
        card: cardId, id: card.many_per_project ? values.id : null, name: card.many_per_project ? instanceName(values) : null,
        count: blocking.length, problems: blocking.map((p) => ({ message: p.message, fix: p.fix })),
      });
    }
  }
  return { ok: stops.length === 0, stops };
}
