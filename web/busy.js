// When the page is locked. While the model works, everything but Check and Stop is out of reach, and that is decided here, in one
// place: the page asks this file whether it is locked and marks its areas (anything with data-locks in index.html) inert, rather than
// each panel disabling its own buttons from its own refresh. Whatever draws later, an area is inert or not because of this one answer.
export function lockReason({ working = false, stopping = false, connection = null } = {}, running = false) {
  if (stopping) return "stopping";
  if (working) return "call";
  if (running) return "run-all";          // between the calls of a run of several chapters
  if (connection === "busy") return "remote";   // a job this page does not track
  return null;
}

// client: the page's client. runAll: the run of several chapters (may be absent). Reads fresh every time, so no copy can go stale.
export function createLock({ client, runAll = null }) {
  const listeners = [];
  let last = null;
  const read = () => lockReason(client.state, Boolean(runAll?.running));
  const update = () => {
    const now = read();
    if (now === last) return;
    last = now;
    for (const listener of listeners) listener(now);
  };
  client.onChange(update);
  runAll?.onChange(update);
  return {
    get reason() { return read(); },
    get locked() { return read() !== null; },
    onChange(listener) { listeners.push(listener); },
    update,
    attach(next) { runAll = next; next.onChange(update); update(); },
  };
}

// Marks every area that locks. Safe to call as often as wanted.
export function applyLock(root, reason) {
  root.body.toggleAttribute("data-locked", reason !== null);
  if (reason) root.body.dataset.lockReason = reason; else delete root.body.dataset.lockReason;
  for (const area of root.querySelectorAll("[data-locks]")) area.inert = reason !== null;
}
