// The progress bar at the right end of the backend bar: what the model is doing, in words, and a bar for how far along it is. It is
// there only while a call runs. The estimate itself (steps, timings, learning) is progress.js; this file only draws it and keeps what
// that learned in localStorage, a set of times for each backend, so the next run starts from real numbers.
import { createMemory, createTracker, stepText } from "./progress.js";
import { settingText } from "./client.js";
import { msg } from "./text.js";

export const PACE_KEY = "pulpermill-pace";

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

const readAll = (storage) => {
  try { return JSON.parse(storage?.getItem(PACE_KEY)) ?? {}; } catch { return {}; }
};

// client: the page's client. host: where the bar goes. cardName(id): a card's name for "Filling: the Characters card".
// storage, now and tick are there for the tests. Returns {node, update}.
export function createProgressBar({ client, host, cardName = (id) => id, storage = globalThis.localStorage, now = Date.now, tick = 250 }) {
  const label = node("span", { className: "run-progress-label" });
  const fill = node("div", { className: "run-progress-fill" });
  const marks = node("div", { className: "run-progress-marks" });
  const root = node("div", { className: "run-progress", hidden: true }, label, node("div", { className: "run-progress-track" }, fill, marks));
  root.setAttribute("role", "progressbar");
  root.setAttribute("aria-valuemin", "0");
  root.setAttribute("aria-valuemax", "100");
  host.append(root);

  let tracker = null;
  let timer = null;
  let drawnMarks = "";

  // What was learned about one backend, kept under its address (or "mock") so a slow machine's times never colour a fast one's.
  function memoryFor(setting) {
    const key = settingText(setting);
    return createMemory(readAll(storage)[key], (snapshot) => {
      try {
        const all = readAll(storage);
        all[key] = snapshot;
        storage.setItem(PACE_KEY, JSON.stringify(all));
      } catch { /* the times are just not kept */ }
    });
  }

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
    tracker = null;
    root.hidden = true;
  }

  function paint() {
    const read = tracker?.read(now());
    if (!read) return;
    const text = stepText(read.label, read.label.card ? cardName(read.label.card) : "");
    const percent = Math.round(read.fraction * 1000) / 10;
    root.hidden = false;
    label.textContent = read.slow ? `${text} · ${msg("progress.slow")}` : text;
    root.title = read.slow ? `${text}: ${msg("progress.slowHelp")}` : text;     // the label is cut to a fixed width, so the whole of it is here
    fill.style.width = `${percent}%`;
    root.toggleAttribute("data-slow", read.slow);
    root.setAttribute("aria-valuenow", String(Math.round(percent)));
    root.setAttribute("aria-valuetext", read.slow ? `${text}, ${msg("progress.slowHelp")}` : text);
    const at = read.marks.map((m) => `${Math.round(m * 1000) / 10}%`).join();
    if (at !== drawnMarks) {
      drawnMarks = at;
      marks.replaceChildren(...read.marks.map((m) => {
        const mark = node("span", { className: "run-progress-mark" });
        mark.style.left = `${Math.round(m * 1000) / 10}%`;
        return mark;
      }));
    }
  }

  function update(state = client.state) {
    const { working, job, stage } = state;
    if (!working || !job) { stop(); return; }
    if (!tracker) {
      tracker = createTracker({ memory: memoryFor(state.setting) });
      tracker.begin(job, now());
      timer = setInterval(paint, tick);
    }
    tracker.stage(stage, now());
    paint();
  }

  // A call that went well teaches the last step's time; one that failed or was stopped teaches nothing.
  client.onFinish((reply) => { tracker?.end(reply?.ok === true, now()); tracker = null; });
  client.onChange(update);
  return { node: root, update };
}
