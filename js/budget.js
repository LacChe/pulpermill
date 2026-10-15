/* Pulpermill page: Length limits: token estimates and the counters under the text boxes. */
/* ---------- length limits ----------
   The backend gives limits in tokens. Han characters cost about one token each and other text about 3.5 characters, so the
   limit shown in characters depends on what is being typed. */
const cjkRe = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/g;
const cpt = () => (st.limits ? st.limits.chars_per_token : 3.5);
const tokensEst = (s) => {
  s = String(s || "");
  const n = (s.match(cjkRe) || []).length;
  return n + (s.length - n) / cpt();
};
const strings = (o) =>
  typeof o === "string"
    ? o
    : Array.isArray(o)
      ? o.map(strings).join(" ")
      : o && typeof o === "object"
        ? Object.values(o).map(strings).join(" ")
        : "";
function priorTokens(k) {
  const c = st.cards;
  if (k === "style") return 0;
  if (k === "characters")
    return c.style
      ? tokensEst(
          [c.style.narrator, c.style.diction].join(" "),
        ) + 60
      : 90;
  const cast = c.characters
    ? tokensEst(
        c.characters
          .map(
            (x) => (x.id || "") + " " + (x.name || "") + " " + (x.role || ""),
          )
          .join(" "),
      ) +
      3 * c.characters.length
    : 170;
  if (k === "world") return cast;
  const w = c.world;
  return (
    cast +
    (w
      ? tokensEst(strings([w.locations, w.rules, w.hidden_truths, w.groups])) +
        8
      : 700)
  );
}
function budgetTokens(k) {
  const L = st.limits;
  if (!L) return null;
  const s = L.stages[k];
  return Math.max(
    0,
    L.n_ctx - s.out - s.fixed - L.retry_reserve - priorTokens(k),
  );
}
/* the same limit as a number of characters, for text that looks like `sample` */
function limitChars(tokens, sample) {
  const s = String(sample || "");
  return Math.floor(
    tokens * (s.length > 20 ? s.length / Math.max(1, tokensEst(s)) : cpt()),
  );
}
/* the example chapter's text as far as card k is concerned: nothing when it is switched off for that card */
const usesExample = (k) => {
  const pg = cur();
  return !pg.useEx || pg.useEx[k] !== false;
};
const chText = (k) => (usesExample(k) ? cur().chapter || "" : "");
const over = (k) => {
  const b = budgetTokens(k);
  return b != null && tokensEst(chText(k) + " " + (st.notes[k] || "")) > b;
};
function setCount(n, len, limit) {
  n.textContent =
    limit == null
      ? t("{n} characters (test the connection to see the limit)", {
          n: len.toLocaleString(),
        })
      : t("{n} / {limit} characters (about {w} words)", {
          n: len.toLocaleString(),
          limit: limit.toLocaleString(),
          w: Math.round(len / 6).toLocaleString(),
        });
  n.className =
    "count" +
    (n.dataset.k ? " nc" : "") +
    (limit != null && len > limit
      ? " over"
      : limit != null && len > limit * 0.9
        ? " warn"
        : "");
}
function updateCounters() {
  const L = st.limits,
    cc = $("#chcount"),
    ch = cur().chapter;
  const using = STAGES.filter((s) => usesExample(s.k)),
    pool = using.length ? using : STAGES; // the tightest of the cards that use it
  if (cc)
    setCount(
      cc,
      ch.length,
      L
        ? limitChars(Math.min(...pool.map((s) => budgetTokens(s.k))), ch)
        : null,
    );
  STAGES.forEach((s) => {
    const n = document.querySelector('.nc[data-k="' + s.k + '"]');
    const notes = st.notes[s.k] || "";
    if (n) {
      const b = budgetTokens(s.k);
      setCount(
        n,
        notes.length,
        b == null
          ? null
          : limitChars(Math.max(0, b - tokensEst(chText(s.k))), notes),
      );
    }
    document.querySelectorAll('.gen[data-k="' + s.k + '"]').forEach((x) => {
      x.disabled = x.dataset.lock === "1" || over(s.k);
    });
  });
}
