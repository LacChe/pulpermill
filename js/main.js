/* Pulpermill page: Startup: wire the buttons, restore the saved project, check the connection, resume a running job. */
$("#stopbtn").onclick = stopGeneration;
$("#lang-en").onclick = () => setLang("en");
$("#lang-zh").onclick = () => setLang("zh");
$("#test").onclick = testConnection;
["base", "slug"].forEach((id) => {
  const e = $("#" + id);
  e.value = load(id);
  e.addEventListener("input", () => save(id, e.value));
});
$("#base").addEventListener("change", testConnection);
$("#importfile").onchange = async (e) => {
  const f = [...e.target.files];
  e.target.value = "";
  if (f.length) await importFiles(f);
};
$("#projfile").onchange = async (e) => {
  const f = e.target.files[0];
  e.target.value = "";
  if (!f) return;
  if (st.busy) {
    st.banner = mk(
      "Wait for the current generation to finish before loading a project.",
    );
    return drawTop();
  }
  if (
    pages().some((p) => Object.keys(p.cards).length) &&
    !confirm(t("Loading replaces everything on the page. Continue?"))
  )
    return;
  try {
    loadProjectFile(await f.text());
  } catch (err) {
    st.banner = emsg(err);
    drawTop();
  }
};
document.addEventListener("input", scheduleSave);
document.addEventListener("change", scheduleSave);
(function restore() {
  let raw = load("project");
  try {
    if (raw) st.story = normalizeProject(JSON.parse(raw));
  } catch (e) {
    // never start empty without saying so; keep the unreadable text so it can be recovered
    let kept = true;
    try {
      localStorage.setItem("pmcg_project_unreadable", raw);
    } catch (e2) {
      kept = false;
    }
    st.banner = kept
      ? mk(
          "Your saved project could not be read, so the page started empty. The unreadable text is kept in this browser as pmcg_project_unreadable.",
        )
      : mk(
          "Your saved project could not be read, and no copy could be kept (browser storage is full). The page started empty.",
        );
  }
  if (!raw && STAGES.some((x) => load("notes_" + x.k) || load("chapter"))) {
    // notes typed in the first version of the page
    const pg = cur();
    STAGES.forEach((x) => (pg.notes[x.k] = load("notes_" + x.k)));
    pg.chapter = load("chapter");
  }
})();
applyStatic();
draw();
if (base()) testConnection();
if (st.story.job && st.story.job.id && base())
  pollChapter(st.story.job); // a chapter was being written when the page closed: pick it up again
else st.story.job = null;

["pointerdown", "keydown", "wheel", "touchstart"].forEach((e) =>
  document.addEventListener(e, seenTab, { capture: true, passive: true }),
);
document.addEventListener("scroll", seenTab, { capture: true, passive: true });
window.addEventListener("focus", seenTab);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) seenTab();
});
setTabIcon("idle");

/* keeps the bar creeping while a step reports nothing new */
setInterval(() => {
  if (st.busy) refreshBar();
  else st.prog = null;
}, 400);
