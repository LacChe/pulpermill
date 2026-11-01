// Runs the chapter trials (evals/trials) through the page's own client and logic: for each chapter the same plan request, the same
// generate request, the same reading of the reply and the same commit the page makes, so the next chapter plans from the new state.
// It records what came out and runs the machine checks (tools/trial_checks.mjs). It does not grade: a person reads the chapters with
// evals/trials/rubric.md and fills the sheets.
//   node tools/run_trials.mjs <address> [--token T] [--runs 3] [--chapters N] [--only t1-salt-coast,t2-quiet-orchard] [--label name]
//        [--runlog PATH] [--out DIR]
//   node tools/run_trials.mjs --dry [--only ...] [--chapters N]
// <address>   `python -m pulpermill.backend --fake` (canned replies), a server whose Config says `prompter: stub`, or a real prompter.
// --chapters  play only the first N chapters of each trial (default: the story's whole chapter_count).
// --runlog    the server's run log (Config.log_path); its first record says the prompter's name and version, which go in summary.csv and
//             meta.json so two result sets can be compared. Blank without it.
// --dry       no backend. The page's mock answers, every request is built and checked against pulpermill.contract.parse_request
//             (evals/trials/tools/check_requests.py). Writes nothing. Exit 1 when a request is refused or a chapter does not complete.
// Output: <out>/summary.csv (one row per trial, run and chapter), <out>/meta.json, <out>/<trial>-run<n>.md (the chapters, then their flags),
// <out>/<trial>-run<n>.json (the finished project). <out> defaults to evals/trials/results/<label>/.
// The cast of each chapter is the one the page starts with (the protagonist and the two ends of the spotlight tie) plus, in some chapters,
// a deterministic extra person, so cast sizes vary within a trial. A trial is the same on every run except for the model.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { schema } from "../tests/web/helpers.mjs";
import "../tests/web/text-setup.mjs";
import { createClient, parseBackendSetting, planChapter, generateChapter } from "../web/client.js";
import { createMock } from "../web/mock.js";
import { ensureBeat, placeBeat, planRequest, CAST_MAX, castProblem, chapterInfo } from "../web/plan.js";
import { lockStaticCards, startGate } from "../web/gate.js";
import { commitChapter } from "../web/generate.js";
import { effectiveProject } from "../web/effective.js";
import { checkChapter, CHECK_COLUMNS } from "./trial_checks.mjs";

