import "./text-setup.mjs";
// The page panels (P5b): the small pieces of logic the plan panel needed, the wording the panels read, and a sweep for removed ideas.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { story, schema } from "./fixture.mjs";
import { bundle } from "./text-setup.mjs";
import { withSpotlight, tieInWords, requiredCast, castProblem, CAST_MAX } from "../../web/plan.js";
import { effectiveProject } from "../../web/effective.js";
import { lockStaticCards, storyStarted, cardLocked, STATIC_CARDS } from "../../web/gate.js";
import { makeAfterStory, afterStoryChanges } from "../../web/endstory.js";
import { stageText } from "../../web/logic.js";

const WEB = new URL("../../web/", import.meta.url);
const copy = (x) => JSON.parse(JSON.stringify(x));

// ---- Logic added for the plan panel (plan.js) ---------------------------------------------------

test("a tie in words names both ends, the bond and the edge; a group end is named by the group", () => {
  const p = story();
  const [parent, board] = p.entanglements.ties;
  assert.equal(tieInWords(schema, p, parent).text, "Marit and Suvi: mother (edge: to bring her daughter home)");
  assert.equal(tieInWords(schema, p, board).from, "Suvi");
  assert.equal(tieInWords(schema, p, board).to, "The Board");
  assert.equal(tieInWords(schema, p, { ...parent, edge: "" }).text, "Marit and Suvi: mother", "a tie with no edge is not worded with an empty one");
});

test("a tie a shift made reads right, because the panel words it from the effective cards", () => {
  const p = story();
  p.shifts.entries.push({ id: "s1", beat: "b0000001", card: "entanglements", target: null,
    patch: { ties: [{ op: "replace", id: "t1000001", values: { bond: "estranged mother" } }] } });
  const eff = effectiveProject(p, 2);
  const tie = eff.entanglements.ties.find((t) => t.id === "t1000001");
  assert.match(tieInWords(schema, eff, tie).text, /estranged mother/);
  assert.doesNotMatch(tieInWords(schema, p, p.entanglements.ties[0]).text, /estranged/);
});

test("changing the spotlight swaps the required characters and keeps the ones the writer added", () => {
  const p = story();
  p.characters.push({ id: "c0000003", name: "Joss" }, { id: "c0000004", name: "Rue" });
  p.entanglements.ties.push({ id: "t3", tie_from: "c0000003", tie_to: "c0000001", bond: "rival", edge: "to win" });
  const beat = { chapter: 2, spotlight: "t1000001", cast: ["c0000001", "c0000002", "c0000004"] };      // Rue was added by hand
  const next = withSpotlight(p, beat, "t3");
  assert.equal(next.spotlight, "t3");
  assert.deepEqual(next.cast, ["c0000001", "c0000003", "c0000004"], "Marit left with her tie; Joss came in; Rue stays");
  assert.equal(castProblem(effectiveProject(p, 2), next.cast, next.spotlight), null);
});

test("a tie that touches a group needs only the protagonist, and the cast is never longer than the limit", () => {
  const p = story();
  for (let i = 3; i <= 8; i++) p.characters.push({ id: `c000000${i}`, name: `Extra ${i}` });
  const beat = { chapter: 2, spotlight: "t1000001", cast: p.characters.map((c) => c.id) };       // eight people, more than allowed on purpose
  const next = withSpotlight(p, beat, "t1000002");
  assert.deepEqual(requiredCast(effectiveProject(p, 2), "t1000002"), ["c0000001"]);
  assert.equal(next.cast[0], "c0000001");
  assert.ok(next.cast.length <= CAST_MAX);
  assert.ok(!next.cast.includes("c0000002") || next.cast.length <= CAST_MAX, "the old tie's character is only kept as an extra");
});

test("withSpotlight changes nothing it was given", () => {
  const p = story();
  const beat = { chapter: 2, spotlight: "t1000001", cast: ["c0000001", "c0000002"] };
  const before = JSON.stringify([p, beat]);
  withSpotlight(p, beat, "t1000002");
  assert.equal(JSON.stringify([p, beat]), before);
});

// ---- The story bar and the end of the story ------------------------------------------------------

test("starting the story locks all five static cards and leaves the Outline open", () => {
  const p = story();
  p.locks = [];
  lockStaticCards(p);
  assert.ok(storyStarted(p));
  assert.deepEqual([...STATIC_CARDS].sort(), ["characters", "entanglements", "setup", "style", "world"]);
  for (const id of STATIC_CARDS) assert.ok(cardLocked(p, id), `${id} is locked`);
  assert.ok(!cardLocked(p, "outline"));
});

