// The page's side of the conversation with the backend. No DOM, so Node can test it.
//
// Every call goes through `client.start(request)`, which gives back {done, stop}:
//   done  a promise that ALWAYS resolves to a reply: the backend's, or a failure the client made itself
//         (unreachable, timeout, stopped, busy). It never rejects, so the page has one path to handle.
//   stop  ends the call. `done` then resolves to a "stopped" failure.
// Nothing here touches the project. The helpers at the bottom (fillCard, judgeCard, checkStyleFit) only work out what
// the backend's answer means; the page decides whether to use it, so a failed or stopped call changes nothing.
//
// Model calls only ever start from a button press. This file never starts one on its own, and the only thing it does
// by itself is ask the backend whether it is idle.

import {
  readPlanReply, readGenerateReply, readStage,
  failure, STORY_CALLS, readStatus, fillRequest, readFillReply, planFill, judgeRequest, readJudgeReply, styleFitRequest,
  readStyleFitReply,
} from "./logic.js";
import { jobOf } from "./progress.js";
import { generateGate, generateRequest, applyGenerated, inputsKey, regenerateGate, regenerateKey, applyRegenerated } from "./generate.js";
import { msg } from "./text.js";
import { planGate, planRequest, landBeat, beatBlockers } from "./plan.js";

// ---- The backend setting ----------------------------------------------------
// "mock" (the default, so the page works with nothing running) or the address of a backend.

export const BACKEND_KEY = "pulpermill-backend";
// The shared secret lives beside the address, never inside it, so it is not shown in the status line or in an error.
export const TOKEN_KEY = "pulpermill-token";

// The headers every request to a real backend carries. The first skips ngrok's browser warning page. The second is
// the writer's token, sent only when one is set.
export function requestHeaders(token) {
  const headers = { "content-type": "application/json", "ngrok-skip-browser-warning": "1" };
  const secret = String(token ?? "").trim();
  if (secret) headers["x-pulpermill-token"] = secret;
  return headers;
}

export function parseBackendSetting(text) {
  const raw = String(text ?? "").trim();
  if (!raw || raw.toLowerCase() === "mock") return { ok: true, kind: "mock" };
  let url;
  try {
    url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `http://${raw}`);
  } catch {
    return { ok: false, reason: "not_a_url" };
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return { ok: false, reason: "not_http" };
  return { ok: true, kind: "url", url: url.origin + url.pathname.replace(/\/+$/, "") };
}

// What the browser kept, or the mock when it kept nothing usable.
export function readStoredSetting(text) {
  const parsed = parseBackendSetting(text);
  return parsed.ok ? parsed : { ok: true, kind: "mock" };
}

// What to show in the box: "mock" or the address.
export function settingText(setting) {
  return setting.kind === "url" ? setting.url : "mock";
}

// A page served over https may not call a plain http address, except one on this computer.
export function blockedByPage(setting, pageProtocol) {
  if (setting.kind !== "url" || pageProtocol !== "https:") return false;
  const { protocol, hostname } = new URL(setting.url);
  return protocol === "http:" && !["localhost", "127.0.0.1", "[::1]"].includes(hostname);
}

// ---- The client ----------------------------------------------------------------

// How long the page waits for one model call before giving up (ms). 900000 = 15 minutes. Written as plain numbers:
// tests/schema/test_contract.py reads this table and wants a number after each call's name.
export const DEFAULT_TIMEOUTS = {
  status: 5000, fill: 900000, judge: 900000, style_fit: 900000,
  plan: 900000, generate: 900000,
};

// The fallback when the body is not an answer. It agrees with HTTP_STATUS in pulpermill/contract.py.
const STATUS_FAILURES = { 400: "bad_request", 401: "unauthorized", 409: "stopped", 413: "too_long", 429: "busy", 502: "bad_output", 503: "busy" };

