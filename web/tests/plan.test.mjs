import "./text-setup.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { addInstance, addItem, readPlanReply } from "../logic.js";
import { createMock } from "../mock.js";
import { lockStaticCards } from "../gate.js";
import { schema, readyProject } from "./helpers.mjs";
import {
  CAST_MAX, chapterInfo, currentGoal, openPlants, availableReveals, useCounts, castChoices, duePressure, suggestedCast, castProblem,
  pickSpotlight, shiftsForChapter, offstageDue, entanglementsHash, planIsStale, planGate, planRequest, offstageRequest,
  latestShifts, landBeat, placeBeat, beatBlockers, beatForChapter,
} from "../plan.js";

const world = schema.cards.world;
const rulesField = world.fields.find((f) => f.key === "rules");

// A started story with three people and a hidden rule, nothing written yet.
async function started() {
  const p = await readyProject();
  const mia = addInstance(p, schema.cards.characters);
  mia.name = "Mia";
  const rule = addItem(rulesField, p.world.rules);
  Object.assign(rule, { statement: "The ledger can be read only at low tide", status: "uncommon", truth: "It is written in tide ink." });
  p.setup.chapter_count = 6;
  p.setup.goal = "Find the ledger.";
  return lockStaticCards(p);
}

// Writes chapter n into the project by hand: a beat, a chapter that points at it, and an events entry.
function writeChapter(p, n, { cast, where, spotlight, shift = "harder", events = {}, beat = {} }) {
  const id = `b000000${n}`;
  (p.outline ??= { beats: [] }).beats.push({ id, chapter: n, where, cast, spotlight, shift, turn: `Turn ${n}`, ...beat });
  // The text names the cast and the place: a value only counts as used when the written chapter says it.
  const named = [...cast.map((c) => p.characters.find((x) => x.id === c)?.name), p.world.places.find((x) => x.id === where)?.name].filter(Boolean);
  (p.chapters ??= []).push({ id: `ch00000${n}`, beat: id, text: `Chapter ${n}. ${named.join(" and ")} were there.` });
  (p.summary_events ??= { entries: [] }).entries.push({ id: `e000000${n}`, beat: id, happened: `Happened ${n}`, ...events });
  return id;
}

