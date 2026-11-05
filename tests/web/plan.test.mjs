import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { story, opening, schema } from "./fixture.mjs";
import {
  pickSpotlight, requiredCast, tiesInPlay, groupsInPlay, holdingsInPlay, newBeat, ensureBeat, castProblem, planGate, planRequest, scene,
  landBeat, placeBeat, commitPlan, beatBlockers, planIsStale, planInputsHash, chapterInfo, beatForChapter, writtenBeatIds, castKey, staleBeatIds, spotlightEdges, earlierBeats,
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
  p.entanglements.ties.push({ id: "t1000003", tie_from: "c0000001", tie_to: "c0000002", bond: "friend", edge: "to stay close" });   // a second tie between two people; the one to the Board is a group tie
  const ids = new Set(p.entanglements.ties.filter((t) => t.id !== "t1000002").map((t) => t.id));
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

test("a new beat's cast is the required members, then the other characters in card order, up to five", () => {
  const p = story();
  p.outline.beats = [p.outline.beats[0]];
  p.characters.push({ id: "c0000003", name: "Joss" });
  const three = newBeat(schema, p, 2);
  assert.equal(three.cast.length, 3, "3 characters: everyone is in");
  assert.deepEqual(three.cast.slice(0, requiredCast(p, three.spotlight).length), requiredCast(p, three.spotlight));
  for (let i = 4; i <= 6; i++) p.characters.push({ id: `c000000${i}`, name: `Extra ${i}` });
  const six = newBeat(schema, p, 2);
  const need = requiredCast(p, six.spotlight);
  assert.equal(six.cast.length, 5, "6 characters: the cast stops at five");
  assert.deepEqual(six.cast.slice(0, need.length), need, "the required members come first");
  const rest = p.characters.map((c) => c.id).filter((id) => !need.includes(id));
  assert.deepEqual(six.cast.slice(need.length), rest.slice(0, 5 - need.length), "then the others in card order");
  assert.equal(castProblem(p, six.cast, six.spotlight), null);
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

// ---- The edge trail (the spotlight tie's edges in earlier chapters) ----

// Three chapters written and the fourth beat planned. The tie "t1000001" starts as "to bring her daughter home", and shifts of chapters 2 and
// 3 change its edge, so going into chapters 1, 2, 3, 4 it reads: home, home, stay, trust.
function threeChapters() {
  const p = story();
  const tie = "t1000001";
  const edgeShift = (id, beat, edge) => ({ id, beat, card: "entanglements", target: null, patch: { ties: [{ op: "replace", id: tie, values: { edge } }] } });
  p.outline.beats.push(
    { id: "b0000003", chapter: 3, where: "p0000001", when_time: "Night", cast: ["c0000001", "c0000002"], spotlight: tie, aim: "Suvi wants out.", plan: "She runs." },
    { id: "b0000004", chapter: 4, where: "p0000002", when_time: "Dawn", cast: ["c0000001", "c0000002"], spotlight: tie, aim: "", plan: "" });
  p.chapters.push({ id: "k0000002", beat: "b0000002", text: "Chapter two." }, { id: "k0000003", beat: "b0000003", text: "Chapter three." });
  p.summary_events.entries.push({ id: "e0000002", beat: "b0000002", happened: "Two.", changed: "" }, { id: "e0000003", beat: "b0000003", happened: "Three.", changed: "" });
  p.shifts.entries.push(edgeShift("s0000001", "b0000002", "to make her daughter stay"), edgeShift("s0000002", "b0000003", "to trust her daughter"));
  return p;
}

test("the edge trail lists the tie's earlier edges oldest first and leaves out the current one", () => {
  const p = threeChapters();
  assert.deepEqual(spotlightEdges(p, "t1000001", 4), ["to bring her daughter home", "to make her daughter stay"], "going into chapter 4 the edge is 'trust'");
  assert.deepEqual(spotlightEdges(p, "t1000001", 3), ["to bring her daughter home"]);
  assert.deepEqual(spotlightEdges(p, "t1000001", 2), [], "the edge has not changed yet, so there is nothing earlier");
  assert.deepEqual(spotlightEdges(p, "t1000001", 1), []);
});

test("an edge that stays the same for several chapters is listed once, and one that comes back is listed again", () => {
  const p = threeChapters();
  p.shifts.entries.push({ id: "s0000003", beat: "b0000003", card: "entanglements", target: null, patch: { ties: [{ op: "replace", id: "t1000001", values: { bond: "mother and daughter" } }] } });
  assert.deepEqual(spotlightEdges(p, "t1000001", 4), ["to bring her daughter home", "to make her daughter stay"], "a shift that leaves the edge alone adds nothing");
  p.outline.beats.push({ id: "b0000004x", chapter: 4, where: "p0000001", when_time: "Noon", cast: [], spotlight: "t1000001", aim: "", plan: "" });
  p.shifts.entries.push({ id: "s0000004", beat: "b0000004", card: "entanglements", target: null, patch: { ties: [{ op: "replace", id: "t1000001", values: { edge: "to bring her daughter home" } }] } });
  assert.deepEqual(spotlightEdges(p, "t1000001", 5), ["to bring her daughter home", "to make her daughter stay", "to trust her daughter"]);
});

test("a tie that did not exist yet, or has no edge, adds nothing to the trail", () => {
  const p = threeChapters();
  p.entanglements.ties.push({ id: "t1000009", tie_from: "c0000001", tie_to: "c0000002", bond: "friend", edge: "" });
  assert.deepEqual(spotlightEdges(p, "t1000009", 4), []);
  p.shifts.entries.push({ id: "s0000005", beat: "b0000002", card: "entanglements", target: null, patch: { ties: [{ op: "replace", id: "t1000009", values: { edge: "to keep a secret" } }] } });
  assert.deepEqual(spotlightEdges(p, "t1000009", 4), [], "from chapter 3 on the edge is the same one, and that is the current one");
  assert.deepEqual(spotlightEdges(p, "t1999999", 4), [], "no such tie");
  assert.deepEqual(spotlightEdges(p, "", 4), []);
  assert.deepEqual(spotlightEdges(p, null, 4), []);
});

test("the plan request carries the trail, an empty one for chapter 1 and for a tie that never changed", () => {
  const p = threeChapters();
  const beat4 = p.outline.beats.find((b) => b.id === "b0000004");
  assert.deepEqual(planRequest(schema, p, beat4).spotlight_edges, ["to bring her daughter home", "to make her daughter stay"]);
  assert.deepEqual(planRequest(schema, p, { ...beat4, spotlight: "t1000002" }).spotlight_edges, [], "the Board tie's edge never changed");
  assert.deepEqual(planRequest(schema, story(), story().outline.beats[1]).spotlight_edges, []);
  const first = opening();
  assert.deepEqual(planRequest(schema, first, first.outline.beats[0]).spotlight_edges, []);
  assert.deepEqual(planRequest(schema, p, beat4), planRequest(schema, copy(p), beat4), "asking again gives the same request");
});

test("working out the trail changes nothing in the project", () => {
  const p = threeChapters();
  const before = JSON.stringify(p);
  spotlightEdges(p, "t1000001", 4);
  planRequest(schema, p, p.outline.beats.find((b) => b.id === "b0000004"));
  assert.equal(JSON.stringify(p), before);
});

// ---- The planner chooses the tie and the pressure (combination-select, stage 1) ----

function twoTieStory() {
  const p = story();
  p.entanglements.ties.push({ id: "t1000003", tie_from: "c0000001", tie_to: "c0000002", bond: "friend", edge: "to stay close" });
  return p;
}
const planned = { where: "The Archive", when_time: "Dusk", aim: "Suvi wants it.", plan: "A plan." };

test("a plan request asks to choose only when told to, and then carries every rule and object with its id", () => {
  const p = twoTieStory();
  const beat = p.outline.beats[1];
  const plain = planRequest(schema, p, beat);
  assert.equal("choose" in plain || "pressure_options" in plain, false, "without choose the request is exactly as it was");
  assert.deepEqual(planRequest(schema, p, beat, { choose: false }), plain);
  const asked = planRequest(schema, p, beat, { choose: true });
  assert.equal(asked.choose, true);
  assert.deepEqual(asked.pressure_options.map((o) => [o.id, o.kind]), [["r0000001", "rule"], ["o0000001", "object"]]);
  assert.equal(asked.pressure_options[1].name, "The ledger");
  assert.equal(asked.spotlight, beat.spotlight, "the page's own pair stays as the fallback");
  assert.deepEqual({ ...asked, choose: undefined, pressure_options: undefined }, { ...plain, choose: undefined, pressure_options: undefined });
});

test("a valid pick sets the beat's tie and pressure before the plan's hash is taken", () => {
  const p = twoTieStory();
  const beat = p.outline.beats[1];
  const landed = landBeat(schema, p, beat, { ok: true, beat: planned, picked: { spotlight: "t1000003", pressure: "r0000001" } });
  assert.deepEqual([landed.beat.spotlight, landed.beat.pressure], ["t1000003", "r0000001"]);
  assert.deepEqual(landed.warnings, []);
  assert.equal(landed.beat.planned_from, planInputsHash(p, landed.beat), "the plan does not look stale at once");
  placeBeat(p, landed.beat);
  assert.equal(planIsStale(p, landed.beat), false);
  const none = landBeat(schema, p, { ...beat, pressure: "o0000001" }, { ok: true, beat: planned, picked: { spotlight: "t1000003", pressure: null } });
  assert.equal("pressure" in none.beat, false, "a null pressure takes the pressure off the beat");
  assert.equal(none.beat.spotlight, "t1000003");
});

test("a pick that is not in the story is ignored with one warning", () => {
  const p = twoTieStory();
  const beat = { ...p.outline.beats[1], pressure: "o0000001" };
  for (const picked of [{ spotlight: "t1000002", pressure: null }, { spotlight: "nope", pressure: null }, { spotlight: "t1000003", pressure: "nope" }]) {
    const landed = landBeat(schema, p, beat, { ok: true, beat: planned, picked });
    assert.deepEqual([landed.beat.spotlight, landed.beat.pressure], [beat.spotlight, "o0000001"], JSON.stringify(picked));
    assert.equal(landed.warnings.length, 1);
    assert.equal(landed.beat.planned_from, planInputsHash(p, landed.beat));
  }
  const outside = landBeat(schema, p, { ...beat, cast: ["c0000001"] }, { ok: true, beat: planned, picked: { spotlight: "t1000003", pressure: null } });
  assert.equal(outside.warnings.length, 1, "a tie with an end outside the cast is not taken");
});

// ---- The planner sees what earlier chapters used (combination-select, stage 3) ----

test("earlier beats carry the two people of the tie and the pressure in a few words, and leave out what is gone", () => {
  const p = twoTieStory();
  const [first] = p.outline.beats;
  const tie = p.entanglements.ties.find((t) => t.id === "t1000001");
  Object.assign(first, { spotlight: "t1000001", pressure: "r0000001" });
  const [rule] = earlierBeats(p, 2);
  assert.equal(rule.tie, "Marit and Suvi", "both names, joined with and");
  assert.equal(rule.pressure, "Debts are written, never spoken.", "a rule by its statement");
  assert.ok(!rule.tie.includes(tie.edge) && !rule.tie.includes(tie.bond), "no edge and no bond: the edge changes from chapter to chapter");
  first.pressure = "o0000001";
  assert.equal(earlierBeats(p, 2)[0].pressure, "The ledger", "an object by its name");
  delete first.pressure;
  assert.equal("pressure" in earlierBeats(p, 2)[0], false, "no pressure on the beat: no key");
  first.pressure = "r9999999";
  assert.equal("pressure" in earlierBeats(p, 2)[0], false, "a pressure that is gone: no key");
  first.spotlight = "gone";
  assert.equal("tie" in earlierBeats(p, 2)[0], false, "a tie that is gone: no key");
  p.entanglements.ties.push({ id: "t9000001", tie_from: "c0000001", tie_to: "c9999999", bond: "friend", edge: "to stay close" });
  first.spotlight = "t9000001";
  assert.equal("tie" in earlierBeats(p, 2)[0], false, "a tie with an end that is gone: no key");
  delete first.spotlight;
  const bare = earlierBeats(p, 2)[0];
  assert.deepEqual(Object.keys(bare), ["chapter", "where", "when", "aim", "plan"], "a beat with neither keeps today's shape");
});
