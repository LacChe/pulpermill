import { readFileSync } from "node:fs";
import { newProject, settledProject, addInstance, fillRequest, readFillReply, planFill, setCardValues, findInstance } from "../../web/logic.js";
import { createMock } from "../../web/mock.js";

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
  p.setup.protagonist = p.characters[0].id;
  p.entanglements.holdings[0].holdee = p.world.objects[0].id;   // the mock names every sample thing alike, so it cannot pick one
  return p;
}

