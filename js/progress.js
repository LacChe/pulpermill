/* Pulpermill page: Tab icon, the progress bar and its estimates, how long a run took. */
const tookTag = (secs) =>
  secs > 0 || secs === 0
    ? el("span", { class: "took" }, t("last run: {d}", { d: fmtDur(secs) }))
    : null;

/* ---------- tab icon ----------
   A blue page icon normally; an hourglass that turns over every two seconds while the model is working (sand on top, then sand
   at the bottom); a bright green tick when it has finished. The tick stays until the person comes back to the tab or touches the
   page (click, key, scroll, tap), then it goes back to the plain icon. A hidden tab's ordinary timers are slowed to a crawl
   by the browser (Chrome gets down to one a minute), and this tab is hidden exactly when someone is waiting on a long chapter, so
   the two-second beat comes from a small worker, whose timer is not slowed; without workers an ordinary timer is used. */
const ICONS = (() => {
  const svg = (b) =>
    "data:image/svg+xml," +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">' +
        b +
        "</svg>",
    );
  const glass = (sand) =>
    '<rect x="3" y="3" width="26" height="26" rx="6" fill="#b7791f"/>' +
    sand +
    '<path d="M9.5 7h13M9.5 25h13M11 7c0 5 5 6 5 9s-5 4-5 9M21 7c0 5-5 6-5 9s5 4 5 9" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
  const SAND = "#fde68a";
  return {
    idle: svg(
      '<rect x="3" y="3" width="26" height="26" rx="6" fill="#1e6fe0"/><path d="M10 9h12M10 14h12M10 19h12M10 24h7" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>',
    ),
    waiting: svg(
      glass(
        '<path d="M12.3 8.8h7.4c-.4 2.6-2.2 3.8-3.7 6.4-1.5-2.6-3.3-3.8-3.7-6.4z" fill="' +
          SAND +
          '"/><path d="M16 15v7" stroke="' +
          SAND +
          '" stroke-width="1.2" stroke-linecap="round"/><path d="M13.2 24h5.6L16 21.6z" fill="' +
          SAND +
          '"/>',
      ),
    ),
    waitingB: svg(
      glass(
        '<path d="M12.3 24h7.4c-.4-2.6-2.2-3.8-3.7-6.4-1.5 2.6-3.3 3.8-3.7 6.4z" fill="' +
          SAND +
          '"/>',
      ),
    ),
    done: svg(
      '<rect x="3" y="3" width="26" height="26" rx="6" fill="#22c55e"/><path d="M9 17l5 5 9-11" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>',
    ),
  };
})();
let tabState = "idle",
  wasBusy = false,
  waitFrame = 0,
  tabBeat = null;
function stopBeat() {
  if (tabBeat) {
    if (tabBeat.terminate) tabBeat.terminate();
    else clearInterval(tabBeat);
    tabBeat = null;
  }
}
function startBeat() {
  stopBeat();
  try {
    const url = URL.createObjectURL(
      new Blob(["setInterval(function(){postMessage(1)},2000)"], {
        type: "text/javascript",
      }),
    );
    tabBeat = new Worker(url);
    tabBeat.onmessage = flipWaitIcon;
    URL.revokeObjectURL(url);
  } catch (e) {
    tabBeat = setInterval(flipWaitIcon, 2000);
  }
}
function flipWaitIcon() {
  if (tabState !== "waiting") return;
  waitFrame = 1 - waitFrame;
  setTabIcon("waiting");
}
function setTabIcon(state) {
  if (state === "waiting" && tabState !== "waiting") {
    waitFrame = 0;
    startBeat();
  } else if (state !== "waiting") stopBeat();
  tabState = state;
  let l = document.getElementById("favicon");
  if (!l) {
    l = document.createElement("link");
    l.id = "favicon";
    l.rel = "icon";
    l.type = "image/svg+xml";
    document.head.append(l);
  }
  l.href = state === "waiting" && waitFrame ? ICONS.waitingB : ICONS[state];
}
function syncTabIcon() {
  const busy = !!st.busy;
  if (busy && !wasBusy) setTabIcon("waiting");
  else if (!busy && wasBusy) setTabIcon("done");
  wasBusy = busy;
}
function seenTab() {
  if (tabState === "done") setTabIcon("idle");
}

/* ---------- the progress bar ----------
   One line for the whole chapter job. Each step the backend reports owns a stretch of it (the chapter text most, then the read for
   card changes, the summary and the setup of the next chapter; the last chapter has no next one, so its stretches are wider).
   Three rules keep it calm:
   - Before the first word of the chapter the bar only creeps through a small share of the writing stretch, because a slow model
     can spend minutes reading the prompt; the words themselves then drive it, against the chapter's target length.
   - A step with no count creeps with a curve that keeps moving but never arrives (it only arrives when the next step starts),
     so a long step never looks stuck and never runs out of road.
   - What is drawn is an eased copy of where the bar should be (a small share of the gap per second, never backwards), so a
     step change or a burst of words is a smooth slide, not a jump. */
