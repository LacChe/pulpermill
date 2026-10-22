// A stand-in for the backend, so the page can be built, tested and shown on GitHub Pages with no model running.
// It answers the same four calls the real backend will (see "The backend contract" in logic.js) in the same shapes,
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
//   other kinds ("too_long", "server", "stopped") come back as that error
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
function sampleValue(field, related, nth) {
  if (field.ref) {
    const names = linkNames(related, field.ref);
    if (!names.length) return undefined;
    if (field.input === "select-multiple") return names.slice(0, 2);
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
  let links = 0;   // each link in a set points at the next name along, so a tie never joins someone to themselves
  for (const field of fields) {
    const second = (owner.one_of ?? []).some((group) => group.fields.indexOf(field.key) > 0);
    if (second || !isVisible(field, values)) continue;
    if (field.repeat) {
      const defs = field.item_fields ?? [];
      const item = sampleFields(field, defs, related, nth);
      // An item that needs a link the project cannot give (no rules yet, say) is left out rather than half made.
      if (defs.some((d) => d.ref && d.required !== false && item[d.key] === undefined)) continue;
      values[field.key] = [item];
      continue;
    }
    const value = sampleValue(field, related, field.ref ? nth + links++ : nth);
    if (value !== undefined) values[field.key] = value;
  }
  return values;
}

export function createMock(schema, options = {}) {
  const { delay = 700 } = options;
  const upcoming = [];
  let working = 0;
  let served = 0;

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
    : call === "judge" ? { ok: true, results: "none" } : { ok: true, fits: "maybe" });

  async function send(request, { signal } = {}) {
    if (request?.call === "status") return { ok: true, state: working ? "busy" : "idle" };
    const scripted = upcoming.shift();
    working += 1;
    try {
      if (scripted === "unreachable") {
        await wait(Math.min(delay, 300), signal);
        throw new TypeError("Failed to fetch");
      }
      if (scripted === "timeout") await wait(Infinity, signal);
      await wait(delay, signal);
      const nth = served;
      served += 1;
      if (scripted === "bad_output") return garbled(request.call);
      if (scripted) return failure(scripted, `This is a mock ${scripted} answer.`);
      switch (request.call) {
        case "fill": return fill(request, nth);
        case "judge": return judge(request);
        case "style_fit": return styleFit(request);
        default: return failure("bad_request", `The mock does not know the call ${request?.call}.`);
      }
    } finally {
      working -= 1;
    }
  }

  return {
    send,
    queue: (...kinds) => { upcoming.push(...kinds); },
    get busy() { return working > 0; },
  };
}
