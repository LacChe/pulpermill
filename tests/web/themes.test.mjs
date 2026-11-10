import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { THEMES, DEFAULT_THEME, THEME_KEY } from "../../web/theme.js";

// The theme files are plain CSS, so these tests read them as text. They keep the rule the themes depend on: the page's own
// stylesheet holds no colour, and every theme block defines every token.

const read = (name) => readFileSync(new URL(`../../web/${name}`, import.meta.url), "utf8");
const withoutComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, "");

// Every token a theme block must define (the same list is at the top of web/themes.css).
export const THEME_TOKENS = [
  "color-scheme", "--bg", "--surface-1", "--surface-2", "--surface-3", "--input", "--line", "--line-strong",
  "--text", "--muted", "--faint", "--accent", "--accent-soft", "--good", "--bad", "--warn", "--shadow-color",
];

// The knobs style.css declares on :root for a theme to override, with the defaults that match the original look.
const KNOBS = ["--bw", "--font-head", "--head-case", "--head-track", "--bar-rule", "--bar-bg", "--bar-text", "--footer-h"];

// Blocks of "selector { declarations }" as {selector, declarations: Map(name -> value)}.
export function blocks(css) {
  const found = [];
  for (const [, selector, body] of withoutComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const declarations = new Map();
    for (const part of body.split(";")) {
      const at = part.indexOf(":");
      if (at > 0) declarations.set(part.slice(0, at).trim(), part.slice(at + 1).trim().replace(/\s+/g, " "));
    }
    found.push({ selector: selector.trim().replace(/\s+/g, " "), declarations });
  }
  return found;
}

