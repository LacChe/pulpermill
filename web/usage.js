// How much each thing has been used, and which few of them a request carries. No DOM, no model.
//
// A value counts as used in a chapter only when it appears in that chapter's written text (never because a beat planned it):
// a name is looked for as a name, a sentence (a behavior, a pressure, a piece of knowledge) by its main words. Only written
// chapters count, so a planned-ahead beat uses nothing up.
//
// A request carries at most SEND_MAX of each kind of value that rotates (places, things, ties, holdings, knowledge, pressures),
// the least used first. A value the beat for this chapter names, by link or in its words, is always carried, and does not
// take a place from the others.

export const SEND_MAX = 5;

const asList = (value) => (Array.isArray(value) ? value : value ? [value] : []);
const present = (value) => typeof value === "string" && value.trim() !== "";
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const WORD = /[\p{L}\p{N}]+/gu;
const STEM = 5;       // "flood" matches "floods" and "flooded"

// Does `text` name `phrase`? A short phrase (a name) must appear whole, with nothing letter-like touching it. A sentence is
// found when at least half of its main words (four letters or more, at least two when it has two) appear, in any form.
export function mentions(text, phrase) {
  if (!present(text) || !present(phrase)) return false;
  const words = phrase.toLowerCase().match(WORD) ?? [];
  if (words.length <= 3) return new RegExp(`(?<![\\p{L}\\p{N}])${escaped(phrase.trim())}(?![\\p{L}\\p{N}])`, "iu").test(text);
  const main = [...new Set(words.filter((w) => w.length >= 4).map((w) => w.slice(0, STEM)))];
  if (!main.length) return false;
  const have = new Set((text.toLowerCase().match(WORD) ?? []).map((w) => w.slice(0, STEM)));
  const hit = main.filter((w) => have.has(w)).length;
  return hit >= Math.min(2, main.length) && hit / main.length >= 0.5;
}

// A person is named by the whole name or by the first name.
const mentionsPerson = (text, name) => mentions(text, name) || (/\s/.test(name ?? "") && mentions(text, name.trim().split(/\s+/)[0]));

// The chapters that are written: {n, text, beat, events}, in order.
export function writtenChapters(project) {
  const beats = project.outline?.beats ?? [];
  const entries = project.summary_events?.entries ?? [];
  return (project.chapters ?? [])
    .map((c) => {
      const beat = beats.find((b) => b.id === c.beat) ?? null;
      return { n: Number(beat?.chapter) || 0, text: c.text ?? "", beat, events: entries.find((e) => e.beat === c.beat) ?? null };
    })
    .filter((c) => c.n > 0)
    .sort((a, b) => a.n - b.n);
}

// What each id has been: {uses, last}, by id, for everything that rotates. `except` leaves out the chapter being planned or
// written again, so it does not count itself.
export function usageOf(project, except = null) {
  const used = {};
  const mark = (id, n) => {
    if (!id) return;
    const entry = (used[id] ??= { uses: 0, last: 0 });
    entry.uses += 1;
    entry.last = Math.max(entry.last, n);
  };
  const world = project.world ?? {};
  const ent = project.entanglements ?? {};
  const people = new Map((project.characters ?? []).map((c) => [c.id, (c.name ?? "").trim()]));
  for (const g of world.powers ?? []) people.set(g.id, (g.name ?? "").trim());
  const nameOf = (id) => people.get(id) ?? "";
  for (const chapter of writtenChapters(project)) {
    if (except !== null && chapter.n === except) continue;
    const { n, text, beat, events } = chapter;
    for (const c of project.characters ?? []) if (mentionsPerson(text, c.name)) mark(c.id, n);
    for (const g of world.powers ?? []) if (mentionsPerson(text, g.name)) mark(g.id, n);
    for (const p of world.places ?? []) if (mentions(text, p.name)) mark(p.id, n);
    for (const o of world.objects ?? []) if (mentions(text, o.name)) mark(o.id, n);
    const seen = new Set(asList(events?.behaviors_seen));
    for (const c of project.characters ?? []) {
      for (const b of c.behaviors ?? []) if (seen.has(b.id) || mentions(text, b.state)) mark(b.id, n);
    }
    for (const t of ent.ties ?? []) if (mentionsPerson(text, nameOf(t.tie_from)) && mentionsPerson(text, nameOf(t.tie_to))) mark(t.id, n);
    const named = (id) => [...(world.places ?? []), ...(world.objects ?? [])].find((x) => x.id === id)?.name;
    for (const h of ent.holdings ?? []) if (mentions(text, named(h.holdee))) mark(h.id, n);
    const landed = new Set(asList(events?.reveals_landed));
    for (const k of ent.knowledge ?? []) {
      const thing = k.rule ? (world.rules ?? []).find((r) => r.id === k.rule)?.statement : k.fact;
      if ((k.rule && landed.has(k.rule)) || mentions(text, thing)) mark(k.id, n);
    }
    for (const p of ent.pressures ?? []) {
      const touched = [p.source_agent, ...asList(p.bears_on)].some((id) => mentionsPerson(text, nameOf(id)));
      if (mentions(text, p.what) || (beat?.spotlight === p.id && touched)) mark(p.id, n);
    }
  }
  return used;
}

// The words of a beat that name things: everything it says in text.
export function beatWords(beat) {
  return ["turn", "collision_goal", "collision_block", "choice_a", "choice_b", "ends_on", "plant", "when_time", "when_gap", "offstage_did", "offstage_reach"]
    .map((k) => beat?.[k]).filter(present).join("\n");
}

// The ids a beat names: the place, the cast, the pressure in focus, the rule to reveal, and anything of `items` whose words
// (`labelOf`) the beat's own text mentions.
export function plannedIds(beat, items, labelOf) {
  const linked = new Set([beat?.where, beat?.spotlight, beat?.reveal_rule, ...asList(beat?.cast), ...asList(beat?.reveal_learners)].filter(Boolean));
  const words = beatWords(beat);
  return new Set(items.filter((i) => linked.has(i.id) || (words && present(labelOf(i)) && mentions(words, labelOf(i)))).map((i) => i.id));
}

// The items a request carries: all that the beat names (`planned`, a set of ids), then the least used, up to `max` in all.
// Ties are settled by who was used longest ago, then by `near` (higher first: the cast's own things before strangers'), then by
// the order the writer listed them. The result keeps the writer's order.
export function choose(items, used, { planned = new Set(), max = SEND_MAX, near = () => 0 } = {}) {
  const must = items.filter((i) => planned.has(i.id));
  const room = Math.max(0, max - must.length);
  const rest = items.map((item, order) => ({ item, order })).filter(({ item }) => !planned.has(item.id))
    .sort((a, b) => (used[a.item.id]?.uses ?? 0) - (used[b.item.id]?.uses ?? 0)
      || (used[a.item.id]?.last ?? 0) - (used[b.item.id]?.last ?? 0)
      || near(b.item) - near(a.item) || a.order - b.order)
    .slice(0, room).map((x) => x.item.id);
  const keep = new Set([...must.map((i) => i.id), ...rest]);
  return items.filter((i) => keep.has(i.id));
}
