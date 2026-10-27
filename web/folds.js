// Which folds the writer left open or shut. Kept outside any drawing, so a panel or card drawn again comes back as it was.
// What is folded or open is the writer's, so it is kept here, outside any drawing: a card drawn again (after an edit, a fill, an
// undo) comes back with every fold as it was left. Keys name the card, the person on it and the fold.
export const foldedItems = new Set();
export const openState = new Map();
export function remember(details, key, fallback) {
  const saved = openState.get(key);
  details.open = saved === undefined ? fallback : saved;
  details.addEventListener("toggle", () => openState.set(key, details.open));
}
export function forgetFolds() { foldedItems.clear(); openState.clear(); }