test("style.css holds no colour literal, so every colour comes from a theme", () => {
  const colour = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(|\boklab\(|\blab\(|\blch\(/;
  const offenders = withoutComments(read("style.css")).split("\n").filter((line) => colour.test(line));
  // The one documented exception: the dialog backdrop, which becomes a token in the polish step of PLAN-themes.md.
  const unexpected = offenders.filter((line) => !line.includes("dialog.ask::backdrop"));
  assert.deepEqual(unexpected, []);
});

test("style.css declares every theme knob on :root, and no colour tokens", () => {
  const root = blocks(read("style.css")).find((block) => block.selector === ":root");
  assert.ok(root, ":root block not found");
  for (const knob of KNOBS) assert.ok(root.declarations.has(knob), `${knob} is missing from :root`);
  for (const token of THEME_TOKENS) assert.ok(!root.declarations.has(token), `${token} must live in a theme, not :root`);
});

test("themes.css has a Circuit block with every token, and it is also what an unthemed page gets", () => {
  const circuit = blocks(read("themes.css")).find((block) => block.selector.includes('[data-theme="circuit"]'));
  assert.ok(circuit, "Circuit block not found");
  assert.equal(circuit.selector, ':root:not([data-theme]), [data-theme="circuit"]');
  for (const token of THEME_TOKENS) assert.ok(circuit.declarations.has(token), `Circuit is missing ${token}`);
});

// The theme blocks: the ones selected by [data-theme="..."] (the footer swatch rules say data-theme-id, so they are not).
const themeBlocks = () => blocks(read("themes.css")).filter((block) => block.selector.includes('[data-theme="'));
const idOf = (block) => block.selector.match(/\[data-theme="(\w+)"\]/)[1];

test("every theme block in themes.css defines every token", () => {
  const themes = themeBlocks();
  assert.ok(themes.length >= 1);
  for (const theme of themes) {
    for (const token of THEME_TOKENS) assert.ok(theme.declarations.has(token), `${theme.selector} is missing ${token}`);
  }
});

test("Circuit keeps the original values, exactly", () => {
  const circuit = blocks(read("themes.css")).find((block) => block.selector.includes('[data-theme="circuit"]'));
  const expected = {
    "color-scheme": "dark", "--hue": "255",
    "--bg": "oklch(0.17 0.012 var(--hue))", "--surface-1": "oklch(0.21 0.014 var(--hue))",
    "--surface-2": "oklch(0.25 0.016 var(--hue))", "--surface-3": "oklch(0.29 0.018 var(--hue))",
    "--input": "oklch(0.14 0.012 var(--hue))", "--line": "oklch(0.34 0.018 var(--hue))",
    "--line-strong": "oklch(0.44 0.020 var(--hue))", "--text": "oklch(0.94 0.008 var(--hue))",
    "--muted": "oklch(0.76 0.015 var(--hue))", "--faint": "oklch(0.60 0.016 var(--hue))",
    "--accent": "oklch(0.82 0.12 200)", "--accent-soft": "oklch(0.30 0.05 205)", "--good": "oklch(0.80 0.14 155)",
    "--bad": "oklch(0.74 0.15 25)", "--warn": "oklch(0.82 0.13 85)", "--shadow-color": "rgb(0 0 0 / 0.4)",
  };
  for (const [name, value] of Object.entries(expected)) assert.equal(circuit.declarations.get(name), value, name);
});

test("index.html loads themes.css after style.css and starts on the default theme", () => {
  const html = read("index.html");
  assert.match(html, new RegExp(`<html[^>]*\\sdata-theme="${DEFAULT_THEME}"`));
  const sheets = [...html.matchAll(/<link rel="stylesheet" href="([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(sheets, ["style.css", "themes.css"]);
});

// ---- Which themes exist ----------------------------------------------------------------------

test("a theme is in THEMES exactly when themes.css has a block for it, and the default is one of them", () => {
  assert.deepEqual(themeBlocks().map(idOf).sort(), [...THEMES].sort());
  assert.ok(THEMES.includes(DEFAULT_THEME));
});

test("the head script of index.html uses theme.js's key and knows exactly the same themes", () => {
  const html = read("index.html");
  const script = html.match(/<script>(try\{[^<]*)<\/script>/)?.[1];
  assert.ok(script, "the head script is missing");
  assert.ok(html.indexOf(script) < html.indexOf('href="style.css"'), "it must run before the stylesheets");
  assert.ok(script.includes(`getItem("${THEME_KEY}")`));
  const ids = script.match(/\^\(([\w|]+)\)\$/)?.[1].split("|");
  assert.deepEqual(ids, THEMES);
});

test("the theme-color meta tag starts as the default theme's background", () => {
  const meta = read("index.html").match(/<meta name="theme-color" content="([^"]+)"/)?.[1];
  const block = themeBlocks().find((b) => idOf(b) === DEFAULT_THEME);
  assert.equal(meta?.toUpperCase(), block.declarations.get("--bg").toUpperCase());
});

// ---- Colour maths: the footer swatches and the contrast floors -------------------------------

const toLinear = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
function oklchToRgb(L, C, h) {
  const a = C * Math.cos((h * Math.PI) / 180), b = C * Math.sin((h * Math.PI) / 180);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, n = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * n, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * n, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * n];
  return lin.map((v) => Math.round(Math.min(1, Math.max(0, toLinear(v))) * 255));
}

// A token's value as [r, g, b] (0-255). Handles #rrggbb and oklch(L C h), where h may be var(--hue) from the same block.
function rgbOf(value, block) {
  const text = value.replace(/var\(--hue\)/g, block.declarations.get("--hue") ?? "0");
  const hex = text.match(/^#([0-9a-f]{6})$/i);
  if (hex) return [0, 2, 4].map((at) => parseInt(hex[1].slice(at, at + 2), 16));
  const ok = text.match(/^oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)$/);
  if (ok) return oklchToRgb(Number(ok[1]), Number(ok[2]), Number(ok[3]));
  throw new Error(`cannot read the colour ${value}`);
}

const luminance = (rgb) => {
  const [r, g, b] = rgb.map((v) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };

test("each footer swatch pair equals the background and accent of the theme it picks", () => {
  const css = withoutComments(read("themes.css"));
  for (const block of themeBlocks()) {
    const id = idOf(block);
    const rule = css.match(new RegExp(`\\.theme-swatch\\[data-theme-id="${id}"\\]\\s*\\{([^}]*)\\}`));
    assert.ok(rule, `${id} has no swatch pair`);
    const pair = Object.fromEntries([...rule[1].matchAll(/(--sw-[12])\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
    const same = (swatch, token) => rgbOf(swatch, block).every((v, at) => Math.abs(v - rgbOf(block.declarations.get(token), block)[at]) <= 1);
    assert.ok(same(pair["--sw-1"], "--bg"), `${id}: --sw-1 is not its --bg`);
    assert.ok(same(pair["--sw-2"], "--accent"), `${id}: --sw-2 is not its --accent`);
  }
});

// Contrast floors (WCAG ratios). Text colours need 4.5; --faint is only for disabled and placeholder text; a line must show.
// A value that misses a floor is fixed in the theme, never by lowering the floor. Circuit must stay as it was, so its misses are
// listed in KNOWN_MISSES, each with the ratio it has today, and the test fails if one of them is fixed or gets worse.
const FLOORS = [
  ...["--bg", "--surface-1", "--surface-2", "--surface-3", "--input"].map((on) => ["--text", on, 4.5]),
  ...["--bg", "--surface-1", "--surface-2"].flatMap((on) => ["--muted", "--accent", "--good", "--bad", "--warn"].map((token) => [token, on, 4.5])),
  ["--faint", "--bg", 3], ["--faint", "--surface-1", 3],
  ["--accent", "--accent-soft", 4.5],
  ["--line", "--bg", 1.3],
];
const KNOWN_MISSES = {};

test("every theme meets the contrast floors", () => {
  const problems = [];
  for (const block of themeBlocks()) {
    const id = idOf(block);
    for (const [token, on, floor] of FLOORS) {
      const ratio = contrast(rgbOf(block.declarations.get(token), block), rgbOf(block.declarations.get(on), block));
      const key = `${id} ${token} on ${on}`;
      if (key in KNOWN_MISSES) { if (ratio >= floor || ratio < KNOWN_MISSES[key] - 0.05) problems.push(`${key} changed: ${ratio.toFixed(2)} (listed as ${KNOWN_MISSES[key]})`); }
      else if (ratio < floor) problems.push(`${key} is ${ratio.toFixed(2)}, needs ${floor}`);
    }
  }
  assert.deepEqual(problems, []);
});

test("the static icon in index.html is drawn in the default theme's colours, so the tab does not change when the script runs", () => {
  const html = read("index.html");
  const link = html.match(/<link rel="icon"[^>]*href="([^"]+)"/)?.[1];
  assert.ok(link, "the static icon is missing");
  const svg = decodeURIComponent(link.replace(/^data:image\/svg\+xml,/, ""));
  const tile = svg.match(/<rect[^>]*fill='(#\w+)'[^>]*stroke='(#\w+)'/);
  const letter = svg.match(/<text[^>]*fill='(#\w+)'/);
  const block = themeBlocks().find((b) => idOf(b) === DEFAULT_THEME);
  const token = (name) => block.declarations.get(name).toUpperCase();
  assert.equal(tile?.[1].toUpperCase(), token("--surface-1"));
  assert.equal(tile?.[2].toUpperCase(), token("--line"));
  assert.equal(letter?.[1].toUpperCase(), token("--accent"));
});
