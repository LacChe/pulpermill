import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { schema, readyProject } from "./helpers.mjs";
import { createMock } from "../mock.js";
import { createClient, planChapter, generateChapter } from "../client.js";
import { lockStaticCards, setWriterLock } from "../gate.js";
import { placeBeat, suggestedCast } from "../plan.js";
import { applyGenerated, commitChapter, MAX_NEW_KNOWLEDGE } from "../generate.js";
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

const reply = (over = {}) => readGenerateReply({
  ok: true, chapter_text: "She went.",
  events: { happened: "Suvi left.", changed: "", planted: null, paid_off: [], reveals_landed: [], behaviors_seen: [], things_seen: [], goal_landed: false },
  shifts: [], changes: [], ...over,
});

const entry = (over) => ({ person: "Suvi", status: "knows", rule: null, fact: "The ledger is forged.", ...over });
const added = (out) => out.changes.applied.filter((a) => a.added);

test("a reply may carry new Knowledge entries, and one with none is still a reply", () => {
  assert.deepEqual(reply().new_knowledge, []);
  assert.deepEqual(reply({ new_knowledge: [entry({ person: " Suvi " })] }).new_knowledge, [entry()]);
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
  assert.match(a.to, /Suvi Knows: The ledger is forged\./);
  commitChapter(project, out);
  assert.equal(project.entanglements.knowledge.length, before + 1);
  const made = project.entanglements.knowledge.at(-1);
  assert.deepEqual([made.rule, made.fact, made.status], ["", "The ledger is forged.", "knows"]);
  const settled = settledProject(schema, project);
  assert.deepEqual(validate(schema.cards.entanglements, settled.entanglements, settled, schema.common).problems.filter((p) => p.severity === "block"), []);
});

test("a proposed entry can name a World rule by its wording", async () => {
  const { project, beat } = await planned();
  const rule = project.world.rules[0];
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: [entry({ rule: rule.statement, fact: null, person: "Ola", status: "suspects" })] }));
  // Ola may not be in this chapter; either way it is never a silent half-entry.
  const [a] = added(out);
  if (a) assert.equal(project.entanglements.knowledge.length + 1, out.entanglements.knowledge.length);
  else assert.ok(out.warnings.some((w) => w.kind === "dropped"));
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
  assert.equal(out.changes.dropped.length, 4);
  assert.equal(out.warnings.filter((w) => w.kind === "dropped").length, 4);
});

test("a person and a thing that already have an entry get no second one", async () => {
  const { project, beat } = await planned();
  const have = project.entanglements.knowledge[0];
  const same = (status) => ({ person: have.person, status, rule: have.rule || null, fact: have.rule ? null : have.fact });
  const quiet = applyGenerated(schema, project, beat, reply({ new_knowledge: [same(have.status)] }));
  assert.equal(added(quiet).length, 0);
  assert.equal(quiet.changes.dropped.length, 0, "the same status is simply nothing new");
  const moved = applyGenerated(schema, project, beat, reply({ new_knowledge: [same(have.status === "knows" ? "suspects" : "knows")] }));
  assert.equal(added(moved).length, 0);
  assert.match(moved.changes.dropped[0].why, /already has an entry/);
});

test("a chapter adds at most as many entries as the page allows", async () => {
  const { project, beat } = await planned();
  const many = Array.from({ length: MAX_NEW_KNOWLEDGE + 2 }, (_, i) => entry({ fact: `Fact number ${i}.` }));
  const out = applyGenerated(schema, project, beat, reply({ new_knowledge: many }));
  assert.equal(added(out).length, MAX_NEW_KNOWLEDGE);
  assert.equal(out.changes.dropped.length, 2);
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
