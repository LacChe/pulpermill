import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { story, opening, schema } from "./fixture.mjs";
import {
  pickSpotlight, requiredCast, tiesInPlay, groupsInPlay, holdingsInPlay, newBeat, ensureBeat, castProblem, planGate, planRequest, scene,
  landBeat, placeBeat, commitPlan, beatBlockers, planIsStale, planInputsHash, chapterInfo, beatForChapter, writtenBeatIds, castKey, staleBeatIds,
} from "../../web/plan.js";

const copy = (x) => JSON.parse(JSON.stringify(x));

test("where the story stands: chapters written, the next one, and whether it is done", () => {
  const p = story();
  assert.deepEqual(chapterInfo(p), { written: 1, next: 2, count: 8, done: false });
  p.setup.chapter_count = 1;
  assert.equal(chapterInfo(p).done, true);
  assert.deepEqual([...writtenBeatIds(p)], ["b0000001"]);
  assert.equal(beatForChapter(p, 2).id, "b0000002");
  assert.equal(beatForChapter(p, 1), null, "a written chapter's beat is not up for planning");
  assert.equal(castKey(["b", "a"]), castKey(["a", "b"]));
  p.outline.beats[1].stale = true;
  assert.deepEqual([...staleBeatIds(p)], ["b0000002"]);
});

test("the spotlight is a tie of the project, the same one every time, and null with no ties", () => {
  const p = story();
  const ids = new Set(p.entanglements.ties.map((t) => t.id));
  assert.ok(ids.has(pickSpotlight(p, 2).id));
  assert.equal(pickSpotlight(p, 2).id, pickSpotlight(copy(p), 2).id);
  const seen = new Set();
  for (let chapter = 1; chapter < 40; chapter++) seen.add(pickSpotlight(p, chapter).id);
  assert.equal(seen.size, 2, "every tie gets its turn");
  p.entanglements.ties = [];
  assert.equal(pickSpotlight(p, 2), null);
});

test("the spotlight is picked from the ties as they stand going into the chapter, shifts included", () => {
  const p = story();
  p.entanglements.ties = [];
  p.shifts.entries.push({ id: "s1", beat: "b0000001", card: "entanglements", target: null, patch: { ties: [{ op: "add", id: "t9", values: { tie_from: "c0000001", tie_to: "c0000002", bond: "x", edge: "y" } }] } });
  assert.equal(pickSpotlight(p, 2).id, "t9");
  assert.equal(pickSpotlight(p, 1), null);
});

test("the required cast is the protagonist and the two characters of the tie, never a group", () => {
  const p = story();
  assert.deepEqual(requiredCast(p, "t1000001"), ["c0000001", "c0000002"]);
  assert.deepEqual(requiredCast(p, "t1000002"), ["c0000001"], "the other end is a group");
  assert.deepEqual(requiredCast(p, "nope"), ["c0000001"]);
  p.characters.push({ id: "c0000003", name: "Joss" });
  p.entanglements.ties.push({ id: "t3", tie_from: "c0000003", tie_to: "c0000002", bond: "b", edge: "e" });
  assert.deepEqual(requiredCast(p, "t3"), ["c0000001", "c0000003", "c0000002"]);
});

function crowd() {
  const p = story();
  p.characters.push({ id: "c0000003", name: "Joss" });
  p.world.powers.push({ id: "g0000002", name: "The Guild" }, { id: "g0000003", name: "The Crown" });
  p.entanglements.ties.push(
    { id: "t3", tie_from: "c0000003", tie_to: "c0000001", bond: "rival", edge: "e" },          // cast member to a character who is out
    { id: "t4", tie_from: "c0000002", tie_to: "g0000002", bond: "owes", edge: "e" },           // cast member to a second group
    { id: "t5", tie_from: "g0000001", tie_to: "g0000002", bond: "feud", edge: "e" },           // two groups, both touch the cast
    { id: "t6", tie_from: "g0000002", tie_to: "g0000003", bond: "treaty", edge: "e" },         // one group touches the cast
    { id: "t7", tie_from: "g0000003", tie_to: "c0000003", bond: "hunts", edge: "e" },          // nobody in the cast
  );
  p.world.powers.push({ id: "g0000004", name: "Far" }, { id: "g0000005", name: "Away" });
  p.entanglements.ties.push({ id: "t8", tie_from: "g0000004", tie_to: "g0000005", bond: "far", edge: "e" });   // two groups that touch nobody
  return p;
}

