import test from "node:test";
import assert from "node:assert/strict";
import { rng, pickMany, projectSeed } from "../../web/pick.js";

const items = Array.from({ length: 12 }, (_, i) => ({ id: `i${i}` }));

test("the same project, chapter and salt give the same numbers; another salt or chapter gives others", () => {
  const take = (...args) => { const r = rng(...args); return [r(), r(), r()]; };
  assert.deepEqual(take("p", 2, "places"), take("p", 2, "places"));
  assert.notDeepEqual(take("p", 2, "places"), take("p", 2, "objects"));
  assert.notDeepEqual(take("p", 2, "places"), take("p", 3, "places"));
  for (const n of take("p", 1)) assert.ok(n >= 0 && n < 1);
});

test("pickMany returns at most n, in the list's order, the same every time", () => {
  const a = pickMany(items, 5, rng("p", 1, "x"));
  assert.equal(a.length, 5);
  assert.deepEqual(a, pickMany(items, 5, rng("p", 1, "x")));
  assert.deepEqual(a.map((i) => i.id), [...a.map((i) => i.id)].sort((x, y) => Number(x.slice(1)) - Number(y.slice(1))));
  assert.notDeepEqual(a, pickMany(items, 5, rng("p", 1, "y")));
});

test("a short list comes back whole, and an empty or missing one comes back empty", () => {
  assert.deepEqual(pickMany(items.slice(0, 3), 5, rng("p", 1)), items.slice(0, 3));
  assert.deepEqual(pickMany([], 5, rng("p", 1)), []);
  assert.deepEqual(pickMany(undefined, 5, rng("p", 1)), []);
});

test("what the scene needs is always in, ids or items, and is never cut", () => {
  for (const must of [["i11", "i0"], [items[11], items[0]]]) {
    for (let chapter = 1; chapter < 20; chapter++) {
      const got = pickMany(items, 5, rng("p", chapter), { must }).map((i) => i.id);
      assert.equal(got.length, 5);
      assert.ok(got.includes("i11") && got.includes("i0"));
    }
  }
  assert.equal(pickMany(items, 2, rng("p", 1), { must: ["i1", "i2", "i3"] }).length, 3);
  assert.deepEqual(pickMany(items, 5, rng("p", 1), { must: ["nobody"] }).length, 5);
});

test("every item gets picked sometimes", () => {
  const seen = new Set();
  for (let chapter = 1; chapter <= 60; chapter++) for (const i of pickMany(items, 5, rng("p", chapter))) seen.add(i.id);
  assert.equal(seen.size, items.length);
});

test("a project is seeded by its id, then its title", () => {
  assert.equal(projectSeed({ id: "abc", title: "T" }), "abc");
  assert.equal(projectSeed({ title: "T" }), "T");
  assert.equal(projectSeed({}), "");
});
