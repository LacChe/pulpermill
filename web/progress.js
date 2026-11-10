// How far along the model's call is, for the bar in the backend bar. No DOM here, so Node can test it.
//
// The backend names the step it is on (status answers {name, index, of}) only for the story calls, plan and generate, and says nothing
// about how far into a step it is. So the position is an estimate made from how long each step usually takes: the steps a call is
// expected to run are laid out as segments as wide as their usual time; the bar stands at the end of the steps already done plus a
// share of the current one that eases toward its end and never reaches it; and it never goes backwards. A step the call skips (the
// backend runs some only now and then) is dropped from the layout when the next step arrives, which moves the bar forward.
//
// How long a step usually takes is learned for each backend, because the same step takes seconds on one machine and minutes on
// another. The seeds below come from one run of five chapters on a slow local model (about 11 to 13 minutes a chapter): only the first
// guess, replaced step by step as the page sees real times. A step the page has not seen yet is scaled by how much faster or slower
// the steps it has seen ran than their seeds.
import { msg } from "./text.js";

export const SEED_SECONDS = {
  style_fit: 6,
  select: 69, labelEarlier: 53, brainstorm: 93, labelIdeas: 53, decide: 75, plan: 116,
  write: 209, events: 69, shifts: 16,
  fill: 60, judge: 15, finish: 60,          // not in that run: guesses until the page has seen them
};
const UNKNOWN_SECONDS = 60;                  // a step the page has never heard of
const EASE_MAX = 0.92;                       // the share of its segment a step's fill can reach before the backend says it is done
const EASE_RATE = 2.5;                       // how fast it gets there: about 85% of that by the step's usual time
const SLOW_AFTER = 1.5;                      // "taking longer than usual" once a step has run this many times its usual time
const KEEP = 0.6;                            // how much of what was learned stays when a new time comes in

// What the page needs to know about a request to lay out its steps and to word them. Nothing of the writer's text.
export function jobOf(request) {
  const call = request?.call;
  return {
    call,
    card: call === "fill" ? request.card ?? null : null,
    rules: call === "judge" ? (Array.isArray(request.rules) ? request.rules.length : 1) : null,
    chapter: Number.isInteger(request?.chapter) ? request.chapter : null,
    choose: Boolean(request?.choose),
  };
}

// The steps a job is expected to run, in order, by key. The two label steps of a plan have keys of their own: one reads the earlier
// chapters, the other checks the brainstorm's ideas against them.
export function expectedKeys(job) {
  if (job.call === "plan") {
    const later = (job.chapter ?? 1) > 1;
    return [
      ...(job.choose ? ["select"] : []),
      ...(later ? ["labelEarlier"] : []),
      "brainstorm",
      ...(later ? ["labelIdeas"] : []),
      "decide",                              // runs in about half of the plans; dropped when the next step arrives without it
      "plan",
    ];
  }
  if (job.call === "generate") return ["write", "events", "shifts"];
  return [job.call];                         // style_fit, fill, judge (all its rules are one segment), finish
}

// What learning has seen on one backend: how long each step took, and how the steps ran against their seeds. `save` is told after every
// change (the page keeps it in localStorage); `start` is what was saved before.
export function createMemory(start = null, save = () => {}) {
  const data = {
    scale: Number.isFinite(start?.scale) && start.scale > 0 ? start.scale : null,
    steps: {},
  };
  for (const [key, entry] of Object.entries(start?.steps ?? {})) {
    if (Number.isFinite(entry?.mean) && entry.mean > 0) data.steps[key] = { mean: entry.mean };
  }
  return {
    // How long one step of this key usually takes, in seconds.
    seconds(key) {
      if (data.steps[key]) return data.steps[key].mean;
      return (SEED_SECONDS[key] ?? UNKNOWN_SECONDS) * (data.scale ?? 1);
    },
    // A step ran for `seconds`. The first time replaces the seed; later times move the mean, a stray very long or very short one only a little.
    observe(key, seconds) {
      if (!(seconds > 0) || !Number.isFinite(seconds)) return;
      const seen = data.steps[key];
      data.steps[key] = { mean: seen ? KEEP * seen.mean + (1 - KEEP) * Math.min(Math.max(seconds, seen.mean / 4), seen.mean * 4) : seconds };
      const seed = SEED_SECONDS[key];
      if (seed) {
        const ratio = seconds / seed;
        data.scale = data.scale === null ? ratio : KEEP * data.scale + (1 - KEEP) * ratio;
      }
      save(this.snapshot());
    },
    snapshot() { return { scale: data.scale, steps: { ...data.steps } }; },
  };
}

