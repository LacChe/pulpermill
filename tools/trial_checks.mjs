// Machine checks for one written chapter. No model, no judgement: each check records a number or a flag so a person knows where to
// look first. A flag means "look here", never "this is bad". The heuristics are simple on purpose and are documented here.
//
//   words          English: words. Chinese (language "zh"): characters of Han script. Flags `too_short` / `too_long` against LIMITS.
//   person, tense  English only. Dialogue (text in quotation marks) is cut out first, then pronouns and verb forms are counted in the
//                  narration. person: first-person pronouns (I, me, my, we, us, our) against third-person ones (he, she, they, him, her,
//                  his, their); the chosen person is flagged when the other side has at least twice as many and there are 10 or more
//                  pronouns in all. tense: a short list of common irregular past and present forms, plus words ending in -ed for the past;
//                  flagged when the other tense has at least twice as many marks and there are 20 or more marks in all.
//                  For Chinese the person check counts 我 against 他/她/它 in the same way and there is no tense check.
//   opening_repeat the first 8 words (or 12 characters) equal the start of an earlier chapter's text.
//   repeated_sentences  sentences of 6 or more words (or 12 or more characters) that also occur in an earlier chapter.
//   edge_in_shifts the spotlight tie's edge appears in this chapter's committed shifts: an Entanglements entry whose ties operation
//                  replaces or removes that tie and, when it replaces, carries an edge that differs from the old one.
//   changed_empty  the events' "changed" line is empty.
//   shift_count    shifts kept; shifts_proposed is what the model sent; flagged above `max` (the schema's cap).
//   unknown_names  capitalised words in the narration that are not at the start of a sentence and are not a cast member, a place, an
//                  object, a group or a term from the cards (or an ordinary calendar word). English only. offstage_names are names of
//                  characters who are in the story but not in this chapter's cast. Both list names and count them.

export const LIMITS = { en: { min: 250, max: 2500 }, zh: { min: 400, max: 5000 } };
const CALENDAR = new Set("Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August September October November December Mr Mrs Ms Dr Sir Lady Lord God I".split(" "));

