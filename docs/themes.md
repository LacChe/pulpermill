# Themes

The page has six looks, called presets: **Timber** (the default), **Circuit** (the original sci-fi look, kept exactly), **Flour**, **Paper**, **Stone** and **Pulp**. They are picked from the thin footer. The choice is a viewing preference of one browser: it is kept in `localStorage` under `pulpermill.theme`, put on before the first paint by a small script in the head of `web/index.html`, and **never written into a project file, an export or an import**.

## What a preset is

One block of tokens in `web/themes.css`, selected by `data-theme` on `<html>`:

```css
[data-theme="flour"] { color-scheme: light; --bg: ...; ... }
```

`web/style.css` holds no colour of its own (no hex, `rgb()`, `hsl()` or `oklch()`); every colour is a token. A preset is complete when its block defines every token below. Differences that are not colour (border thickness, corner radius, heading case, the rule under the top bar) go through the knobs, so no preset needs selectors of its own.

The selector of each block is exactly one attribute selector, so no block beats another and source order never matters. Circuit's is `:root:not([data-theme]), [data-theme="circuit"]`, so a page with no `data-theme` also looks like Circuit.

### Tokens every preset defines

`color-scheme` (`light` or `dark`, matching the background, so native inputs and scrollbars suit it), `--bg`, `--surface-1`, `--surface-2`, `--surface-3`, `--input`, `--line`, `--line-strong`, `--text`, `--muted`, `--faint`, `--accent`, `--accent-soft`, `--good`, `--bad`, `--warn`, `--shadow-color` (under tooltips), `--backdrop` (behind a question dialog; black at 0.6 on dark presets, a lighter warm shade on light ones).

Surfaces step up with nesting: `--bg` is the page, `--surface-1` bars and panels, `--surface-2` items in panels, `--surface-3` anything inside those. `--input` is the text well, and it is not always darker than the surfaces: dark presets have it darkest, light presets lightest. Every preset sets it itself.

`--accent`, `--good`, `--bad` and `--warn` are used as text colours as well as fills, which is why the floors below cover them.

### Knobs (declared on `:root` in `style.css`, with defaults equal to the original look)

| Knob | What it does | Default |
|---|---|---|
| `--bw` | border width of panels, fields, buttons, chips | `1px` |
| `--font-head` | the page title's font | `var(--font-ui)` |
| `--head-case`, `--head-track` | capitals and letter spacing of the title | `none`, `normal` |
| `--bar-rule` | the line under the top bar | `1px solid var(--line)` |
| `--bar-bg`, `--bar-text` | the top bar's colours | `var(--surface-1)`, `var(--text)` |
| `--scroll-thumb` | scrollbar thumb (it sits on `--bg`) | `var(--surface-3)` |
| `--footer-h` | the footer's height; both columns leave room for it | `32px` |

A preset may also set `--font-ui` and `--radius-s`, `--radius-m`, `--radius-l` (Flour rounds, Paper and Pulp square them off).

### A bar of a different colour

Pulp's top bar (the header and the backend bar) is black with cream type on an otherwise light page. A preset that sets `--bar-bg` also needs a scope, `[data-theme="x"] .app-header { ... }`, that sets again every token the bar's controls read, for the bar's colour: `color-scheme`, `--text`, `--muted`, `--faint`, `--line`, `--line-strong`, `--input`, `--accent`, `--accent-soft`, `--good`, `--bad`, `--warn`, `--surface-1`, `--surface-3`. It must also set `--btn` and `--btn-hover` again. A custom property that uses `var()` is worked out where it is declared, so redefining `--text` on a descendant does not update `--btn` there.

## Contrast floors

Checked by `tests/web/themes.test.mjs` for every block in `themes.css` (WCAG contrast ratios):

- `--text` on `--bg`, `--surface-1`, `--surface-2`, `--surface-3` and `--input`: 4.5
- `--muted`, `--accent`, `--good`, `--bad`, `--warn` on `--bg`, `--surface-1` and `--surface-2`: 4.5
- `--accent` on `--accent-soft`: 4.5
- `--faint` on `--bg` and `--surface-1`: 3 (it is only for disabled and placeholder text)
- `--line` against `--bg`: 1.3
- the scrollbar thumb against `--bg`: 1.3
- inside a bar scope: `--bar-text` on `--bar-bg` at least 7, and the tokens the bar uses meet the same floors against the bar

When a value fails, change the **value** (darken or lighten it), never the floor. Circuit must stay as it was; if one of its values ever misses a floor, record it in `KNOWN_MISSES` in the test with a comment instead of changing Circuit. Today none does.

## Adding a seventh preset

1. Add a block to `web/themes.css` with every token above and its `color-scheme`, plus whatever knobs it wants. Run the tests and fix any value that misses a floor.
2. Add its id to `THEMES` in `web/theme.js` (the array is the footer order) and to the `nameOf` map beside it, written out in full: the test that ties code to the text bundle looks for each key spelled out.
3. Add the same id to the list in the regex of the head script in `web/index.html`.
4. Add its name under `theme` in **both** `web/data/text.en.json` and `web/data/text.zh.json`.
5. Add its footer swatch to `themes.css`: `.theme-swatch[data-theme-id="x"] { --sw-1: <its --bg>; --sw-2: <its --accent>; }`. The footer shows the colours of the theme each button picks, not of the theme in use, so the pair carries its own colours. A test keeps them equal to the real tokens.
6. If the preset is ever made the default, change `DEFAULT_THEME`, the static `data-theme` on `<html>`, the `theme-color` meta, and the static `<link rel="icon">` in `index.html` (drawn in the default's surface, line and accent colours). Tests fail until they agree.

Tests that fail when a step is missed: the block set must equal `THEMES`; the head script's id list must equal `THEMES`; every theme must be named in both languages; each swatch pair must equal the real tokens.

## Rules

- No colour literal in `web/style.css`. All colour goes through tokens, and the literals live in theme blocks.
- The theme is never in the project file, an export or an import.
- Every word the footer shows is in the text bundle, read through `section("theme")`; nothing is worded in code.
- Storage is never required: reads and writes are in `try`/`catch`, and without it the page starts on Timber.
- The tab icon is drawn from the theme's tokens when it is painted, and `theme.js` sends a `themechange` event so it paints again after a switch.
