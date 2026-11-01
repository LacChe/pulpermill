// Runs the page's own client against a running backend: the whole story, end to end (P7). It uses the mock to build a ready project, then talks to the real address.
//   python -m pulpermill.backend --fake --port 8000 &        (canned replies: shifts are empty, so the shift checks only prove the plumbing)
//   node tools/smoke_page.mjs http://127.0.0.1:8000 [token]
// tests/e2e/test_e2e.py runs it against the real runner with the stub prompter and a scripted fake engine, where shifts are real.
// The story: start (five cards locked), plan and write chapters 1 to 3, write chapter 2 again, plan and write chapter 4, finish.
import { fileURLToPath } from "node:url";
import { readyProject, schema } from "../tests/web/helpers.mjs";
import "../tests/web/text-setup.mjs";
import { createClient, parseBackendSetting, planChapter, generateChapter, regenerateChapter, checkStyleFit } from "../web/client.js";
import { ensureBeat, placeBeat, planRequest, newBeat, castProblem, requiredCast, chapterInfo } from "../web/plan.js";
import { makeAfterStory } from "../web/endstory.js";
import { STATIC_CARDS, lockStaticCards, cardLocked, storyStarted, startGate } from "../web/gate.js";
import { commitChapter, commitRegenerated } from "../web/generate.js";
import { effectiveProject, applyPatch } from "../web/effective.js";
import { projectSnapshot, readProject } from "../web/logic.js";

const copy = (x) => JSON.parse(JSON.stringify(x));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// The cards going into `chapter`, folded by hand from the base cards: every shift of an earlier chapter, in chapter order. This is
// written apart from effective.js on purpose (it only borrows applyPatch for a single patch).
function foldByHand(project, chapter) {
  const number = new Map((project.outline.beats ?? []).map((b) => [b.id, Number(b.chapter)]));
  const entries = (project.shifts?.entries ?? []).map((e, order) => ({ e, order, at: number.get(e.beat) }))
    .filter((x) => Number.isFinite(x.at) && x.at < chapter).sort((a, b) => a.at - b.at || a.order - b.order);
  const out = { characters: copy(project.characters), world: copy(project.world), entanglements: copy(project.entanglements) };
  for (const { e } of entries) {
    if (e.card === "characters") out.characters = out.characters.map((c) => (c.id === e.target ? applyPatch(c, e.patch) : c));
    else out[e.card] = applyPatch(out[e.card], e.patch);
  }
  return out;
}
const cardsOf = (p) => ({ characters: p.characters, world: p.world, entanglements: p.entanglements });

