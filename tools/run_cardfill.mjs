// Runs the card-fill kit (tests/cardfill) against a running backend, through the page's own client and logic: the same
// request the page builds, the same reply reading, the same code rules. It writes what came out, and the rules that fired,
// for grading by hand with tests/cardfill/03-scoring-protocol.md. It does not grade.
//   node tools/run_cardfill.mjs <address> [--token T] [--runs 3] [--only s1-tempting,case-1] [--label name]
// Output: tests/cardfill/results/<label>/<fixture>-run<n>.json and summary.csv (one row per fixture and run).
// Characters: the fixtures' note names no character, so one character is created per run and the note is attached to it
// (a case with several characters is filled for that one; fill the others by hand in the page).
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { schema } from "../web/tests/helpers.mjs";
import "../web/tests/text-setup.mjs";
import { createClient, parseBackendSetting, fillCard } from "../web/client.js";
import { addInstance, setCardValues, validate } from "../web/logic.js";

const args = process.argv.slice(2);
const address = args.find((a) => !a.startsWith("--") && !args[args.indexOf(a) - 1]?.startsWith("--"));
const opt = (name, fallback = "") => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : fallback; };
if (!address) { console.error("usage: node tools/run_cardfill.mjs <address> [--token T] [--runs 3] [--only a,b] [--label name]"); process.exit(2); }
const runs = Number(opt("runs", "3"));
const only = opt("only") ? opt("only").split(",") : null;
const label = opt("label", new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-"));

const kit = new URL("../tests/cardfill/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("fixtures/manifest.json", kit), "utf8"));
const out = new URL(`results/${label}/`, kit);
mkdirSync(out, { recursive: true });
const client = createClient({ setting: parseBackendSetting(address), token: opt("token"), pollEvery: 500 });
const rows = [["fixture", "run", "card", "ok", "error", "seconds", "filled", "replaced", "unresolved", "rules_fired"]];

async function fillOne(project, cardId) {
  const card = schema.cards[cardId];
  let instance = null;
  if (card.many_per_project) {
    instance = (project[cardId] ?? [])[0] ?? addInstance(project, card);
    for (const note of project.card_notes ?? []) if (note.card === cardId && !note.character) note.character = instance.id;
  }
  const started = Date.now();
  const outcome = await fillCard(client, schema, project, cardId, instance?.id ?? null).done;
  const seconds = ((Date.now() - started) / 1000).toFixed(1);
  if (!outcome.ok) return { card: cardId, ok: false, error: outcome.error?.kind ?? outcome.reason ?? "failed", seconds };
  const target = card.many_per_project ? instance : (project[cardId] ??= {});
  setCardValues(card, target, outcome.next);
  const { problems } = validate(card, target, project);
  return { card: cardId, ok: true, seconds, values: outcome.next, filled: outcome.filled, replaced: outcome.replaced,
           unresolved: outcome.unresolved, rules: problems.map((p) => `${p.rule}@${p.field}${p.item ? "." + p.item : ""}(${p.severity})`) };
}

for (const entry of manifest) {
  if (only && !only.includes(entry.id)) continue;
  const source = JSON.parse(readFileSync(new URL(`fixtures/projects/${entry.id}.json`, kit), "utf8"));
  for (let run = 1; run <= runs; run++) {
    const project = structuredClone(source);
    const steps = [];
    for (const cardId of entry.fill) {
      const step = await fillOne(project, cardId);
      steps.push(step);
      rows.push([entry.id, run, cardId, step.ok, step.error ?? "", step.seconds, (step.filled ?? []).join(" "), (step.replaced ?? []).join(" "),
                 (step.unresolved ?? []).length, (step.rules ?? []).join(" ")]);
      console.log(`${step.ok ? "ok  " : "FAIL"} ${entry.id} run ${run} ${cardId} ${step.seconds}s ${step.error ?? ""}`);
      if (!step.ok) break;
    }
    writeFileSync(new URL(`${entry.id}-run${run}.json`, out), JSON.stringify({ fixture: entry, run, steps, project }, null, 2));
  }
}
const csv = rows.map((r) => r.map((c) => `"${String(c).replaceAll('"', '""')}"`).join(",")).join("\n");
writeFileSync(new URL("summary.csv", out), csv + "\n");
console.log(`written to tests/cardfill/results/${label}/`);
