// The tab icon. Four states: default, generating (animated), done, failed.
//
// Why it is drawn by code: browsers do not animate a favicon themselves, so each frame is painted on a canvas and the
// <link rel="icon"> is replaced with it. Why the clock and a worker: a hidden tab has its page timers slowed (to once a
// second, and after about five minutes to once a minute), and a story call can run ten minutes with the tab hidden. So
// the frame is worked out from the wall clock (a late tick still shows the right frame) and the ticks come from a
// Web Worker, whose timers the browser does not slow the same way. If a worker cannot be made, a plain interval is used.

export const SIZE = 64;
export const STEPS = 8;           // segments in the ring
export const TURN = 1200;         // ms for the bright head to go once round
const TICK = 150;                 // ms between checks while generating

// ---- The state machine (no page needed) ----------------------------------------------------------------------

// state: "default" | "generating" | "done" | "failed"
// events: { type: "start" } | { type: "finish", outcome: "ok" | "failed" | "stopped", hidden } | { type: "seen" }
export function nextIconState(state, event) {
  if (event.type === "start") return "generating";
  if (event.type === "finish") {
    if (event.outcome === "stopped" || !event.hidden) return "default";   // stopped by the writer, or they are looking at the page
    return event.outcome === "ok" ? "done" : "failed";
  }
  if (event.type === "seen") return state === "done" || state === "failed" ? "default" : state;
  return state;
}

// Which frame of the ring is brightest, from the clock alone.
export function headAt(now) {
  return Math.floor(((now % TURN) / TURN) * STEPS);
}

// ---- Drawing -------------------------------------------------------------------------------------------------

const FALLBACK = { accent: "#4cdbe3", surface: "#14191f", line: "#323941", bad: "#fb817a" };

// Reads the page's own colour tokens, so the icon follows the theme. A value the canvas cannot parse falls back to hex.
function palette(doc, ctx) {
  const style = doc.defaultView.getComputedStyle(doc.documentElement);
  const pick = (name, fallback) => {
    const value = style.getPropertyValue(name).trim();
    if (!value) return fallback;
    ctx.fillStyle = "#000000";
    ctx.fillStyle = value;
    return ctx.fillStyle === "#000000" && !/^(#000|#000000|black)$/i.test(value) ? fallback : value;
  };
  return {
    accent: pick("--accent", FALLBACK.accent), surface: pick("--surface-1", FALLBACK.surface),
    line: pick("--line", FALLBACK.line), bad: pick("--bad", FALLBACK.bad),
  };
}

function square(ctx, fill, stroke) {
  ctx.beginPath();
  ctx.roundRect(2, 2, SIZE - 4, SIZE - 4, 14);
  ctx.fillStyle = fill;
  ctx.fill();
  if (stroke) { ctx.lineWidth = 2; ctx.strokeStyle = stroke; ctx.stroke(); }
}

export function drawIcon(ctx, colours, state, now = Date.now()) {
  ctx.clearRect(0, 0, SIZE, SIZE);
  ctx.lineCap = "round";
  if (state === "done") {
    square(ctx, colours.accent);
    ctx.strokeStyle = colours.surface; ctx.lineWidth = 7; ctx.lineJoin = "round";
    ctx.beginPath(); ctx.moveTo(18, 34); ctx.lineTo(28, 44); ctx.lineTo(46, 22); ctx.stroke();
  } else if (state === "failed") {
    square(ctx, colours.bad);
    ctx.strokeStyle = colours.surface; ctx.fillStyle = colours.surface; ctx.lineWidth = 8;
    ctx.beginPath(); ctx.moveTo(32, 16); ctx.lineTo(32, 36); ctx.stroke();
    ctx.beginPath(); ctx.arc(32, 47, 4.5, 0, Math.PI * 2); ctx.fill();
  } else if (state === "generating") {
    square(ctx, colours.surface, colours.line);
    const head = headAt(now);
    const slice = (Math.PI * 2) / STEPS;
    ctx.lineWidth = 7; ctx.lineCap = "butt"; ctx.strokeStyle = colours.accent;
    for (let i = 0; i < STEPS; i++) {
      const behind = (head - i + STEPS) % STEPS;                       // 0 is the head, then the tail fading away
      ctx.globalAlpha = 0.16 + 0.84 * Math.pow(1 - behind / STEPS, 1.6);
      ctx.beginPath();
      ctx.arc(32, 32, 19, i * slice - Math.PI / 2 + 0.08, (i + 1) * slice - Math.PI / 2 - 0.08);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  } else {
    square(ctx, colours.surface, colours.line);
    ctx.fillStyle = colours.accent;
    ctx.font = "700 42px system-ui, -apple-system, 'Segoe UI', sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("P", 32, 35);
  }
}

// ---- The page side -------------------------------------------------------------------------------------------

// A repeating tick that does not slow down in a hidden tab, as far as the browser allows. Returns a function that stops it.
function ticker(callback, ms, win) {
  try {
    const source = `setInterval(() => postMessage(0), ${ms});`;
    const url = win.URL.createObjectURL(new win.Blob([source], { type: "text/javascript" }));
    const worker = new win.Worker(url);
    worker.onmessage = callback;
    return () => { worker.terminate(); win.URL.revokeObjectURL(url); };
  } catch {
    const id = win.setInterval(callback, ms);
    return () => win.clearInterval(id);
  }
}

// Ties the icon to a client: generating while a model call runs, then done or failed if the tab is hidden, until the
// writer comes back to it or does anything on the page. `onChange(state)` lets the page mark its title.
export function mountTabIcon(client, { doc = document, onChange = () => {} } = {}) {
  const win = doc.defaultView;
  const canvas = doc.createElement("canvas");
  canvas.width = canvas.height = SIZE;
  const ctx = canvas.getContext?.("2d");
  if (!ctx || !ctx.roundRect) return { state: () => "default", mark: () => "default" };   // no canvas here: the static icon stays
  let state = "default";
  let shown = null;
  let wasWorking = false;
  let stopTicks = null;

  function paint() {
    const now = Date.now();
    const key = state === "generating" ? `generating:${headAt(now)}` : state;
    if (key === shown) return;                    // the same picture: nothing to replace
    shown = key;
    drawIcon(ctx, palette(doc, ctx), state, now);
    const link = doc.createElement("link");       // replaced, not edited: some browsers ignore a changed href
    link.rel = "icon"; link.type = "image/png"; link.href = canvas.toDataURL("image/png");
    const old = doc.querySelector('link[rel~="icon"]');
    if (old) old.replaceWith(link); else doc.head.append(link);
  }

  function move(event) {
    const before = state;
    state = nextIconState(state, event);
    if (state === "generating" && !stopTicks) stopTicks = ticker(paint, TICK, win);
    if (state !== "generating" && stopTicks) { stopTicks(); stopTicks = null; }
    paint();
    if (state !== before) onChange(state);
  }

  client.onChange((now) => {
    if (now.working && !wasWorking) move({ type: "start" });
    wasWorking = now.working;
  });
  client.onFinish((reply) => {
    const outcome = reply?.ok === true ? "ok" : reply?.error?.kind === "stopped" ? "stopped" : "failed";
    move({ type: "finish", outcome, hidden: doc.hidden });
  });
  const seen = () => move({ type: "seen" });
  doc.addEventListener("visibilitychange", () => { if (!doc.hidden) seen(); });
  for (const name of ["pointerdown", "keydown", "focus"]) win.addEventListener(name, seen, true);

  return { state: () => state, mark: () => state };
}
