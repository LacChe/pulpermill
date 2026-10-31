// Runs the page's own client against a running backend: the story calls end to end (plan, generate, then the end of story folded by the page), plus
// style_fit and a status check. It uses the mock to build a ready project, then talks to the real address.
//   python -m pulpermill.backend --fake --port 8000 &
//   node tools/smoke_page.mjs http://127.0.0.1:8000 [token]
import { readyProject, schema } from "../tests/web/helpers.mjs";
import "../tests/web/text-setup.mjs";
import { createClient, parseBackendSetting, planChapter, generateChapter, checkStyleFit } from "../web/client.js";
import { ensureBeat, placeBeat } from "../web/plan.js";
import { makeAfterStory } from "../web/endstory.js";
import { lockStaticCards } from "../web/gate.js";
import { commitChapter } from "../web/generate.js";

const [address, token = ""] = process.argv.slice(2);
if (!address) { console.error("usage: node tools/smoke_page.mjs <address> [token]"); process.exit(2); }

const project = await readyProject();
project.setup.chapter_count = 2;
lockStaticCards(project);
const client = createClient({ setting: parseBackendSetting(address), token, pollEvery: 200 });
const say = (what, ok, extra = "") => { console.log(`${ok ? "ok  " : "FAIL"} ${what} ${extra}`); if (!ok) process.exitCode = 1; };

say("status", (await client.checkStatus()) === "idle");
const fit = await checkStyleFit(client, schema, project).done;
say("style_fit", fit.ok === true, fit.error?.kind ?? "");
for (let n = 1; n <= 2; n++) {
  const plan = await planChapter(client, schema, project, ensureBeat(schema, project)).done;
  say(`plan chapter ${n}`, plan.ok === true, plan.error?.kind ?? plan.reason ?? "");
  if (!plan.ok) break;
  placeBeat(project, plan.beat);
  const written = await generateChapter(client, schema, project).done;
  say(`generate chapter ${n}`, written.ok === true, written.error?.kind ?? written.reason ?? "");
  if (!written.ok) break;
  commitChapter(project, written.outcome);
}
// The end of the story is mechanical now (no model call): the page folds the shifts into the cards.
const end = makeAfterStory(project);
say("end of story (no call)", end.ok === true, end.reason ?? "");
