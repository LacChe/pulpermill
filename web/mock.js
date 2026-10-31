// A stand-in for the backend, so the page can be built, tested and shown on GitHub Pages with no model running.
// It answers the same calls the real backend will (fill, judge, style_fit, plan, generate, status) (see "The backend contract" in logic.js) in the same shapes,
// so the page cannot tell the difference. It writes no story: its answers are plain samples that are valid for the
// schema, which is enough to see every state the page has to handle.
//
//   const mock = createMock(schema, { delay: 700 });
//   const reply = await mock.send(request, { signal });   // like fetch: resolves with the reply, rejects on abort
//
// Making it misbehave, so each failure can be seen and tested:
//   mock.queue("busy", "bad_output")  the next calls (not status checks) fail in this order, then it behaves again
//   mock.queue("unreachable")         nothing answers: rejects like a network error
//   mock.queue("timeout")             never answers; only an abort ends it
//   other kinds ("too_long", "server", "stopped", "unauthorized") come back as that error
// Writing "FLAG ME" in a card makes the judge and the style-fit check complain about it, so the writer can see a
// model's warning appear on demand.

import { isVisible, failure } from "./logic.js";

export const MOCK_FLAG = "FLAG ME";

// A name for a link, taken from the cards the request carries. `sources` are like "characters" or "world.powers".
function linkNames(related, sources) {
  const names = [];
  for (const source of sources) {
    const [cardId, key] = source.split(".");
    const held = related[cardId];
    const list = key ? held?.[key] : held;
    for (const entry of Array.isArray(list) ? list : []) {
      const name = entry.name ?? entry.statement ?? entry.term;
      if (typeof name === "string" && name.trim()) names.push(name.trim());
    }
  }
  return names;
}

// One sample value for a field, or undefined when there is nothing sensible to put (a link with nothing to link to).
function sampleValue(field, related, nth, taken = new Set()) {
  if (field.ref) {
    const names = linkNames(related, field.ref);
    if (!names.length) return undefined;
    if (field.input === "select-multiple") {
      // Several lists of the same people in one item must not share a name.
      const free = names.filter((n) => !taken.has(n)).slice(0, 2);
      free.forEach((n) => taken.add(n));
      return free.length ? free : undefined;
    }
    return names[nth % names.length];
  }
  if (field.options?.length) {
    const option = field.options[nth % field.options.length].value;
    return field.input === "select-multiple" ? [option] : option;
  }
  if (field.input === "number") return field.key === "chapter_count" ? 8 : 34;
  if (field.input === "checkbox") return undefined;
  return `Sample ${(field.label ?? field.key).toLowerCase()}.`;
}

// A set of fields filled in order. A field that is hidden by an earlier answer is skipped, and only the first half
// of an either-or pair gets a value, so the sample never breaks the card's own shape rules.
function sampleFields(owner, fields, related, nth) {
  const values = {};
  const taken = new Set();
  let links = 0;   // each link in a set points at the next name along, so a tie never joins someone to themselves
  for (const field of fields) {
    const second = (owner.one_of ?? []).some((group) => group.fields.indexOf(field.key) > 0);
    if (second || !isVisible(field, values)) continue;
    if (field.repeat) {
      const defs = field.item_fields ?? [];
      const item = sampleFields(field, defs, related, nth);
      // An item that needs a link the project cannot give (no rules yet, say) is left out rather than half made.
      if (defs.some((d) => d.ref && d.required !== false && item[d.key] === undefined)) continue;
      // Nor one that would point two of its own links at the same thing (a tie from someone to themselves).
      const picked = defs.filter((d) => d.ref && d.input !== "select-multiple" && item[d.key] !== undefined).map((d) => item[d.key]);
      if (new Set(picked).size < picked.length) continue;
      values[field.key] = [item];
      continue;
    }
    const value = sampleValue(field, related, field.ref ? nth + links++ : nth, taken);
    if (value !== undefined) values[field.key] = value;
  }
  return values;
}