// One call to a real backend: POST the request as JSON to <url>/api. The backend answers in the contract's shapes,
// with an HTTP status that agrees. A body that is not an answer falls back on the status.
async function post(fetchImpl, url, request, signal, token) {
  let response;
  try {
    response = await fetchImpl(`${url}/api`, {
      method: "POST", headers: requestHeaders(token), body: JSON.stringify(request), signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    return failure("unreachable", error?.message);
  }
  // A long call is answered as a stream: the headers go out first and the body arrives at the end. If the connection drops
  // while the body is still coming, reading it fails with a network error. That is a lost connection, not an answer in
  // the wrong shape (which fails to parse, a SyntaxError).
  let body = null;
  try { body = await response.json(); } catch (error) {
    if (error?.name === "AbortError") throw error;
    if (!(error instanceof SyntaxError)) return failure("unreachable", error?.message);
  }
  if (body && typeof body === "object" && !Array.isArray(body) && typeof body.ok === "boolean") return body;
  if (!response.ok) return failure(STATUS_FAILURES[response.status] ?? "server", msg("backend.answered", { status: response.status }));
  return failure("bad_output", "The backend's answer was not JSON.");
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// options: {setting, token, mock, fetchImpl, timeouts, sleep, pollEvery, lostAfter}
//   setting    from parseBackendSetting
//   token      the writer's shared secret, sent to a real backend when set (client.setToken changes it)
//   mock       the object from createMock, used when the setting is "mock"
//   sleep      how to wait between the idle checks after a Stop or a timeout (tests pass a fast one)
//   pollEvery  while a story call runs, how often to ask status (ms): it shows the stage and notices a lost connection
//   lostAfter  how many status checks in a row may fail before the connection is counted as lost
//   recoverEvery, recoverFor  after a lost connection, a named call is asked for by name every `recoverEvery` ms for up to `recoverFor` ms
export function createClient({ setting = { kind: "mock" }, token = "", mock = null, fetchImpl = globalThis.fetch, timeouts = {}, sleep = wait, pollEvery = 1000, lostAfter = 3, recoverEvery = 3000, recoverFor = 20 * 60 * 1000, projectRef = () => null } = {}) {
  let current = setting;
  let secret = token;
  let running = null;                 // the model call this page has going, if any
  let since = null;                   // when that call began (ms), so a button can show how long it has run
  let job = null;                     // what that call is ({call, card, rules, chapter, choose}), so the progress bar can lay out its steps
  let connection = "unknown";         // unknown | idle | busy | unreachable
  let stage = null;                   // what the backend says it is doing, while a story call runs
  let stopping = null;                // the Stop in progress (a promise), if any
  let calls = [];                     // the named calls the backend listed in its last status answer
  let ref = projectRef;               // () => {id, title} | null: which project a story call is for, so the backend can say after a reload
  const listeners = new Set();
  const finishers = new Set();        // told each time a model call ends, with its reply
  const judgeCache = new Map();

  const limits = { ...DEFAULT_TIMEOUTS, ...timeouts };
  const changed = () => { for (const listener of listeners) listener(client.state); };
  const setConnection = (value) => { if (value !== connection) { connection = value; changed(); } };

  function transport(request, signal) {
    if (current.kind === "mock") return mock.send(request, { signal });
    return post(fetchImpl, current.url, request, signal, secret);
  }

  // While a story call runs, ask status every `pollEvery` ms. It shows the stage the backend names, and it is how the
  // page notices the connection dropped: `lostAfter` failed checks in a row end the call as unreachable.
  // Returns a function that stops watching.
  function watch(onLost) {
    let alive = true;
    let misses = 0;
    let wake = null;
    // A real timer that the end of the call can cut short, so nothing is left waiting and the loop always yields.
    const nap = () => new Promise((resolve) => { const t = setTimeout(resolve, pollEvery); wake = () => { clearTimeout(t); resolve(); }; });
    (async () => {
      while (alive) {
        await nap();
        if (!alive) break;
        const reply = readStatus(await start({ call: "status" }).done);
        if (!alive) break;
        if (!reply.ok) {
          if (++misses >= lostAfter) { onLost(); break; }
        } else {
          misses = 0;
          const next = reply.state === "busy" ? reply.stage ?? null : null;
          if (JSON.stringify(next) !== JSON.stringify(stage)) { stage = next; changed(); }
        }
      }
    })();
    return () => { alive = false; wake?.(); if (stage !== null) { stage = null; changed(); } };
  }

  // Waits until the backend says idle: every `interval` ms, `tries` times (a minute by default, so a slow cancel is not given up
  // on early). Resolves false if it never went idle. Callers that arrive while one wait is going share it.
  let settling = null;
  function settle({ interval = 500, tries = 120 } = {}) {
    settling ??= (async () => {
      for (let i = 0; i < tries; i++) {
        if ((await client.checkStatus()) === "idle") return true;
        await sleep(interval);
      }
      return false;
    })().finally(() => { settling = null; });
    return settling;
  }

  // Asks the backend to stop what it is running: that call when its id is known, otherwise whatever it is running.
  // Resolves to the backend's reply, or a failure the caller can show; it never throws.
  const cancelOnBackend = (jobId) => post(fetchImpl, current.url, jobId ? { call: "cancel", job_id: jobId } : { call: "cancel" }, undefined, secret)
    .catch((error) => failure("unreachable", error?.message));

  // A name for one call, sent with it so the backend keeps the call going if the connection drops and keeps its answer.
  const makeJobId = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`).replace(/[^A-Za-z0-9_-]/g, "");

  // The call's connection dropped but the call may be going on in the backend. Ask for it by name until it is done, the
  // backend says it has never heard of it (it restarted: nothing to fetch), the page gives up, or Stop is pressed.
  async function recover(jobId, signal) {
    const tries = Math.max(1, Math.ceil(recoverFor / recoverEvery));
    setConnection("unreachable");
    for (let i = 0; i < tries && !signal.aborted; i++) {
      await sleep(recoverEvery);
      if (signal.aborted) break;
      const reply = await post(fetchImpl, current.url, { call: "job", job_id: jobId }, signal, secret).catch(() => failure("unreachable"));
      if (reply?.ok === true && reply.state === "running") {
        setConnection("busy");
        const next = readStage(reply.stage) ?? null;
        if (JSON.stringify(next) !== JSON.stringify(stage)) { stage = next; changed(); }
        continue;
      }
      if (reply?.ok === true && reply.state === "unknown") return failure("unreachable", msg("backend.jobGone"));
      if (reply?.ok === false && reply.error?.kind === "unreachable") { setConnection("unreachable"); continue; }
      return reply;                       // the call's own answer, or its own error
    }
    return failure("unreachable", msg("backend.jobLost"));
  }

  // Story calls say which project they are for and what for (the backend repeats both in status), so a page that was reloaded can tell
  // its own project's call from another's. Only a project that has an id (the story has started) is named.
  function labelled(request, tag) {
    if (!STORY_CALLS.includes(request?.call)) return {};
    const project = ref();
    const out = {};
    if (project?.id) out.project = { id: project.id, title: String(project.title ?? "").slice(0, 120) };
    if (tag) out.tag = tag;
    return out;
  }

  // Takes over a named call this page did not start (it was running when the page was reloaded): shows it as the page's own call,
  // asks for it by name until it is done, and resolves to its reply, as `start` does. Stop cancels it by name.
  function adopt({ job_id: jobId, call, chapter = null }) {
    if (running) return { done: Promise.resolve(failure("busy", "This page is already waiting for an answer.")), stop() {} };
    const controller = new AbortController();
    const handle = { stop() { controller.abort(); return cancelOnBackend(jobId); } };
    running = handle; since = Date.now(); job = jobOf({ call, chapter }); changed();
    const done = (async () => {
      let reply;
      try {
        reply = await recover(jobId, controller.signal);
        if (controller.signal.aborted) reply = failure("stopped");
      } finally { running = null; since = null; job = null; }
      if (reply?.ok === false && reply.error?.kind === "stopped") await settle();
      else if (reply?.error?.kind === "unreachable") setConnection("unreachable");
      for (const finisher of finishers) finisher(reply);
      changed();
      return reply;
    })();
    return { done, stop: handle.stop };
  }

  // The reply of a named call that finished while the page was away (what `start` would have resolved to), or a failure.
  async function fetchJob(jobId) {
    if (current.kind !== "url") return failure("unreachable");
    const reply = await post(fetchImpl, current.url, { call: "job", job_id: jobId }, null, secret).catch(() => failure("unreachable"));
    if (reply?.ok === true && reply.state === "unknown") return failure("unreachable", msg("backend.jobGone"));
    return reply;
  }

  function start(request, { tag = null } = {}) {
    const call = request?.call;
    const isStatus = call === "status";
    if (!isStatus && running) {
      return { done: Promise.resolve(failure("busy", "This page is already waiting for an answer.")), stop() {} };
    }
    const named = current.kind === "url" && !isStatus;
    const jobId = named ? makeJobId() : null;
    const sent = named ? { ...request, job_id: jobId, ...labelled(request, tag) } : request;
    const controller = new AbortController();                // ends the whole call: Stop or the time limit
    let attempt = new AbortController();                      // one try at the connection; it alone ends when the connection is lost
    controller.signal.addEventListener("abort", () => attempt.abort());
    let lost = false;
    let why = null;
    // On the time limit the call is also cancelled by name, as Stop does, so the backend does not go on running a call the page gave up on.
    const timer = setTimeout(() => {
      why = "timeout"; controller.abort();
      if (jobId) cancelOnBackend(jobId);
    }, limits[call] ?? limits.fill);
    const handle = {
      // Resolves to the backend's answer to the cancel (null when there was no call on a backend to cancel).
      stop() {
        why ??= "stopped"; controller.abort();
        return jobId ? cancelOnBackend(jobId) : Promise.resolve(null);
      },
    };
    if (!isStatus) { running = handle; since = Date.now(); job = jobOf(request); changed(); }
    const unwatch = STORY_CALLS.includes(call) ? watch(() => { lost = true; attempt.abort(); }) : () => {};
    const done = (async () => {
      let reply;
      try {
        reply = await transport(sent, attempt.signal);
      } catch (error) {
        reply = why === "timeout" ? failure("timeout", "No answer in time.")
          : lost && !why ? failure("unreachable", "The backend stopped answering.")
          : error?.name === "AbortError" ? failure("stopped") : failure("unreachable", error?.message);
      }
      try {
        if (named && !why && reply?.ok === false && reply.error?.kind === "unreachable") reply = await recover(jobId, controller.signal);
        if (why === "timeout") reply = failure("timeout", "No answer in time.");
        else if (why === "stopped") reply = failure("stopped");
      } finally {
        clearTimeout(timer);
        unwatch();
        if (!isStatus) { running = null; since = null; job = null; }
      }
      if (!isStatus) {
        // A call that ended without an answer may still be running on the backend. The page stays locked until the
        // backend says it is idle.
        if (reply?.ok === false && ["stopped", "timeout"].includes(reply.error?.kind)) await settle();
        else if (reply?.error?.kind === "unreachable") setConnection("unreachable");
        for (const finisher of finishers) finisher(reply);
        changed();
      }
      return reply;
    })();
    return { done, stop: handle.stop };
  }

  const client = {
    start,
    settle,
    judgeCache,
    // Ask the backend whether it is free. Returns "idle", "busy" or "unreachable".
    async checkStatus() {
      const reply = readStatus(await start({ call: "status" }).done);
      calls = reply.ok ? reply.calls : [];
      setConnection(reply.ok ? reply.state : "unreachable");
      return connection;
    },
    adopt,
    fetchJob,
    setProjectRef(next) { ref = next; },
    // The named calls the backend listed the last time it was asked (running first, then finished). Empty when it was not reachable.
    get calls() { return calls; },
    // Stop whatever the backend is doing, whether or not this page has a call going: cancel it by name when the page knows
    // it, otherwise without a name, then wait until the backend says idle. Resolves to {idle, cancelFailed}; `idle` is false
    // when the wait ran out with the backend still busy. A second press while one Stop is going joins it.
    stop() {
      if (!stopping) {
        stopping = (async () => {
          const call = running;
          let cancel = null;
          if (call) cancel = await call.stop();
          else if (current.kind === "url") cancel = await cancelOnBackend(null);
          if (cancel?.ok === false) return { idle: false, cancelFailed: true };
          return { idle: await settle(), cancelFailed: false };
        })().finally(() => { stopping = null; changed(); });
        changed();
      }
      return stopping;
    },
    setSetting(next) { current = next; connection = "unknown"; judgeCache.clear(); changed(); },
    setToken(next) { secret = String(next ?? ""); connection = "unknown"; changed(); },
    onChange(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    // Called with the reply each time a model call ends (not status checks): the tab icon uses it to say done or failed.
    onFinish(listener) { finishers.add(listener); return () => finishers.delete(listener); },
    // What the page needs to draw: whether this page is waiting on a call, and what the backend last said.
    get state() { return { working: Boolean(running), stopping: Boolean(stopping), since, connection, setting: current, stage, job }; },
  };
  return client;
}

// ---- What an answer means -------------------------------------------------------
// Each returns {done, stop} like client.start. `done` resolves to {ok: true, ...} or a failure, and never changes the
// project. A request the page cannot even make resolves at once to {ok: false, reason}.

const refused = (reason) => ({ done: Promise.resolve({ ok: false, reason }), stop() {} });

// Fill one card. Resolves to {ok: true, plan, ignored} where `plan` is planFill's: the page shows what would change
// and lands it with setCardValues once the writer agrees.
export function fillCard(client, schema, project, cardId, instanceId = null) {
  const made = fillRequest(schema, project, cardId, instanceId);
  if (!made.ok) return refused(made.reason);
  const card = schema.cards[cardId];
  const current = card.many_per_project ? project[cardId].find((i) => i.id === instanceId) : project[cardId] ?? {};
  const call = client.start(made.request);
  return {
    stop: call.stop,
    done: call.done.then((reply) => {
      const read = readFillReply(card, reply);
      return read.ok ? planFill(card, current, read, project) : read;
    }),
  };
}

// Ask the model about a card's model-judged rules. A rule whose fields (and the cards it reads) are the same as the
// last time it was asked about comes from memory, so Validate on an unchanged card makes no call at all.
// Resolves to {ok: true, problems, answered, missing, asked, fromMemory}.
export function judgeCard(client, schema, project, cardId, values, ruleIds = null) {
  const card = schema.cards[cardId];
  const request = judgeRequest(schema, project, cardId, values, ruleIds);
  const keyOf = (rule) => JSON.stringify([cardId, rule.id, rule.fields.map((key) => values[key] ?? null), request.related, request.language]);
  const remembered = new Map();
  const toAsk = [];
  for (const rule of request.rules) {
    const hit = client.judgeCache.get(keyOf(rule));
    if (hit) remembered.set(rule.id, hit);
    else toAsk.push(rule);
  }
  const combine = (fresh) => {
    const problems = [];
    const answered = [];
    for (const rule of request.rules) {
      const list = remembered.get(rule.id) ?? fresh.get(rule.id);
      if (!list) continue;
      answered.push(rule.id);
      problems.push(...list);
    }
    return { ok: true, problems, answered, missing: request.rules.map((r) => r.id).filter((id) => !answered.includes(id)),
      asked: toAsk.map((r) => r.id), fromMemory: [...remembered.keys()] };
  };
  if (!toAsk.length) return { done: Promise.resolve(combine(new Map())), stop() {} };
  const call = client.start({ ...request, rules: toAsk });
  return {
    stop: call.stop,
    done: call.done.then((reply) => {
      const read = readJudgeReply(card, values, toAsk.map((r) => r.id), reply);
      if (!read.ok) return read;
      const fresh = new Map();
      for (const id of read.answered) {
        const list = read.problems.filter((p) => p.rule === id);
        fresh.set(id, list);
        client.judgeCache.set(keyOf(toAsk.find((r) => r.id === id)), list);
      }
      return combine(fresh);
    }),
  };
}

// The story-start check: does the protagonist's personality allow the chosen person, tense and voice?
// Resolves to {ok: true, fits, message}.
export function checkStyleFit(client, schema, project) {
  const made = styleFitRequest(schema, project);
  if (!made.ok) return refused(made.reason);
  const call = client.start(made.request);
  return { stop: call.stop, done: call.done.then(readStyleFitReply) };
}

// Plan a chapter: think and fill the beat, and one more try when the Outline's own blocking rules refuse the first beat (the
// second attempt is told what was wrong). `beat` is the chapter's beat as the writer left it (the cast and the spotlight tie).
// Nothing is changed: it resolves to {ok: true, beat, unresolved, dropped, warnings, blockers, retried} and the page decides
// what to land (placeBeat). The planner always picks the tie and the pressure (`choose` defaults to true; the beat then carries its pick, and the page's own pair is the stand-in and the fallback). A request the page cannot make resolves to {ok: false, reason} (see planGate); a failed call to its failure.
export function planChapter(client, schema, project, beat, { choose = true, originHistory = true } = {}) {
  const gate = planGate(project, beat);
  if (!gate.ok) return refused(gate.reason === "cast" ? `cast_${gate.why}` : gate.reason);
  let current = null;
  let stopped = false;
  const call = (request) => { current = client.start(request, { tag: `plan:${beat.chapter}` }); return current.done; };
  const done = (async () => {
    let read = readPlanReply(await call(planRequest(schema, project, beat, { choose, originHistory })));
    if (!read.ok) return read;
    let landed = landBeat(schema, project, beat, read);
    let blockers = beatBlockers(schema, project, landed.beat);
    let retried = false;
    if (blockers.length && !stopped) {
      retried = true;
      // The retry keeps the pair the first reply landed (the planner's choice, or the page's own) and chooses nothing again.
      const kept = { ...beat, spotlight: landed.beat.spotlight, pressure: landed.beat.pressure };
      const second = readPlanReply(await call(planRequest(schema, project, kept, { retry: { beat: read.beat, problems: blockers }, choose: false, originHistory })));
      if (!second.ok) return second;
      read = second;
      landed = landBeat(schema, project, kept, read);
      blockers = beatBlockers(schema, project, landed.beat);
    }
    return { ok: true, beat: landed.beat, unresolved: landed.unresolved, dropped: landed.dropped, warnings: landed.warnings, blockers, retried };
  })();
  return { done, stop() { stopped = true; current?.stop(); } };
}

// Write the next chapter: one call that writes it and reads it. Nothing is changed: it resolves to
// {ok: true, outcome, beat, stale} where `outcome` is applyGenerated's (the chapter, its events, its shifts and the lines the chapter
// note shows) and the page commits it with commitChapter. {ok: false, reason} when the page cannot make the request (see
// generateGate), {ok: false, reason: "changed"} only when the beat is gone, and the call's failure otherwise. A plan edited while the model wrote is kept, with `edited: true`.
export function generateChapter(client, schema, project) {
  const gate = generateGate(schema, project);
  if (!gate.ok) return { done: Promise.resolve({ ok: false, reason: gate.reason, problems: gate.problems }), stop() {} };
  const key = inputsKey(schema, project, gate.beat);
  const call = client.start(generateRequest(schema, project, gate.beat), { tag: `chapter:${gate.beat.chapter}` });
  return {
    stop: call.stop,
    done: call.done.then((reply) => landGenerateReply(schema, project, gate, key, reply)),
  };
}

// What a chapter reply means for the project as it is now (nothing is changed). Used for a call this page made and for one it collects
// after a reload (then `gate` and `key` are made from the project as it is now, so an edit made since is simply what the project is).
export function landGenerateReply(schema, project, gate, key, reply) {
  const read = readGenerateReply(reply);
  if (!read.ok) return read;
  const again = generateGate(schema, project);
  if (!again.ok) return { ok: false, reason: "changed" };      // the beat itself is gone, so there is nothing to write into
  const edited = inputsKey(schema, project, again.beat) !== key;   // edited meanwhile: the chapter is kept, the page warns
  return { ok: true, beat: gate.beat, stale: gate.stale, read, edited, outcome: applyGenerated(schema, project, gate.beat, read) };
}

// A chapter reply collected after a reload: the same landing, from the project as it is. {ok: false, reason} when the page could not
// have made that request now (see generateGate) or the reply is for another chapter than the next one.
export function collectGenerated(schema, project, chapter, reply) {
  const gate = generateGate(schema, project);
  if (!gate.ok) return { ok: false, reason: gate.reason, problems: gate.problems };
  if (Number(gate.beat.chapter) !== Number(chapter)) return { ok: false, reason: "other_chapter" };
  return landGenerateReply(schema, project, gate, inputsKey(schema, project, gate.beat), reply);
}

// A plan reply collected after a reload (no second try: the writer sees what is still blocked and plans again if they want).
// Resolves to planChapter's result, or {ok: false, reason} when there is no next chapter to plan or it is not chapter `chapter`.
export function collectPlan(schema, project, beat, chapter, reply) {
  if (Number(beat?.chapter) !== Number(chapter)) return { ok: false, reason: "other_chapter" };
  const read = readPlanReply(reply);
  if (!read.ok) return read;
  const landed = landBeat(schema, project, beat, read);
  return { ok: true, beat: landed.beat, unresolved: landed.unresolved, dropped: landed.dropped, warnings: landed.warnings,
    blockers: beatBlockers(schema, project, landed.beat), retried: false };
}

// Write chapter `number` again, from the state going into it. Nothing is changed: it resolves to
// {ok: true, ctx, read, outcome} (applyRegenerated's outcome, with the old text as `before`), or a failure as generateChapter does.
export function regenerateChapter(client, schema, project, number) {
  const gate = regenerateGate(schema, project, number);
  if (!gate.ok) return { done: Promise.resolve({ ok: false, reason: gate.reason, problems: gate.problems }), stop() {} };
  const key = regenerateKey(schema, project, number);
  const call = client.start(generateRequest(schema, gate.trial, gate.beat), { tag: `again:${number}` });
  return {
    stop: call.stop,
    done: call.done.then((reply) => {
      const read = readGenerateReply(reply);
      if (!read.ok) return read;
      const edited = regenerateKey(schema, project, number) !== key;   // edited meanwhile: the chapter is kept, the page warns
      return { ok: true, ctx: gate, read, edited, outcome: applyRegenerated(schema, project, gate, read) };
    }),
  };
}
