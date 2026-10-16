/* Pulpermill page: The project in memory: pages, cards, the edited/stale flags, schema copy, who a chapter is about. */
/* The page keeps no copy of the schema: enums, nullable fields and hidden fields come from the backend's /schema
   (cached here so saved cards still edit while disconnected). */
let SCH = (() => {
  try {
    return JSON.parse(localStorage.getItem("pmcg_schema") || "null");
  } catch (e) {
    return null;
  }
})() || { enums: {}, nullable: [], hidden: [], refs: {}, choices: {}, lists: {} };
/* ---------- state ----------
   story.pages[j] is chapter j+1: the cards it starts from (editable), the notes that go with them, and the chapter
   written from them (`result`). Page 1 starts blank; every later page is filled from the chapter before it. */
const CARD_KEYS = ["style", "characters", "world", "outline"];
/* what the example chapter can be for; any number can be ticked (the backend knows the same four words) */
const EXAMPLE_USES = [
  { k: "", t: "Same story", d: "the cards describe the example's own story" },
  { k: "sequel", t: "Continue after it", d: "carries on after this chapter" },
  {
    k: "parallel",
    t: "New story in the same world",
    d: "another story in the same world, running alongside this one",
  },
];
const newPage = () => ({
  cards: {},
  stale: {},
  err: {},
  warn: {},
  notes: { style: "", characters: "", world: "", outline: "" },
  notesOpen: {},
  chapter: "",
  use: "",
  useEx: { style: true, characters: true, world: true, outline: true },
  base_hash: null,
  result: null,
  msg: "",
  took: {},
});
const st = {
  limits: null,
  busy: null,
  busyPg: null,
  banner: "",
  armed: false,
  report: null,
  ask: null,
  jobId: null,
  stopping: false,
  step: "",
  conn: null,
  story: { pages: [newPage()], cur: 0, job: null },
};
const cur = () => st.story.pages[st.story.cur];
const pages = () => st.story.pages;
["cards", "stale", "err", "warn", "notes"].forEach((k) =>
  Object.defineProperty(st, k, {
    get: () => cur()[k],
    set: (v) => {
      cur()[k] = v;
    },
  }),
);

const hash = (o) => {
  const s = JSON.stringify(o);
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return String(h);
};
const haveCards = (pg) => CARD_KEYS.every((k) => pg.cards[k]);
/* `path` is the dotted route from the card's name with list positions left out ("world.objects.owner"), which is how
   /schema names the fields that may be null. */
function clean(v, path, noUses) {
  if (Array.isArray(v)) return v.map((x) => clean(x, path, noUses));
  if (v && typeof v === "object")
    return Object.fromEntries(
      Object.entries(v)
        .filter(([k]) => !(noUses && k === "uses"))
        .map(([k, x]) => [k, clean(x, path + "." + k, noUses)]),
    );
  if (v === "" && (SCH.nullable || []).includes(path)) return null;
  return typeof v === "string" ? v.replace(/\*/g, "") : v;
}
const cleanCards = (c, noUses) => {
  const o = {};
  CARD_KEYS.forEach((k) => {
    if (c[k]) o[k] = clean(c[k], k, noUses);
  });
  return o;
};
/* How often a detail was used is not an edit of the card, so every comparison of cards leaves the use counts out: the hash a
   chapter remembers of the cards it started from (`startHash`) and the hash of the cards now (`snap`) must be taken the same way,
   or the page thinks the cards were edited the moment a later chapter has any counts. */
const startHash = (cards) => hash(cleanCards(cards, true));
const snap = (pg) => startHash(pg.cards);
const beatOf = (pg, k) =>
  pg.cards.outline &&
  (pg.cards.outline.chapter_beats || []).find(
    (b) => Number(b.chapter_num) === k,
  );
/* A written chapter is out of date when the chapter before it was rewritten after it was (or is itself out of date).
   Only ONE version of the cards between two chapters exists: page j+1's cards are both what chapter j+1 starts from and
   what chapter j ended with, so editing them edits that single copy. */
function resStale(j) {
  const P = pages(),
    pg = P[j];
  if (!pg || !pg.result || j === 0) return false;
  const prev = P[j - 1].result;
  return !prev || pg.result.parent_id !== prev.id || resStale(j - 1);
}
/* The narrator paragraph is written from these fields. The story keeps one note (`narrBasis`) of what they were and what the
   paragraph said when it was last generated or imported. The paragraph is out of date when one of them has changed since, unless
   the paragraph itself was edited by hand (the author has then reconciled it). No note (an older project): not flagged. */
const NARRATOR_FROM = [
  "lens",
  "stance",
  "cadence",
  "dialogue_manner",
  "time_handling",
  "economy",
  "diction",
  "figurative",
  "interiority",
  "humor",
];
const narratorInputs = (s) => hash(NARRATOR_FROM.map((k) => s[k]));
const stampNarrator = (s) => {
  st.story.narrBasis = s
    ? { inputs: narratorInputs(s), narrator: s.narrator }
    : null;
};
function narratorStale(pg) {
  const b = st.story.narrBasis,
    s = pg && pg.cards && pg.cards.style;
  return !!(b && s && b.narrator === s.narrator && b.inputs !== narratorInputs(s));
}
const cardsEdited = (pg) => !!pg.result && pg.result.start_hash !== snap(pg);
const edited = (pg) => pg.base_hash == null || pg.base_hash !== snap(pg);
function fillPage(pg, cards) {
  pg.cards = clone(cards);
  pg.stale = {};
  pg.warn = {};
  pg.err = {};
  pg.base_hash = snap(pg);
}
/* The page after the last chapter in the outline holds the cards the story ended with. It has nothing to write. */
/* Who a chapter is written about. A project can hold any number of characters; each chapter is written about a chosen few (at most
   `max_cast`, the main character always one of them), and the model never sees anyone else. `pg.cast` is the choice for the
   chapter this page's cards start (unset: the people the chapter's beat puts in the scene). */
const maxCast = () => (st.limits && st.limits.max_cast) || 6;
const leadOf = (pg) => pg.cards.outline && pg.cards.outline.protagonist;
function castFor(pg, k) {
  const ids = (pg.cards.characters || []).map((c) => c.id),
    lead = leadOf(pg),
    b = beatOf(pg, k);
  const picked = Array.isArray(pg.cast) ? pg.cast : (b && b.present) || [];
  const sel = [
    ...new Set([lead, ...picked].filter((i) => i && ids.includes(i))),
  ];
  return sel.slice(0, maxCast());
}
const totalOf = (pg) => {
  const o = pg.cards.outline;
  return o ? Number(o.total_chapters) || (o.chapter_beats || []).length : 0;
}; // fixed up front; beats exist only up to the chapter being worked on
const isEnding = (j) =>
  j > 0 &&
  !!pages()[j] &&
  !!pages()[j].cards.outline &&
  j + 1 > totalOf(pages()[j]);
const pageName = (j) =>
  isEnding(j) ? t("Ending") : t("Chapter {k}", { k: j + 1 });