const CHAPTER_BANDS = {
  more: {
    starting: [0, 0.03],
    planning: [0.03, 0.09],
    writing: [0.03, 0.66],
    extracting: [0.66, 0.78],
    summarizing: [0.78, 0.84],
    next: [0.84, 0.98],
  },
  last: {
    starting: [0, 0.03],
    planning: [0.03, 0.09],
    writing: [0.03, 0.8],
    extracting: [0.8, 0.93],
    summarizing: [0.93, 0.98],
  },
};
const STEP_HALF = {
  starting: 10,
  planning: 40,
  writing: 45,
  extracting: 40,
  summarizing: 20,
  next: 45,
}; // seconds until its creep is half way
const creep = (secs, half) => secs / (secs + half);
function chapterFrac(r, stepSecs, last) {
  const B = last ? CHAPTER_BANDS.last : CHAPTER_BANDS.more;
  const [a, b] = B[r.step] || B.starting;
  let f;
  if (r.step === "writing") {
    const target =
      r.target_words || (st.limits && st.limits.default_words) || 3000; // only for the bar: chapters end where the story does
    f =
      r.words > 0
        ? 0.06 + 0.91 * Math.min(1, r.words / target)
        : 0.06 * creep(stepSecs, STEP_HALF.writing);
  } else if (r.tokens > 0 && r.max_tokens)
    f = Math.min(0.9, (0.9 * r.tokens) / (r.max_tokens * 0.55));
  else f = 0.9 * creep(stepSecs, STEP_HALF[r.step] || 30);
  return a + (b - a) * f;
}
function cardFrac(r, stepSecs) {
  if (r.tokens > 0 && r.max_tokens)
    return Math.min(
      0.95,
      0.05 + 0.9 * Math.min(1, r.tokens / (r.max_tokens * 0.55)),
    );
  return 0.05 * creep(stepSecs, 15); // reading the prompt, before the first word
}
function noteProg(kind, r, t0) {
  let p = st.prog;
  if (!p || p.kind !== kind || p.t0 !== t0)
    p = st.prog = {
      kind,
      t0,
      r: {},
      stepT0: Date.now(),
      frac: 0,
      shown: 0,
      key: "",
    };
  const key =
    kind === "chapter"
      ? r.step || ""
      : "a" + (r.attempt || 1) + (r.tokens > 0 ? "t" : "p");
  if (key !== p.key) {
    p.key = key;
    p.stepT0 = Date.now();
  }
  p.r = r;
  refreshBar();
}
let lastBarTick = 0;
function refreshBar() {
  const p = st.prog;
  if (!st.busy || !p) return;
  const now = Date.now(),
    secs = (now - p.stepT0) / 1000;
  const last = !!(st.story && st.story.job && st.story.job.last);
  const f =
    p.kind === "chapter" ? chapterFrac(p.r, secs, last) : cardFrac(p.r, secs);
  p.frac = Math.max(p.frac || 0, f); // never backwards (a retry keeps its place)
  const dt = Math.min(3, Math.max(0.05, (now - (p.tick || now)) / 1000));
  p.tick = now;
  const gap = p.frac - (p.shown || 0);
  if (gap > 0)
    p.shown =
      (p.shown || 0) + Math.min(gap, Math.max(0.0015 * dt, gap * 0.22 * dt)); // a slice of the gap per second, at least a crawl
  const pct = Math.round((p.shown || 0) * 1000) / 10;
  document.querySelectorAll(".pbar").forEach((b) => {
    b.setAttribute("aria-valuenow", String(Math.round(pct)));
    b.firstChild.style.width = pct + "%";
  });
  if (p.kind === "card") {
    const line =
      (p.r.attempt > 1
        ? t("Trying again (attempt {n})", { n: p.r.attempt }) + " · "
        : "") +
      (p.r.tokens > 0 ? t("Writing the card") : t("Starting")) +
      " · " +
      fmtDur((Date.now() - p.t0) / 1000);
    document.querySelectorAll(".cardprog").forEach((n) => {
      if (!st.stopping) n.textContent = line;
    });
  }
}
/* the bar and the note that it can take a while; `status` adds a line of text for a card (a chapter has its own) */
function progBlock(status) {
  return el(
    "div",
    { class: "prog" },
    el(
      "div",
      {
        class: "pbar",
        role: "progressbar",
        "aria-valuemin": "0",
        "aria-valuemax": "100",
        "aria-valuenow": "0",
        "aria-label": t("Progress"),
      },
      el("div", { class: "pfill" }),
    ),
    status
      ? el("div", { class: "hint cardprog", role: "status" }, t("Starting"))
      : null,
    el("div", { class: "hint pwait" }, t("This may take a few minutes.")),
  );
}
