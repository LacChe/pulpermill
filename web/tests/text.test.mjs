import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { msg, fill, section, joinList, setText } from "../text.js";
import { bundle } from "./text-setup.mjs";

// ---- The helpers ---------------------------------------------------------------------------

test("msg fills {marks} and leaves a mark with no value as it is", () => {
  assert.equal(msg("common.quoted", { text: "Suvi" }), "“Suvi”");
  assert.equal(fill("a {x} b {y}", { x: 1 }), "a 1 b {y}");
  assert.equal(fill("{n} left", { n: 0 }), "0 left");
});

test("a key the bundle does not have comes back as itself, so the gap shows on the page", () => {
  assert.equal(msg("nothing.here"), "nothing.here");
  assert.equal(msg("common"), "common");           // a section is not a sentence
});

test("a section reads through to the bundle each time, so a bundle set later is seen", () => {
  const view = section("common");
  assert.equal(view.unnamed, "Unnamed");
  assert.deepEqual(Object.keys(view), Object.keys(bundle.common));
  try {
    setText({ ...bundle, common: { ...bundle.common, unnamed: "Sans nom" } });
    assert.equal(view.unnamed, "Sans nom");
    assert.equal(msg("common.unnamed"), "Sans nom");
  } finally {
    setText(bundle);
  }
  assert.equal(view.unnamed, "Unnamed");
});

test("joinList joins the way the bundle says", () => {
  assert.equal(joinList(["a", "b", "c"]), "a, b, c");
  assert.equal(joinList(["a", "b"], "semicolon"), "a; b");
  assert.equal(joinList(["One.", "Two."], "sentence"), "One. Two.");
  assert.equal(joinList(["1 warning", "2 notes"], "dotted"), "1 warning · 2 notes");
  assert.equal(joinList([]), "");
});

// ---- The bundle itself --------------------------------------------------------------------

function* strings(value, path) {
  if (typeof value === "string") yield [path, value];
  else if (Array.isArray(value)) for (const [i, v] of value.entries()) yield* strings(v, `${path}[${i}]`);
  else if (value && typeof value === "object") for (const [k, v] of Object.entries(value)) yield* strings(v, path ? `${path}.${k}` : k);
}

test("the bundle names its language and holds no empty text", () => {
  assert.equal(typeof bundle._meta.language, "string");
  assert.equal(typeof bundle._meta.name, "string");
  for (const [path, text] of strings(bundle, "")) assert.ok(text.trim() !== "" || path === "common.sentence", `${path} is empty`);
});

test("every {mark} in the bundle is a plain word, so fill can find it", () => {
  for (const [path, text] of strings(bundle, "")) {
    for (const [, inside] of text.matchAll(/\{([^}]*)\}/g)) assert.match(inside, /^\w+$/, `${path} has a mark that is not a word: {${inside}}`);
    assert.equal((text.match(/\{/g) ?? []).length, (text.match(/\}/g) ?? []).length, `${path} has an unmatched brace`);
  }
});

// ---- The bundle and the code agree -------------------------------------------------------

const WEB = new URL("../", import.meta.url);
const sourceFiles = readdirSync(WEB).filter((f) => f.endsWith(".js") && !["text.js", "mock.js"].includes(f));
const read = (name) => readFileSync(new URL(name, WEB), "utf8");
const sources = Object.fromEntries(sourceFiles.map((f) => [f, read(f)]));
const html = read("index.html");
const sectionNames = Object.keys(bundle).filter((k) => k !== "_meta");

// {file: {NAME: section}} from `const NAME = section("x")`, and an alias such as `STRINGS as CARD_STRINGS` from another file.
function bindings() {
  const own = {};
  for (const [file, src] of Object.entries(sources)) {
    own[file] = {};
    for (const m of src.matchAll(/(?:export )?const (\w+) = section\("(\w+)"\)/g)) own[file][m[1]] = m[2];
  }
  const all = structuredClone(own);
  for (const [file, src] of Object.entries(sources)) {
    for (const m of src.matchAll(/import \{([^}]*)\} from "\.\/(\w+\.js)"/g)) {
      for (const part of m[1].split(",")) {
        const [from, , as] = part.trim().split(/\s+/);
        if (as && own[m[2]]?.[from]) all[file][as] = own[m[2]][from];
      }
    }
  }
  return all;
}

// Every dotted key the code writes out as a literal: msg("files.untitled"), or the first of two in msg(a ? "x.y" : "x.z").
function literalKeys() {
  const found = new Map();
  const note = (key, where) => { if (!found.has(key)) found.set(key, where); };
  for (const [file, src] of Object.entries({ ...sources, "text.js": read("text.js") })) {
    for (const m of src.matchAll(/"([a-z_]+(?:\.\w+)+)"/g)) if (sectionNames.includes(m[1].split(".")[0])) note(m[1], file);
  }
  for (const m of html.matchAll(/data-text="([\w.]+)"/g)) note(m[1], "index.html");
  for (const m of html.matchAll(/data-text-attrs="([^"]*)"/g)) {
    for (const pair of m[1].split(";")) note(pair.slice(pair.indexOf(":") + 1).trim(), "index.html");
  }
  return found;
}

