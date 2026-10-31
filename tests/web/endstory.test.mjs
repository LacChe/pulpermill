import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { story, schema } from "./fixture.mjs";
import { endGate, makeAfterStory, afterStoryChanges, chaptersFingerprint, afterStoryStale, afterStoryProblems } from "../../web/endstory.js";

const finished = () => {
  const p = story();
  p.setup.chapter_count = 1;
  p.shifts.entries.push(
    { id: "s1", beat: "b0000001", card: "characters", target: "c0000001", patch: { fear: "Her mother", behaviors: [{ op: "add", id: "h9", values: { state: "When happy", tendency: "she hums" } }] } },
    { id: "s2", beat: "b0000001", card: "entanglements", target: null, patch: { holdings: [{ op: "remove", id: "h1000001" }] } },
  );
  return p;
};

test("the end of the story needs every chapter written", () => {
  assert.deepEqual(endGate(finished()), { ok: true, replaces: false });
  assert.equal(endGate(story()).reason, "not_done");
  assert.equal(makeAfterStory(story()).reason, "not_done");
  assert.equal(endGate({ ...finished(), after_story: {} }).replaces, true);
});

test("the after-story copy is every shift folded in, with Style as it is and the originals left alone", () => {
  const p = finished();
  const was = JSON.stringify(p);
  const { ok, after } = makeAfterStory(p);
  assert.equal(ok, true);
  assert.equal(after.characters[0].fear, "Her mother");
  assert.deepEqual(after.characters[0].behaviors.map((b) => b.id), ["h0000001", "h9"]);
  assert.deepEqual(after.entanglements.holdings, []);
  assert.deepEqual(after.style, p.style);
  assert.equal(after.characters[1].name, "Marit");
  assert.equal(JSON.stringify(p), was);
});

test("the changes read as before and after, in words", () => {
  const p = finished();
  const { after } = makeAfterStory(p);
  const changes = afterStoryChanges(schema, p, after);
  const fear = changes.find((c) => c.field === "fear");
  assert.deepEqual([fear.who, fear.kind, fear.before, fear.after], ["Suvi", "changed", "Being found out", "Her mother"]);
  assert.ok(changes.some((c) => c.field === "behaviors" && c.kind === "added"));
  assert.ok(changes.some((c) => c.card === "entanglements" && c.kind === "removed"));
  assert.equal(afterStoryChanges(schema, story(), makeAfterStory({ ...story(), setup: { ...story().setup, chapter_count: 1 } }).after).length, 0, "no shifts, no changes");
});

test("the copy is out of date when a chapter or a record it was made from changes", () => {
  const p = finished();
  const { after } = makeAfterStory(p);
  p.after_story = after;
  p.end_note = { id: "n1", problems: 0, made_from: chaptersFingerprint(p) };
  assert.equal(afterStoryStale(p), false);
  p.chapters[0].text = "Different.";
  assert.equal(afterStoryStale(p), true);
  p.chapters[0].text = "She closed the door on the quay and did not look back.";
  assert.equal(afterStoryStale(p), false, "put back, it is current again");
  p.shifts.entries.pop();
  assert.equal(afterStoryStale(p), true, "the shifts count");
  assert.equal(afterStoryStale({ ...p, end_note: undefined }), false);
});

test("blocking problems in the copy are counted", () => {
  const p = finished();
  const { after } = makeAfterStory(p);
  const clean = afterStoryProblems(schema, p, after);
  after.characters[0].name = "";
  assert.ok(afterStoryProblems(schema, p, after) > clean);
});
