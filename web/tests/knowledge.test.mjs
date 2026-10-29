import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { createMock } from "../mock.js";
import { createClient, planChapter, generateChapter } from "../client.js";
import { lockStaticCards, setWriterLock } from "../gate.js";
import { placeBeat, suggestedCast, pickSpotlight } from "../plan.js";
import { applyGenerated, commitChapter } from "../generate.js";
import { readGenerateReply, validate, settledProject } from "../logic.js";

async function planned() {
  const project = await readyProject();
  lockStaticCards(project);
  const mock = createMock(schema, { delay: 0 });
  const client = createClient({ setting: { ok: true, kind: "mock" }, mock, pollEvery: 5 });
  const plan = await planChapter(client, schema, project, suggestedCast(project, 1)).done;
  placeBeat(project, plan.beat);
  return { project, client, beat: plan.beat };
}

const goalEnds = { goal_change: "redefined", goal_now: "Find the ledger in the cellar before Friday's count." };

const reply = (over = {}) => readGenerateReply({
  ok: true, chapter_text: "She went.",
  events: { happened: "Suvi left.", changed: "", planted: null, paid_off: [], reveals_landed: [], behaviors_seen: [], things_seen: [], ...goalEnds },
  shifts: [], changes: [], ...over,
  ...(over.events ? { events: { ...goalEnds, ...over.events } } : {}),
});

const entry = (over) => ({ person: "Suvi", status: "knows", rule: null, fact: "The ledger is forged.", ...over });
const stands = (e) => ["knows", "suspects", "misled"].flatMap((status) => (e[status] ?? []).map((id) => ({ id, status })));
const added = (out) => out.changes.applied.filter((a) => a.added);

test("a reply may carry new Knowledge entries, and one with none is still a reply", () => {
  assert.deepEqual(reply().new_knowledge, []);
  assert.deepEqual(reply({ new_knowledge: [entry({ person: " Suvi " })] }).new_knowledge, [entry({ belief: null, entry: null })]);
});

test("a malformed new entry makes the whole reply bad_output", () => {
  for (const bad of [[{ status: "knows", fact: "x" }], [entry({ status: "believes" })], [entry({ fact: 7 })], "nope"]) {
    const read = readGenerateReply({ ok: true, chapter_text: "x", events: { happened: "x" }, shifts: [], changes: [], new_knowledge: bad });
    assert.equal(read.ok, false, JSON.stringify(bad));
    assert.equal(read.error.kind, "bad_output");
  }
});

test("a proposed entry with a fact is added, shown in the review as a change, and valid on the card", async () => {
  const { project, beat } = await planned();
  const before = project.entanglements.knowledge.length;
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: [entry()] }));
  assert.equal(project.entanglements.knowledge.length, before, "nothing changes until the commit");
  const [a] = added(out);
  assert.equal(a.label, "New Knowledge entry");
  assert.equal(a.from, "");
  assert.match(a.to, /^The ledger is forged\. \(Knows it: Suvi\)$/);
  commitChapter(project, out);
  assert.equal(project.entanglements.knowledge.length, before + 1);
  const made = project.entanglements.knowledge.at(-1);
  assert.deepEqual([made.rule, made.fact, made.knows.length, made.suspects, made.misled], ["", "The ledger is forged.", 1, [], []]);
  const settled = settledProject(schema, project);
  assert.deepEqual(validate(schema.cards.entanglements, settled.entanglements, settled, schema.common).problems.filter((p) => p.severity === "block"), []);
});

test("a proposed entry can name a World rule by its wording", async () => {
  const { project, beat } = await planned();
  const rule = project.world.rules[0];
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: [entry({ rule: rule.statement, fact: null, person: "Ola", status: "suspects" })] }));
  // Ola may not be in this chapter; either way it is never a silent half-entry, and an entry about that rule gets no twin.
  for (const k of out.entanglements.knowledge) assert.ok(stands(k).length, "every entry has someone in it");
  const about = (list) => list.filter((k) => k.rule === rule.id).length;
  assert.equal(about(out.entanglements.knowledge), Math.max(1, about(project.entanglements.knowledge)));
});

test("an entry is left out, with its reason, when it cannot be trusted", async () => {
  const { project, beat } = await planned();
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: [
    entry({ person: "Nobody" }),
    entry({ rule: "No such rule" , fact: null }),
    entry({ rule: "x", fact: "y" }),
    entry({ fact: null }),
  ] }));
  assert.equal(added(out).length, 0);
  assert.equal(out.changes.dropped.length, 3, "an empty entry is skipped without a warning");
  assert.equal(out.warnings.filter((w) => w.kind === "dropped").length, 3);
});