// One model call's progress. `at` is a time in ms (Date.now() in the page); the tests give their own.
//   begin(job, at)   a call began
//   stage(stage)     the backend's last word about its step ({name, index, of}); null or the same step again changes nothing
//   end(ok, at)      the call ended; when it went well, the last step's time is learned
//   read(at)         {label: {key, card}, fraction, slow, marks} or null when no call is going
export function createTracker({ memory = createMemory() } = {}) {
  let job = null;
  let steps = [];          // [{key, confirmed}]: the layout; the page's own guess until the backend names a step
  let at = 0;              // the step now running (an index into steps)
  let stepStart = 0;
  let high = 0;
  let passedBrainstorm = false;
  const staged = () => job.call === "plan" || job.call === "generate";

  const keyOf = (name) => {
    if (name === "label") return passedBrainstorm ? "labelIdeas" : "labelEarlier";
    return name;
  };
  const weight = (step) => memory.seconds(step.key) * (step.key === "judge" ? job.rules ?? 1 : 1);

  // A step is over: learn its time, but only a step the backend confirmed (the first one is a guess until then).
  function leave(now) {
    const step = steps[at];
    if (step?.confirmed) memory.observe(step.key, ((now - stepStart) / 1000) / (step.key === "judge" ? job.rules ?? 1 : 1));
  }

  return {
    begin(next, now) {
      job = next;
      steps = expectedKeys(job).map((key) => ({ key, confirmed: !staged() }));      // a call with no stages is one step, known from the start
      at = 0;
      stepStart = now;
      high = 0;
      passedBrainstorm = false;
    },
    stage(stage, now = stepStart) {
      if (!job || !stage || !staged()) return;
      const key = keyOf(stage.name);
      if (steps[at].key === key) { steps[at].confirmed = true; return; }
      leave(now);
      if (steps[at].key === "brainstorm") passedBrainstorm = true;
      const ahead = steps.findIndex((s, i) => i > at && s.key === key);
      if (ahead >= 0) steps.splice(at + 1, ahead - at - 1);               // the steps skipped on the way are left out of the layout
      else steps.splice(at + 1, 0, { key, confirmed: false });            // one the page did not expect
      at += 1;
      steps[at].confirmed = true;
      stepStart = now;
      if (key === "brainstorm") passedBrainstorm = true;
    },
    end(ok, now) {
      if (job && ok) leave(now);
      job = null;
      steps = [];
    },
    read(now) {
      if (!job) return null;
      const weights = steps.map(weight);
      const total = weights.reduce((a, b) => a + b, 0);
      const done = weights.slice(0, at).reduce((a, b) => a + b, 0);
      const elapsed = Math.max(0, (now - stepStart) / 1000);
      const usual = weights[at];
      const inner = EASE_MAX * (1 - Math.exp(-EASE_RATE * elapsed / usual));
      high = Math.max(high, (done + usual * inner) / total);
      let sum = 0;
      const marks = weights.slice(0, -1).map((w) => (sum += w) / total);
      const step = steps[at];
      return { label: { key: step.key, card: job.card }, fraction: high, slow: elapsed > SLOW_AFTER * usual, marks };
    },
  };
}

// The words for each step the page knows.
const STEP_TEXT = {
  style_fit: "progress.steps.style_fit", select: "progress.steps.select", labelEarlier: "progress.steps.labelEarlier",
  brainstorm: "progress.steps.brainstorm", labelIdeas: "progress.steps.labelIdeas", decide: "progress.steps.decide",
  plan: "progress.steps.plan", write: "progress.steps.write", events: "progress.steps.events", shifts: "progress.steps.shifts",
  fill: "progress.steps.fill", judge: "progress.steps.judge", finish: "progress.steps.finish",
};

// "Planning: brainstorming three ideas". A step the page has no words for gets the generic line.
export function stepText(label, cardName) {
  return Object.hasOwn(STEP_TEXT, label.key) ? msg(STEP_TEXT[label.key], { card: cardName ?? "" }) : msg("progress.generic");
}
