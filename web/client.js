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
  readOffstageReply, readPlanReply, readGenerateReply, readEndStoryReply,
  failure, STORY_CALLS, readStatus, fillRequest, readFillReply, planFill, judgeRequest, readJudgeReply, styleFitRequest,
  readStyleFitReply,
} from "./logic.js";
import { generateGate, generateRequest, applyGenerated, inputsKey, regenerateGate, regenerateKey, applyRegenerated } from "./generate.js";
import { endGate, endStoryRequest, landEndStory } from "./endstory.js";
import { msg } from "./text.js";
import { planGate, offstageDue, offstageRequest, planRequest, landBeat, beatForChapter, beatBlockers } from "./plan.js";

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

export const DEFAULT_TIMEOUTS = {
  status: 5000, fill: 180000, judge: 180000, style_fit: 120000,
  offstage: 120000, plan: 300000, generate: 1800000, end_story: 600000,
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
export function createClient({ setting = { kind: "mock" }, token = "", mock = null, fetchImpl = globalThis.fetch, timeouts = {}, sleep = wait, pollEvery = 1000, lostAfter = 3, recoverEvery = 3000, recoverFor = 20 * 60 * 1000 } = {}) {
  let current = setting;
  let secret = token;
  let running = null;                 // the model call this page has going, if any
  let since = null;                   // when that call began (ms), so a button can show how long it has run
  let connection = "unknown";         // unknown | idle | busy | unreachable
  let stage = null;                   // what the backend says it is doing, while a story call runs
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
          if (next !== stage) { stage = next; changed(); }
        }
      }
    })();
    return () => { alive = false; wake?.(); if (stage !== null) { stage = null; changed(); } };
  }

  async function settle({ interval = 500, tries = 20 } = {}) {
    for (let i = 0; i < tries; i++) {
      if ((await client.checkStatus()) === "idle") return true;
      await sleep(interval);
    }
    return false;
  }

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
        if ((reply.stage ?? null) !== stage) { stage = reply.stage ?? null; changed(); }
        continue;
      }
      if (reply?.ok === true && reply.state === "unknown") return failure("unreachable", msg("backend.jobGone"));
      if (reply?.ok === false && reply.error?.kind === "unreachable") { setConnection("unreachable"); continue; }
      return reply;                       // the call's own answer, or its own error
    }
    return failure("unreachable", msg("backend.jobLost"));
  }

  function start(request) {
    const call = request?.call;
    const isStatus = call === "status";
    if (!isStatus && running) {
      return { done: Promise.resolve(failure("busy", "This page is already waiting for an answer.")), stop() {} };
    }
    const named = current.kind === "url" && !isStatus;
    const jobId = named ? makeJobId() : null;
    const sent = named ? { ...request, job_id: jobId } : request;
    const controller = new AbortController();                // ends the whole call: Stop or the time limit
    let attempt = new AbortController();                      // one try at the connection; it alone ends when the connection is lost
    controller.signal.addEventListener("abort", () => attempt.abort());
    let lost = false;
    let why = null;
    const timer = setTimeout(() => { why = "timeout"; controller.abort(); }, limits[call] ?? limits.fill);
    const handle = {
      stop() {
        why ??= "stopped"; controller.abort();
        if (jobId) post(fetchImpl, current.url, { call: "cancel", job_id: jobId }, undefined, secret).catch(() => {});
      },
    };
    if (!isStatus) { running = handle; since = Date.now(); changed(); }
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
        if (!isStatus) { running = null; since = null; }
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
      setConnection(reply.ok ? reply.state : "unreachable");
      return connection;
    },
    // End whatever call this page has going. Does nothing when there is none.
    stop() { running?.stop(); },
    setSetting(next) { current = next; connection = "unknown"; judgeCache.clear(); changed(); },
    setToken(next) { secret = String(next ?? ""); connection = "unknown"; changed(); },
    onChange(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    // Called with the reply each time a model call ends (not status checks): the tab icon uses it to say done or failed.
    onFinish(listener) { finishers.add(listener); return () => finishers.delete(listener); },
    // What the page needs to draw: whether this page is waiting on a call, and what the backend last said.
    get state() { return { working: Boolean(running), since, connection, setting: current, stage }; },
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

// Plan the next chapter: the offstage move when one is due, then think and fill the beat, and one more try when the
// Outline's own blocking rules refuse the first beat (the second attempt is told what was wrong). Nothing is changed:
// it resolves to {ok: true, beat, thinking, offstage, unresolved, dropped, warnings, blockers, retried, replaces} and the page decides
// what to land. `replaces` is the unwritten beat for the same chapter that landing it would replace.
// A request the page cannot make resolves to {ok: false, reason} (see planGate); a failed call to its failure.
export function planChapter(client, schema, project, castIds) {
  const gate = planGate(project, castIds);
  if (!gate.ok) return refused(gate.reason === "cast" ? `cast_${gate.why}` : gate.reason);
  const replaces = beatForChapter(project, gate.chapter);
  let current = null;
  let stopped = false;
  const call = (request) => { current = client.start(request); return current.done; };
  const done = (async () => {
    let offstage = null;
    if (offstageDue(gate.chapter)) {
      const read = readOffstageReply(await call(offstageRequest(schema, project, castIds)));
      if (!read.ok) return read;
      offstage = { did: read.did, reach: read.reach };
    }
    if (stopped) return failure("stopped");
    let read = readPlanReply(await call(planRequest(schema, project, castIds, { offstage })));
    if (!read.ok) return read;
    let landed = landBeat(schema, project, castIds, read, { offstage, existing: replaces });
    let blockers = beatBlockers(schema, project, landed.beat);
    let retried = false;
    if (blockers.length && !stopped) {
      retried = true;
      const second = readPlanReply(await call(planRequest(schema, project, castIds, { offstage, retry: { thinking: read.thinking, beat: read.beat, problems: blockers } })));
      if (!second.ok) return second;
      read = second;
      landed = landBeat(schema, project, castIds, read, { offstage, existing: replaces });
      blockers = beatBlockers(schema, project, landed.beat);
    }
    return { ok: true, beat: landed.beat, thinking: read.thinking, offstage, unresolved: landed.unresolved, dropped: landed.dropped, warnings: landed.warnings, blockers, retried, replaces };
  })();
  return { done, stop() { stopped = true; current?.stop(); } };
}

// Write the next chapter: one call that writes it and reads it twice. Nothing is changed: it resolves to
// {ok: true, outcome, beat, stale} where `outcome` is applyGenerated's (the records, the changed Entanglements, the changes that
// touch locked values) and the page commits it with commitChapter once the writer has answered any question.
// {ok: false, reason} when the page cannot make the request (see generateGate), {ok: false, reason: "changed"} when the
// Entanglements or the beat were edited while the model wrote, and the call's failure otherwise.
export function generateChapter(client, schema, project) {
  const gate = generateGate(schema, project);
  if (!gate.ok) return { done: Promise.resolve({ ok: false, reason: gate.reason, problems: gate.problems }), stop() {} };
  const key = inputsKey(schema, project, gate.beat);
  const call = client.start(generateRequest(schema, project, gate.beat));
  return {
    stop: call.stop,
    done: call.done.then((reply) => {
      const read = readGenerateReply(reply);
      if (!read.ok) return read;
      const again = generateGate(schema, project);
      if (!again.ok || inputsKey(schema, project, again.beat) !== key) return { ok: false, reason: "changed" };
      return { ok: true, beat: gate.beat, stale: gate.stale, read, outcome: applyGenerated(schema, project, gate.beat, read, { overwriteLocked: true }) };
    }),
  };
}

// Write chapter `number` again, from the state it was first written from. Nothing is changed: it resolves to
// {ok: true, ctx, read, outcome} (applyRegenerated's outcome, with the old text as `before`), or a failure as generateChapter does.
// The writer's answer to the locked-values question is applied with applyRegenerated(schema, project, ctx, read, {overwriteLocked}).
export function regenerateChapter(client, schema, project, number) {
  const gate = regenerateGate(schema, project, number);
  if (!gate.ok) return { done: Promise.resolve({ ok: false, reason: gate.reason, problems: gate.problems }), stop() {} };
  const key = regenerateKey(schema, project, number);
  const call = client.start(generateRequest(schema, gate.trial, gate.beat));
  return {
    stop: call.stop,
    done: call.done.then((reply) => {
      const read = readGenerateReply(reply);
      if (!read.ok) return read;
      if (regenerateKey(schema, project, number) !== key) return { ok: false, reason: "changed" };
      return { ok: true, ctx: gate, read, outcome: applyRegenerated(schema, project, gate, read, { overwriteLocked: true }) };
    }),
  };
}

// The end of the story: the model updates Characters and World from the records. Nothing is changed: it resolves to
// {ok: true, after, forced, dropped} (landEndStory's) and the page stores `after` as project.after_story once the writer has seen
// it. {ok: false, reason: "not_done"} while a chapter is still to write, and the call's failure otherwise.
export function endStory(client, schema, project) {
  const gate = endGate(project);
  if (!gate.ok) return { done: Promise.resolve({ ok: false, reason: gate.reason }), stop() {} };
  const call = client.start(endStoryRequest(schema, project));
  return {
    stop: call.stop,
    done: call.done.then((reply) => {
      const read = readEndStoryReply(reply);
      return read.ok ? landEndStory(schema, project, read) : read;
    }),
  };
}