test("a person who already stands one way on a thing is moved inside that entry, never given a second entry", async () => {
  const { project, beat } = await planned();
  const have = project.entanglements.knowledge.find((k) => stands(k).some((x) => project.characters.some((c) => c.id === x.id)));
  const { id, status } = stands(have).find((x) => project.characters.some((c) => c.id === x.id));
  const name = project.characters.find((c) => c.id === id).name;
  const same = (to) => ({ person: name, status: to, rule: have.rule || null, fact: have.rule ? null : have.fact });
  const cast = new Set(beat.cast);
  if (!cast.has(id)) beat.cast = [...beat.cast, id];
  const quiet = applyGenerated(schema, project, beat, reply({ new_knowledge: [same(status)] }));
  assert.equal(quiet.changes.applied.length, 0, "the same standing is simply nothing new");
  const to = status === "knows" ? "suspects" : "knows";
  const moved = applyGenerated(schema, project, beat, reply({ new_knowledge: [same(to)] }));
  assert.equal(added(moved).length, 0, "no new entry");
  assert.equal(moved.entanglements.knowledge.length, project.entanglements.knowledge.length);
  const entry = moved.entanglements.knowledge.find((k) => k.id === have.id);
  assert.ok(entry[to].includes(id) && !entry[status].includes(id), "moved from one list to the other");
  const [change] = moved.changes.applied.filter((a) => a.item === have.id);
  assert.equal(change.field, to);
});

test("people proposed for the same new thing share one entry", async () => {
  const { project, beat } = await planned();
  const [a, b] = project.characters.filter((c) => beat.cast.includes(c.id)).slice(0, 2);
  if (!b) return;
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: [
    entry({ person: a.name, status: "knows" }), entry({ person: b.name, status: "suspects" }),
  ] }));
  assert.equal(added(out).length, 1);
  const made = out.entanglements.knowledge.at(-1);
  assert.deepEqual([made.knows, made.suspects], [[a.id], [b.id]]);
  assert.match(added(out)[0].to, new RegExp(`${a.name}.*${b.name}`));
});

test("a chapter may add any number of entries", async () => {
  const { project, beat } = await planned();
  const many = Array.from({ length: 12 }, (_, i) => entry({ fact: `Fact number ${i}.` }));
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: many }));
  assert.equal(added(out).length, 12);
  assert.equal(out.changes.dropped.length, 0);
});

test("a change names the one person who now knows, suspects or is misled, and the entry moves them", async () => {
  const { project, beat } = await planned();
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: [entry({ status: "suspects" })] }));
  commitChapter(project, out);
  const made = project.entanglements.knowledge.at(-1);
  const learned = applyGenerated(schema, project, beat, reply({ changes: [{ section: "knowledge", item: made.id, field: "knows", value: "Suvi" }] }));
  const [c] = learned.changes.applied;
  assert.deepEqual([c.field, c.from, c.to], ["knows", "", "Suvi"]);
  commitChapter(project, learned);
  const now = project.entanglements.knowledge.at(-1);
  assert.deepEqual([now.knows.length, now.suspects], [1, []]);
  const nobody = applyGenerated(schema, project, beat, reply({ changes: [{ section: "knowledge", item: made.id, field: "knows", value: "Nobody" }] }));
  assert.equal(nobody.changes.applied.length, 0);
  assert.equal(nobody.changes.dropped.length, 1);
});

test("a lock on the Knowledge list asks first, and declining leaves the list alone", async () => {
  const { project, beat } = await planned();
  project.locks.push({ id: "lock0007", card: "entanglements", field: "knowledge" });
  const asked = applyGenerated(schema, project, beat, reply({ new_knowledge: [entry()] }));
  assert.equal(asked.changes.locked.length, 1);
  assert.deepEqual(asked.unlock, ["lock0007"]);
  const declined = applyGenerated(schema, project, beat, reply({ new_knowledge: [entry()] }), { overwriteLocked: false });
  assert.equal(added(declined).length, 0);
  assert.equal(declined.entanglements.knowledge.length, project.entanglements.knowledge.length);
  const single = { ...project, locks: [{ id: "lock0008", card: "entanglements", field: "knowledge", item: project.entanglements.knowledge[0].id }] };
  assert.equal(added(applyGenerated(schema, single, beat, reply({ new_knowledge: [entry()] }), { overwriteLocked: false })).length, 1, "a lock on one entry does not cover a new one");
});

