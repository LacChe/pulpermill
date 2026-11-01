import test from "node:test";
import assert from "node:assert/strict";
import { checkChapter, personFound, tenseFound, strangeNames, edgeMoved, narration, LIMITS } from "../../tools/trial_checks.mjs";

const eff = {
  characters: [{ id: "a", name: "Suvi" }, { id: "b", name: "Aino" }, { id: "c", name: "Pekka" }],
  world: { name: "The Salt Coast", places: [{ name: "The Docks" }], objects: [{ name: "The ledger" }], powers: [{ name: "The Harbour Board" }], terms: [{ term: "first-day visit" }] },
  entanglements: { ties: [{ id: "t", tie_from: "a", tie_to: "b", edge: "She wants to know whom he reports to." }] },
};
const filler = (n, word = "walked") => Array.from({ length: n }, (_, i) => `I ${word} past door number${i}.`).join(" ");
const base = { language: "en", style: { person: "first", tense: "past" }, eff, cast: ["a", "b"], spotlight: "t", earlier: [], events: { changed: "x" }, shifts: [], proposed: 0, maxShifts: 7 };

test("length is counted in words, and a short or long chapter is flagged", () => {
  assert.equal(checkChapter({ ...base, text: "One two three." }).length_flag, "too_short");
  assert.equal(checkChapter({ ...base, text: "word ".repeat(LIMITS.en.max + 1) }).length_flag, "too_long");
  assert.equal(checkChapter({ ...base, text: "word ".repeat(400) }).length_flag, "");
});

test("Chinese length counts Han characters", () => {
  const out = checkChapter({ ...base, language: "zh", style: { person: "third", tense: "past" }, text: "她走进内库。".repeat(100) });
  assert.equal(out.length, 500);
  assert.equal(out.tense_found, "n/a");
  assert.equal(out.unknown_names, "");
});

test("person: dialogue is cut out first, and drift is flagged only when clear", () => {
  const narr = "She went to the dock and he followed her. They left their coats. She said nothing to him. He looked at her hands. They walked on.";
  assert.equal(personFound(`${narr} "I think I know, and I told you my plan."`, "en").found, "third");
  assert.equal(narration('He said "I came here" and left.').includes("came"), false);
  assert.equal(checkChapter({ ...base, text: narr }).person_flag, "drift");
  assert.equal(checkChapter({ ...base, style: { person: "third", tense: "past" }, text: narr }).person_flag, "");
  assert.equal(personFound("Short.", "en").found, "unclear");
});

test("tense: past against present, and too few marks is unclear", () => {
  assert.equal(tenseFound("She walked and she looked. He turned and he said that she had it. They found it and kept it. We stood. I sat. It was done and gave way. They knew it. ".repeat(2)).found, "past");
  assert.equal(tenseFound("She is here and she looks. He says that she has it. They find it and keep it. We stand. I sit. It is done and goes. They know it. She comes and sees. He takes it. ".repeat(3)).found, "present");
  assert.equal(tenseFound("It was.").found, "unclear");
  assert.equal(checkChapter({ ...base, style: { person: "first", tense: "present" }, text: filler(40) }).tense_flag, "drift");
});

test("an opening or a sentence that repeats an earlier chapter is counted", () => {
  const first = "The lamp guttered and went out in the cold harbour. Nobody on the quay said a word about it that night.";
  const out = checkChapter({ ...base, earlier: [first], text: `The lamp guttered and went out in the cold harbour. Then something else happened in the town. Nobody on the quay said a word about it that night.` });
  assert.equal(out.opening_repeat, true);
  assert.equal(out.repeated_sentences, 2);
  const fresh = checkChapter({ ...base, earlier: [first], text: "A different start entirely, with new words in every place that matters here." });
  assert.equal(fresh.opening_repeat, false);
  assert.equal(fresh.repeated_sentences, 0);
});

test("the spotlight edge counts as moved when the tie is replaced with a different edge, or removed", () => {
  const replace = (edge) => [{ card: "entanglements", patch: { ties: [{ op: "replace", id: "t", values: { edge } }] } }];
  assert.equal(edgeMoved("t", "old", replace("new")), true);
  assert.equal(edgeMoved("t", "old", replace("old")), false);
  assert.equal(edgeMoved("t", "old", [{ card: "entanglements", patch: { ties: [{ op: "remove", id: "t" }] } }]), true);
  assert.equal(edgeMoved("t", "old", [{ card: "entanglements", patch: { ties: [{ op: "replace", id: "other", values: { edge: "new" } }] } }]), false);
  assert.equal(edgeMoved("t", "old", [{ card: "world", patch: {} }]), false);
  assert.equal(edgeMoved("t", "old", []), false);
});

test("an empty changed line and the shift cap are flagged", () => {
  const out = checkChapter({ ...base, text: "word ".repeat(300), events: { changed: "  " }, proposed: 9, shifts: Array(8).fill({ card: "world", patch: {} }) });
  assert.equal(out.changed_empty, true);
  assert.equal(out.shift_flag, "over_cap");
  assert.equal(out.shift_count, 8);
  assert.equal(checkChapter({ ...base, text: "word ".repeat(300), proposed: 7, shifts: Array(7).fill({ card: "world", patch: {} }) }).shift_flag, "");
});

test("a capitalised name that is on no card is listed; cast, places, terms and sentence starts are not", () => {
  const text = "I met Marcus Hale at The Docks. Aino carried the ledger to Pekka. He stayed on The Salt Coast. On Tuesday the Harbour Board held a first-day visit. Then Dara laughed.";
  const out = checkChapter({ ...base, text });
  assert.deepEqual(out.unknown_names.split(" ").sort(), ["Dara", "Hale", "Marcus"]);
  assert.equal(out.offstage_names, "Pekka");
  assert.equal(out.unknown_count, 3);
  assert.ok(!out.unknown_names.includes("Then") && !out.unknown_names.includes("Tuesday"));
  assert.deepEqual(strangeNames("He knew Wren well.", new Set(), new Set(["Wren"])), { unknown: [], away: ["Wren"] });
});

test("every column the runner writes is present in a check", () => {
  const out = checkChapter({ ...base, text: filler(30) });
  for (const k of ["length", "length_flag", "person_found", "person_flag", "tense_found", "tense_flag", "opening_repeat", "repeated_sentences", "edge_in_shifts", "changed_empty", "shifts_proposed", "shift_count", "shift_flag", "unknown_count", "unknown_names", "offstage_names"]) assert.ok(k in out, k);
});
