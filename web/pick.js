// Seeded random picks (P0, "Random selection"). Every count and rotation of the old design is replaced by a coded random
// choice: the spotlight tie, and "at most 5 random items" wherever a list is merged into a prompt. The choice is deterministic
// for a project and a chapter, so planning, generating and regenerating a chapter see the same picks and nothing reshuffles
// behind the writer's back. A different salt gives a different list. No DOM, so Node can test it.

export const PICK_MAX = 5;      // the most items of one list a request carries (items the scene needs come on top of that)

// A 32-bit number from text (FNV-1a, then a final mix so close texts give far-apart seeds).
function seedOf(text) {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b) >>> 0;
  h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35) >>> 0;
  h ^= h >>> 16;
  return h >>> 0;
}

// What identifies a project for the seed: its id (a project is an Item). A project with none falls back on its title, so a
// hand-made project still gets stable picks.
export const projectSeed = (project) => String(project?.id ?? project?.title ?? "");

// A generator of numbers in [0, 1): mulberry32, started from the project, the chapter and a salt (which list this is for).
export function rng(projectId, chapter, salt = "") {
  let a = seedOf(`${projectId}|${chapter}|${salt}`);
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const idOf = (x) => (typeof x === "string" ? x : x?.id);

// At most `n` of `items`, always including the ones in `must` (ids, or items with ids), in the order the list has them.
// The scene's own items come first and are never cut: when `must` alone is longer than `n`, all of it is returned. The rest
// are drawn at random with `rand` (a generator from rng).
export function pickMany(items, n = PICK_MAX, rand = Math.random, { must = [] } = {}) {
  const list = Array.isArray(items) ? items : [];
  const wanted = new Set([...must].map(idOf).filter(Boolean));
  const kept = new Set();
  list.forEach((item, i) => { if (wanted.has(item?.id)) kept.add(i); });
  const rest = list.map((_, i) => i).filter((i) => !kept.has(i));
  for (let i = rest.length - 1; i > 0; i--) {                       // Fisher-Yates
    const j = Math.floor(rand() * (i + 1));
    [rest[i], rest[j]] = [rest[j], rest[i]];
  }
  for (const i of rest.slice(0, Math.max(0, n - kept.size))) kept.add(i);
  return list.filter((_, i) => kept.has(i));
}
