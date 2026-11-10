// The page's theme: which look it wears (web/themes.css has one block of tokens per theme, picked by data-theme on <html>).
// The choice is a viewing preference of this browser. It is remembered here and is never part of a project or an export.
import { section, fill } from "./text.js";

export const THEMES = ["timbermill", "circuit"];     // footer order; each id has a block in themes.css and a name in the text bundle
export const DEFAULT_THEME = "timbermill";
export const THEME_KEY = "pulpermill.theme";         // index.html reads the same key in its head, so a saved choice is on before the first paint
export const STRINGS = section("theme");

// Anything that is not a known theme (an old value, a hand edit) is the default.
export const resolveTheme = (value) => (THEMES.includes(value) ? value : DEFAULT_THEME);

// Storage can be missing or refuse (private windows, blocked cookies): the page then simply starts on the default.
export function readTheme(storage) {
  try { return resolveTheme(storage?.getItem(THEME_KEY)); } catch { return DEFAULT_THEME; }
}

export function saveTheme(storage, id) {
  if (!storage) return false;
  try { storage.setItem(THEME_KEY, resolveTheme(id)); return true; } catch { return false; }
}

// Mobile browsers tint their own bar with the page's colour. The theme's --bg can be any CSS colour, so it is painted on a one
// pixel canvas and read back as plain rgb, the same way favicon.js does it.
function tintBrowser(doc) {
  try {
    const value = doc.defaultView.getComputedStyle(doc.documentElement).getPropertyValue("--bg").trim();
    const ctx = doc.createElement("canvas").getContext?.("2d", { willReadFrequently: true });
    if (!value || !ctx) return;
    ctx.fillStyle = "#000000";
    ctx.fillStyle = value;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
    let meta = doc.querySelector('meta[name="theme-color"]');
    if (!meta) { meta = doc.createElement("meta"); meta.name = "theme-color"; doc.head.append(meta); }
    meta.content = `rgb(${r}, ${g}, ${b})`;
  } catch { /* the browser's bar keeps the colour index.html gave it */ }
}

// Put a theme on the page. The event lets parts that painted themselves from the old colours (the tab icon) paint again.
export function applyTheme(doc, id) {
  const theme = resolveTheme(id);
  doc.documentElement.dataset.theme = theme;
  tintBrowser(doc);
  doc.dispatchEvent(new CustomEvent("themechange", { detail: { id: theme } }));
  return theme;
}

// Spelled out one by one because the test that ties the code to the text bundle looks for each key written out in full.
const nameOf = (id) => ({ timbermill: STRINGS.timbermill, circuit: STRINGS.circuit })[id];

function pageStorage(doc) {
  try { return doc.defaultView.localStorage; } catch { return null; }
}

function element(doc, tag, className, attributes = {}) {
  const made = doc.createElement(tag);
  made.className = className;
  for (const [name, value] of Object.entries(attributes)) made.setAttribute(name, value);
  return made;
}

// The footer: a label and one radio button per theme. A radio group has one tab stop (the chosen theme) and the arrow keys
// move and choose, as people expect from radio buttons. Returns { current, set }.
export function mountThemeBar(root, { doc = document, storage = pageStorage(doc) } = {}) {
  let current = readTheme(storage);

  const label = element(doc, "span", "theme-label");
  const group = element(doc, "div", "theme-options", { role: "radiogroup" });

  const names = [];     // each button's visible name, kept so relabel can reword it
  const buttons = THEMES.map((id) => {
    const button = element(doc, "button", "theme-swatch", { type: "button", role: "radio" });
    button.dataset.themeId = id;
    const dot = element(doc, "span", "theme-dot", { "aria-hidden": "true" });
    const text = element(doc, "span", "theme-name");
    button.append(dot, text);
    names.push(text);
    button.addEventListener("click", () => set(id));
    group.append(button);
    return button;
  });

  // Every word of the footer, read from the bundle each time: the page can change language while it is open.
  function relabel() {
    label.textContent = STRINGS.label;
    group.setAttribute("aria-label", STRINGS.groupLabel);
    buttons.forEach((button, at) => {
      const name = nameOf(THEMES[at]);
      button.setAttribute("aria-label", name);
      button.setAttribute("title", fill(STRINGS.pick, { name }));
      names[at].textContent = name;
    });
  }

  function show() {
    buttons.forEach((button, at) => {
      const chosen = THEMES[at] === current;
      button.setAttribute("aria-checked", String(chosen));
      button.setAttribute("tabindex", chosen ? "0" : "-1");
    });
  }

  function set(id, { focus = false } = {}) {
    current = applyTheme(doc, id);
    saveTheme(storage, current);
    show();
    if (focus) buttons[THEMES.indexOf(current)].focus();
  }

  group.addEventListener("keydown", (event) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    const at = THEMES.indexOf(current);
    let next = null;
    if (step) next = (at + step + THEMES.length) % THEMES.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = THEMES.length - 1;
    if (next === null) return;
    event.preventDefault();
    set(THEMES[next], { focus: true });
  });

  root.replaceChildren(label, group);
  relabel();
  current = applyTheme(doc, current);     // index.html's head script already did this; doing it again keeps the bar and the page in step
  show();
  return { current: () => current, set, relabel };
}
