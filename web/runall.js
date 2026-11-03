// Run all: one button plans and writes every chapter that is left, one after the other, so the writer need not come back to press
// the two single buttons for each chapter. It takes exactly the steps those buttons take, through the page's own client: plan the
// chapter (planChapter), put the plan in the Outline (commitPlan), write it (generateChapter), commit it (commitChapter) with its
// chapter note, then save through the same hooks (changed, redraw). Nothing is asked between chapters.
//
// It stops at the first problem (a gate that refuses, or a failed or stopped call) and leaves every chapter already written in place.
// A beat the writer already planned is written as it is, not planned again. Warn-level findings do not stop the run.
// No DOM here, so Node can test it. The button and the progress line are drawn by planpanel.js from this controller.
//
//   const runAll = createRunAll({schema, client, getProject, changed(), redraw(), notice(text, kind), errorText(error)});
//   runAll.start(project, firstBeat)   resolves to {ok, written, stoppedAt, reason}
//   runAll.stop()                      cancels the call in progress and ends the loop
//   runAll.running, runAll.progressText(), runAll.onChange(listener)
import { planChapter, generateChapter } from "./client.js";
import { chapterInfo, beatForChapter, newBeat, commitPlan, CAST_MAX } from "./plan.js";
import { commitChapter } from "./generate.js";
import { setChapterNote } from "./modelnotes.js";
import { stageText } from "./logic.js";
import { section, fill, joinList } from "./text.js";

export const STRINGS = section("runall");
const PLAN = section("plan");
const GENERATE = section("generate");

export function createRunAll(hooks) {
  const { schema, client } = hooks;
  let run = null;                         // {project, chapter, total, phase, call, stopped} while a run is going
  const listeners = new Set();
  const tell = () => { for (const listener of listeners) listener(); };

  // "Chapter 3 of 6: The model is writing the chapter… (step 2 of 3)": the backend's own stage when it names one.
  function progressText() {
    if (!run) return "";
    const what = stageText(client.state.stage) || (run.phase === "plan" ? STRINGS.planning : STRINGS.writing);
    return fill(STRINGS.progress, { n: run.chapter, total: run.total, what });
  }

  // Why a call or a gate said no, in the words the single buttons use.
  function whyText(result, reasons) {
    if (result.reason) return joinList([fill(reasons[result.reason] ?? result.reason, { max: CAST_MAX }), ...(result.problems ?? [])], "sentence");
    return hooks.errorText(result.error);
  }

  async function step(call) {
    run.call = call;
    const result = await call.done;
    if (run) run.call = null;
    return result;
  }

  async function loop(project, firstBeat) {
    let written = 0;
    const first = run.chapter;
    const gone = { ok: false, written, reason: "switched" };                    // another project was opened: end without a word
    const end = (n, phase, result, reasons) => {
      const stopped = result.error?.kind === "stopped" || run.stopped;
      const text = stopped ? fill(STRINGS.stopped, { n }) : fill(phase === "plan" ? STRINGS.failedPlan : STRINGS.failedWrite, { n, why: whyText(result, reasons) });
      hooks.notice(joinList([text, STRINGS.kept], "sentence"), stopped ? "" : "notice-bad");
      return { ok: false, written, stoppedAt: n, reason: stopped ? "stopped" : (result.reason ?? result.error?.kind ?? "failed") };
    };
    for (;;) {
      const info = chapterInfo(project);
      if (info.done) break;
      const n = info.next;
      if (run.stopped) return end(n, "plan", { ok: false, error: { kind: "stopped" } }, PLAN.reasons);
      run.chapter = n;

      // Plan it, unless the writer has planned it already. The first chapter starts from the beat the panel shows (its spotlight and cast).
      const existing = beatForChapter(project, n);
      if (!existing?.plan) {
        run.phase = "plan";
        tell();
        const beat = n === first && firstBeat ? firstBeat : existing ?? newBeat(schema, project, n);
        const planned = await step(planChapter(client, schema, project, beat));
        if (hooks.getProject() !== project) return gone;
        if (planned.reason || !planned.ok) return end(n, "plan", planned, PLAN.reasons);
        commitPlan(project, planned.beat);
        hooks.changed();
        hooks.redraw();
      }

      run.phase = "write";
      tell();
      const wrote = await step(generateChapter(client, schema, project));
      if (hooks.getProject() !== project) return gone;
      if (wrote.reason || !wrote.ok) return end(n, "write", wrote, GENERATE.reasons);
      const outcome = wrote.outcome;
      commitChapter(project, outcome);
      setChapterNote(project, outcome.chapter.id, { changes: outcome.changes, warnings: outcome.warnings });
      written++;
      hooks.changed();
      hooks.redraw();
    }
    hooks.notice(fill(STRINGS.done, { k: written, from: first, to: run.total }));
    return { ok: true, written };
  }

  async function start(project = hooks.getProject(), firstBeat = null) {
    if (run || !project) return { ok: false, written: 0, reason: "running" };
    const info = chapterInfo(project);
    if (!info.count || info.done) return { ok: false, written: 0, reason: "nothing_to_do" };
    run = { project, chapter: info.next, total: info.count, phase: "plan", call: null, stopped: false };
    tell();
    try { return await loop(project, firstBeat); } finally { run = null; tell(); }
  }

  return {
    start,
    stop() { if (run) { run.stopped = true; run.call?.stop(); } },
    reset() { this.stop(); },
    get running() { return run !== null; },
    progressText,
    onChange(listener) { listeners.add(listener); return () => listeners.delete(listener); },
  };
}
