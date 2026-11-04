import "./text-setup.mjs";
import test, { afterEach } from "node:test";
import assert from "node:assert/strict";
import { story, opening, schema } from "./fixture.mjs";
import {
  newBeat, pickPressure, pressureOf, pressureInWords, pressureElements, readPressureFlag, setPressureFlag, pressureOn,
  planRequest, scene, planInputsHash, planIsStale,
} from "../../web/plan.js";
import { generateRequest } from "../../web/generate.js";

const copy = (x) => JSON.parse(JSON.stringify(x));
afterEach(() => setPressureFlag(false));

// The fixture story with a bigger world, so the seeded 5-item cut has something to drop: 12 rules and 12 objects.
function bigWorld() {
  const p = story();
  p.world.rules = Array.from({ length: 12 }, (_, i) => ({ id: `r00000${String(i).padStart(2, "0")}`, statement: `Rule ${i}.`, cost: `Cost ${i}.`, when_broken: `Broken ${i}.` }));
  p.world.objects = Array.from({ length: 12 }, (_, i) => ({ id: `o00000${String(i).padStart(2, "0")}`, name: `Thing ${i}`, description: `Looks ${i}.`, significance: `Does ${i}.` }));
  return p;
}
const ids = (list) => list.map((x) => x.id);

test("the flag is on only for ?pressure=on in the page address", () => {
  assert.equal(readPressureFlag("?pressure=on"), true);
  assert.equal(readPressureFlag("?x=1&pressure=on"), true);
  for (const s of ["", "?pressure=off", "?pressure=", "?pressure=1", "?pressures=on"]) assert.equal(readPressureFlag(s), false, s);
  assert.equal(pressureOn(), false, "off by default");
});

test("flag off: a new beat has no pressure field, and requests, scene() and the hash are what they were", () => {
  const p = story();
  p.outline.beats[1].pressure = "r0000001";                // even a beat that carries one sends nothing while the flag is off
  const clean = copy(p);
  delete clean.outline.beats[1].pressure;

  assert.equal("pressure" in newBeat(schema, p, 2), false);
  const withField = planRequest(schema, p, p.outline.beats[1]);
  const without = planRequest(schema, clean, clean.outline.beats[1]);
  assert.deepEqual(withField, without);
  assert.equal("pressure" in withField, false);
  assert.deepEqual(generateRequest(schema, p, p.outline.beats[1]), generateRequest(schema, clean, clean.outline.beats[1]));
  assert.equal("pressure" in generateRequest(schema, p, p.outline.beats[1]), false);
  assert.equal(planInputsHash(p, p.outline.beats[1]), planInputsHash(clean, clean.outline.beats[1]));
  assert.deepEqual(scene(p, 2, ["c0000001"], { pressure: null }), scene(p, 2, ["c0000001"]));
  assert.equal(pickPressure(p, 2), null);
});

test("flag on: a new beat gets one rule or object, the same one when asked again", () => {
  setPressureFlag(true);
  const p = bigWorld();
  const all = new Set(pressureElements(p).map((e) => e.id));
  const first = newBeat(schema, p, 2).pressure;
  assert.ok(all.has(first));
  assert.equal(newBeat(schema, copy(p), 2).pressure, first, "same project and chapter, same element");
  assert.equal(pickPressure(p, 2), first);
});

test("flag on: a different chapter or a different seed can give a different element", () => {
  setPressureFlag(true);
  const p = bigWorld();
  const byChapter = new Set([1, 2, 3, 4, 5, 6, 7, 8].map((c) => pickPressure(p, c)));
  assert.ok(byChapter.size > 1, "chapters do not all draw the same element");
  const bySeed = new Set(["pr000001", "pr000002", "pr000003", "pr000004", "pr000005", "pr000006"].map((id) => pickPressure({ ...p, id }, 2)));
  assert.ok(bySeed.size > 1, "seeds do not all draw the same element");
  const kinds = new Set(pressureElements(p).filter((e) => byChapter.has(e.id)).map((e) => e.kind));
  assert.ok([...kinds].every((k) => k === "rule" || k === "object"));
});

test("flag on: nothing earlier is looked at, so the same element may come twice in a row", () => {
  setPressureFlag(true);
  const p = story();
  p.world.rules = [];                                      // one object only: every chapter draws it
  const a = pickPressure(p, 2);
  p.outline.beats[1].pressure = a;
  assert.equal(pickPressure(p, 3), a);
});

