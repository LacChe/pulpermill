// Runs the card-fill kit (evals/cardfill) through the page's own client and logic: the same request the page builds, the same
// reply reading, the same code rules. It writes what came out, and the rules that fired, for grading by hand with
// evals/cardfill/03-scoring-protocol.md. It does not grade.
//   node tools/run_cardfill.mjs <address> [--token T] [--runs 3] [--only s1-tempting,case-1] [--label name]
//        [--judge] [--runlog PATH] [--out DIR]
//   node tools/run_cardfill.mjs --dry [--only ...]
// <address>   a running backend: `python -m pulpermill.backend --fake` (canned replies), or a server whose Config says `prompter: stub`
//             (or any real prompter).
// --judge     after each fill, also ask the model about the card's model-judged rules (the `judge` call) and record the answer next
//             to the code rules. With the stub or the fake backend this only proves the mechanics.
// --runlog    the server's run log (Config.log_path). Its first line says the prompter's name and version, which go in summary.csv
//             and meta.json so two result sets can be compared. Without it they are recorded as blank.
// --dry       no backend. Builds every request the kit would send (fills and judges, chained on the page's own mock engine) and checks
//             each against the contract (pulpermill.contract, through evals/cardfill/tools/check_requests.py). Writes nothing. Exit 1 on any refusal.
// Output: <out>/summary.csv (one row per fixture, run and card), <out>/meta.json, <out>/<fixture>-run<n>.json. <out> defaults to
// evals/cardfill/results/<label>/.
// Characters: a fixture's character notes name no character, so one character is created per note, in order, and the note is attached to it
// (a fixture with no character note gets one character, for the chapter to fill).
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { schema } from "../tests/web/helpers.mjs";
import "../tests/web/text-setup.mjs";
import { createClient, parseBackendSetting, fillCard, judgeCard } from "../web/client.js";
import { createMock } from "../web/mock.js";
import { addInstance, setCardValues, validate } from "../web/logic.js";

