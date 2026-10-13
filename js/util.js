/* Pulpermill page: Small helpers with no knowledge of the page: DOM, storage, ids, time. */
const $ = (s) => document.querySelector(s);
const el = (t, a = {}, ...kids) => {
  const e = document.createElement(t);
  for (const k in a) {
    if (k === "class") e.className = a[k];
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), a[k]);
    else if (a[k] !== false && a[k] !== null) e.setAttribute(k, a[k]);
  }
  for (const c of kids.flat()) if (c != null) e.append(c);
  return e;
};
const save = (k, v) => {
  try {
    localStorage.setItem("pmcg_" + k, v);
  } catch (e) {
    /* small settings (address, language); a full store is reported by the project autosave */
  }
};
const load = (k) => {
  try {
    return localStorage.getItem("pmcg_" + k) || "";
  } catch (e) {
    return "";
  }
};
const slugify = (s) =>
  String(s || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "_")
    .replace(/^_|_$/g, "") || "x";
const blank = (v) =>
  Array.isArray(v)
    ? []
    : v && typeof v === "object"
      ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, blank(x)]))
      : typeof v === "number"
        ? 0
        : "";

const clone = (o) => JSON.parse(JSON.stringify(o));
const uid = () => Math.random().toString(36).slice(2, 10);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pad = (n) => String(n).padStart(2, "0");
const fmtDur = (secs) => {
  secs = Math.max(0, Math.round(secs));
  return secs < 60
    ? t("{s}s", { s: secs })
    : t("{m}m {s}s", { m: Math.floor(secs / 60), s: pad(secs % 60) });
};
