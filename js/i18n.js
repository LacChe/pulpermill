/* Pulpermill page: Language: t(), message objects, error texts. The Chinese table itself is in i18n_zh.js. */
/* ---------- language ----------
   Every visible string is written in English and passed through t(). ZH maps the English text to Simplified Chinese;
   a string with no entry shows in English. Messages from the backend arrive as {t: English template, p: params} and are
   rendered here too, so switching language re-translates everything already on the page. */
let LANG = load("lang") === "zh" ? "zh" : "en";
const MISS = new Set();
const mk = (tpl, p) => ({ t: tpl, p: p || {} });
function pyd(s) {
  if (LANG !== "zh" || typeof s !== "string") return s;
  for (const [re, zh] of PYD) {
    const r = new RegExp(re);
    if (r.test(s)) return s.replace(r, zh);
  }
  return s;
}
function val(x) {
  if (Array.isArray(x)) return x.map(val).join(LANG === "zh" ? "、" : ", ");
  if (x && typeof x === "object" && "t" in x) return msg(x);
  return x == null ? "" : String(x);
}
function msg(x) {
  if (x == null) return "";
  if (typeof x === "string") return x;
  if (x.t) {
    const p = {};
    for (const k in x.p || {})
      p[k] = k === "why" && typeof x.p[k] === "string" ? pyd(x.p[k]) : x.p[k];
    return t(x.t, p);
  }
  return x.s || String(x);
}
function t(s, v) {
  let out = s;
  if (LANG === "zh") {
    if (Object.prototype.hasOwnProperty.call(ZH, s)) out = ZH[s];
    else {
      if (!MISS.has(s))
        console.warn("Pulpermill: no Chinese translation for: " + s);
      MISS.add(s);
    } // shown in English; logged once per string
  }
  return v
    ? out.replace(/\{(\w+)\}/g, (m, k) => (k in v ? val(v[k]) : m))
    : out;
}
/* an Error that remembers its translatable message, so a stored error can be shown in whichever language is on */
function fail(tpl, p) {
  const e = new Error(t(tpl, p));
  e.m = mk(tpl, p);
  return e;
}
const emsg = (e) => e.m || e.error_msg || null || e.message;
const unitWord = () => t("words");
const label = (k) => t(k.replace(/_/g, " "));
const optLabel = (o) => {
  const k = String(o).replace(/_/g, " ");
  return LANG === "zh" &&
    Object.prototype.hasOwnProperty.call(ZH, "option " + k)
    ? ZH["option " + k]
    : k;
};
