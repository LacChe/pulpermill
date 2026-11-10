import "./text-setup.mjs";
// A written chapter's tab shows only that chapter and has its own Write again button; the generate panel no longer lists chapters.
// There is no browser here, so a very small stand-in for `document` is enough to draw the two panels and read what they drew.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { story, schema } from "./fixture.mjs";
import { bundle } from "./text-setup.mjs";
import { fill } from "../../web/text.js";

class Element {
  constructor(tagName) { this.tagName = tagName; this.children = []; this.listeners = {}; this.dataset = {}; this.isConnected = true; }
  append(...kids) { this.children.push(...kids); }
  addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
  click() { for (const fn of this.listeners.click ?? []) fn(); }
}
globalThis.document = { createElement: (tag) => new Element(tag) };

const { createChapterPanel } = await import("../../web/chapterpanel.js");
const { createGeneratePanel } = await import("../../web/generatepanel.js");
const { setChapterNote } = await import("../../web/modelnotes.js");
const { setWriterLock } = await import("../../web/gate.js");
const { generateGate } = await import("../../web/generate.js");

const GENERATE = bundle.generate;
const walk = (node, out = []) => { out.push(node); for (const kid of node.children ?? []) walk(kid, out); return out; };
const buttons = (root) => walk(root).filter((n) => n.tagName === "button");
const withClass = (root, name) => walk(root).filter((n) => n.className === name || String(n.className ?? "").split(/\s+/).includes(name));
const texts = (root) => walk(root).map((n) => n.textContent).filter((t) => typeof t === "string" && t);

const SECOND = "Marit found the ledger in the quay stores.";
function twoWritten() {
  const p = story();
  p.chapters.push({ id: "k0000002", beat: "b0000002", text: SECOND });
  p.summary_events.entries.push({ id: "e0000002", beat: "b0000002", happened: "Marit found the ledger.", changed: "" });
  return p;
}
const idleClient = () => ({ state: { working: false, stage: null, since: null }, onChange() {} });

function chapterPanel(project, client = idleClient(), redo = () => {}) {
  const panel = createChapterPanel({ schema, client, getProject: () => project, redo });
  const draw = (chapter) => { const root = new Element("div"); panel.draw(root, chapter); return root; };
  return { panel, draw };
}

test("each written chapter's tab has one Write again button, for that chapter, and shows nothing of the other chapters", () => {
  const project = twoWritten();
  const { draw } = chapterPanel(project);
  const first = draw(1);
  assert.deepEqual(buttons(first).map((b) => b.textContent), [fill(GENERATE.again, { n: 1 })]);
  assert.ok(!texts(first).includes(SECOND), "chapter 2's text is not on chapter 1's tab");
  const second = draw(2);
  assert.deepEqual(buttons(second).map((b) => b.textContent), [fill(GENERATE.again, { n: 2 })]);
  assert.ok(texts(second).includes(SECOND));
  assert.ok(!texts(second).includes(project.chapters[0].text), "chapter 1's text is not on chapter 2's tab");
  assert.equal(withClass(first, "chapter-list").length + withClass(second, "chapter-list").length, 0);
});

test("the button asks for that chapter again and says how many later chapters it affects", () => {
  const project = twoWritten();
  const asked = [];
  const { draw } = chapterPanel(project, idleClient(), async (...args) => { asked.push(args); });
  buttons(draw(1))[0].click();
  buttons(draw(2))[0].click();
  assert.deepEqual(asked.map(([p, number, later]) => [p === project, number, later]), [[true, 1, 1], [true, 2, 0]]);
});

test("a locked Outline shows the reason in place of the button", () => {
  const project = twoWritten();
  setWriterLock(project, "outline", true);
  const root = chapterPanel(project).draw(1);
  assert.equal(buttons(root).length, 0);
  assert.ok(texts(root).includes(GENERATE.reasonsAgain.outline_locked));
});

test("a chapter that is not written has no Write again button", () => {
  const root = chapterPanel(story()).draw(2);
  assert.equal(buttons(root).length, 0);
});

test("after Write again, the chapter's tab shows the earlier text beside the new one", () => {
  const project = twoWritten();
  setChapterNote(project, "k0000002", { changes: [], warnings: [], before: "An older version." });
  const root = chapterPanel(project).draw(2);
  const [compare] = withClass(root, "chapter-compare");
  assert.ok(compare, "the two texts sit side by side");
  assert.deepEqual(texts(compare), [GENERATE.before, "An older version.", GENERATE.after, SECOND]);
  assert.equal(withClass(chapterPanel(project).draw(1), "chapter-compare").length, 0, "the other chapter was not written again");
});

test("the generate panel lists no written chapters and has no Write again buttons, whatever is written", () => {
  const project = twoWritten();
  project.outline.beats.push({ id: "b0000003", chapter: 3, where: "p0000002", when_time: "Night", cast: ["c0000001", "c0000002"], spotlight: "t1000001", aim: "Suvi wants out.", plan: "She packs." });
  assert.equal(generateGate(schema, project).ok, true, "this project can write chapter 3, so the panel draws its button");
  const panel = createGeneratePanel({ schema, client: idleClient(), getProject: () => project, backendWhere: () => "the sample", errorText: String, changed() {}, redraw() {}, notice() {} });
  const root = new Element("div");
  panel.draw(root);
  assert.deepEqual(buttons(root).map((b) => b.textContent), [fill(GENERATE.button, { n: 3 })]);
  assert.equal(withClass(root, "chapter-list").length, 0);
  assert.ok(!texts(root).some((t) => t.includes(project.chapters[0].text) || t.includes(SECOND)));
  assert.equal(typeof panel.again, "function", "the chapter tabs write a chapter again through the generate panel");
});

test("chapterpanel.js reads only strings the app and generate sections have", () => {
  const code = readFileSync(new URL("../../web/chapterpanel.js", import.meta.url), "utf8").split("\n").map((line) => line.split("//")[0]).join("\n");
  const missing = [];
  for (const [, key] of code.matchAll(/\bSTRINGS\.(\w+)/g)) if (!(key in bundle.app)) missing.push(`app.${key}`);
  for (const [, key] of code.matchAll(/\bGENERATE\.(\w+)/g)) if (!(key in bundle.generate)) missing.push(`generate.${key}`);
  assert.deepEqual([...new Set(missing)], []);
});