test("a writer's lock on the whole Entanglements card asks first", async () => {
  const { project, beat } = await planned();
  setWriterLock(project, "entanglements", true);
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: [entry()] }), { overwriteLocked: false });
  assert.equal(added(out).length, 0);
});

test("a new entry counts as knowledge having changed, and Generate's undo takes it out again", async () => {
  const { project, client } = await planned();
  const before = JSON.stringify(project.entanglements.knowledge);
  const result = await generateChapter(client, schema, project).done;
  assert.equal(result.ok, true);
  assert.ok(added(result.outcome).length >= 1, "the mock proposes one in chapter 1");
  const { undo } = commitChapter(project, result.outcome);
  assert.ok(project.entanglements.knowledge.length > JSON.parse(before).length);
  assert.equal(undo(), true);
  assert.equal(JSON.stringify(project.entanglements.knowledge), before);
});

test("an entry keeps what the misled wrongly believe, and loses it when no one is misled any more", async () => {
  const { project, beat } = await planned();
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: [entry({ status: "misled", belief: "The ledger is honest." })] }));
  commitChapter(project, out);
  const made = project.entanglements.knowledge.at(-1);
  assert.deepEqual([made.misled.length, made.belief], [1, "The ledger is honest."]);
  const learned = applyGenerated(schema, project, beat, reply({ changes: [{ section: "knowledge", item: made.id, field: "knows", value: "Suvi" }] }));
  commitChapter(project, learned);
  assert.equal(project.entanglements.knowledge.at(-1).belief, "");
  const knows = applyGenerated(schema, project, beat, reply({ new_knowledge: [entry({ person: "Ola", status: "knows", belief: "ignored", fact: "Another fact." })] }));
  assert.equal(added(knows)[0]?.now.belief ?? "", "");
});

test("a proposal that names an existing line puts the person into it, and a line that is not there is left out", async () => {
  const { project, beat } = await planned();
  const line = project.entanglements.knowledge[0];
  const who = project.characters.find((c) => beat.cast.includes(c.id));
  const other = project.characters.find((c) => c.id !== who.id);
  Object.assign(line, { knows: [other.id], suspects: [], misled: [], belief: "" });
  const before = project.entanglements.knowledge.length;
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: [
    { person: who.name, status: "suspects", rule: null, fact: null, entry: line.id },
    { person: who.name, status: "knows", rule: null, fact: null, entry: "no-such-line" },
  ] }));
  commitChapter(project, out);
  assert.equal(project.entanglements.knowledge.length, before, "nothing new is made: the person joined the line that was there");
  const same = project.entanglements.knowledge.find((k) => k.id === line.id);
  assert.deepEqual(stands(same).filter((s) => s.id === who.id), [{ id: who.id, status: "suspects" }]);
  assert.equal(out.changes.dropped.length, 1);
});

test("the chapter's record keeps which live entanglements it showed, and only live ones", async () => {
  const { project, beat } = await planned();
  const [pressure] = project.entanglements.pressures;
  const [tie] = project.entanglements.ties;
  const out = applyGenerated(schema, project, beat, reply({ shown: [tie.id, tie.id, pressure.id, "gone"] }));
  assert.deepEqual(out.events.entanglements_shown, [tie.id], "a pressure's use is the spotlight, so it is not kept here");
});

test("a pressure the pass marks resolved is resolved once the chapter commits, and the next spotlight passes over it", async () => {
  const { project, beat } = await planned();
  const [pressure] = project.entanglements.pressures;
  project.entanglements.pressures.push({ ...JSON.parse(JSON.stringify(pressure)), id: "pr000002", what: "Winter is coming and the coal is unpaid." });
  const out = applyGenerated(schema, project, beat, reply({ changes: [{ section: "pressures", item: pressure.id, field: "status", value: "resolved" }] }));
  assert.equal(out.changes.dropped.length, 0, JSON.stringify(out.changes.dropped));
  assert.deepEqual(out.changes.applied.map((a) => [a.field, a.from, a.to]), [["status", "Active", "Resolved"]]);
  commitChapter(project, out);
  assert.equal(project.entanglements.pressures.find((x) => x.id === pressure.id).status, "resolved");
  assert.equal(pickSpotlight(project, project.characters.map((c) => c.id)).id, "pr000002");
});
