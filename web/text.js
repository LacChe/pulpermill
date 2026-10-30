// The page's words. Every sentence, label and button text the page shows lives in one bundle per language
// (web/data/text.en.json), so a translation is one file and nothing is worded in code. No DOM here, so Node can test it.
//
//   msg(key, values)        the text at a dotted key ("section.key"), with {name} marks filled from values
//   section(name)           a live view of one section, for a module that reads many keys (STRINGS.title)
//   joinList(items, how)    items joined the way the language joins them: "comma" (the default), "semicolon", "sentence"
//                           (what separates one sentence from the next), or "dotted" (a separator inside one line)
//   setText(bundle)         what the page (and the tests) call once the bundle has been read
//   applyStaticText(root)   fills in the text and attributes that index.html marks with data-text and data-text-attrs
//
// The bundle is read once at start, so a section is looked up each time it is used and never copied.

export const TEXT_FILE = "data/text.en.json";

// The one sentence kept in code: if the bundle itself failed to load, there is nothing else to say it with.
export const BOOT_FAILURE = "The page couldn't load its text or schema.";

let bundle = null;

export function setText(next) { bundle = next; }
export const hasText = () => bundle !== null;

// Fills {name} marks. A mark with no value is left as it is, so a missing value shows up instead of reading "undefined".
export const fill = (text, values = {}) => text.replace(/\{(\w+)\}/g, (mark, key) => (key in values ? values[key] : mark));

function need() {
  if (!bundle) throw new Error("The text bundle is not loaded yet. The page loads it at start; tests import tests/text-setup.mjs first.");
  return bundle;
}

function lookup(path) {
  let at = need();
  for (const part of String(path).split(".")) {
    if (at === null || typeof at !== "object" || !(part in at)) return undefined;
    at = at[part];
  }
  return at;
}

// The text at `key`. A key the bundle does not have comes back as itself, so the gap shows on the page; the tie test
// (tests/web/text.test.mjs) keeps that from happening.
export function msg(key, values) {
  const found = lookup(key);
  return typeof found === "string" ? fill(found, values) : String(key);
}

// A live view of one section of the bundle. It reads through to the bundle on every access.
export function section(name) {
  const read = () => {
    const found = lookup(name);
    return found !== null && typeof found === "object" ? found : {};
  };
  return new Proxy({}, {
    get: (_, key) => read()[key],
    has: (_, key) => key in read(),
    ownKeys: () => Reflect.ownKeys(read()),
    getOwnPropertyDescriptor: (_, key) => {
      const descriptor = Object.getOwnPropertyDescriptor(read(), key);
      return descriptor && { ...descriptor, configurable: true };
    },
  });
}

const JOINERS = { comma: "common.comma", semicolon: "common.semicolon", sentence: "common.sentence", dotted: "common.dotted" };

export function joinList(items, how = "comma") {
  return items.join(msg(JOINERS[how] ?? JOINERS.comma));
}

// root is the document. Marked elements: data-text="key" sets the element's text; data-text-attrs="attr:key; attr:key"
// sets attributes. The page language comes from the bundle.
export function applyStaticText(root) {
  const language = need()._meta?.language;
  for (const node of root.querySelectorAll("[data-text]")) node.textContent = msg(node.dataset.text);
  for (const node of root.querySelectorAll("[data-text-attrs]")) {
    for (const pair of node.dataset.textAttrs.split(";")) {
      const at = pair.indexOf(":");
      if (at > 0) node.setAttribute(pair.slice(0, at).trim(), msg(pair.slice(at + 1).trim()));
    }
  }
  if (language && root.documentElement) root.documentElement.lang = language;
}