test("ties in play: among the cast, cast to group, and group to group when one touches the cast; never a tie to an absent character", () => {
  const ids = (cast) => tiesInPlay(crowd(), cast).map((t) => t.id);
  assert.deepEqual(ids(["c0000001", "c0000002"]), ["t1000001", "t1000002", "t4", "t5", "t6"]);
  assert.deepEqual(ids(["c0000001"]), ["t1000002", "t5"], "t5 joins a group that touches the cast to another; t6 reaches one step further, through a group that does not touch the cast itself, so it is not sent");
  assert.deepEqual(ids([]), []);
});

test("the groups in play are the groups at the ends of ties in play, and their holdings are sent with them", () => {
  const p = crowd();
  p.entanglements.holdings.push({ id: "h2", holdee: "o0000001", held_by: "c0000002" }, { id: "h3", holdee: "p0000001", held_by: "g0000005" }, { id: "h4", holdee: "p0000002", held_by: "g0000002" });
  assert.deepEqual(groupsInPlay(p, ["c0000001", "c0000002"]).map((g) => g.id), ["g0000001", "g0000002", "g0000003"]);
  assert.deepEqual(holdingsInPlay(p, ["c0000001", "c0000002"]).map((h) => h.id), ["h1000001", "h2", "h4"]);
  assert.deepEqual(holdingsInPlay(p, ["c0000001"]).map((h) => h.id), ["h1000001", "h4"], "g0000002 is in play through the tie between the groups");
  assert.deepEqual(holdingsInPlay(p, ["c0000002"]).map((h) => h.id), ["h1000001", "h2", "h4"], "a cast member's own holdings, the group they touch, and the group at the other end of that group's tie");
});

test("a new beat has its code fields set, the picked spotlight, and the required cast", () => {
  const p = story();
  p.outline.beats = [p.outline.beats[0]];
  const beat = newBeat(schema, p, 2);
  const spot = pickSpotlight(p, 2).id;
  assert.equal(beat.chapter, 2);
  assert.equal(beat.spotlight, spot);
  assert.deepEqual(beat.cast, requiredCast(p, spot));
  assert.equal(beat.stale, false);
  assert.equal(beat.planned_from, null);
  assert.equal(beat.aim, "");
  assert.ok(beat.id && p.outline.beats.every((b) => b.id !== beat.id));
});

test("ensureBeat makes and places the next chapter's beat once", () => {
  const p = story();
  p.outline.beats = [p.outline.beats[0]];
  const first = ensureBeat(schema, p);
  assert.equal(first.chapter, 2);
  assert.equal(p.outline.beats.length, 2);
  assert.equal(ensureBeat(schema, p).id, first.id);
  assert.equal(p.outline.beats.length, 2);
});

test("a cast must have the protagonist, at most five, real characters, and the spotlight's pair", () => {
  const p = story();
  assert.equal(castProblem(p, ["c0000001", "c0000002"], "t1000001"), null);
  assert.equal(castProblem(p, [], null), "empty");
  assert.equal(castProblem(p, ["c0000002"], null), "no_protagonist");
  assert.equal(castProblem(p, ["c0000001", "zzz"], null), "unknown");
  assert.equal(castProblem(p, ["c0000001"], "t1000001"), "spotlight_pair");
  assert.equal(castProblem(p, ["c0000001"], "t1000002"), null);
  p.characters.push(...[3, 4, 5, 6].map((n) => ({ id: `c000000${n}`, name: `N${n}` })));
  assert.equal(castProblem(p, ["c0000001", "c0000002", "c0000003", "c0000004", "c0000005", "c0000006"], null), "too_many");
});

test("planning needs a started story, an open outline, a chapter to write, a tie and a sound cast", () => {
  const p = story();
  const beat = p.outline.beats[1];
  assert.deepEqual(planGate(p, beat), { ok: true, chapter: 2 });
  assert.equal(planGate({ ...p, locks: [] }, beat).reason, "not_started");
  assert.equal(planGate({ ...p, locks: [...p.locks, { id: "lx", card: "outline" }] }, beat).reason, "outline_locked");
  assert.equal(planGate({ ...p, setup: { ...p.setup, chapter_count: 1 } }, beat).reason, "done");
  assert.equal(planGate(p, { ...beat, spotlight: "nope" }).reason, "no_tie");
  assert.deepEqual(planGate(p, { ...beat, cast: ["c0000001"] }), { ok: false, reason: "cast", why: "spotlight_pair" });
});