const words = (text) => (text.match(/[\p{L}\p{N}'’-]+/gu) ?? []);
const han = (text) => (text.match(/\p{Script=Han}/gu) ?? []).length;
const norm = (text) => text.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, "").replace(/\s+/g, " ").trim();

// The narration: the text with anything in quotation marks cut out.
export function narration(text) {
  return text.replace(/“[^”]*”/g, " ").replace(/"[^"]*"/g, " ").replace(/「[^」]*」/g, " ").replace(/『[^』]*』/g, " ").replace(/‘[^’]*’(?=[\s.,!?])/g, " ");
}

const FIRST = /\b(I|me|my|mine|myself|we|us|our|ours)\b/g;
const THIRD = /\b(he|she|they|him|her|his|hers|their|them|himself|herself|themselves)\b/gi;
const PAST = new Set("was were had did said went came saw took made knew got thought felt told found gave left kept stood sat ran began held brought heard turned looked".split(" "));
const PRESENT = new Set("is are am has does says goes comes sees takes makes knows gets thinks feels tells finds gives leaves keeps stands sits runs begins holds brings hears turns looks".split(" "));

export function personFound(text, language) {
  const n = narration(text);
  if (language === "zh") {
    const first = (n.match(/我/g) ?? []).length, third = (n.match(/[他她它]/g) ?? []).length;
    return { first, third, found: first + third < 10 ? "unclear" : first >= 2 * third ? "first" : third >= 2 * first ? "third" : "mixed" };
  }
  const first = (n.match(FIRST) ?? []).length, third = (n.match(THIRD) ?? []).length;
  return { first, third, found: first + third < 10 ? "unclear" : first >= 2 * third ? "first" : third >= 2 * first ? "third" : "mixed" };
}

export function tenseFound(text) {
  const n = words(narration(text));
  let past = 0, present = 0;
  for (const w of n) {
    const l = w.toLowerCase();
    if (PAST.has(l) || (l.length > 4 && l.endsWith("ed"))) past++;
    else if (PRESENT.has(l)) present++;
  }
  return { past, present, found: past + present < 20 ? "unclear" : past >= 2 * present ? "past" : present >= 2 * past ? "present" : "mixed" };
}

const sentences = (text, language) => {
  const parts = text.split(/(?<=[.!?。！？])\s*/u).map(norm).filter(Boolean);
  return parts.filter((s) => (language === "zh" ? han(s) >= 12 : words(s).length >= 6));
};

const opening = (text, language) => (language === "zh" ? text.replace(/\s/g, "").slice(0, 12) : norm(text).split(" ").slice(0, 8).join(" "));

// Names the cards hold: every word of a name counts as known ("Iris Vane" knows Iris and Vane).
function knownWords(names) {
  const out = new Set();
  for (const name of names) for (const w of words(name)) out.add(w);
  return out;
}

export function strangeNames(text, known, offstage) {
  const n = narration(text);
  const found = new Map();
  const re = /(^|[.!?…:;—\n]\s*["“‘']?|\s)([A-Z][a-z]+(?:[’']s)?)/g;
  for (const m of n.matchAll(re)) {
    const atStart = m[1] !== " " && !/^\s$/.test(m[1]) ? true : false;
    if (atStart) continue;
    const word = m[2].replace(/[’']s$/, "");
    if (known.has(word) || CALENDAR.has(word)) continue;
    found.set(word, (found.get(word) ?? 0) + 1);
  }
  const unknown = [], away = [];
  for (const w of found.keys()) (offstage.has(w) ? away : unknown).push(w);
  return { unknown, away };
}

// What the cards held going into the chapter, as lists of names.
export function namesOf(eff, castIds) {
  const cast = (eff.characters ?? []).filter((c) => castIds.includes(c.id)).map((c) => c.name);
  const others = (eff.characters ?? []).filter((c) => !castIds.includes(c.id)).map((c) => c.name);
  const w = eff.world ?? {};
  const things = [w.name, ...["places", "objects", "powers"].flatMap((k) => (w[k] ?? []).map((x) => x.name)), ...(w.terms ?? []).map((t) => t.term)];
  return { cast, others, things: things.filter(Boolean) };
}

export function edgeMoved(spotlightId, oldEdge, entries) {
  for (const entry of entries ?? []) {
    if (entry.card !== "entanglements") continue;
    for (const op of entry.patch?.ties ?? []) {
      if (op.id !== spotlightId) continue;
      if (op.op === "remove") return true;
      if (op.op === "replace" && op.values && "edge" in op.values && String(op.values.edge).trim() !== String(oldEdge ?? "").trim()) return true;
    }
  }
  return false;
}

// One chapter. `ctx`: {language, style, text, eff (effective cards going in), cast (ids), spotlight (tie id), earlier (texts of earlier
// chapters), events ({changed}), shifts (committed entries), proposed (number the model sent), maxShifts}.
export function checkChapter(ctx) {
  const lang = ctx.language === "zh" ? "zh" : "en";
  const text = ctx.text ?? "";
  const length = lang === "zh" ? han(text) : words(text).length;
  const limit = LIMITS[lang];
  const out = { length, length_flag: length < limit.min ? "too_short" : length > limit.max ? "too_long" : "" };
  const person = personFound(text, lang), tense = lang === "zh" ? { found: "n/a" } : tenseFound(text);
  out.person_found = person.found;
  out.person_flag = person.found !== "unclear" && person.found !== ctx.style.person && person.found !== "mixed" ? "drift" : "";
  out.tense_found = tense.found;
  out.tense_flag = lang === "en" && tense.found !== "unclear" && tense.found !== "mixed" && tense.found !== ctx.style.tense ? "drift" : "";
  const first = opening(text, lang);
  out.opening_repeat = ctx.earlier.some((t) => first && opening(t, lang) === first);
  const seen = new Set(ctx.earlier.flatMap((t) => sentences(t, lang)));
  out.repeated_sentences = sentences(text, lang).filter((s) => seen.has(s)).length;
  const tie = (ctx.eff.entanglements?.ties ?? []).find((t) => t.id === ctx.spotlight);
  out.edge_in_shifts = edgeMoved(ctx.spotlight, tie?.edge, ctx.shifts);
  out.changed_empty = !String(ctx.events?.changed ?? "").trim();
  out.shifts_proposed = ctx.proposed;
  out.shift_count = ctx.shifts.length;
  out.shift_flag = ctx.proposed > ctx.maxShifts || ctx.shifts.length > ctx.maxShifts ? "over_cap" : "";
  const names = namesOf(ctx.eff, ctx.cast);
  if (lang === "en") {
    const known = knownWords([...names.cast, ...names.things]);
    const away = knownWords(names.others);
    const { unknown, away: offstage } = strangeNames(text, known, away);
    out.unknown_names = unknown.slice(0, 12).join(" ");
    out.unknown_count = unknown.length;
    out.offstage_names = offstage.join(" ");
  } else Object.assign(out, { unknown_names: "", unknown_count: 0, offstage_names: "" });
  return out;
}

// The columns a summary row takes from a check, in order.
export const CHECK_COLUMNS = ["length", "length_flag", "person_found", "person_flag", "tense_found", "tense_flag", "opening_repeat", "repeated_sentences",
                              "edge_in_shifts", "changed_empty", "shifts_proposed", "shift_count", "shift_flag", "unknown_count", "unknown_names", "offstage_names"];