const args = process.argv.slice(2);
const FLAGS = new Set(["--dry"]);
const opt = (name, fallback = "") => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : fallback; };
const dry = args.includes("--dry");
const address = args.find((a, i) => !a.startsWith("--") && !(i > 0 && args[i - 1].startsWith("--") && !FLAGS.has(args[i - 1])));
if (!dry && !address) {
  console.error("usage: node tools/run_trials.mjs <address> [--token T] [--runs 3] [--chapters N] [--only a,b] [--label name] [--runlog PATH] [--out DIR]\n       node tools/run_trials.mjs --dry [--only a,b] [--chapters N]");
  process.exit(2);
}
const runs = dry ? 1 : Number(opt("runs", "3"));
const onlyChapters = opt("chapters") ? Number(opt("chapters")) : null;
const only = opt("only") ? opt("only").split(",") : null;
const label = opt("label", new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-"));

const kit = new URL("../evals/trials/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("manifest.json", kit), "utf8"));
if (only) for (const id of only) if (!manifest.some((e) => e.id === id)) { console.error(`no trial named ${id}`); process.exit(2); }
const wanted = manifest.filter((e) => !only || only.includes(e.id));

// ---- the backend: a real address, or (dry) the page's mock that remembers every request it was sent
const sent = [];
let current = "";
let client;
if (dry) {
  const mock = createMock(schema, { delay: 0 });
  const send = mock.send.bind(mock);
  mock.send = (request, options) => { sent.push({ label: `${current} ${request.call}`, request: structuredClone(request) }); return send(request, options); };
  client = createClient({ setting: { kind: "mock" }, mock, pollEvery: 1 });
} else {
  client = createClient({ setting: parseBackendSetting(address), token: opt("token"), pollEvery: 500 });
}

const prompter = (() => {
  const path = opt("runlog");
  if (!path || !existsSync(path)) return { name: "", version: "" };
  for (const line of readFileSync(path, "utf8").split("\n")) {
    try { const rec = JSON.parse(line); if (rec.record === "settings") return { name: rec.prompter?.name ?? "", version: rec.prompter?.version ?? "" }; } catch { /* not a record */ }
  }
  return { name: "", version: "" };
})();

// A deterministic extra person for some chapters: chapters 2, 4, 6... add the next character not yet in the cast, up to CAST_MAX.
function chooseCast(project, beat) {
  const n = Number(beat.chapter);
  const cast = [...beat.cast];
  if (n % 2 === 0) {
    const eff = effectiveProject(project, n);
    const rest = (eff.characters ?? []).map((c) => c.id).filter((id) => !cast.includes(id));
    const next = rest[(n / 2 - 1) % Math.max(rest.length, 1)];
    if (next && cast.length < CAST_MAX) cast.push(next);
  }
  return cast;
}

const csv = (rows) => rows.map((r) => r.map((c) => `"${String(c ?? "").replaceAll('"', '""')}"`).join(",")).join("\n") + "\n";
const header = ["trial", "run", "chapter", "ok", "error", "seconds", "cast_size", "spotlight", ...CHECK_COLUMNS, "plan_retried", "warnings", "prompter_name", "prompter_version"];
const rows = [];
const out = dry ? null : (opt("out") ? new URL(opt("out").replace(/\/?$/, "/"), `file://${process.cwd()}/`) : new URL(`results/${label}/`, kit));
if (out) mkdirSync(out, { recursive: true });
const started = new Date().toISOString();
let failures = 0;

for (const entry of wanted) {
  current = entry.id;
  const source = JSON.parse(readFileSync(new URL(`projects/${entry.id}.json`, kit), "utf8"));
  for (let run = 1; run <= runs; run++) {
    const project = structuredClone(source);
    const gate = startGate(schema, project);
    if (!gate.ok) { console.error(`FAIL ${entry.id}: the start gate refuses: ${JSON.stringify(gate.stops.map((s) => s.card))}`); failures++; continue; }
    lockStaticCards(project);
    const total = Math.min(onlyChapters ?? Infinity, chapterInfo(project).count);
    const sections = [];
    for (let n = 1; n <= total; n++) {
      const beat = ensureBeat(schema, project);
      beat.cast = chooseCast(project, beat);
      const eff = effectiveProject(project, n);
      const why = castProblem(eff, beat.cast, beat.spotlight);
      const t0 = Date.now();
      const row = [entry.id, run, n];
      const fail = (error) => {
        rows.push([...row, false, error, ((Date.now() - t0) / 1000).toFixed(1), beat.cast.length, beat.spotlight, ...Array(CHECK_COLUMNS.length).fill(""), "", "", prompter.name, prompter.version]);
        console.log(`FAIL ${entry.id} run ${run} chapter ${n}: ${error}`);
        sections.push(`## Chapter ${n}\n\nNot written: ${error}\n`);
        failures++;
      };
      if (why) { fail(`cast_${why}`); break; }
      const plan = await planChapter(client, schema, project, beat).done;
      if (!plan.ok) { fail(`plan ${plan.error?.kind ?? plan.reason ?? "failed"}`); break; }
      placeBeat(project, plan.beat);
      const written = await generateChapter(client, schema, project).done;
      if (!written.ok) { fail(`generate ${written.error?.kind ?? written.reason ?? "failed"}`); break; }
      const outcome = written.outcome;
      const placed = project.outline.beats.find((b) => b.id === beat.id);
      const earlier = (project.chapters ?? []).map((c) => c.text);
      const checks = checkChapter({ language: source.output_language, style: eff.style ?? source.style, text: outcome.chapter.text, eff, cast: placed.cast,
        spotlight: placed.spotlight, earlier, events: outcome.events, shifts: outcome.shifts, proposed: written.read.shifts.length, maxShifts: schema.max_shifts_per_chapter ?? 7 });
      commitChapter(project, outcome);
      const seconds = ((Date.now() - t0) / 1000).toFixed(1);
      const warnings = outcome.warnings.map((w) => w.text).join(" | ");
      rows.push([...row, true, "", seconds, placed.cast.length, placed.spotlight, ...CHECK_COLUMNS.map((c) => checks[c]), plan.retried, warnings, prompter.name, prompter.version]);
      const names = Object.fromEntries((eff.characters ?? []).map((c) => [c.id, c.name]));
      const tie = (eff.entanglements?.ties ?? []).find((t) => t.id === placed.spotlight);
      const flags = Object.entries(checks).filter(([k, v]) => (/_flag$/.test(k) && v) || (k === "opening_repeat" && v) || (k === "changed_empty" && v)
        || (k === "repeated_sentences" && v) || (k === "unknown_count" && v) || (k === "offstage_names" && v)).map(([k, v]) => `${k}=${v}`);
      sections.push([`## Chapter ${n}`, "",
        `Where: ${(eff.world?.places ?? []).find((x) => x.id === placed.where)?.name ?? placed.where} · When: ${placed.when_time} · Cast: ${placed.cast.map((id) => names[id] ?? id).join(", ")}`,
        `Spotlight: ${names[tie?.tie_from] ?? tie?.tie_from} toward ${names[tie?.tie_to] ?? tie?.tie_to}, ${tie?.bond ?? ""} (edge: ${tie?.edge ?? ""})`,
        `Aim: ${placed.aim}`, `Plan: ${placed.plan}`, "", outcome.chapter.text, "",
        `**Happened:** ${outcome.events.happened}`, `**Changed:** ${outcome.events.changed}`,
        `**Shifts (${outcome.shifts.length}):** ${outcome.shifts.map((s) => `${s.card}${s.target ? ":" + (names[s.target] ?? s.target) : ""} ${JSON.stringify(s.patch)}`).join("; ") || "none"}`,
        `**Flags:** ${flags.join(", ") || "none"}`, ""].join("\n"));
      console.log(`ok   ${entry.id} run ${run} chapter ${n}/${total} ${seconds}s ${checks.length} ${source.output_language === "zh" ? "characters" : "words"}${flags.length ? " [" + flags.join(" ") + "]" : ""}`);
    }
    if (out) {
      writeFileSync(new URL(`${entry.id}-run${run}.md`, out), `# ${entry.title} (run ${run})\n\nPrompter: ${prompter.name || "(not recorded: pass --runlog)"} ${prompter.version}. Read each chapter first, then its flags.\n\n${sections.join("\n")}`);
      writeFileSync(new URL(`${entry.id}-run${run}.json`, out), JSON.stringify({ trial: entry, run, prompter, project }, null, 2));
    }
  }
}

if (dry) {
  const check = spawnSync("python3", [fileURLToPath(new URL("evals/trials/tools/check_requests.py", new URL("../", import.meta.url)))], { input: JSON.stringify(sent), encoding: "utf8" });
  process.stdout.write(check.stdout);
  if (check.status !== 0) { process.stderr.write(check.stderr); console.error("dry run: some requests break the contract"); process.exit(1); }
  if (failures) { console.error(`dry run: ${failures} chapters did not complete`); process.exit(1); }
  console.log(`dry run passed: ${wanted.length} trials, ${sent.length} requests`);
} else {
  writeFileSync(new URL("summary.csv", out), csv([header, ...rows]));
  writeFileSync(new URL("meta.json", out), JSON.stringify({ label, started, finished: new Date().toISOString(), address, runs, chapters: onlyChapters,
    schema_version: schema.schema_version, trials: wanted.map((e) => e.id), prompter, runlog: opt("runlog") || null, failures }, null, 2) + "\n");
  console.log(`written to ${fileURLToPath(out)}${failures ? ` (${failures} chapters failed)` : ""}`);
  if (failures) process.exitCode = 1;
}