test("the plan request caps every list at five with the scene's own items kept, and is the same every time", () => {
  const p = story();
  for (let i = 0; i < 9; i++) {
    p.world.places.push({ id: `px${i}`, name: `Place ${i}` });
    p.world.objects.push({ id: `ox${i}`, name: `Object ${i}` });
    p.world.rules.push({ id: `rx${i}`, statement: `Rule ${i}` });
    p.world.terms.push({ id: `tx${i}`, term: `Term ${i}` });
  }
  p.characters[0].behaviors = Array.from({ length: 8 }, (_, i) => ({ id: `bx${i}`, state: `s${i}`, tendency: `t${i}` }));
  const request = planRequest(schema, p, p.outline.beats[1]);
  assert.equal(request.world.places.length, 5);
  assert.equal(request.world.rules.length, 5);
  assert.equal(request.world.terms.length, 5);
  assert.equal(request.world.objects.length, 5);
  assert.ok(request.world.objects.some((o) => o.id === "o0000001"), "the ledger is held by a group in play, so it is always sent");
  assert.equal(request.cast[0].behaviors.length, 5);
  assert.deepEqual(request, planRequest(schema, copy(p), p.outline.beats[1]));
  const next = planRequest(schema, p, { ...p.outline.beats[1], chapter: 3 });
  assert.notDeepEqual(request.world.rules, next.world.rules, "another chapter draws other rules");
});

test("the generate request always carries the beat's place, even when picks would drop it", () => {
  const p = story();
  for (let i = 0; i < 12; i++) p.world.places.push({ id: `px${i}`, name: `Place ${i}` });
  const beat = { ...p.outline.beats[1], where: "px7" };
  const request = scene(p, 2, beat.cast, { where: beat.where });
  assert.ok(request.world.places.some((x) => x.id === "px7"));
  assert.equal(request.world.places.length, 5);
});

test("only the groups in play are sent, and the cast cards come in the beat's order", () => {
  const p = crowd();
  const request = planRequest(schema, p, { ...p.outline.beats[1], cast: ["c0000002", "c0000001"] });
  assert.deepEqual(request.cast.map((c) => c.id), ["c0000002", "c0000001"]);
  assert.deepEqual(request.world.powers.map((g) => g.id), ["g0000001", "g0000002", "g0000003"]);
  assert.equal(request.ties.some((t) => t.id === "t3"), false);
});

test("the request is built from the effective cards: shifts of earlier chapters count, later ones do not", () => {
  const p = story();
  p.shifts.entries.push({ id: "s1", beat: "b0000001", card: "characters", target: "c0000001", patch: { fear: "Fire" } });
  p.shifts.entries.push({ id: "s2", beat: "b0000002", card: "characters", target: "c0000001", patch: { fear: "Water" } });
  assert.equal(planRequest(schema, p, p.outline.beats[1]).cast[0].fear, "Fire");
  assert.equal(p.characters[0].fear, "Being found out", "the base card is never changed");
});

test("a plan goes stale when the cast cards, the ties or the picks it was made from change", () => {
  const p = story();
  const beat = p.outline.beats[1];
  const landed = landBeat(schema, p, beat, { ok: true, beat: { where: "The Archive", when_time: "Dusk", aim: "Suvi wants it.", plan: "A plan." } });
  placeBeat(p, landed.beat);
  assert.equal(planIsStale(p, landed.beat), false);
  assert.equal(planIsStale(p, { ...landed.beat, planned_from: null }), false, "a plan from before the hash is never called stale");
  const edit = (change) => { const q = copy(p); change(q); return planIsStale(q, q.outline.beats[1]); };
  assert.equal(edit((q) => { q.characters[1].sketch = "Changed"; }), true);
  assert.equal(edit((q) => { q.entanglements.ties[0].edge = "changed"; }), true);
  assert.equal(edit((q) => { q.outline.beats[1].spotlight = "t1000002"; }), true);
  assert.equal(edit((q) => { q.shifts.entries.push({ id: "s1", beat: "b0000001", card: "characters", target: "c0000001", patch: { fear: "x" } }); }), true);
  assert.equal(edit((q) => { q.outline.beats[1].aim = "A different aim"; }), false, "the plan's own words are not its inputs");
  assert.equal(planInputsHash(p, landed.beat), landed.beat.planned_from);
});