export async function runStory(address, token = "", { log = console.log } = {}) {
  const results = [];
  const say = (what, ok, extra = "") => { results.push({ what, ok: Boolean(ok), extra }); log(`${ok ? "ok  " : "FAIL"} ${what} ${extra}`); return ok; };
  const client = createClient({ setting: parseBackendSetting(address), token, pollEvery: 100 });
  const settle = async () => { for (let i = 0; i < 200 && (await client.checkStatus()) !== "idle"; i++) await sleep(25); };

  say("status", (await client.checkStatus()) === "idle");

  // ---- Create the project and start the story ----
  const project = await readyProject();
  project.setup.chapter_count = 4;
  const fit = await checkStyleFit(client, schema, project).done;
  say("style_fit", fit.ok === true, fit.error?.kind ?? "");
  say("the start gate lets the story start", startGate(schema, project).ok);
  lockStaticCards(project);
  say("starting the story locks the five cards", storyStarted(project) && STATIC_CARDS.length === 5 && STATIC_CARDS.every((id) => cardLocked(project, id)));
  const base = copy(cardsOf(project));
  const startedWith = copy(project);

  // Picks are the same however many times the same chapter is planned, even on separate copies of the project.
  const aBeat = newBeat(schema, copy(startedWith), 1), bBeat = newBeat(schema, copy(startedWith), 1);
  say("planning chapter 1 twice picks the same spotlight and cast", aBeat.spotlight && same([aBeat.spotlight, aBeat.cast], [bBeat.spotlight, bBeat.cast]));
  say("planning chapter 1 twice builds the same request", same(planRequest(schema, copy(startedWith), aBeat), planRequest(schema, copy(startedWith), bBeat)));

  // ---- One chapter the way the page does it ----
  async function writeChapter(label, { undoCheck = true } = {}) {
    const beat = ensureBeat(schema, project);
    const n = Number(beat.chapter);
    const eff = effectiveProject(project, n);
    const tie = (eff.entanglements?.ties ?? []).find((t) => t.id === beat.spotlight);
    const need = requiredCast(eff, beat.spotlight);
    say(`${label}: the spotlight tie exists and the cast holds everyone it requires`, tie && castProblem(eff, beat.cast, beat.spotlight) === null && need.every((id) => beat.cast.includes(id)));
    const asked = JSON.stringify(planRequest(schema, project, beat));
    const plan = await planChapter(client, schema, project, beat).done;
    if (!say(`${label}: plan`, plan.ok === true, plan.error?.kind ?? plan.reason ?? "")) return null;
    say(`${label}: planning the same chapter again builds the same request`, JSON.stringify(planRequest(schema, project, beat)) === asked);
    placeBeat(project, plan.beat);
    const written = await generateChapter(client, schema, project).done;
    if (!say(`${label}: generate`, written.ok === true, written.error?.kind ?? written.reason ?? "")) return null;
    const before = copy(project);
    const committed = commitChapter(project, written.outcome);
    const nShifts = written.outcome.shifts.length;
    say(`${label}: the chapter, its Events and its shifts commit together`, project.chapters.length === (before.chapters ?? []).length + 1
      && project.summary_events.entries.length === (before.summary_events?.entries ?? []).length + 1
      && project.shifts.entries.length === (before.shifts?.entries ?? []).length + nShifts
      && project.shifts.entries.slice(-nShifts || undefined).every((s) => nShifts === 0 || s.beat === beat.id)
      && project.chapters.at(-1).beat === beat.id && project.summary_events.entries.at(-1).beat === beat.id, `(${nShifts} shifts)`);
    if (undoCheck) {
      say(`${label}: undo restores the project exactly`, committed.undo() === true && same(project, before));
      commitChapter(project, written.outcome);   // put it back (the outcome is only read)
    }
    return { beat, n, nShifts };
  }

  const shiftCounts = [];
  for (const n of [1, 2]) {
    const r = await writeChapter(`chapter ${n}`);
    if (!r) return results;
    shiftCounts.push(r.nShifts);
  }

  // The state going into chapter 3 is the base cards plus the shifts of chapters 1 and 2.
  say("before chapter 3 the effective cards are the base cards plus the shifts of chapters 1 and 2",
    same(cardsOf(effectiveProject(project, 3)), foldByHand(project, 3)));
  say("before chapter 3 the base cards themselves are untouched", same(cardsOf(project), base));
  const r3 = await writeChapter("chapter 3");
  if (!r3) return results;
  shiftCounts.push(r3.nShifts);
  say("the story produced shifts to fold (so the fold checks are not empty)", shiftCounts.some((c) => c > 0), `(${shiftCounts.join(", ")})`);

  // ---- Chapter 2 again ----
  const oldIds = project.shifts.entries.map((s) => s.id);
  const beat2 = project.outline.beats.find((b) => Number(b.chapter) === 2), beat1 = project.outline.beats.find((b) => Number(b.chapter) === 1);
  const oneIds = project.shifts.entries.filter((s) => s.beat === beat1.id).map((s) => s.id);
  const laterText = project.chapters[2].text;
  const regen = await regenerateChapter(client, schema, project, 2).done;
  if (!say("regenerate chapter 2", regen.ok === true, regen.error?.kind ?? regen.reason ?? "")) return results;
  const beforeRegen = copy(project);
  const regenCommit = commitRegenerated(project, regen.outcome);
  const ids = project.shifts.entries.map((s) => s.id);
  say("regenerating chapter 2 drops the shifts of chapter 2 and later and keeps chapter 1's",
    oneIds.every((id) => ids.includes(id))
    && oldIds.filter((id) => !oneIds.includes(id)).every((id) => !ids.includes(id))
    && project.shifts.entries.filter((s) => !oneIds.includes(s.id)).every((s) => s.beat === beat2.id));
  say("regenerating chapter 2 marks the later beats stale and keeps the later chapters", project.outline.beats.filter((b) => Number(b.chapter) > 2).every((b) => b.stale === true)
    && project.chapters.length === 3 && project.chapters[2].text === laterText);
  say("after regenerating chapter 2 the effective cards going into chapter 3 are still the by-hand fold", same(cardsOf(effectiveProject(project, 3)), foldByHand(project, 3)));
  say("undoing the regeneration restores the project exactly", regenCommit.undo() === true && same(project, beforeRegen));
  commitRegenerated(project, regen.outcome);
  // Chapter 3 was written from the old chapter 2 and its beat is stale. Writing it again either works, or is refused because the beat
  // points at something the old chapter 2's shifts made (a tie that is gone): then the beat must be planned again. Both are by design.
  const again = await regenerateChapter(client, schema, project, 3).done;
  say("chapter 3 after a new chapter 2: written again, or refused because its beat must be planned again", again.ok === true || again.reason === "beat_blocked", again.ok ? "(written again)" : again.reason ?? again.error?.kind ?? "");
  if (again.ok) commitRegenerated(project, again.outcome);

  // ---- Chapter 4, with a Stop in the middle of the writing ----
  const beat4 = ensureBeat(schema, project);
  const plan4 = await planChapter(client, schema, project, beat4).done;
  if (!say("chapter 4: plan", plan4.ok === true, plan4.error?.kind ?? plan4.reason ?? "")) return results;
  placeBeat(project, plan4.beat);
  const beforeStop = copy(project);
  const call = generateChapter(client, schema, project);
  // Stop once the backend says it is writing, so the Stop lands in the middle of the model's work and not before it starts.
  const api = address.replace(/\/+$/, "") + "/api";
  const headers = { "content-type": "application/json", "ngrok-skip-browser-warning": "1", ...(token ? { "x-pulpermill-token": token } : {}) };
  for (let i = 0; i < 400; i++) {
    const status = await fetch(api, { method: "POST", headers, body: JSON.stringify({ call: "status" }) }).then((r) => r.json()).catch(() => ({}));
    if (status.stage?.name === "write") break;
    await sleep(10);
  }
  call.stop();
  const stopped = await call.done;
  say("a stop in the middle of a generate fails as stopped", stopped.ok === false && stopped.error?.kind === "stopped", stopped.error?.kind ?? stopped.reason ?? "");
  say("a stop in the middle of a generate leaves the project unchanged", same(project, beforeStop));
  await settle();
  const r4 = await writeChapter("chapter 4");
  if (!r4) return results;
  say("every chapter is written", chapterInfo(project).done === true);

  // ---- Finish the story ----
  const end = makeAfterStory(project);
  say("end of story (no call)", end.ok === true, end.reason ?? "");
  if (end.ok) {
    const byHand = foldByHand(project, Infinity);
    say("the end copy of Characters, World and Entanglements is the fold of all shifts", same([end.after.characters, end.after.world, end.after.entanglements], [byHand.characters, byHand.world, byHand.entanglements]));
    say("the original Characters, World and Entanglements are untouched", same(cardsOf(project), base));
    say("the end copy keeps Style as it was", same(end.after.style, project.style));
  }

  // ---- Export and import ----
  const text = projectSnapshot(schema, project);
  const read = readProject(text, schema);
  say("an exported project reads back", read.ok === true, read.reason ?? "");
  if (read.ok) say("exporting and importing a project gives the same project", projectSnapshot(schema, read.project) === text && same(read.project, JSON.parse(text)));
  await settle();
  say("the backend is idle at the end", (await client.checkStatus()) === "idle");
  say("the story ran to its end", true);
  return results;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [address, token = ""] = process.argv.slice(2);
  if (!address) { console.error("usage: node tools/smoke_page.mjs <address> [token]"); process.exit(2); }
  const results = await runStory(address, token);
  if (results.some((r) => !r.ok)) process.exitCode = 1;
}
