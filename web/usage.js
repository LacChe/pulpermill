// How much each thing has been used, and which few of them a request carries. No DOM, no model.
//
// A value counts as used in a chapter only when the written chapter shows it, never because a beat planned it.
//   People, groups, places and things are looked for by name in the chapter's text: a name is exact, so there is nothing to judge.
//   Behaviors, ties, holdings and knowledge are sentences, and whether a sentence "happened" is a judgment. The model that reads
//   the chapter afterwards says which of them it showed (`behaviors_seen`, `entanglements_shown` in the chapter's record), and that
//   record is what is counted.
//   A pressure is counted by the spotlight, never by that judgment: the chapter that put it in the spotlight moved it (the pass after
//   the chapter gives it its new state), so the spotlight is its use. The model over-reports what a chapter showed, and counts that
//   tie send the rotation back to the first pressure every time.
//
// A request carries at most SEND_MAX of each kind of value that rotates (places, things, ties, holdings, knowledge, pressures),
// the least used first. A value the beat for this chapter names, by link or by name, is always carried, and does not take a
// place from the others.

export const SEND_MAX = 5;

const asList = (value) => (Array.isArray(value) ? value : value ? [value] : []);
const present = (value) => typeof value === "string" && value.trim() !== "";
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Does `text` name `phrase`? The whole phrase must appear, with nothing letter-like touching it. Only names are looked for this
// way: a sentence is never matched by its words (the model judges those), so a sentence only matches when it is quoted whole.
export function mentions(text, phrase) {
  if (!present(text) || !present(phrase)) return false;
  return new RegExp(`(?<![\\p{L}\\p{N}])${escaped(phrase.trim())}(?![\\p{L}\\p{N}])`, "iu").test(text);
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
  for (const chapter of writtenChapters(project)) {
    if (except !== null && chapter.n === except) continue;
    const { n, text, events, beat } = chapter;
    for (const c of project.characters ?? []) if (mentionsPerson(text, c.name)) mark(c.id, n);
    for (const g of world.powers ?? []) if (mentionsPerson(text, g.name)) mark(g.id, n);
    for (const p of world.places ?? []) if (mentions(text, p.name)) mark(p.id, n);
    for (const o of world.objects ?? []) if (mentions(text, o.name)) mark(o.id, n);
    const seen = new Set(asList(events?.behaviors_seen));
    for (const c of project.characters ?? []) for (const b of c.behaviors ?? []) if (seen.has(b.id)) mark(b.id, n);
    const landed = new Set(asList(events?.reveals_landed));
    const shown = new Set(asList(events?.entanglements_shown));
    for (const group of [ent.ties, ent.holdings]) for (const x of group ?? []) if (shown.has(x.id)) mark(x.id, n);
    if ((ent.pressures ?? []).some((x) => x.id === beat?.spotlight)) mark(beat.spotlight, n);
    for (const k of ent.knowledge ?? []) if (shown.has(k.id) || (k.rule && landed.has(k.rule))) mark(k.id, n);
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
