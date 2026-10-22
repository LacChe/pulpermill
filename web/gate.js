// The story-start gate and the card locks. No DOM, so Node can test it.
//
// Starting the story locks Style, Characters, World and Setup: from then on only the live fields of Entanglements and
// each chapter's plan change. A lock is an entry in the project's `locks` list, so the project file says what is
// locked and the backend reads the same thing. A card is locked by a lock that names the card and nothing narrower.
// The story has started when all four static cards are locked.
//
// Before the lock, the gate asks two things. The first is code: every card must be free of blocking problems.
// The second is the model's (the style-fit check, in client.js), and it is only an opinion: the writer can go on anyway.

import { newId, settledProject, validate, instanceName } from "./logic.js";

// Fixed once the story starts.
export const STATIC_CARDS = ["style", "characters", "world", "setup"];
// Every card the gate checks. Entanglements stays editable, but it has to be sound when the story starts.
export const GATE_CARDS = ["style", "characters", "world", "entanglements", "setup"];

const wholeCard = (lock, cardId) => lock.card === cardId && !lock.owner && !lock.field && !lock.item && !lock.part;

export function cardLocked(project, cardId) {
  return (project.locks ?? []).some((lock) => wholeCard(lock, cardId));
}

export function storyStarted(project) {
  return STATIC_CARDS.every((id) => cardLocked(project, id));
}

// Adds a lock for each static card that has none. Locks the writer set by hand stay as they are.
export function lockStaticCards(project) {
  const locks = project.locks ?? (project.locks = []);
  for (const card of STATIC_CARDS) {
    if (!cardLocked(project, card)) locks.push({ id: newId(locks.map((l) => l.id)), card });
  }
  return project;
}

// Takes the whole-card locks off the static cards. Narrower locks (one field, one item) stay.
export function unlockStaticCards(project) {
  project.locks = (project.locks ?? []).filter((lock) => !STATIC_CARDS.some((card) => wholeCard(lock, card)));
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
