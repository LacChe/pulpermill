// A small "12 s" beside a button that started a model call, counting up while the call runs. No call logic here: it reads
// when the client's call began (client.state.since) and repaints once a second until the call ends or the tag leaves the page.
import { msg } from "./text.js";

export const secondsSince = (since, now = Date.now()) => Math.max(0, Math.floor((now - since) / 1000));

// client: the page's client. mine(): whether this tag's button is the one that began the call (default: any call).
// Returns {node, update}; call update() whenever the client's state may have changed.
export function elapsedTag(client, mine = () => true) {
  const node = document.createElement("span");
  node.className = "elapsed";
  node.hidden = true;
  let timer = null;
  const stop = () => { if (timer) { clearInterval(timer); timer = null; } };
  function paint() {
    const { working, since } = client.state;
    const on = working && since !== null && mine();
    node.hidden = !on;
    if (on) node.textContent = msg("common.elapsed", { n: secondsSince(since) });
    else { node.textContent = ""; stop(); }
    if (timer && !node.isConnected) stop();             // the panel was drawn again: this tag is gone
  }
  function update() {
    paint();
    const { working, since } = client.state;
    if (working && since !== null && mine() && !timer) timer = setInterval(paint, 1000);
  }
  return { node, update };
}

// The same tag for a call the page times itself (the Fill button on a card, which has no client in reach).
export function stopwatch() {
  const node = document.createElement("span");
  node.className = "elapsed";
  node.hidden = true;
  let timer = null;
  let began = 0;
  const paint = () => { node.textContent = msg("common.elapsed", { n: secondsSince(began) }); if (!node.isConnected) stop(); };
  function stop() { if (timer) { clearInterval(timer); timer = null; } node.hidden = true; }
  function start() { began = Date.now(); node.hidden = false; paint(); timer = setInterval(paint, 1000); }
  return { node, start, stop };
}
