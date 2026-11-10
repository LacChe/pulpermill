import { bundle } from "./text-setup.mjs";
import { setText } from "../../web/text.js";
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import { THEMES, DEFAULT_THEME, THEME_KEY, resolveTheme, readTheme, saveTheme, applyTheme, mountThemeBar } from "../../web/theme.js";

// ---- Choosing and remembering a theme --------------------------------------------------------

test("a known theme stays, and anything else is the default", () => {
  for (const id of THEMES) assert.equal(resolveTheme(id), id);
  for (const odd of [undefined, null, "", "Timber", "neon", 3, {}]) assert.equal(resolveTheme(odd), DEFAULT_THEME);
  assert.equal(DEFAULT_THEME, "timber");
});

const memory = (start = {}) => {
  const data = { ...start };
  return { data, getItem: (key) => (key in data ? data[key] : null), setItem: (key, value) => { data[key] = String(value); } };
};
const broken = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };

test("a saved theme is read back, and a missing or unreadable one is the default", () => {
  const storage = memory();
  assert.equal(readTheme(storage), DEFAULT_THEME);
  assert.equal(saveTheme(storage, "circuit"), true);
  assert.equal(storage.data[THEME_KEY], "circuit");
  assert.equal(readTheme(storage), "circuit");
  assert.equal(readTheme(memory({ [THEME_KEY]: "gone" })), DEFAULT_THEME);
  assert.equal(readTheme(broken), DEFAULT_THEME);
  assert.equal(readTheme(undefined), DEFAULT_THEME);
});

test("saving never throws when storage refuses or is missing, and never stores a theme that does not exist", () => {
  assert.equal(saveTheme(broken, "circuit"), false);
  assert.equal(saveTheme(undefined, "circuit"), false);
  const storage = memory();
  saveTheme(storage, "neon");
  assert.equal(storage.data[THEME_KEY], DEFAULT_THEME);
});

// ---- A stand-in for the page ---------------------------------------------------------------

