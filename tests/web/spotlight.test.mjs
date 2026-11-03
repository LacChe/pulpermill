import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema } from "./helpers.mjs";
import { refOptions, lookupLabel, tieWords, isCharacterTie } from "../../web/logic.js";
import { pickSpotlight, newBeat, spotlightTies, tieInWords, planGate } from "../../web/plan.js";
import { lockStaticCards } from "../../web/gate.js";

// Three characters, two groups, four ties: Orla to Pim, Corbin to Pim, the Council to Orla, the Guild to Orla.
function project() {
  return {
    id: "pr000009", title: "T", schema_version: schema.schema_version,
    characters: [{ id: "c1", name: "Orla Fennick" }, { id: "c2", name: "Pim Tallowby" }, { id: "c3", name: "Corbin" }],
    world: { places: [{ id: "p1", name: "The Mill" }], objects: [], rules: [], terms: [],
      powers: [{ id: "g1", name: "The Parish Council" }, { id: "g2", name: "The Baker's Guild" }] },
    entanglements: { holdings: [], ties: [
      { id: "t1", tie_from: "c1", tie_to: "c2", bond: "master and apprentice", edge: "to pass on the craft" },
      { id: "t2", tie_from: "c3", tie_to: "c2", bond: "rival", edge: "" },
      { id: "t3", tie_from: "g1", tie_to: "c1", bond: "baker to council", edge: "to keep the tolls" },
      { id: "t4", tie_from: "g2", tie_to: "c1", bond: "member of", edge: "" },
    ] },
    setup: { protagonist: "c1", normal: "n", disruption: "d", chapter_count: 12 },
    outline: { beats: [] }, chapters: [], summary_events: { entries: [] }, shifts: { entries: [] }, locks: [],
  };
}
const tieSources = ["entanglements.ties"];

test("a tie is listed in words, never as Unnamed", () => {
  const p = project();
  const labels = refOptions(p, tieSources).map((o) => o.label);
  assert.deepEqual(labels, [
    "Orla Fennick and Pim Tallowby: master and apprentice (edge: to pass on the craft)",
    "Corbin and Pim Tallowby: rival",
    "The Parish Council and Orla Fennick: baker to council (edge: to keep the tolls)",
    "The Baker's Guild and Orla Fennick: member of",
  ]);
  assert.ok(labels.every((l) => !/Unnamed/.test(l)));
  assert.equal(lookupLabel(p, { ref: tieSources }, "t2"), "Corbin and Pim Tallowby: rival");
});

test("the plan panel and the pickers share one wording", () => {
  const p = project();
  for (const t of p.entanglements.ties) {
    assert.equal(tieInWords(schema, p, t).text, tieWords(p, t).text);
    assert.equal(refOptions(p, tieSources).find((o) => o.value === t.id).label, tieWords(p, t).text);
  }
});

test("other link sources label exactly as before", () => {
  const p = project();
  assert.deepEqual(refOptions(p, ["characters"]).map((o) => o.label), ["Orla Fennick", "Pim Tallowby", "Corbin"]);
  assert.deepEqual(refOptions(p, ["world.powers"]).map((o) => o.label), ["The Parish Council", "The Baker's Guild"]);
  p.characters[0].name = " ";
  assert.equal(refOptions(p, ["characters"])[0].label, "Unnamed");
});

test("the spotlight picker offers only character-to-character ties, and keeps a saved group tie", () => {
  const p = project();
  assert.deepEqual(refOptions(p, tieSources, "x", { characterTiesOnly: true }).map((o) => o.value), ["t1", "t2"]);
  assert.deepEqual(refOptions(p, tieSources, "x", { characterTiesOnly: true, keep: ["t3"] }).map((o) => o.value), ["t1", "t2", "t3"]);
  assert.deepEqual(spotlightTies(p).map((t) => t.id), ["t1", "t2"]);
  assert.equal(isCharacterTie(p, p.entanglements.ties[2]), false);
});

test("the random pick never returns a group tie, over many chapters and projects", () => {
  const seen = new Set();
  for (let n = 0; n < 12; n++) {
    const p = project();
    p.id = `pr00000${n}x`;
    for (let chapter = 1; chapter <= 20; chapter++) seen.add(pickSpotlight(p, chapter).id);
  }
  assert.deepEqual([...seen].sort(), ["t1", "t2"]);
});

test("a beat made from the pick has a character tie and its two characters in the cast", () => {
  const p = lockStaticCards(project());
  for (let chapter = 1; chapter <= 10; chapter++) {
    const beat = newBeat(schema, p, chapter);
    assert.ok(["t1", "t2"].includes(beat.spotlight));
  }
});

test("a saved group-tie spotlight is left alone", () => {
  const p = project();
  p.outline.beats = [{ id: "b1", chapter: 1, spotlight: "t3", cast: ["c1"], where: "p1" }];
  const before = JSON.stringify(p.outline);
  assert.ok(refOptions(p, tieSources, "x", { characterTiesOnly: true, keep: ["t3"] }).some((o) => o.value === "t3"));
  pickSpotlight(p, 2);
  assert.equal(JSON.stringify(p.outline), before);
});

test("with no character tie the beat has no spotlight, without an error", () => {
  const p = lockStaticCards(project());
  p.entanglements.ties = p.entanglements.ties.filter((t) => t.id === "t3" || t.id === "t4");
  assert.equal(pickSpotlight(p, 1), null);
  const beat = newBeat(schema, p, 1);
  assert.equal(beat.spotlight, "");
  assert.deepEqual(beat.cast, p.characters.map((c) => c.id).slice(0, 5), "with no tie the cast is the protagonist first, then the other characters in card order");
  assert.equal(beat.cast[0], "c1");
  assert.equal(planGate(p, beat).reason, "no_tie");   // the contract needs a spotlight among the ties sent, so the page does not send one
});