const lookup = (path) => path.split(".").reduce((at, part) => (at && typeof at === "object" ? at[part] : undefined), bundle);

test("every key the code uses is in the bundle", () => {
  const bound = bindings();
  const missing = [];
  for (const [file, src] of Object.entries(sources)) {
    for (const [name, sec] of Object.entries(bound[file])) {
      if (!(sec in bundle)) { missing.push(`${file}: section "${sec}"`); continue; }
      for (const m of src.matchAll(new RegExp(`\\b${name}\\.(\\w+)`, "g"))) {
        if (!(m[1] in bundle[sec])) missing.push(`${file}: ${name}.${m[1]} (section ${sec})`);
      }
    }
  }
  for (const [key, file] of literalKeys()) if (lookup(key) === undefined) missing.push(`${file}: "${key}"`);
  assert.deepEqual(missing, []);
});

test("every key in the bundle is used by the code", () => {
  const bound = bindings();
  const literal = [...literalKeys().keys()];
  const unused = [];
  for (const sec of sectionNames) {
    for (const key of Object.keys(bundle[sec])) {
      const byName = Object.entries(bound).some(([file, names]) => Object.entries(names)
        .some(([name, s]) => s === sec && new RegExp(`\\b${name}\\.${key}\\b`).test(sources[file])));
      const byLiteral = literal.some((k) => k === `${sec}.${key}` || k.startsWith(`${sec}.${key}.`));
      if (!byName && !byLiteral) unused.push(`${sec}.${key}`);
    }
  }
  assert.deepEqual(unused, []);
});

test("index.html holds no words of its own: every visible word is marked to come from the bundle", () => {
  const body = html.slice(html.indexOf("<body>"));
  const text = body.replace(/<script[\s\S]*?<\/script>/g, "").replace(/<[^>]*>/g, "").trim();
  assert.equal(text, "");
  for (const attr of ["placeholder", "aria-label", "title", "alt"]) assert.doesNotMatch(html, new RegExp(`\\s${attr}="`), `${attr} is worded in index.html`);
});

// A sentence worded in code would never be translated. These are the only ones left, and none of them is ever shown to the
// writer: they are notes for whoever reads a failing test or the browser console (errorText shows a backend's own words only
// for "server" and "bad_request").
const DIAGNOSTICS = new Set([
  "The backend's answer was not JSON.", "This page is already waiting for an answer.", "No answer in time.", "The backend stopped answering.",
  "The updated characters must be the same people, each with the id it was sent with.",
  "The updated characters must each carry the id they were sent with.", "The updated world is missing.",
  "The reply is not an object.", "The reply does not say whether it worked.", "The state is neither idle nor busy.", "The reply has no values.",
  "The value for ${key} is the wrong kind of thing.", "The reply has no results.", "The answer for ${rule.id} has no hits list.",
  "The answer for ${rule.id} names a field the card does not have.", "The reply does not say whether the style fits.",
  "The offstage move needs words for what happened and how it reaches the protagonist.", "The offstage move is missing one of its two parts.",
  "The plan has no thinking text.", "The plan has no beat.", "The chapter text is empty.", "The chapter's events are missing.",
  "The chapter's events have text of the wrong kind.", "The events' ${key} is not a list of names.", "The chapter's events do not say how the goal ended up.",
  "The chapter's shifts are missing.", "A shift does not say who moved.", "A shift's ${key} is not text.", "The proposed changes are missing.", "The new knowledge entries are not a list.",
  "A new knowledge entry does not say who or how they stand.", "A new knowledge entry's rule or fact is not text.",
  "A proposed change does not say what to change.", "The shown entanglements are not a list of ids.", "Rules this page cannot run yet:",
  "Two files are called ${file.name}", "A file name is too long for a zip", "The files are too big for a zip",
]);

test("no sentence is worded in the code except the diagnostics nobody is shown", () => {
  const strip = (line) => (/["'`][^"'`]*\/\//.test(line) ? line : line.split("//")[0]);
  const found = [];
  for (const [file, src] of Object.entries(sources)) {
    src.split("\n").forEach((line, at) => {
      if (/^\s*(import|export \{)/.test(line) || line.includes('from "')) return;
      for (const m of strip(line).matchAll(/"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`/g)) {
        const text = m[1] ?? m[2];
        if (/^[A-Z][a-z’']+ [^\s]+ [^\s]+/.test(text) && !/^[a-z-]+( [a-z-]+)*$/.test(text) && !DIAGNOSTICS.has(text)) found.push(`${file}:${at + 1}: ${text.slice(0, 70)}`);
      }
    });
  }
  assert.deepEqual(found, []);
});