test("the end copy shows the final ties in words, with before and after, like Characters and World", () => {
  const p = story();
  p.setup.chapter_count = 1;
  p.shifts.entries.push(
    { id: "s1", beat: "b0000001", card: "entanglements", target: null,
      patch: { ties: [{ op: "replace", id: "t1000001", values: { edge: "to let her daughter go" } }, { op: "remove", id: "t1000002" }] } },
    { id: "s2", beat: "b0000001", card: "characters", target: "c0000001", patch: { fear: "Being left" } });
  const made = makeAfterStory(p);
  assert.ok(made.ok);
  const lines = afterStoryChanges(schema, p, made.after);
  const tieLines = lines.filter((l) => l.card === "entanglements");
  assert.ok(tieLines.some((l) => l.kind === "changed" && l.before === "to bring her daughter home" && l.after === "to let her daughter go"), "an edge that moved: before and after");
  assert.ok(tieLines.some((l) => l.kind === "removed"), "a tie that went");
  assert.ok(lines.some((l) => l.card === "characters" && l.who === "Suvi" && l.before === "Being found out" && l.after === "Being left"));
  assert.deepEqual(p.entanglements.ties.map((t) => t.id), ["t1000001", "t1000002"], "the original cards are not touched");
});

test("the end needs every chapter written, and asks the model for nothing", () => {
  const p = story();
  assert.deepEqual(makeAfterStory(p), { ok: false, reason: "not_done" });
  assert.equal(typeof bundle.end.reasons.not_done, "string");
});

// ---- Progress ---------------------------------------------------------------------------------

test("a stage shows its name and step i of n when n is known, and an unknown name gets the generic line", () => {
  assert.match(stageText({ name: "write", index: 1, of: 3 }), /writing the chapter.*step 1 of 3/);
  assert.match(stageText({ name: "think", index: 2, of: null }), /thinking/);
  assert.doesNotMatch(stageText({ name: "think", index: 2, of: null }), /step/);
  assert.equal(stageText({ name: "brand-new", index: 1, of: null }), bundle.progress.generic);
  assert.match(stageText({ name: "brand-new", index: 2, of: 4 }), /step 2 of 4/);
});

// ---- The wording the panels read ---------------------------------------------------------------------

// Every `STRINGS.key` (and STRINGS.group.key) a panel file reads is a key of its section in the bundle, so no panel shows a bare key.
const PANELS = { "planpanel.js": "plan", "generatepanel.js": "generate", "endpanel.js": "end", "story.js": "story", "welcomestrip.js": "welcome" };
for (const [file, name] of Object.entries(PANELS)) {
  test(`${file} reads only strings the ${name} section has`, () => {
    const code = readFileSync(new URL(file, WEB), "utf8").split("\n").map((line) => line.split("//")[0]).join("\n");
    const missing = [];
    for (const [, key] of code.matchAll(/\bSTRINGS\.(\w+)/g)) if (!(key in bundle[name])) missing.push(key);
    assert.deepEqual([...new Set(missing)], []);
  });
}

test("the welcome steps name the five cards and no longer mention anything removed", () => {
  const text = JSON.stringify(bundle.welcome);
  for (const word of ["Entanglements", "Outline", "shift"]) assert.match(text, new RegExp(word, "i"));
  assert.doesNotMatch(text, /pressure|knowledge|reveal|plant|offstage|goal/i);
  assert.match(bundle.story.intro, /Style, Characters, World, Entanglements and Setup/);
});

// ---- Removed ideas ------------------------------------------------------------------------------------------

const REMOVED = /pressure|knowledge|offstage|reveal|plant|payoff|goal|stakes|usage/i;

test("no panel, style or page text refers to a removed idea (comments excepted)", () => {
  const found = [];
  const code = (line) => line.replace(/^\s*\/\/.*$/, "").replace(/\s\/\/\s.*$/, "");
  for (const file of readdirSync(WEB).filter((f) => /\.(js|css|html)$/.test(f))) {
    readFileSync(new URL(file, WEB), "utf8").split("\n").forEach((line, at) => { if (REMOVED.test(code(line))) found.push(`${file}:${at + 1}`); });
  }
  const bundleText = JSON.stringify(bundle, null, 1).split("\n");
  bundleText.forEach((line, at) => { if (REMOVED.test(line)) found.push(`text.en.json:${at + 1}`); });
  assert.deepEqual(found, []);
});

test("no form label or help in the schema data refers to a removed field, except the two rule ids P1 still owns", () => {
  const lines = readFileSync(new URL("data/schema.en.json", WEB), "utf8").split("\n").filter((line) => REMOVED.test(line));
  const allowed = /"id": "(object_has_stakes|power_no_current_goals)"/;
  assert.deepEqual(lines.filter((line) => !allowed.test(line)), []);
});