test("the chapter being planned is the one after the last written", async () => {
  const p = await started();
  assert.deepEqual(chapterInfo(p), { written: 0, next: 1, count: 6, done: false });
  const [suvi, , mia] = p.characters;
  writeChapter(p, 1, { cast: [suvi.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id });
  assert.equal(chapterInfo(p).next, 2);
  p.setup.chapter_count = 1;
  assert.equal(chapterInfo(p).done, true);
  assert.equal(mia.name, "Mia");
});

test("the current goal is Setup's, replaced by a redefinition that landed, and gone after one that ended it", async () => {
  const p = await started();
  const [suvi] = p.characters;
  const common = { cast: [suvi.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id };
  assert.equal(currentGoal(p), "Find the ledger.");
  writeChapter(p, 1, { ...common, beat: { goal_change: "redefined", goal_now: "Get the ledger out of the city." }, events: { goal_landed: false } });
  assert.equal(currentGoal(p), "Find the ledger.", "planned is not done: it did not land");
  p.summary_events.entries[0].goal_landed = true;
  assert.equal(currentGoal(p), "Get the ledger out of the city.");
  writeChapter(p, 2, { ...common, beat: { goal_change: "achieved" }, events: { goal_landed: true } });
  assert.equal(currentGoal(p), null, "once achieved there is no goal and the story winds down");
});

test("an open plant is one planted and not yet paid off, and a reveal is available until it lands", async () => {
  const p = await started();
  const [suvi] = p.characters;
  const common = { cast: [suvi.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id };
  const rule = p.world.rules.find((r) => r.statement.startsWith("The ledger"));
  assert.deepEqual(availableReveals(p).map((r) => r.statement), ["The ledger can be read only at low tide"]);
  writeChapter(p, 1, { ...common, events: { planted: "A torn page", reveals_landed: [rule.id] } });
  assert.deepEqual(openPlants(p), [{ id: "e0000001", text: "A torn page", chapter: 1 }]);
  assert.deepEqual(availableReveals(p), []);
  writeChapter(p, 2, { ...common, events: { paid_off: ["e0000001"] } });
  assert.deepEqual(openPlants(p), []);
});

test("common rules are never offered as reveals", async () => {
  const p = await started();
  p.world.rules.forEach((r) => { r.status = "common"; });
  assert.deepEqual(availableReveals(p), []);
});

test("the cast suggestion is the protagonist and the two least-used others, and every character is a choice", async () => {
  const p = await started();
  const [suvi, ola, mia] = p.characters;
  const extra = addInstance(p, schema.cards.characters);
  extra.name = "Dov";
  p.entanglements.pressures[0].source_agent = suvi.id;      // a pressure that involves only the protagonist, so use counts decide
  p.entanglements.pressures[0].bears_on = [suvi.id];
  assert.deepEqual(suggestedCast(p, 1).sort(), [suvi.id, ola.id, mia.id].sort(), "a fresh story: the first two others in order");
  writeChapter(p, 1, { cast: [suvi.id, ola.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id });
  const choices = castChoices(p, 2);
  assert.deepEqual(choices.map((c) => c.name), ["Suvi", "Ola", "Mia", "Dov"]);
  assert.deepEqual(choices.filter((c) => c.suggested).map((c) => c.name), ["Suvi", "Mia", "Dov"], "Ola was used, so Mia and Dov come first");
  assert.deepEqual(choices.find((c) => c.name === "Ola"), { id: ola.id, name: "Ola", uses: 1, last: 1, protagonist: false, inPressure: false, suggested: false });
  assert.equal(choices.find((c) => c.protagonist).id, suvi.id);
});

test("replanning a chapter does not count its own earlier plan against the cast", async () => {
  const p = await started();
  const [suvi, ola] = p.characters;
  writeChapter(p, 1, { cast: [suvi.id, ola.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id });
  assert.equal(useCounts(p, 1).characters[ola.id], undefined);
  assert.equal(useCounts(p, null).characters[ola.id], 1);
});

test("a cast needs the protagonist, at most five people, and people who exist", async () => {
  const p = await started();
  const [suvi, ola] = p.characters;
  assert.equal(castProblem(p, [suvi.id, ola.id]), null);
  assert.equal(castProblem(p, []), "empty");
  assert.equal(castProblem(p, [ola.id]), "no_protagonist");
  assert.equal(castProblem(p, [suvi.id, "nobody"]), "unknown");
  const many = Array.from({ length: CAST_MAX + 1 }, () => addInstance(p, schema.cards.characters).id);
  assert.equal(castProblem(p, [suvi.id, ...many]), "too_many");
});

test("the spotlight is a pressure involving the cast, the least-spotlit first", async () => {
  const p = await started();
  const [suvi, ola, mia] = p.characters;
  const pressures = p.entanglements.pressures;
  pressures.push({ id: "pr000002", what: "Another", source_agent: ola.id, source_circumstance: "", next_move: "x", bears_on: [] });
  pressures[0].source_agent = suvi.id;
  pressures[0].bears_on = [];
  assert.equal(pickSpotlight(p, [suvi.id]).id, pressures[0].id);
  assert.equal(pickSpotlight(p, [ola.id]).id, "pr000002");
  writeChapter(p, 1, { cast: [suvi.id], where: p.world.places[0].id, spotlight: pressures[0].id });
  assert.equal(pickSpotlight(p, [suvi.id, ola.id]).id, "pr000002", "the other one is due now");
  assert.equal(pickSpotlight(p, [mia.id]).id, "pr000002", "nothing involves Mia: the least-spotlit overall");
  assert.equal(pickSpotlight(p, [suvi.id, ola.id], 1).id, pressures[0].id, "replanning chapter 1 forgets its own spotlight");
  p.entanglements.pressures = [];
  assert.equal(pickSpotlight(p, [suvi.id]), null);
});

test("legal shifts follow the earlier beats, and an offstage change is due every second chapter", async () => {
  const p = await started();
  const [suvi] = p.characters;
  const common = { cast: [suvi.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id };
  assert.deepEqual(shiftsForChapter(p, 1), ["harder", "easier"]);
  writeChapter(p, 1, { ...common, shift: "harder" });
  writeChapter(p, 2, { ...common, shift: "harder" });
  assert.deepEqual(shiftsForChapter(p, 3), ["easier"], "never a third harder in a row");
  assert.deepEqual([1, 2, 3, 4, 5, 6].map(offstageDue), [false, true, false, true, false, true]);
});

test("the plan hash changes with the Entanglements, and a visit alone changes nothing", async () => {
  const p = await started();
  const hash = entanglementsHash(schema, p);
  assert.match(hash, /^[0-9a-f]{8}$/);
  const beat = { planned_from: hash };
  assert.equal(planIsStale(schema, p, beat), false);
  assert.equal(planIsStale(schema, p, { planned_from: "" }), false, "a beat with no hash is not stale");
  p.entanglements.pressures[0].next_move = "Something new";
  assert.equal(planIsStale(schema, p, beat), true);
});

test("a chapter can be planned once the story has started, with a cast, a pressure and chapters left", async () => {
  const p = await started();
  const [suvi, ola] = p.characters;
  assert.deepEqual(planGate(p, [suvi.id, ola.id]), { ok: true, chapter: 1 });
  assert.equal(planGate({ ...p, locks: [] }, [suvi.id]).reason, "not_started");
  assert.deepEqual(planGate(p, [ola.id]), { ok: false, reason: "cast", why: "no_protagonist" });
  assert.equal(planGate({ ...p, entanglements: { ...p.entanglements, pressures: [] } }, [suvi.id]).reason, "no_pressure");
  p.setup.chapter_count = 0;
  assert.equal(planGate(p, [suvi.id]).ok, true, "a story with no count set is not done");
  const done = await started();
  done.setup.chapter_count = 1;
  writeChapter(done, 1, { cast: [suvi.id], where: done.world.places[0].id, spotlight: done.entanglements.pressures[0].id });
  assert.equal(planGate(done, [suvi.id]).reason, "done");
});

test("the plan request carries numbers worked out here, names for links, and only the cast", async () => {
  const p = await started();
  const [suvi, ola, mia] = p.characters;
  const request = planRequest(schema, p, [suvi.id, ola.id]);
  assert.deepEqual([request.call, request.chapter, request.chapter_count, request.goal], ["plan", 1, 6, "Find the ledger."]);
  assert.deepEqual(request.cast.map((c) => c.name), ["Suvi", "Ola"], "Mia is not on stage, so she is not sent");
  assert.equal(request.setup.protagonist, "Suvi", "the protagonist is a name, not an id");
  assert.deepEqual(request.legal_shifts, ["harder", "easier"]);
  assert.deepEqual(request.available_reveals.map((r) => r.statement), ["The ledger can be read only at low tide"]);
  assert.deepEqual(request.open_plants, []);
  assert.equal(request.offstage, null);
  assert.equal(request.retry, null);
  assert.equal(request.spotlight.id, p.entanglements.pressures[0].id);
  assert.equal(request.spotlight.source_agent, p.characters.find((c) => c.id === p.entanglements.pressures[0].source_agent).name, "a link is a name");
  assert.ok(request.entanglements.ties.length > 0);
  for (const tie of request.entanglements.ties) assert.ok(["Suvi", "Ola"].includes(tie.tie_from), "a tie is shown from someone on stage");
  assert.deepEqual(request.use_counts.characters.map((c) => [c.name, c.uses]), [["Suvi", 0], ["Ola", 0], ["Mia", 0]]);
  assert.equal(JSON.stringify({ ...request, use_counts: null }).includes(mia.id), false, "Mia is nowhere but the use counts");
  const again = planRequest(schema, p, [suvi.id], { offstage: { did: "x", reach: "y" }, retry: { thinking: "t", beat: { turn: "z" }, problems: ["fix it"] } });
  assert.deepEqual(again.offstage, { did: "x", reach: "y" });
  assert.deepEqual(again.retry, { thinking: "t", beat: { turn: "z" }, problems: ["fix it"] });
});

test("the plan request does not change the project and shows earlier chapters as they were", async () => {
  const p = await started();
  const [suvi, ola] = p.characters;
  writeChapter(p, 1, { cast: [suvi.id, ola.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id, events: { planted: "A torn page", changed: "She has a page." } });
  p.summary_shifts = { shifts: [
    { id: "s1", beat: "b0000001", character: suvi.id, decided: "Keep it secret." },
    { id: "s2", beat: "b0000001", character: suvi.id, fears: "The board." },
  ] };
  const text = JSON.stringify(p);
  const request = planRequest(schema, p, [suvi.id]);
  assert.equal(JSON.stringify(p), text);
  assert.equal(request.chapter, 2);
  assert.deepEqual(request.open_plants, [{ text: "A torn page", chapter: 1 }]);
  assert.deepEqual(request.earlier_events.map((e) => [e.chapter, e.happened, e.changed]), [[1, "Happened 1", "She has a page."]]);
  assert.equal(request.earlier_beats[0].cast.every((name) => typeof name === "string"), true);
  assert.deepEqual(request.earlier_beats[0].cast, ["Suvi", "Ola"]);
  assert.deepEqual(request.latest_shifts, [{ character: "Suvi", decided: "Keep it secret.", fears: "The board." }]);
  assert.deepEqual(latestShifts(p, [ola.id]), []);
});

test("the offstage request holds only groups, places and what touches them", async () => {
  const p = await started();
  const [suvi] = p.characters;
  const power = addItem(world.fields.find((f) => f.key === "powers"), p.world.powers);
  power.name = "The Harbour Board";
  p.entanglements.pressures.push({ id: "pr000009", what: "The board wants the ledger", source_agent: power.id, source_circumstance: "", next_move: "Raid", bears_on: [suvi.id] });
  writeChapter(p, 1, { cast: [suvi.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id, events: { changed: "A page found." } });
  const request = offstageRequest(schema, p, [suvi.id]);
  assert.deepEqual([request.call, request.chapter], ["offstage", 2]);
  assert.deepEqual(request.entanglements.pressures.map((x) => x.id), ["pr000009"]);
  assert.equal(request.entanglements.pressures[0].source_agent, "The Harbour Board");
  assert.deepEqual(request.entanglements.pressures[0].bears_on, ["Suvi"]);
  assert.equal(request.latest_events.chapter, 1);
  assert.ok(request.world.powers.some((x) => x.name === "The Harbour Board"));
});

// ---- Landing a plan ----

async function mockPlan(p, castIds, extra = {}) {
  const mock = createMock(schema, { delay: 0 });
  const request = { ...planRequest(schema, p, castIds), ...extra };
  return readPlanReply(await mock.send(request));
}

test("a planned beat lands with ids, and the code fills what the model does not", async () => {
  const p = await started();
  const [suvi, ola] = p.characters;
  const reply = await mockPlan(p, [suvi.id, ola.id]);
  const { beat, unresolved } = landBeat(schema, p, [suvi.id, ola.id], reply, { offstage: null });
  assert.equal(beat.chapter, 1);
  assert.deepEqual(beat.cast, [suvi.id, ola.id]);
  assert.equal(beat.spotlight, p.entanglements.pressures[0].id);
  assert.equal(beat.planned_from, entanglementsHash(schema, p));
  assert.equal(beat.where, p.world.places[0].id, "the place the model named is now its id");
  assert.equal(beat.stale, false);
  assert.equal(beat.when_gap, "");
  assert.ok(beat.turn && beat.id);
  assert.deepEqual(unresolved, []);
});

test("the model cannot set the chapter, the cast, the spotlight or the offstage move", async () => {
  const p = await started();
  const [suvi] = p.characters;
  const reply = { ok: true, thinking: "t", beat: { turn: "She chooses.", chapter: 9, cast: ["x"], spotlight: "zzz", offstage_did: "nope", planned_from: "nope" } };
  const { beat } = landBeat(schema, p, [suvi.id], reply, { offstage: { did: "Board raids.", reach: "Bells." } });
  assert.deepEqual([beat.chapter, beat.cast, beat.offstage_did, beat.offstage_reach], [1, [suvi.id], "Board raids.", "Bells."]);
  assert.notEqual(beat.spotlight, "zzz");
  assert.notEqual(beat.planned_from, "nope");
});

test("a shift that is not harder or easier is dropped, and a link that matches nothing is reported", async () => {
  const p = await started();
  const [suvi] = p.characters;
  const reply = { ok: true, thinking: "t", beat: { turn: "x", shift: "sideways", where: "Nowhere Land", goal_change: "vanished" } };
  const { beat, unresolved, dropped } = landBeat(schema, p, [suvi.id], reply);
  assert.deepEqual(dropped.sort(), ["goal_change", "shift"]);
  assert.equal(beat.shift, "");
  assert.deepEqual(unresolved.map((u) => [u.key, u.words, u.why]), [["where", "Nowhere Land", "none"]]);
});

test("a reveal the page did not offer is refused, and an offered one lands as its id", async () => {
  const p = await started();
  const [suvi, ola] = p.characters;
  const rule = p.world.rules.find((r) => r.statement.startsWith("The ledger"));
  const ok = landBeat(schema, p, [suvi.id], { beat: { reveal_rule: rule.statement, reveal_learners: ["Suvi", "Ola"] } });
  assert.equal(ok.beat.reveal_rule, rule.id);
  assert.deepEqual(ok.beat.reveal_learners, [suvi.id, ola.id]);
  p.world.rules[0].status = "common";
  const common = landBeat(schema, p, [suvi.id], { beat: { reveal_rule: p.world.rules[0].statement } });
  assert.equal(common.beat.reveal_rule, "");
  assert.equal(common.unresolved[0].key, "reveal_rule");
});

test("a payoff is the wording of an open plant, and lands as that entry's id", async () => {
  const p = await started();
  const [suvi] = p.characters;
  writeChapter(p, 1, { cast: [suvi.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id, events: { planted: "A torn page" } });
  const { beat, unresolved } = landBeat(schema, p, [suvi.id], { beat: { payoff: ["A torn page", "A thing never planted"] } });
  assert.deepEqual(beat.payoff, ["e0000001"]);
  assert.deepEqual(unresolved.map((u) => u.words), ["A thing never planted"]);
});

test("placing a beat adds it, then replaces the unwritten beat for that chapter and keeps its id", async () => {
  const p = await started();
  const [suvi] = p.characters;
  const first = landBeat(schema, p, [suvi.id], { beat: { turn: "First try." } }).beat;
  assert.equal(placeBeat(p, first), null);
  assert.equal(p.outline.beats.length, 1);
  assert.equal(beatForChapter(p, 1).turn, "First try.");
  const second = landBeat(schema, p, [suvi.id], { beat: { turn: "Second try." } }, { existing: beatForChapter(p, 1) }).beat;
  assert.equal(second.id, first.id);
  assert.equal(placeBeat(p, second).turn, "First try.", "what it replaced comes back, so Undo can put it back");
  assert.equal(p.outline.beats.length, 1);
  assert.equal(beatForChapter(p, 1).turn, "Second try.");
});

test("a written chapter's beat is not offered as the plan, and a beat for the next chapter is", async () => {
  const p = await started();
  const [suvi] = p.characters;
  writeChapter(p, 1, { cast: [suvi.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id });
  assert.equal(beatForChapter(p, 1), null);
  assert.equal(beatForChapter(p, 2), null);
});

test("a beat's blocking problems come back in words, and only that beat's", async () => {
  const p = await started();
  const [suvi, ola] = p.characters;
  const broken = landBeat(schema, p, [suvi.id], { beat: { turn: "x" } }).beat;
  const words = beatBlockers(schema, p, broken);
  assert.ok(words.length > 0, "a beat with most fields empty is blocked");
  assert.ok(words.every((w) => typeof w === "string" && w.length > 3));
  const missingLead = { ...broken, cast: [ola.id] };
  assert.ok(beatBlockers(schema, p, missingLead).some((w) => /protagonist/i.test(w)), "no protagonist in the cast");
  assert.equal(p.outline?.beats?.length ?? 0, 0, "checking a beat does not add it");
});

test("a complete mock plan passes the Outline card's blocking rules", async () => {
  const p = await started();
  const [suvi, ola] = p.characters;
  const reply = await mockPlan(p, [suvi.id, ola.id]);
  const { beat } = landBeat(schema, p, [suvi.id, ola.id], reply);
  assert.deepEqual(beatBlockers(schema, p, beat), []);
});

test("staleBeatIds names the beats marked as possibly out of step, and castKey ignores order", async () => {
  const { staleBeatIds, castKey } = await import("../plan.js");
  const project = { outline: { beats: [{ id: "b1", stale: true }, { id: "b2", stale: false }, { id: "b3" }] } };
  assert.deepEqual([...staleBeatIds(project)], ["b1"]);
  assert.equal(staleBeatIds({}).size, 0);
  assert.equal(castKey(["b", "a"]), castKey(["a", "b"]));
  assert.notEqual(castKey(["a"]), castKey(["a", "b"]));
  assert.equal(castKey(undefined), "");
});

test("the suggestion puts the people in the least-spotlit pressure first, and it stays a suggestion", async () => {
  const p = await started();
  const [suvi, ola, mia] = p.characters;
  const dov = addInstance(p, schema.cards.characters);
  dov.name = "Dov";
  const [first] = p.entanglements.pressures;
  first.source_agent = suvi.id; first.bears_on = [suvi.id];
  const second = { ...JSON.parse(JSON.stringify(first)), id: "pressure2", what: "Dov is owed a debt.", source_agent: dov.id, bears_on: [dov.id, suvi.id] };
  p.entanglements.pressures.push(second);
  writeChapter(p, 1, { cast: [suvi.id, ola.id, dov.id], where: p.world.places[0].id, spotlight: first.id });
  assert.equal(duePressure(p, 2).id, "pressure2", "the first one has been the spotlight, the second has not");
  const choices = castChoices(p, 2);
  assert.deepEqual(choices.filter((c) => c.suggested).map((c) => c.name), ["Suvi", "Mia", "Dov"], "Dov is in the due pressure, so he is suggested ahead of Ola, who has been used just as often");
  assert.deepEqual(choices.filter((c) => c.inPressure).map((c) => c.name), ["Suvi", "Dov"]);
  assert.equal(choices.find((c) => c.name === "Mia").inPressure, false);
  assert.ok(pickSpotlight(p, suggestedCast(p, 2), null), "the suggested cast has a pressure to turn on");
  assert.equal(pickSpotlight(p, suggestedCast(p, 2), 2).id, "pressure2");
});

test("with no pressure, or one that names nobody else, the suggestion is by use alone", async () => {
  const p = await started();
  const [suvi, ola, mia] = p.characters;
  assert.equal(duePressure({ ...p, entanglements: { ...p.entanglements, pressures: [] } }), null);
  p.entanglements.pressures[0].source_agent = suvi.id; p.entanglements.pressures[0].bears_on = [suvi.id];
  assert.deepEqual(castChoices(p, 1).filter((c) => c.inPressure).map((c) => c.name), ["Suvi"]);
  assert.deepEqual(suggestedCast(p, 1).sort(), [suvi.id, ola.id, mia.id].sort());
});

// ---- The goal arc -------------------------------------------------------------------------------------------------
import { goalArc, goalDue, goalDirections, goalWarnings } from "../plan.js";

test("a goal that ends mid-story does not end the story: the next plan needs a new goal, and a late one winds down", async () => {
  const p = await started();
  p.setup.chapter_count = 6;
  const [suvi] = p.characters;
  const common = { cast: [suvi.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id };
  writeChapter(p, 1, { ...common, beat: { goal_change: "abandoned" }, events: { goal_landed: true } });
  let arc = goalArc(p);
  assert.equal(arc.state, "needs_goal");
  assert.deepEqual(arc.lastEnd, { kind: "abandoned", goal: "Find the ledger." });
  assert.equal(goalDue(p, 2).due, "set");
  writeChapter(p, 2, { ...common, beat: { goal_change: "redefined", goal_now: "Hide the ledger from the board." }, events: { goal_landed: true } });
  arc = goalArc(p);
  assert.equal(arc.state, "active");
  assert.equal(arc.goal, "Hide the ledger from the board.");
  assert.equal(arc.since, 3);
  assert.deepEqual(arc.goals, ["Find the ledger.", "Hide the ledger from the board."]);
  writeChapter(p, 3, { ...common, beat: { goal_change: "achieved" }, events: { goal_landed: true } });
  writeChapter(p, 4, { ...common, beat: { goal_change: "redefined", goal_now: "Learn who paid for the dock." }, events: { goal_landed: true } });
  writeChapter(p, 5, { ...common, beat: { goal_change: "achieved" }, events: { goal_landed: true } });
  assert.equal(goalArc(p).state, "ended", "one chapter is left, so the story winds down");
});

test("the goal arc advises, and never forbids: due, directions and warnings", async () => {
  const p = await started();
  p.setup.chapter_count = 6;
  assert.equal(goalDue(p, 1).due, null);
  assert.equal(goalDue(p, 3).due, "twist", "the middle of the story, goal unchanged");
  assert.equal(goalDue(p, 6).due, "settle");
  const [suvi] = p.characters;
  const dirs = goalDirections(p, [suvi.id], 3);
  assert.ok(dirs.length >= 2 && dirs.length <= 3);
  assert.equal(new Set(dirs.map((d) => d.kind)).size, dirs.length, "different kinds");
  assert.notDeepEqual(goalDirections(p, [suvi.id], 4).map((d) => d.kind), dirs.map((d) => d.kind), "the first kind moves on each chapter");
  const beat = { id: "b", chapter: 6, goal_change: "", collision_goal: "x" };
  assert.ok(goalWarnings(p, beat, 6).length >= 1, "the last chapter should settle the story's goal");
  assert.equal(goalWarnings(p, { ...beat, goal_change: "achieved" }, 6).length, 0);
  assert.ok(goalWarnings(p, { ...beat, goal_change: "achieved" }, 2).length >= 1, "the story's own goal achieved with 4 chapters left");
});

test("a goal and a scene aim that repeat an earlier one are noticed", async () => {
  const p = await started();
  p.setup.chapter_count = 6;
  const [suvi] = p.characters;
  const common = { cast: [suvi.id], where: p.world.places[0].id, spotlight: p.entanglements.pressures[0].id };
  writeChapter(p, 1, { ...common, beat: { collision_goal: "Suvi wants to prove the beechwood loaf can rise quickly", goal_change: "redefined", goal_now: "Prove that beechwood bakes a reliable loaf" }, events: { goal_landed: true } });
  const again = { id: "next", chapter: 2, goal_change: "redefined", goal_now: "Prove beechwood bakes a reliable loaf", collision_goal: "Suvi wants to prove the beechwood loaf can rise quickly again" };
  assert.equal(goalWarnings(p, again, 2).length, 2);
});
