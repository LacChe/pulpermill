// Finding the way back after the page was reloaded or the connection dropped while the backend was working.
//
// The backend remembers every named call (what is running, what finished, which project it was for: call `status`). This file turns that
// list into what the page does about it, and nothing here asks the model for anything:
// - a call for THIS project that is still running (a plan or a chapter) is taken over: the page shows it as its own and lands the result
//   when it arrives, as if it had never been away;
// - a call for this project that finished while the page was away is offered with the Collect button, and applied only when pressed;
// - a call for ANOTHER project is only reported, with that project's title (or its id when it has none), so the writer opens the right file;
// - anything else that finished (a failed call, a chapter written again) is reported once.
// A run of several chapters does not go on by itself after a reload: the call in flight is landed or collected, and the writer chooses.
// `handled` is the set of job ids already applied or reported (kept in the browser), so one result is never applied twice.
import { collectGenerated, collectPlan } from "./client.js";
import { beatForChapter, chapterInfo, newBeat } from "./plan.js";
import { section, fill, msg } from "./text.js";

export const STRINGS = section("resume");
export const HANDLED_KEY = "pulpermill.handled";
const HANDLED_MAX = 100;

// The page's tag for what a call is for: plan:3, chapter:3, again:3.
export function parseTag(tag) {
  const found = /^(plan|chapter|again):(\d{1,4})$/.exec(String(tag ?? ""));
  return found ? { kind: found[1], n: Number(found[2]) } : null;
}

const resumable = (call) => ["plan", "chapter"].includes(parseTag(call.tag)?.kind) && ["plan", "generate"].includes(call.call);

// Sorts the backend's calls into what the page does. project: the open project (its id decides which calls are its own).
// Returns {running, wait, collect, report, other}: `running` is the call to take over, `wait` a running call of this project the page
// cannot take over, `collect` the finished ones that can be applied, `report` finished ones to say once, `other` calls of another project.
export function reconcile({ calls = [], project = null, handled = new Set() } = {}) {
  const out = { running: null, wait: [], collect: [], report: [], other: [] };
  for (const call of calls) {
    if (!call.project) continue;                       // a call without a project is not something to find the way back to
    if (handled.has(call.job_id)) continue;
    if (!project?.id || call.project.id !== project.id) { out.other.push(call); continue; }
    if (call.state === "running") {
      if (resumable(call) && !out.running) out.running = call; else out.wait.push(call);
    } else if (call.state === "done" && resumable(call)) out.collect.push(call);
    else out.report.push(call);
  }
  return out;
}

// How a project is named in a message: its title when it has one, otherwise its id.
export const projectName = (ref) => (ref?.title ? msg("common.quoted", { text: ref.title }) : ref?.id ?? "");

export function whatOf(call) {
  const tag = parseTag(call.tag);
  const words = { plan: STRINGS.what_plan, chapter: STRINGS.what_chapter, again: STRINGS.what_again };
  return fill(words[tag?.kind] ?? STRINGS.what_call, { n: tag?.n ?? "" });
}

export function storedHandled(storage) {
  try { return new Set(JSON.parse(storage.getItem(HANDLED_KEY) ?? "[]").filter((id) => typeof id === "string")); } catch { return new Set(); }
}

function keepHandled(storage, ids) {
  try { storage.setItem(HANDLED_KEY, JSON.stringify([...ids].slice(-HANDLED_MAX))); } catch { /* not remembered: the result may be offered again */ }
}

// hooks: {schema, client, getProject, getPlanPanel(), getGeneratePanel(), notice(text, kind), errorText(error), storage, button}
export function createCollector(hooks) {
  const handled = storedHandled(hooks.storage);
  let waiting = [];                                    // finished calls of this project the button can apply
  const mark = (id) => { handled.add(id); keepHandled(hooks.storage, handled); };

  function drawButton() {
    if (!hooks.button) return;
    hooks.button.hidden = !waiting.length || hooks.client.state.working;
    hooks.button.title = waiting.length ? whatOf(waiting[0]) : "";
  }

  // Applies a finished call's reply to the project as it is now, through the panel that would have landed it.
  function apply(call, reply, project) {
    const tag = parseTag(call.tag);
    if (reply?.ok === false && reply.error?.kind === "unreachable") { hooks.notice(hooks.errorText(reply.error), "notice-bad"); return false; }
    mark(call.job_id);
    if (!tag) return true;
    if (reply?.ok === false) {
      hooks.notice(hooks.errorText(reply.error), reply.error?.kind === "stopped" ? "" : "notice-bad");
      return true;
    }
    if (tag.kind === "plan") {
      const next = chapterInfo(project).next;
      const beat = next === tag.n ? (beatForChapter(project, next) ?? newBeat(hooks.schema, project, next)) : null;
      hooks.getPlanPanel().land(project, beat ? collectPlan(hooks.schema, project, beat, tag.n, reply) : { ok: false, reason: "other_chapter" });
    } else if (tag.kind === "chapter") {
      hooks.getGeneratePanel().land(project, collectGenerated(hooks.schema, project, tag.n, reply));
    }
    return true;
  }

  // Looks at what the backend last listed (call client.checkStatus first) and acts on it. Safe to call as often as wanted.
  function follow() {
    const project = hooks.getProject();
    const found = reconcile({ calls: hooks.client.calls, project, handled });
    waiting = found.collect;
    drawButton();
    const lines = [];
    for (const call of found.other) {
      lines.push(fill(call.state === "running" ? STRINGS.otherRunning : STRINGS.otherDone, { what: whatOf(call), name: projectName(call.project) }));
    }
    for (const call of found.wait) lines.push(fill(STRINGS.stillRunning, { what: whatOf(call) }));
    for (const call of found.report) {
      lines.push(fill(call.state === "failed" ? STRINGS.failed : STRINGS.finishedAway, { what: whatOf(call), error: call.error ?? "" }));
      mark(call.job_id);
    }
    if (found.collect.length) lines.push(fill(STRINGS.ready, { what: whatOf(found.collect[0]) }));
    if (found.running && !hooks.client.state.working) {
      lines.push(fill(STRINGS.reconnected, { what: whatOf(found.running) }));
      take(found.running, project);
    }
    if (lines.length) hooks.notice(lines.join(" "), found.other.length || found.report.some((c) => c.state === "failed") ? "notice-bad" : "");
  }

  async function take(call, project) {
    const tag = parseTag(call.tag);
    const reply = await hooks.client.adopt({ job_id: call.job_id, call: call.call, chapter: tag?.n ?? null }).done;
    if (hooks.getProject() !== project) return;
    apply(call, reply, project);
    await hooks.client.checkStatus();
    follow();
  }

  // The Collect button: fetches the oldest waiting result and applies it.
  async function collect() {
    const call = waiting[0];
    const project = hooks.getProject();
    if (!call) return;
    const reply = await hooks.client.fetchJob(call.job_id);
    if (hooks.getProject() !== project) return;
    apply(call, reply, project);
    await hooks.client.checkStatus();
    follow();
  }

  hooks.button?.addEventListener("click", collect);
  hooks.client.onChange(drawButton);
  return { follow, collect, handled };
}
