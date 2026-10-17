/* Pulpermill page: The project in memory: chapters, cards, the edited/stale flags, schema copy, who a chapter is about. */
/* The app keeps no copy of the schema: enums, nullable fields and hidden fields come from the backend's /schema
   (cached here so saved cards still edit while disconnected). */
let SCH = (() => {
  try {
    return JSON.parse(localStorage.getItem("pmcg_schema") || "null");
  } catch (e) {
    return null;
  }
})() || { enums: {}, nullable: [], hidden: [], refs: {}, choices: {}, lists: {} };
/* ---------- state ----------
   story.cards is the single, current card set for the whole story. story.chapters[j] is chapter j+1 and holds its cast,
   rewrite notes, and written result. */
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
const newChapter = () => ({
  cast: undefined,
  result: null,
  msg: "",
  draft: {},
});
const newStory = () => ({
  cards: {},
  stale: {},
  err: {},
  warn: {},
  notes: { style: "", characters: "", world: "", outline: "" },
  notesOpen: {},
  cardDraft: {},
  chapter: "",
  use: "",
  useEx: { style: true, characters: true, world: true, outline: true },
  took: {},
  chapters: [newChapter()],
  cur: 0,
  job: null,
  narrBasis: null,
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
  story: newStory(),
};
const cur = () => st.story.chapters[st.story.cur];
const chapters = () => st.story.chapters;
const ensureChapter = (n) => {
  while (st.story.chapters.length < n)
    st.story.chapters.push(newChapter());
};
["cards", "stale", "err", "warn", "notes"].forEach((k) =>
  Object.defineProperty(st, k, {
    get: () => st.story[k],
    set: (v) => {
      st.story[k] = v;
    },
  }),
);

const hash = (o) => {
  const s = JSON.stringify(o);
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return String(h);
};
const haveCards = () => CARD_KEYS.every((k) => st.story.cards[k]);
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
const cardsHash = (cards) => hash(cleanCards(cards));
const cardsForChapter = (cards, n) => {
  const out = cleanCards(cards);
  if (out.outline)
    out.outline.chapter_beats = (out.outline.chapter_beats || []).filter(
      (b) => Number(b.chapter_num) <= n,
    );
  return out;
};
const beatOf = (k) =>
  st.story.cards.outline &&
  (st.story.cards.outline.chapter_beats || []).find(
    (b) => Number(b.chapter_num) === k,
  );
/* A written chapter is out of date when the chapter before it was rewritten after it was (or is itself out of date). */
function resStale(j) {
  const P = chapters(),
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
function narratorStale() {
  const b = st.story.narrBasis,
    s = st.story.cards && st.story.cards.style;
  return !!(b && s && b.narrator === s.narrator && b.inputs !== narratorInputs(s));
}
/* Who a chapter is written about. A project can hold any number of characters; each chapter is written about a chosen few (at most
   `max_cast`, the main character always one of them), and the model never sees anyone else. `pg.cast` is the chapter-specific
   choice (unset: the people the chapter's beat puts in the scene). */
const maxCast = () => (st.limits && st.limits.max_cast) || 6;
const leadOf = () =>
  st.story.cards.outline && st.story.cards.outline.protagonist;
function castFor(pg, k) {
  const ids = (st.story.cards.characters || []).map((c) => c.id),
    lead = leadOf(),
    b = beatOf(k);
  const picked = Array.isArray(pg.cast) ? pg.cast : (b && b.present) || [];
  const sel = [
    ...new Set([lead, ...picked].filter((i) => i && ids.includes(i))),
  ];
  return sel.slice(0, maxCast());
}
const totalOf = () => {
  const o = st.story.cards.outline;
  return o ? Number(o.total_chapters) || (o.chapter_beats || []).length : 0;
}; // fixed up front; beats exist only up to the chapter being worked on
const pageName = (j) => t("Chapter {k}", { k: j + 1 });
