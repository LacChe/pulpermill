/* Pulpermill page: Saving and loading the project (browser storage and project files). */
const transient = (k, v) =>
  k === "msg" || k === "err" || k === "draft" ? undefined : v; // drafts: unsent notes, kept across redraws only
/* the text fields a style card gained when the narrator was redesigned (kept here only so an older project can be upgraded) */
const STYLE_TEXT_FIELDS = [
  "lens",
  "stance",
  "cadence",
  "dialogue_manner",
  "time_handling",
  "narrator",
];
/* the style dials: each is {level: 1 to 5, note}; 3 is the middle and the default */
const STYLE_DIALS = ["economy", "diction", "figurative", "interiority", "humor"];
let saveT = null;
function scheduleSave() {
  clearTimeout(saveT);
  saveT = setTimeout(saveProject, 500);
}
/* Browsers keep about 5 million characters per site. The warning comes at 70% so there is time to use Save project, and only once
   (it comes back if the project shrinks well below the line and grows again). */
const STORE_LIMIT_CHARS = 5 * 1024 * 1024,
  STORE_WARN_AT = 0.7,
  STORE_REARM_AT = 0.6;
let storeWarned = false;
function saveProject() {
  try {
    const text = JSON.stringify(
      { format: "pulpermill-project", version: 2, story: st.story },
      transient,
    );
    localStorage.setItem("pmcg_project", text);
    const used = text.length / STORE_LIMIT_CHARS;
    if (used < STORE_REARM_AT) storeWarned = false;
    else if (used >= STORE_WARN_AT && !storeWarned && !st.banner) {
      storeWarned = true;
      st.banner = mk(
        "Your project is using about {pct}% of the autosave space this browser allows. Use Save project to keep a copy before it fills up.",
        { pct: Math.round(used * 100) },
      );
      drawTop();
    }
    return true;
  } catch (e) {
    st.banner = mk(
      "Autosave failed (browser storage is full). Use Save project to keep your work.",
    );
    drawTop();
    return false;
  }
}
function projectFile() {
  return JSON.stringify(
    {
      format: "pulpermill-project",
      version: 2,
      saved: new Date().toISOString(),
      slug: $("#slug").value,
      lang: LANG,
      story: { ...st.story, job: null },
    },
    transient,
    1,
  );
}
/* Accepts the current format and the earlier ones. Older projects stored two copies of the cards between chapters
   (a chapter's "after" and the next page's "before"); only the page's copy is kept. */
