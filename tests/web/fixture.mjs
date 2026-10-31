// A small story in the shape the contract vectors use (tests/shared/contract-vectors.json): two characters, a group, two ties,
// one holding, one written chapter and the beat of chapter 2. Tests copy it and change what they need.
import { schema } from "./helpers.mjs";

export { schema };

export function story() {
  return {
    id: "pr000001", title: "The Salt Coast", schema_version: schema.schema_version,
    style: { person: "first", tense: "past" },
    characters: [
      { id: "c0000001", name: "Suvi", age: 31, sex: "female", appearance: "Ink on her cuffs.", sketch: "An archivist who keeps score.",
        wants: [{ id: "w0000001", text: "To be left alone with the records" }], fear: "Being found out", flaw: "She hoards what she knows", values: [],
        behaviors: [{ id: "h0000001", state: "When cornered", tendency: "she goes quiet and counts" }] },
      { id: "c0000002", name: "Marit", age: 58, sex: "female", appearance: "Grey braid.", sketch: "Suvi's mother, a fisher.", wants: [], fear: "", flaw: "", values: [], behaviors: [] },
    ],
    world: {
      name: "The Salt Coast", era_and_technology: "Lamps and ledgers.", everyday_life: "Tides set the day.", history: "",
      places: [
        { id: "p0000001", name: "The Archive", description: "Damp stone.", effect: "People whisper." },
        { id: "p0000002", name: "The Quay", description: "Salt and rope.", effect: "Nothing stays secret." },
      ],
      objects: [{ id: "o0000001", name: "The ledger", description: "Green cloth cover.", significance: "Names who owes the board." }],
      powers: [{ id: "g0000001", name: "The Board", nature: "Harbour council.", hold: "It sets the tolls.", felt: "Everyone pays." }],
      rules: [{ id: "r0000001", statement: "Debts are written, never spoken.", cost: "A spoken debt is void.", when_broken: "The board is shamed." }],
      terms: [{ id: "t0000001", term: "toll", meaning: "the harbour fee" }],
    },
    entanglements: {
      ties: [
        { id: "t1000001", tie_from: "c0000002", tie_to: "c0000001", bond: "mother", edge: "to bring her daughter home" },
        { id: "t1000002", tie_from: "c0000001", tie_to: "g0000001", bond: "clerk of", edge: "to keep the board from finding the ledger gone" },
      ],
      holdings: [{ id: "h1000001", holdee: "o0000001", held_by: "g0000001" }],
    },
    setup: { protagonist: "c0000001", normal: "", disruption: "", chapter_count: 8 },
    outline: { beats: [
      { id: "b0000001", chapter: 1, where: "p0000002", when_time: "Morning", cast: ["c0000001", "c0000002"], spotlight: "t1000002", aim: "Suvi wants to learn who took the ledger.", plan: "She asks around the quay." },
      { id: "b0000002", chapter: 2, where: "p0000001", when_time: "Dusk, the second day", cast: ["c0000001", "c0000002"], spotlight: "t1000001",
        aim: "Suvi wants the ledger out before the board counts.",
        plan: "Suvi hides the ledger in the quay stores. Marit arrives and asks her to come home. Suvi must choose which to protect first." },
    ] },
    chapters: [{ id: "k0000001", beat: "b0000001", text: "She closed the door on the quay and did not look back." }],
    summary_events: { entries: [{ id: "e0000001", beat: "b0000001", happened: "Suvi learned the board has the ledger.", changed: "Suvi now knows the board is hunting her." }] },
    shifts: { entries: [] },
    locks: ["style", "characters", "world", "entanglements", "setup"].map((card, i) => ({ id: `l000000${i}`, card })),
  };
}

// The same story before chapter 1 is written, with the opening filled in.
export function opening() {
  const p = story();
  p.setup.normal = "Tides and ledgers.";
  p.setup.disruption = "The ledger is gone.";
  p.chapters = [];
  p.summary_events = { entries: [] };
  p.outline.beats = [p.outline.beats[1]];
  p.outline.beats[0].chapter = 1;
  return p;
}
