/* Pulpermill page: Importing card files into a chapter page. */
async function importFiles(files) {
  const pg = cur(),
    j = st.story.cur,
    warn = [],
    items = [];
  if (st.busy) return;
  /* the backend's limits (it sends them with /limits), checked here first so a file that is too big gets a plain sentence, not an HTTP error */
  const maxChars = (st.limits && st.limits.max_import_json) || 1000000,
    maxFiles = (st.limits && st.limits.max_import_files) || 100;
  files = [...files];
  if (files.length > maxFiles) {
    warn.push(
      mk("Too many files: only the first {max} of {n} were read.", {
        max: maxFiles,
        n: files.length,
      }),
    );
    files = files.slice(0, maxFiles);
  }
  for (const f of files) {
    let text;
    try {
      text = await f.text();
    } catch (e) {
      warn.push(
        mk("{name}: could not be read ({why})", {
          name: f.name,
          why: e.message,
        }),
      );
      continue;
    }
    let data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      warn.push(
        mk("{name}: is not valid JSON ({why})", {
          name: f.name,
          why: e.message,
        }),
      );
      continue;
    }
    const size = JSON.stringify(data).length;
    if (size > maxChars) {
      warn.push(
        mk(
          "{name}: is too large to import ({size} KB; the limit is {max} KB).",
          {
            name: f.name,
            size: Math.ceil(size / 1000).toLocaleString(),
            max: Math.floor(maxChars / 1000).toLocaleString(),
          },
        ),
      );
      continue;
    }
    items.push({ name: String(f.name).slice(0, 300), data });
  }
  let res = { cards: {}, imported: [], warnings: [], checks: [] };
  if (items.length) {
    try {
      res = await api("/import", {
        method: "POST",
        body: JSON.stringify({ items, existing: cleanCards(pg.cards) }),
      });
    } catch (e) {
      warn.push(
        mk(
          "The backend could not check these cards, so nothing was imported ({why}). Test the connection and try again.",
          { why: e.m || e.message },
        ),
      );
    }
  }
  const undo = clone(pg.cards),
    got = res.cards || {};
  Object.keys(got).forEach((k) => {
    if (CARD_KEYS.includes(k)) {
      pg.cards[k] = got[k];
      delete pg.stale[k];
      delete pg.err[k];
      delete pg.warn[k];
    }
  });
  st.report = {
    idx: j,
    imported: res.imported || [],
    warn: warn.concat(res.warnings || []),
    checks: res.checks || [],
    undo: Object.keys(got).length ? undo : null,
  };
  draw();
}
function reportNode() {
  const r = st.report;
  if (!r || r.idx !== st.story.cur) return null;
  const box = el("div", { class: "pending", role: "status" });
  box.append(
    r.imported.length
      ? el(
          "div",
          { class: "msg ok" },
          t("Imported: {items}.", { items: r.imported }),
        )
      : el("div", { class: "msg warn" }, t("Nothing was imported.")),
  );
  if (r.warn.length)
    box.append(
      el(
        "div",
        { class: "msg warn" },
        t("Not imported or changed:"),
        el(
          "ul",
          {},
          r.warn.map((w) => el("li", {}, msg(w))),
        ),
      ),
    );
  if (r.checks.length)
    box.append(
      el(
        "div",
        { class: "msg warn" },
        t("Consistency notes on the cards now on this page:"),
        el(
          "ul",
          {},
          r.checks.map((w) => el("li", {}, msg(w))),
        ),
      ),
    );
  box.append(
    el(
      "div",
      { class: "row" },
      r.undo
        ? el(
            "button",
            {
              class: "sm",
              onclick: () => {
                cur().cards = r.undo;
                st.report = null;
                draw();
              },
            },
            t("Undo this import"),
          )
        : null,
      el(
        "button",
        {
          class: "sm",
          onclick: () => {
            st.report = null;
            draw();
          },
        },
        t("Dismiss"),
      ),
    ),
  );
  return box;
}