const args = process.argv.slice(2);
const FLAGS = new Set(["--dry", "--judge"]);
const opt = (name, fallback = "") => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : fallback; };
const flag = (name) => args.includes(`--${name}`);
const dry = flag("dry");
const withJudge = flag("judge") || dry;   // a dry run builds the judge requests too
const address = args.find((a, i) => !a.startsWith("--") && !(i > 0 && args[i - 1].startsWith("--") && !FLAGS.has(args[i - 1])));
if (!dry && !address) {
  console.error("usage: node tools/run_cardfill.mjs <address> [--token T] [--runs 3] [--only a,b] [--label name] [--judge] [--runlog PATH] [--out DIR]\n       node tools/run_cardfill.mjs --dry [--only a,b]");
  process.exit(2);
}
const runs = dry ? 1 : Number(opt("runs", "3"));
const only = opt("only") ? opt("only").split(",") : null;
const label = opt("label", new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-"));

const kit = new URL("../evals/cardfill/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("fixtures/manifest.json", kit), "utf8"));
const wanted = manifest.filter((e) => !only || only.includes(e.id));
if (only) for (const id of only) if (!manifest.some((e) => e.id === id)) { console.error(`no fixture named ${id}`); process.exit(2); }

// ---- the backend: a real address, or (dry) the page's mock that remembers every request it was sent
const sent = [];
let current = "";
let client;
if (dry) {
  const mock = createMock(schema, { delay: 0 });
  const send = mock.send.bind(mock);
  mock.send = (request, options) => { sent.push({ label: `${current} ${request.call}${request.card ? ":" + request.card : ""}`, request: structuredClone(request) }); return send(request, options); };
  client = createClient({ setting: { kind: "mock" }, mock, pollEvery: 1 });
} else {
  client = createClient({ setting: parseBackendSetting(address), token: opt("token"), pollEvery: 500 });
}

const fmt = (problems) => problems.map((p) => `${p.rule}@${p.field}${p.item ? "." + p.item : ""}(${p.severity})`);

// Fill one card of the project; returns what happened. `instance` is the character the fill is for (Characters only).
async function fillOne(project, cardId, instance) {
  const card = schema.cards[cardId];
  const started = Date.now();
  const outcome = await fillCard(client, schema, project, cardId, instance?.id ?? null).done;
  const seconds = ((Date.now() - started) / 1000).toFixed(1);
  const who = instance ? `${cardId}#${project[cardId].indexOf(instance) + 1}` : cardId;
  if (!outcome.ok) return { card: who, ok: false, error: outcome.error?.kind ?? outcome.reason ?? "failed", seconds };
  const target = card.many_per_project ? instance : (project[cardId] ??= {});
  setCardValues(card, target, outcome.next);
  const { problems } = validate(card, target, project);
  const step = { card: who, ok: true, seconds, values: outcome.next, filled: outcome.filled, replaced: outcome.replaced,
                 unresolved: outcome.unresolved, rules: fmt(problems) };
  if (withJudge) {
    client.judgeCache.clear();   // every run asks the model afresh
    const judged = await judgeCard(client, schema, project, cardId, target).done;
    step.judge = judged.ok
      ? { ok: true, fired: fmt(judged.problems), answered: judged.answered, missing: judged.missing }
      : { ok: false, error: judged.error?.kind ?? judged.reason ?? "failed", fired: [], answered: [], missing: [] };
  }
  return step;
}

// The cards to fill for one fixture: a card per entry of `fill`; Characters once per character note (or once, for a chapter).
function plan(project, fill) {
  const jobs = [];
  for (const cardId of fill) {
    const card = schema.cards[cardId];
    if (!card.many_per_project) { jobs.push({ cardId, instance: null }); continue; }
    const notes = (project.card_notes ?? []).filter((n) => n.card === cardId && !n.character);
    const people = notes.length ? notes.map((note) => { const person = addInstance(project, card); note.character = person.id; return person; })
                               : [(project[cardId] ?? [])[0] ?? addInstance(project, card)];
    for (const instance of people) jobs.push({ cardId, instance });
  }
  return jobs;
}

const header = ["fixture", "run", "card", "ok", "error", "seconds", "filled", "replaced", "unresolved", "rules_fired",
                "judge_fired", "judge_missing", "prompter_name", "prompter_version"];
const rows = [];
const prompter = (() => {
  const path = opt("runlog");
  if (!path || !existsSync(path)) return { name: "", version: "" };
  for (const line of readFileSync(path, "utf8").split("\n")) {
    try { const rec = JSON.parse(line); if (rec.record === "settings") return { name: rec.prompter?.name ?? "", version: rec.prompter?.version ?? "" }; } catch { /* not a record */ }
  }
  return { name: "", version: "" };
})();

const out = dry ? null : (opt("out") ? new URL(opt("out").replace(/\/?$/, "/"), `file://${process.cwd()}/`) : new URL(`results/${label}/`, kit));
if (out) mkdirSync(out, { recursive: true });
const started = new Date().toISOString();

for (const entry of wanted) {
  current = entry.id;
  const source = JSON.parse(readFileSync(new URL(`fixtures/projects/${entry.id}.json`, kit), "utf8"));
  for (let run = 1; run <= runs; run++) {
    const project = structuredClone(source);
    const steps = [];
    for (const { cardId, instance } of plan(project, entry.fill)) {
      const step = await fillOne(project, cardId, instance);
      steps.push(step);
      rows.push([entry.id, run, step.card, step.ok, step.error ?? "", step.seconds, (step.filled ?? []).join(" "), (step.replaced ?? []).join(" "),
                 (step.unresolved ?? []).length, (step.rules ?? []).join(" "), (step.judge?.fired ?? []).join(" "), (step.judge?.missing ?? []).join(" "),
                 prompter.name, prompter.version]);
      console.log(`${step.ok ? "ok  " : "FAIL"} ${entry.id} run ${run} ${step.card} ${step.seconds}s ${step.error ?? ""}`);
      if (!step.ok) break;
    }
    if (out) writeFileSync(new URL(`${entry.id}-run${run}.json`, out), JSON.stringify({ fixture: entry, run, prompter, steps, project }, null, 2));
  }
}

if (dry) {
  // Judge requests are built too: one per card the fixture filled, from the finished values.
  const check = spawnSync("python3", [fileURLToPath(new URL("tools/check_requests.py", kit))], { input: JSON.stringify(sent), encoding: "utf8" });
  process.stdout.write(check.stdout);
  if (check.status !== 0) { process.stderr.write(check.stderr); console.error("dry run: some requests break the contract"); process.exit(1); }
  const failed = rows.filter((r) => r[3] !== true);
  if (failed.length) { console.error(`dry run: ${failed.length} fills did not complete`); process.exit(1); }
  console.log(`dry run passed: ${wanted.length} fixtures, ${sent.length} requests`);
} else {
  const csv = [header, ...rows].map((r) => r.map((c) => `"${String(c).replaceAll('"', '""')}"`).join(",")).join("\n");
  writeFileSync(new URL("summary.csv", out), csv + "\n");
  writeFileSync(new URL("meta.json", out), JSON.stringify({ label, started, finished: new Date().toISOString(), address, runs, judge: withJudge,
    schema_version: JSON.parse(readFileSync(new URL("fixtures/projects/" + wanted[0].id + ".json", kit), "utf8")).schema_version,
    fixtures: wanted.length, prompter, runlog: opt("runlog") || null }, null, 2) + "\n");
  console.log(`written to ${fileURLToPath(out)}`);
}
