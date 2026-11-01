// The page's own client reads real stub replies for `fill` and `judge` (the two calls the story in tools/smoke_page.mjs does not make).
//   node tests/e2e/fill_judge_page.mjs http://127.0.0.1:8000
// Prints one JSON line per check: {"what": ..., "ok": true|false, "extra": ...}. tests/e2e/test_e2e.py runs it against the real runner
// on the scripted stub engine.
import { readyProject, schema } from "../web/helpers.mjs";
import "../web/text-setup.mjs";
import { createClient, parseBackendSetting, fillCard, judgeCard } from "../../web/client.js";

const address = process.argv[2];
const out = (what, ok, extra = "") => console.log(JSON.stringify({ what, ok: Boolean(ok), extra }));
const client = createClient({ setting: parseBackendSetting(address), token: process.argv[3] ?? "", pollEvery: 50 });
const project = await readyProject();

// ---- fill: one card, then one instance of a card held many times ----
for (const [cardId, instance] of [["world", null], ["characters", project.characters[0].id]]) {
  const result = await fillCard(client, schema, project, cardId, instance).done;
  out(`fill ${cardId}: the page reads the stub's reply`, result.ok === true, result.ok ? "" : JSON.stringify(result));
  if (result.ok) {
    const keys = new Set(schema.cards[cardId].fields.map((f) => f.key));
    const touched = [...(result.filled ?? []), ...(result.replaced ?? [])].map((x) => (typeof x === "string" ? x : x.key ?? x.field));
    out(`fill ${cardId}: the reply gives the page something to land, all of it fields of the card`, touched.length > 0 && touched.every((k) => keys.has(k)), touched.join(","));
    out(`fill ${cardId}: nothing the reply named is left unresolved`, (result.unresolved ?? []).length === 0, JSON.stringify(result.unresolved ?? []));
  }
}

// ---- judge: every model rule of a card, answered ----
for (const cardId of ["world", "characters"]) {
  const card = schema.cards[cardId];
  const instance = card.many_per_project ? project[cardId][0] : project[cardId];
  const asked = card.rules.filter((r) => r.needs_model).map((r) => r.id);
  const result = await judgeCard(client, schema, project, cardId, instance).done;
  out(`judge ${cardId}: the page reads the stub's reply`, result.ok === true, result.ok ? "" : JSON.stringify(result));
  if (result.ok) {
    out(`judge ${cardId}: every model rule asked is answered`, asked.length > 0 && result.missing.length === 0 && asked.every((id) => result.answered.includes(id)),
      `asked ${asked.length}, answered ${result.answered.length}, missing ${result.missing.length}`);
    out(`judge ${cardId}: each problem names a rule that was asked`, result.problems.every((p) => asked.includes(p.rule)), `${result.problems.length} problems`);
  }
}
