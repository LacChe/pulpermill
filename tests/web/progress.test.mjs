import "./text-setup.mjs";
// The progress estimate: which steps a call is laid out as, where the bar stands, what it learns, and the words.
import test from "node:test";
import assert from "node:assert/strict";
import { jobOf, expectedKeys, createMemory, createTracker, stepText, SEED_SECONDS } from "../../web/progress.js";

const S = 1000;
const plan = (chapter, choose = false) => ({ call: "plan", chapter, choose, card: null, rules: null });

test("a request becomes a job of only what the bar needs", () => {
  assert.deepEqual(jobOf({ call: "plan", chapter: 3, choose: true, earlier_beats: [{ plan: "secret" }] }), { call: "plan", card: null, rules: null, chapter: 3, choose: true });
  assert.deepEqual(jobOf({ call: "fill", card: "world", values: {} }), { call: "fill", card: "world", rules: null, chapter: null, choose: false });
  assert.equal(jobOf({ call: "judge", card: "world", rules: [{}, {}, {}] }).rules, 3);
});

test("the steps a call is laid out as follow the call, the chapter and the choose mode", () => {
  assert.deepEqual(expectedKeys(plan(1)), ["brainstorm", "decide", "plan"]);
  assert.deepEqual(expectedKeys(plan(2, true)), ["select", "labelEarlier", "brainstorm", "labelIdeas", "decide", "plan"]);
  assert.deepEqual(expectedKeys({ call: "generate" }), ["write", "events", "shifts"]);
  for (const call of ["fill", "judge", "finish", "style_fit"]) assert.deepEqual(expectedKeys({ call }), [call]);
});

// A tracker over one plan call, with the times the page would give it.
function planned(chapter = 2, choose = true, memory = createMemory()) {
  const tracker = createTracker({ memory });
  tracker.begin(plan(chapter, choose), 0);
  return tracker;
}

test("the bar only moves forward, and does not reach the end of a step before the backend says it is done", () => {
  const tracker = planned();
  let last = 0;
  for (const [name, at] of [["select", 1], ["select", 40], ["select", 80], ["label", 90], ["label", 130], ["brainstorm", 150], ["brainstorm", 400], ["label", 410], ["decide", 470], ["plan", 560], ["plan", 900]]) {
    tracker.stage({ name, index: 1, of: null }, at * S);
    const now = tracker.read(at * S);
    assert.ok(now.fraction >= last, `${name} at ${at}s went back`);
    assert.ok(now.fraction < 1);
    last = now.fraction;
  }
});

test("the two label steps are told apart by whether the brainstorm came first", () => {
  const tracker = planned();
  tracker.stage({ name: "select", index: 1, of: 6 }, 1 * S);
  tracker.stage({ name: "label", index: 2, of: 6 }, 60 * S);
  assert.equal(tracker.read(61 * S).label.key, "labelEarlier");
  tracker.stage({ name: "brainstorm", index: 3, of: 6 }, 120 * S);
  tracker.stage({ name: "label", index: 4, of: 6 }, 210 * S);
  assert.equal(tracker.read(211 * S).label.key, "labelIdeas");
});

test("a step the backend skips leaves the layout, and the bar moves forward", () => {
  const tracker = planned(2, false);
  tracker.stage({ name: "label", index: 1, of: 5 }, 1 * S);
  tracker.stage({ name: "brainstorm", index: 2, of: 5 }, 60 * S);
  tracker.stage({ name: "label", index: 3, of: 5 }, 150 * S);
  const before = tracker.read(150 * S);
  assert.equal(before.marks.length, 4);              // labelEarlier | brainstorm | labelIdeas | decide | plan
  tracker.stage({ name: "plan", index: 4, of: 5 }, 210 * S);       // no decide this time
  const after = tracker.read(210 * S);
  assert.equal(after.marks.length, 3);
  assert.equal(after.label.key, "plan");
  assert.ok(after.fraction > before.fraction);
});

test("a step nobody expected is added, and the bar does not go back for it", () => {
  const tracker = createTracker();
  tracker.begin({ call: "generate", chapter: 1, choose: false, card: null, rules: null }, 0);
  tracker.stage({ name: "write", index: 1, of: 3 }, 1 * S);
  tracker.stage({ name: "events", index: 2, of: 3 }, 210 * S);
  const before = tracker.read(260 * S).fraction;
  tracker.stage({ name: "polish", index: 3, of: 4 }, 270 * S);
  const now = tracker.read(270 * S);
  assert.equal(now.label.key, "polish");
  assert.ok(now.fraction >= before);
  assert.equal(stepText(now.label), "Working…");
});