class FakeElement {
  constructor(tag, doc) { this.tag = tag; this.doc = doc; this.className = ""; this.dataset = {}; this.attributes = {}; this.children = []; this.listeners = {}; this.textContent = ""; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  append(...kids) { this.children.push(...kids); }
  replaceChildren(...kids) { this.children = kids; }
  addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
  focus() { this.doc.focused = this; }
  fire(name, event = {}) { for (const fn of this.listeners[name] ?? []) fn(event); }
}

function fakePage() {
  const doc = {
    documentElement: { dataset: {} }, head: { append() {} }, defaultView: {}, events: [], focused: null,
    createElement: (tag) => new FakeElement(tag, doc),
    querySelector: () => null,
    dispatchEvent: (event) => doc.events.push(event),
  };
  return doc;
}

test("applying a theme sets data-theme and tells the page, even when the browser has no canvas to tint its bar with", () => {
  const doc = fakePage();
  assert.equal(applyTheme(doc, "circuit"), "circuit");
  assert.equal(doc.documentElement.dataset.theme, "circuit");
  assert.equal(doc.events.length, 1);
  assert.equal(doc.events[0].type, "themechange");
  assert.deepEqual(doc.events[0].detail, { id: "circuit" });
  assert.equal(applyTheme(doc, "bogus"), DEFAULT_THEME);
  assert.equal(doc.documentElement.dataset.theme, DEFAULT_THEME);
});

// ---- The footer ----------------------------------------------------------------------------------

function mounted(start) {
  const doc = fakePage();
  const storage = memory(start);
  const root = new FakeElement("footer", doc);
  const bar = mountThemeBar(root, { doc, storage });
  const [label, group] = root.children;
  return { doc, storage, bar, label, group, buttons: group.children };
}
const checked = (buttons) => buttons.filter((b) => b.getAttribute("aria-checked") === "true").map((b) => b.dataset.themeId);

test("the footer is a radio group with one button per theme, named in words, and one tab stop", () => {
  const { group, buttons, label, doc } = mounted();
  assert.equal(label.textContent, "Theme");
  assert.equal(group.getAttribute("role"), "radiogroup");
  assert.ok(group.getAttribute("aria-label"));
  assert.deepEqual(buttons.map((b) => b.dataset.themeId), THEMES);
  assert.deepEqual(buttons.map((b) => b.getAttribute("aria-label")), ["Timber", "Circuit", "Flour", "Paper", "Stone", "Pulp"]);
  for (const button of buttons) { assert.equal(button.getAttribute("role"), "radio"); assert.match(button.getAttribute("title"), /^Use the \w+ theme$/); }
  assert.deepEqual(checked(buttons), ["timber"]);
  assert.deepEqual(buttons.map((b) => b.getAttribute("tabindex")), ["0", "-1", "-1", "-1", "-1", "-1"]);
  assert.equal(doc.documentElement.dataset.theme, "timber");
});

test("the footer starts on the saved theme", () => {
  const { buttons, doc } = mounted({ [THEME_KEY]: "circuit" });
  assert.deepEqual(checked(buttons), ["circuit"]);
  assert.equal(doc.documentElement.dataset.theme, "circuit");
});

test("clicking a theme puts it on the page, saves it, and moves the one tab stop", () => {
  const { buttons, doc, storage, bar } = mounted();
  buttons[1].fire("click");
  assert.equal(doc.documentElement.dataset.theme, "circuit");
  assert.equal(storage.data[THEME_KEY], "circuit");
  assert.equal(bar.current(), "circuit");
  assert.deepEqual(checked(buttons), ["circuit"]);
  assert.deepEqual(buttons.map((b) => b.getAttribute("tabindex")), ["-1", "0", "-1", "-1", "-1", "-1"]);
  assert.equal(doc.events.at(-1).detail.id, "circuit");
});

test("the arrow keys, Home and End move and choose, wrapping round, and other keys are left alone", () => {
  const { group, buttons, doc, bar } = mounted();
  const press = (key) => { const event = { key, prevented: false, preventDefault() { this.prevented = true; } }; group.fire("keydown", event); return event; };
  assert.equal(press("ArrowRight").prevented, true);
  assert.equal(bar.current(), "circuit");
  assert.equal(doc.focused, buttons[1]);
  press("ArrowLeft");
  assert.equal(bar.current(), "timber");
  press("ArrowLeft");
  assert.equal(bar.current(), THEMES.at(-1));               // wrapped round to the last
  press("ArrowRight");
  assert.equal(bar.current(), "timber");                    // and round to the first
  press("Home");
  assert.equal(bar.current(), "timber");
  press("End");
  assert.equal(bar.current(), THEMES.at(-1));
  assert.equal(press("a").prevented, false);
  assert.equal(press("Tab").prevented, false);
});

test("the footer still works when storage is missing", () => {
  const doc = fakePage();
  const root = new FakeElement("footer", doc);
  const bar = mountThemeBar(root, { doc, storage: null });
  bar.set("circuit");
  assert.equal(doc.documentElement.dataset.theme, "circuit");
});

test("the footer is worded again when the page changes language, and says the same of every theme in the new one", () => {
  const { bar, label, group, buttons } = mounted();
  const zh = JSON.parse(readFileSync(new URL("../../web/data/text.zh.json", import.meta.url), "utf8"));
  try {
    setText(zh);
    bar.relabel();
    assert.equal(label.textContent, zh.theme.label);
    assert.equal(group.getAttribute("aria-label"), zh.theme.groupLabel);
    assert.equal(buttons[0].getAttribute("title"), zh.theme.pick.replace("{name}", zh.theme.timber));
    assert.equal(buttons[0].children[1].textContent, zh.theme.timber);
  } finally { setText(bundle); }
  bar.relabel();
  assert.equal(label.textContent, "Theme");
});
