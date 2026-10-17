/* Pulpermill project persistence: browser storage and project files. */
const transient = (k, v) =>
  k === "msg" || k === "err" || k === "draft" ? undefined : v; // drafts: unsent notes, kept across redraws only
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
      { format: "pulpermill-project", version: 3, story: st.story },
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
      version: 3,
      saved: new Date().toISOString(),
      slug: $("#slug").value,
      lang: LANG,
      story: { ...st.story, job: null },
    },
    transient,
    1,
  );
}
function normalizeProject(p) {
  if (!p || typeof p !== "object" || Array.isArray(p))
    throw fail("That is not a Pulpermill project file.");
  if (p.format !== "pulpermill-project")
    throw fail("That is not a Pulpermill project file.");
  if (p.version !== 3)
    throw fail("This project file version is not supported.");
  const s = p.story;
  if (
    !s ||
    typeof s !== "object" ||
    !s.cards ||
    typeof s.cards !== "object" ||
    !Array.isArray(s.chapters) ||
    !s.chapters.length
  )
    throw fail("This project file is damaged.");
  const P = s.chapters.map((x) => {
    if (!x || typeof x !== "object" || Array.isArray(x))
      throw fail("This project file is damaged.");
    return Object.assign(newChapter(), x, {
      cast: Array.isArray(x.cast) ? x.cast : undefined,
      result:
        x.result && typeof x.result === "object"
          ? Object.assign(
              { changes: [], warnings: [], unintroduced: [] },
              x.result,
            )
          : null,
      msg: "",
    });
  });
  return Object.assign(newStory(), s, {
    chapters: P,
    cur: Math.min(Math.max(Number(s.cur) || 0, 0), P.length - 1),
  });
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
