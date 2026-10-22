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
  failure, readStatus, fillRequest, readFillReply, planFill, judgeRequest, readJudgeReply, styleFitRequest,
  readStyleFitReply,
} from "./logic.js";

// ---- The backend setting ----------------------------------------------------
// "mock" (the default, so the page works with nothing running) or the address of a backend.

export const BACKEND_KEY = "pulpermill-backend";

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

export const DEFAULT_TIMEOUTS = { status: 5000, fill: 180000, judge: 180000, style_fit: 120000 };

// The fallback when the body is not an answer. It agrees with HTTP_STATUS in pulpermill/schema/contract.py.
const STATUS_FAILURES = { 400: "bad_request", 409: "stopped", 413: "too_long", 429: "busy", 502: "bad_output", 503: "busy" };

// One call to a real backend: POST the request as JSON to <url>/api. The backend answers in the contract's shapes,
// with an HTTP status that agrees. A body that is not an answer falls back on the status.
async function post(fetchImpl, url, request, signal) {
  let response;
  try {
    response = await fetchImpl(`${url}/api`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request), signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    return failure("unreachable", error?.message);
  }
  let body = null;
  try { body = await response.json(); } catch { /* not JSON */ }
  if (body && typeof body === "object" && !Array.isArray(body) && typeof body.ok === "boolean") return body;
  if (!response.ok) return failure(STATUS_FAILURES[response.status] ?? "server", `The backend answered ${response.status}.`);
  return failure("bad_output", "The backend's answer was not JSON.");
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// options: {setting, mock, fetchImpl, timeouts, sleep}
//   setting    from parseBackendSetting
//   mock       the object from createMock, used when the setting is "mock"
//   sleep      how to wait between idle checks (tests pass a fast one)
export function createClient({ setting = { kind: "mock" }, mock = null, fetchImpl = globalThis.fetch, timeouts = {}, sleep = wait } = {}) {
  let current = setting;
  let running = null;                 // the model call this page has going, if any
  let connection = "unknown";         // unknown | idle | busy | unreachable
  const listeners = new Set();
  const judgeCache = new Map();

  const limits = { ...DEFAULT_TIMEOUTS, ...timeouts };
  const changed = () => { for (const listener of listeners) listener(client.state); };
  const setConnection = (value) => { if (value !== connection) { connection = value; changed(); } };

  function transport(request, signal) {
    if (current.kind === "mock") return mock.send(request, { signal });
    return post(fetchImpl, current.url, request, signal);
  }

  async function settle({ interval = 500, tries = 20 } = {}) {
    for (let i = 0; i < tries; i++) {
      if ((await client.checkStatus()) === "idle") return true;
      await sleep(interval);
    }
    return false;
  }

  function start(request) {
    const call = request?.call;
    const isStatus = call === "status";
    if (!isStatus && running) {
      return { done: Promise.resolve(failure("busy", "This page is already waiting for an answer.")), stop() {} };
    }
    const controller = new AbortController();
    let why = null;
    const timer = setTimeout(() => { why = "timeout"; controller.abort(); }, limits[call] ?? limits.fill);
    const handle = { stop() { why ??= "stopped"; controller.abort(); } };
    if (!isStatus) { running = handle; changed(); }
    const done = (async () => {
      let reply;
      try {
        reply = await transport(request, controller.signal);
      } catch (error) {
        reply = why === "timeout" ? failure("timeout", "No answer in time.")
          : error?.name === "AbortError" ? failure("stopped") : failure("unreachable", error?.message);
      } finally {
        clearTimeout(timer);
        if (!isStatus) running = null;
      }
      if (!isStatus) {
        // A call that ended without an answer may still be running on the backend. The page stays locked until the
        // backend says it is idle.
        if (reply?.ok === false && ["stopped", "timeout"].includes(reply.error?.kind)) await settle();
        else if (reply?.error?.kind === "unreachable") setConnection("unreachable");
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
    onChange(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    // What the page needs to draw: whether this page is waiting on a call, and what the backend last said.
    get state() { return { working: Boolean(running), connection, setting: current }; },
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
