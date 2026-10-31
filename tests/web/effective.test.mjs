import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { applyShifts, applyPatch, effectiveProject, foldAll, validatePatch } from "../../web/effective.js";
import { schema } from "./helpers.mjs";

const vectors = JSON.parse(readFileSync(new URL("../shared/overlay-vectors.json", import.meta.url), "utf8"));

for (const v of vectors.overlay) {
  test(`overlay: ${v.name}`, () => {
    const before = JSON.stringify(v.base);
    assert.deepEqual(applyShifts(v.base, v.shifts, v.beats, v.chapter), v.expected, v.why);
    assert.equal(JSON.stringify(v.base), before, "the base cards are not changed");
  });
}

for (const v of vectors.patch_validation) {
  test(`patch: ${v.name}`, () => {
    const got = validatePatch(schema, v.card, v.patch).map(({ code, field }) => ({ code, field }));
    assert.deepEqual(got, v.problems);
  });
}

test("a patch for a card that cannot be shifted is refused", () => {
  assert.equal(validatePatch(schema, "style", { person: "first" })[0].code, "unknown_card");
  assert.equal(validatePatch(schema, "setup", { chapter_count: 3 })[0].code, "unknown_card");
});

test("every problem has words for the writer", () => {
  for (const v of vectors.patch_validation) for (const p of validatePatch(schema, v.card, v.patch)) assert.ok(p.message && !p.message.startsWith("patch."), p.code);
});

test("applyPatch ignores an add of an id that is already there and keeps the rest", () => {
  const card = { wants: [{ id: "a", text: "x" }] };
  assert.deepEqual(applyPatch(card, { wants: [{ op: "add", id: "a", values: { text: "y" } }, { op: "add", id: "b", values: { text: "z" } }] }).wants.map((w) => w.id), ["a", "b"]);
});

const project = () => ({
  characters: [{ id: "c1", name: "Ines", fear: "the dark" }],
  world: { name: "W", places: [{ id: "p1", name: "Quay" }] },
  entanglements: { ties: [{ id: "t1", tie_from: "c1", tie_to: "g1", bond: "clerk", edge: "to hide it" }], holdings: [] },
  outline: { beats: [{ id: "b1", chapter: 1 }, { id: "b2", chapter: 2 }] },
  shifts: { entries: [
    { id: "s1", beat: "b1", card: "characters", target: "c1", patch: { fear: "fire" } },
    { id: "s2", beat: "b2", card: "world", target: null, patch: { places: [{ op: "add", id: "p2", values: { name: "Mill" } }] } },
  ] },
});

test("effectiveProject is the state going into a chapter and leaves the project alone", () => {
  const p = project();
  const was = JSON.stringify(p);
  assert.equal(effectiveProject(p, 1).characters[0].fear, "the dark");
  assert.equal(effectiveProject(p, 2).characters[0].fear, "fire");
  assert.equal(effectiveProject(p, 2).world.places.length, 1);
  assert.equal(effectiveProject(p, 3).world.places.length, 2);
  assert.equal(JSON.stringify(p), was);
});

test("foldAll applies every shift, and a project with none comes back the same", () => {
  assert.equal(foldAll(project()).world.places.length, 2);
  const bare = { characters: [{ id: "c1" }], outline: { beats: [] } };
  assert.deepEqual(foldAll(bare), bare);
});