function normalizeProject(p) {
  if (!p || typeof p !== "object" || Array.isArray(p))
    throw fail("That is not a Pulpermill project file.");
  if (p.format && p.format !== "pulpermill-project")
    throw fail("That is not a Pulpermill project file.");
  /* older projects: chapters had their own point of view and the style could be omniscient; now there is one main character
     and one person for the whole story */
  const migrate = (pg, was) => {
    /* older pages had one switch for the whole page (my notes / pasted chapter); now the example chapter is always there and
       each card decides for itself, so a page that was in notes mode keeps every card off, and one in chapter mode keeps them on */
    const on = was && was.mode === "chapter",
      has = was && was.useEx && typeof was.useEx === "object";
    pg.useEx = Object.assign(
      { style: true, characters: true, world: true, outline: true },
      has
        ? was.useEx
        : was && "mode" in was
          ? { style: on, characters: on, world: on, outline: on }
          : {},
    );
    /* the example's purpose used to be a list of ticks; it is now one choice (the first of sequel / parallel that was ticked) */
    pg.use = EXAMPLE_USES.some((e) => e.k && e.k === pg.use)
      ? pg.use
      : Array.isArray(pg.uses)
        ? pg.uses.includes("sequel")
          ? "sequel"
          : pg.uses.includes("parallel")
            ? "parallel"
            : ""
        : "";
    delete pg.uses;
    delete pg.mode;
    const c = pg.cards || {},
      o = c.outline,
      s = c.style;
    if (s && (s.pov === "third_omniscient" || s.pov === "third_person"))
      s.pov = "third_limited";
    /* a style card missing a field (one saved before the dials) gets the middle level and blank text */
    if (s && typeof s === "object") {
      STYLE_DIALS.forEach((k) => {
        if (!s[k] || typeof s[k] !== "object") s[k] = { level: 3, note: "" };
      });
      STYLE_TEXT_FIELDS.forEach((k) => {
        if (typeof s[k] !== "string") s[k] = "";
      });
      ["signature_moves", "off_limits"].forEach((k) => {
        if (!Array.isArray(s[k])) s[k] = [];
      });
    }
    if (o && typeof o === "object") {
      const bs = Array.isArray(o.chapter_beats) ? o.chapter_beats : [];
      if (o.protagonist == null || o.protagonist === "")
        o.protagonist =
          (bs[0] && bs[0].pov) || ((o.arcs || [])[0] || {}).character || "";
      bs.forEach((b) => {
        if (b && typeof b === "object") delete b.pov;
      });
    }
    return pg;
  };
  const asPage = (x) =>
    migrate(
      Object.assign(newPage(), x, {
        err: {},
        msg: "",
        notes: Object.assign(
          { style: "", characters: "", world: "", outline: "" },
          (x && x.notes) || {},
        ),
      }),
      x,
    );
  let P,
    curIdx = 0,
    tail = null;
  if (p.story && Array.isArray(p.story.pages)) {
    if (!p.story.pages.length) throw fail("This project has no pages.");
    P = p.story.pages.map((x) => {
      if (!x || typeof x !== "object")
        throw fail("This project file is damaged.");
      return asPage(x);
    });
    curIdx = Number(p.story.cur) || 0;
    const last = P[P.length - 1].result;
    if (last && last.cards_after) tail = last.cards_after;
  } else if (p.cards || p.story) {
    const ch = (p.story && p.story.chapters) || [],
      drafts = (p.story && p.story.drafts) || {};
    P = [
      asPage({
        cards: p.cards || {},
        stale: p.stale || {},
        warn: p.warn || {},
        notes: p.notes,
        mode: p.mode === "chapter" ? "chapter" : "notes",
        chapter: p.chapter || "",
      }),
    ];
    ch.forEach((c, i) => {
      if (i >= P.length) return;
      const pg = P[i];
      pg.result = Object.assign({}, c, {
        start_hash: startHash(c.cards_before || {}),
        changes: c.changes || [],
        warnings: c.warnings || [],
        unintroduced: c.unintroduced || [],
      });
      if (i + 1 < ch.length) {
        const np = asPage({});
        np.cards = clone(ch[i + 1].cards_before || {});
        np.base_hash = startHash(c.cards_after || {});
        P.push(np);
      }
    });
    const last = ch[ch.length - 1];
    if (last && last.cards_after)
      tail = drafts[ch.length + 1] || last.cards_after;
  } else throw fail("This file does not contain a project.");
  if (tail) {
    const np = asPage({});
    fillPage(np, tail);
    P.push(np);
  }
  P.forEach((pg) => {
    delete pg.from_id;
    if (pg.result)
      ["cards_before", "cards_after", "card_checks", "target_words"].forEach(
        (k) => {
          delete pg.result[k];
        },
      );
  });
  return {
    pages: P,
    cur: Math.min(Math.max(curIdx, 0), P.length - 1),
    job: null,
  };
}
function loadProjectFile(text) {
  let p;
  try {
    p = JSON.parse(text);
  } catch (e) {
    throw fail("That file is not valid JSON.");
  }
  const story = normalizeProject(p);
  st.story = story;
  st.report = null;
  st.armed = false;
  st.banner = "";
  $("#slug").value = p.slug || "";
  save("slug", $("#slug").value);
  if (p.lang === "zh" || p.lang === "en") {
    LANG = p.lang;
    save("lang", LANG);
    applyStatic();
  }
  draw(false);
  saveProject();
}