test("flag on: a world with no rules and no objects gives none, and the beat has no field", () => {
  setPressureFlag(true);
  const p = story();
  p.world.rules = []; p.world.objects = [];
  assert.equal(pickPressure(p, 2), null);
  assert.equal("pressure" in newBeat(schema, p, 2), false);
});

test("the pick follows the cards as they stand going into the chapter", () => {
  setPressureFlag(true);
  const p = story();
  p.world.rules = [{ id: "r0000001", statement: "Debts are written, never spoken.", cost: "c", when_broken: "w" }];
  p.world.objects = [];
  assert.equal(pickPressure(p, 2), "r0000001");
});

test("the picked element is in the scene's lists even when the 5-item cut would drop it", () => {
  setPressureFlag(true);
  const p = bigWorld();
  let droppedWithout = 0;
  for (const element of pressureElements(p)) {
    const base = scene(p, 2, ["c0000001"]);
    const kept = scene(p, 2, ["c0000001"], { pressure: element.id });
    const list = element.kind === "rule" ? "rules" : "objects";
    assert.ok(ids(kept.world[list]).includes(element.id), `${element.id} is in world.${list}`);
    if (!ids(base.world[list]).includes(element.id)) droppedWithout++;
    assert.ok(kept.world[list].length <= 6, "the cut still holds: at most 5 and the pressure");
  }
  assert.ok(droppedWithout > 0, "the cut did drop some element without the pressure, so this test shows something");
});

test("the request carries the pressure in words, no id, and the same element is in the world lists", () => {
  setPressureFlag(true);
  const p = bigWorld();
  for (const id of [p.world.rules[7].id, p.world.objects[9].id]) {
    const beat = { ...p.outline.beats[1], pressure: id };
    for (const request of [planRequest(schema, p, beat), generateRequest(schema, p, beat)]) {
      const w = request.pressure;
      assert.ok(w && !("id" in w));
      if (w.kind === "rule") {
        assert.deepEqual(Object.keys(w), ["kind", "statement", "cost", "when_broken"]);
        assert.ok(request.world.rules.some((r) => r.statement === w.statement));
      } else {
        assert.deepEqual(Object.keys(w), ["kind", "name", "description", "significance"]);
        assert.ok(request.world.objects.some((o) => o.name === w.name));
      }
    }
  }
  const s = story();
  assert.deepEqual(pressureInWords(s, { pressure: "r0000001" }), { kind: "rule", statement: "Debts are written, never spoken.", cost: "A spoken debt is void.", when_broken: "The board is shamed." });
  assert.deepEqual(pressureInWords(s, { pressure: "o0000001" }), { kind: "object", name: "The ledger", description: "Green cloth cover.", significance: "Names who owes the board." });
});

test("a pressure whose id no longer exists, or none at all, is left out of the request", () => {
  setPressureFlag(true);
  const p = story();
  const gone = { ...p.outline.beats[1], pressure: "r9999999" };
  assert.equal(pressureOf(p, gone), null);
  assert.equal("pressure" in planRequest(schema, p, gone), false);
  assert.equal("pressure" in generateRequest(schema, p, gone), false);
  assert.equal("pressure" in planRequest(schema, p, { ...p.outline.beats[1], pressure: "" }), false);
});

test("changing or clearing the pressure makes a planned beat stale; the same pressure does not", () => {
  setPressureFlag(true);
  const p = story();
  const beat = p.outline.beats[1];
  beat.pressure = "r0000001";
  beat.planned_from = planInputsHash(p, beat);
  assert.equal(planIsStale(p, beat), false);
  assert.equal(planIsStale(p, { ...beat, pressure: "o0000001" }), true, "another element");
  const cleared = { ...beat, pressure: "" };
  assert.equal(planIsStale(p, cleared), true, "cleared");
  delete cleared.pressure;
  assert.equal(planIsStale(p, cleared), true, "cleared, field gone");
});

test("the hash holds the pressure's id only when the flag is on and one is set", () => {
  const p = story();
  const beat = { ...p.outline.beats[1] };
  const plain = planInputsHash(p, beat);
  assert.equal(planInputsHash(p, { ...beat, pressure: "r0000001" }), plain, "flag off");
  setPressureFlag(true);
  assert.equal(planInputsHash(p, beat), plain, "flag on, none set");
  assert.notEqual(planInputsHash(p, { ...beat, pressure: "r0000001" }), plain, "flag on, one set");
});

test("the opening story, planned for chapter 1, takes a pressure like any other chapter", () => {
  setPressureFlag(true);
  const p = opening();
  const beat = newBeat(schema, p, 1);
  assert.ok(!beat.pressure || pressureElements(p).some((e) => e.id === beat.pressure));
});