export function createMock(schema, options = {}) {
  const { delay = 700 } = options;
  const upcoming = [];
  let working = 0;
  let served = 0;
  let stage = null;     // what a busy mock says it is doing, like a real backend answering status

  // Resolve after `ms`, or reject the way fetch does when the writer presses Stop.
  function wait(ms, signal) {
    return new Promise((resolve, reject) => {
      const aborted = () => reject(Object.assign(new Error("The request was stopped."), { name: "AbortError" }));
      if (signal?.aborted) return aborted();
      const timer = ms === Infinity ? null : setTimeout(() => { signal?.removeEventListener("abort", onAbort); resolve(); }, ms);
      const onAbort = () => { clearTimeout(timer); aborted(); };
      signal?.addEventListener("abort", onAbort, { once: true });
    });
  }

  const fill = (request, nth) => {
    const card = schema.cards[request.card];
    if (!card) return failure("bad_request", `No card called ${request.card}.`);
    const values = sampleFields(card, card.fields, request.related ?? {}, nth);
    if (request.card === "characters" && request.instance) values.name = `Mock character ${nth + 1}`;
    return { ok: true, values };
  };

  // ---- The story calls: plain samples that are valid for the shapes ----
  const AIMS = ["find who took the ledger", "get past the harbour clerk", "keep a promise to an old friend", "reach the island before the tide", "burn the evidence", "ask forgiveness",
    "cross the border unseen", "win back the shop", "learn what the letter says", "stand up to the board"];

  const plan = (request) => {
    const place = (request.world?.places ?? [])[0]?.name;
    const tie = (request.ties ?? []).find((t) => t.id === request.spotlight);
    const beat = {
      when_time: `Mock time ${request.chapter}`,
      aim: `Mock aim: ${AIMS[(request.chapter - 1) % AIMS.length]}`,
      plan: `Mock plan for chapter ${request.chapter}${tie ? `, about ${tie.bond}` : ""}.`,
    };
    if (place) beat.where = place;
    return { ok: true, beat };
  };

  const generate = (request) => {
    const beat = request.beat ?? {};
    const who = (request.cast ?? [])[0];
    return {
      ok: true,
      chapter_text: `Mock chapter ${request.chapter} of ${request.chapter_count}. ${beat.aim ?? ""}`.trim(),
      events: { happened: `Mock events of chapter ${request.chapter}.`, changed: "Mock change." },
      shifts: who ? [{ card: "characters", target: who.id, patch: { fear: `Mock fear after chapter ${request.chapter}` } }] : [],
    };
  };

  const judge = (request) => {
    const card = schema.cards[request.card];
    if (!card) return failure("bad_request", `No card called ${request.card}.`);
    const results = (request.rules ?? []).map((rule) => {
      const hits = [];
      for (const key of rule.fields ?? []) {
        const value = request.values?.[key];
        const flagged = (v) => JSON.stringify(v ?? "").includes(MOCK_FLAG);
        if (Array.isArray(value)) {
          for (const item of value) if (flagged(item)) hits.push({ field: key, item: item.id });
        } else if (flagged(value)) {
          hits.push({ field: key });
        }
      }
      return { rule: rule.id, hits };
    });
    return { ok: true, results };
  };

  const styleFit = (request) => {
    const flagged = JSON.stringify(request.protagonist ?? "").includes(MOCK_FLAG);
    return flagged
      ? { ok: true, fits: false, message: "This is a mock answer: the protagonist's personality is flagged, so the chosen voice may not suit them." }
      : { ok: true, fits: true, message: "" };
  };

  // What a bad output looks like for each call: the envelope is fine, the content is not.
  const garbled = (call) => (call === "fill" ? { ok: true, values: ["not", "a", "card"] }
    : call === "judge" ? { ok: true, results: "none" }
    : call === "plan" ? { ok: true, beat: "not a beat" }
    : call === "generate" ? { ok: true, chapter_text: "", events: {}, shifts: [] } : { ok: true, fits: "maybe" });

  // The stages a story call goes through, so status can say where it is: {name, index, of}. Each takes an equal share of the delay.
  const STAGES_OF = { plan: ["think", "beat"], generate: ["write", "events", "shifts"] };
  async function through(call, signal, retrying) {
    const list = retrying && call === "plan" ? ["retry", "beat"] : STAGES_OF[call] ?? [];
    if (!list.length) return wait(delay, signal);
    for (const [i, name] of list.entries()) { stage = { name, index: i + 1, of: list.length }; await wait(delay / list.length, signal); }
  }

  async function send(request, { signal } = {}) {
    if (request?.call === "status") return working ? { ok: true, state: "busy", ...(stage ? { stage } : {}) } : { ok: true, state: "idle" };
    const scripted = upcoming.shift();
    working += 1;
    try {
      if (scripted === "unreachable") {
        await wait(Math.min(delay, 300), signal);
        throw new TypeError("Failed to fetch");
      }
      if (scripted === "timeout") await wait(Infinity, signal);
      await through(request?.call, signal, Boolean(request?.retry));
      const nth = served;
      served += 1;
      if (scripted === "bad_output") return garbled(request.call);
      if (scripted) return failure(scripted, `This is a mock ${scripted} answer.`);
      switch (request.call) {
        case "fill": return fill(request, nth);
        case "judge": return judge(request);
        case "style_fit": return styleFit(request);
        case "plan": return plan(request);
        case "generate": return generate(request);
        default: return failure("bad_request", `The mock does not know the call ${request?.call}.`);
      }
    } finally {
      working -= 1;
      if (!working) stage = null;
    }
  }

  return {
    send,
    queue: (...kinds) => { upcoming.push(...kinds); },
    get busy() { return working > 0; },
  };
}