test("landing a plan: the words become ids, the code fields stay, and what did not match is reported", () => {
  const p = story();
  const beat = { ...p.outline.beats[1], where: "", aim: "", plan: "" };
  const ok = landBeat(schema, p, beat, { ok: true, beat: { where: "the archive", when_time: " Dusk ", aim: "Aim.", plan: "Plan." } });
  assert.deepEqual([ok.beat.where, ok.beat.when_time, ok.beat.aim, ok.beat.plan], ["p0000001", "Dusk", "Aim.", "Plan."]);
  assert.deepEqual([ok.beat.id, ok.beat.chapter, ok.beat.spotlight, ok.beat.cast, ok.beat.stale], [beat.id, 2, beat.spotlight, beat.cast, false]);
  assert.match(ok.beat.planned_from, /^[0-9a-f]{8}$/);
  const lost = landBeat(schema, p, beat, { ok: true, beat: { where: "The Moon", aim: "Aim.", cast: ["x"], spotlight: "t", extra: "y" } });
  assert.equal(lost.beat.where, "");
  assert.deepEqual(lost.unresolved.map((u) => [u.key, u.why]), [["where", "none"]]);
  assert.deepEqual(lost.dropped.sort(), ["cast", "extra", "spotlight"]);
  assert.deepEqual([lost.beat.cast, lost.beat.spotlight], [beat.cast, beat.spotlight], "the model never changes the cast or the tie");
  assert.deepEqual(landBeat(schema, p, beat, { ok: true, beat: { aim: 5 } }).dropped, ["aim"]);
});

test("a place the story added in an earlier chapter can be the beat's place", () => {
  const p = story();
  p.shifts.entries.push({ id: "s1", beat: "b0000001", card: "world", target: null, patch: { places: [{ op: "add", id: "p9", values: { name: "The Mill", description: "d", effect: "e" } }] } });
  const landed = landBeat(schema, p, p.outline.beats[1], { ok: true, beat: { where: "The Mill" } });
  assert.equal(landed.beat.where, "p9");
});

test("placing a beat replaces the one with its id, or adds it", () => {
  const p = story();
  const was = placeBeat(p, { ...p.outline.beats[1], aim: "New" });
  assert.equal(was.aim, "Suvi wants the ledger out before the board counts.");
  assert.equal(p.outline.beats.length, 2);
  assert.equal(placeBeat(p, { id: "bnew", chapter: 3 }), null);
  assert.equal(p.outline.beats.length, 3);
});

test("the Outline's block rules judge the beat against the cards going into its chapter", () => {
  const p = story();
  const good = { ...p.outline.beats[1] };
  assert.deepEqual(beatBlockers(schema, p, good), []);
  const blocked = beatBlockers(schema, p, { ...good, cast: ["c0000002"] });
  assert.ok(blocked.length > 0, "a cast without the protagonist is blocked");
  const same = beatBlockers(schema, p, { ...good, aim: p.outline.beats[0].aim });
  assert.ok(Array.isArray(same));
  assert.equal(p.outline.beats.length, 2, "checking leaves the project alone");
  const withMill = story();
  withMill.shifts.entries.push({ id: "s1", beat: "b0000001", card: "world", target: null, patch: { places: [{ op: "add", id: "p9", values: { name: "The Mill", description: "d", effect: "e" } }] } });
  assert.deepEqual(beatBlockers(schema, withMill, { ...good, where: "p9" }), [], "a place the story added is a place");
  assert.ok(beatBlockers(schema, story(), { ...good, where: "p9" }).length > 0, "and without the shift it is not");
});

test("the first chapter's plan has no earlier beats or events", () => {
  const o = opening();
  const request = planRequest(schema, o, o.outline.beats[0]);
  assert.deepEqual([request.chapter, request.earlier_beats, request.earlier_events], [1, [], []]);
});

test("landing a plan is one commit with an undo that refuses when the Outline was edited since", () => {
  const p = story();
  const was = JSON.stringify(p.outline);
  const { undo } = commitPlan(p, { ...p.outline.beats[1], aim: "A new aim." });
  assert.equal(p.outline.beats[1].aim, "A new aim.");
  assert.equal(undo(), true);
  assert.equal(JSON.stringify(p.outline), was);
  const second = commitPlan(p, { ...p.outline.beats[1], aim: "Again." });
  p.outline.beats[1].plan = "Edited by hand.";
  assert.equal(second.undo(), false);
  assert.equal(p.outline.beats[1].aim, "Again.");
});
