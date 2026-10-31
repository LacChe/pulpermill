import { readFileSync } from "node:fs";
import { newProject, settledProject, addInstance, fillRequest, readFillReply, planFill, setCardValues, findInstance } from "../../web/logic.js";
import { createMock } from "../../web/mock.js";
import { planChapter, generateChapter } from "../../web/client.js";
import { ensureBeat, placeBeat } from "../../web/plan.js";
import { commitChapter } from "../../web/generate.js";

export const schema = JSON.parse(readFileSync(new URL("../../web/data/schema.en.json", import.meta.url), "utf8"));
const characters = schema.cards.characters;

// A project every card of which the mock has filled in, with the two things the mock cannot make sensible on its own set by hand.
export async function readyProject() {
  const mock = createMock(schema, { delay: 0 });
  const p = settledProject(schema, { ...newProject(schema), example_chapter: "Once." });
  async function fillOne(cardId, instanceId = null) {
    const card = schema.cards[cardId];
    const read = readFillReply(card, await mock.send(fillRequest(schema, p, cardId, instanceId).request));
    const current = card.many_per_project ? findInstance(p, card, instanceId) : p[cardId];
    const plan = planFill(card, current, read, p);
    setCardValues(card, current, Object.fromEntries([...plan.filled, ...plan.replaced].map((key) => [key, plan.next[key]])));
  }
  for (const name of ["Suvi", "Ola"]) {
    const person = addInstance(p, characters);
    person.name = name;
    await fillOne("characters", person.id);
    person.name = name;
  }
  for (const id of ["style", "world", "entanglements", "setup"]) await fillOne(id);
  p.world.places.forEach((place, i) => { place.name = `Place ${i + 1}`; });   // the mock names every sample place alike, so give each its own
  p.setup.protagonist = p.characters[0].id;
  p.entanglements.holdings[0].holdee = p.world.objects[0].id;   // the mock names every sample thing alike, so it cannot pick one
  return p;
}


// Writes the next chapter the way the page does: make the beat, plan it, put the plan in the Outline, write, commit. Returns commitChapter's result.
export async function writeNext(client, project) {
  const beat = ensureBeat(schema, project);
  const plan = await planChapter(client, schema, project, beat).done;
  if (!plan.ok) throw new Error(`plan refused: ${JSON.stringify(plan)}`);
  placeBeat(project, plan.beat);
  const written = await generateChapter(client, schema, project).done;
  if (!written.ok) throw new Error(`generate refused: ${JSON.stringify(written)}`);
  return commitChapter(project, written.outcome);
}