test("a step that runs well past its usual time is called slow, and the bar waits inside its segment", () => {
  const tracker = createTracker();
  tracker.begin({ call: "generate", chapter: 1, choose: false, card: null, rules: null }, 0);
  tracker.stage({ name: "write", index: 1, of: 3 }, 1 * S);
  assert.equal(tracker.read(100 * S).slow, false);
  const late = tracker.read(2000 * S);
  assert.equal(late.slow, true);
  assert.ok(late.fraction < late.marks[0]);           // still inside the write segment
});

test("what a call teaches: a first time replaces the seed, a later one only moves it, and the steps not yet seen follow the pace", () => {
  const memory = createMemory();
  assert.equal(memory.seconds("write"), SEED_SECONDS.write);
  memory.observe("write", 21);                          // about ten times faster than the seed
  assert.equal(memory.seconds("write"), 21);
  assert.ok(Math.abs(memory.seconds("events") - SEED_SECONDS.events * (21 / SEED_SECONDS.write)) < 1e-9);
  memory.observe("write", 1e9);                         // a stray huge time moves it by at most four times
  assert.ok(memory.seconds("write") <= 21 * (0.6 + 0.4 * 4) + 1e-9);
  memory.observe("write", -5);
  memory.observe("write", NaN);
  assert.ok(Number.isFinite(memory.seconds("write")));
});

test("a call that went well teaches its last step's time; one that did not teaches nothing", () => {
  const good = createMemory();
  const a = createTracker({ memory: good });
  a.begin({ call: "generate", chapter: 1, choose: false, card: null, rules: null }, 0);
  a.stage({ name: "write", index: 1, of: 3 }, 1 * S);
  a.stage({ name: "events", index: 2, of: 3 }, 21 * S);          // write ran from the start of the call to 21 s
  a.end(true, 27 * S);                                           // events took 6 s
  assert.equal(good.seconds("write"), 21);
  assert.equal(good.seconds("events"), 6);
  const bad = createMemory();
  const b = createTracker({ memory: bad });
  b.begin({ call: "generate", chapter: 1, choose: false, card: null, rules: null }, 0);
  b.stage({ name: "write", index: 1, of: 3 }, 1 * S);
  b.end(false, 5 * S);
  assert.equal(bad.seconds("write"), SEED_SECONDS.write);
});

test("a call with no stages is one step, timed whole, and a judge call is timed per rule", () => {
  const memory = createMemory();
  const fillCall = createTracker({ memory });
  fillCall.begin({ call: "fill", card: "world", rules: null, chapter: null, choose: false }, 0);
  assert.equal(fillCall.read(1 * S).label.key, "fill");
  fillCall.end(true, 30 * S);
  assert.equal(memory.seconds("fill"), 30);
  const judge = createTracker({ memory });
  judge.begin({ call: "judge", card: "world", rules: 4, chapter: null, choose: false }, 0);
  judge.end(true, 20 * S);
  assert.equal(memory.seconds("judge"), 5);
});

test("what was learned is handed on and read back, and bad saved data is ignored", () => {
  let saved = null;
  const first = createMemory(null, (snapshot) => { saved = snapshot; });
  first.observe("plan", 12);
  const second = createMemory(JSON.parse(JSON.stringify(saved)));
  assert.equal(second.seconds("plan"), 12);
  const broken = createMemory({ scale: "x", steps: { plan: { mean: -3 }, write: "nope" } });
  assert.equal(broken.seconds("plan"), SEED_SECONDS.plan);
});

test("each step has words, a fill names its card, and a step with none gets the generic line", () => {
  assert.equal(stepText({ key: "brainstorm" }), "Planning: brainstorming");
  assert.equal(stepText({ key: "write" }), "Writing: the chapter");
  assert.equal(stepText({ key: "fill", card: "world" }, "World"), "Filling: the World card");
  assert.equal(stepText({ key: "dreaming" }), "Working…");
  for (const key of Object.keys(SEED_SECONDS).filter((k) => k !== "judge" && k !== "fill")) assert.doesNotMatch(stepText({ key }), /^Working/, key);
});
