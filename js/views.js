/* Pulpermill page: Drawing: navigation, cards, story, top bar, redraw that keeps the caret and scroll position. */
function inline(text) {
  const out = [],
    re = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g;
  let last = 0,
    m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const s = m[0];
    out.push(
      s.startsWith("**")
        ? el("strong", {}, s.slice(2, -2))
        : el("em", {}, s.slice(1, -1)),
    );
    last = m.index + s.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
function prose(text) {
  const box = el("div", { class: "prose" });
  String(text)
    .split(/\n{2,}/)
    .forEach((p) => {
      if (p.trim()) box.append(el("p", {}, inline(p.trim())));
    });
  return box;
}

function navSub(pg, j) {
  const S = st.story;
  if (S.job && S.job.j === j && st.busy === "chapter") return t("Writing…");
  if (pg.result)
    return (
      pg.result.words.toLocaleString() +
      " " +
      unitWord() +
      (resStale(j) ? t(" · out of date") : "")
    );
  return haveCards() && (j === 0 || chapters()[j - 1].result)
    ? t("Ready to write")
    : j === 0
      ? t("Setting up the cards")
      : haveCards()
        ? t("Write chapter {j} first.", { j })
        : t("Ready");
}
function goPage(j) {
  st.story.cur = j;
  st.report = null;
  st.armed = false;
  st.ask = null;
  draw(false);
  const r = $("#right");
  if (r) r.scrollTop = 0;
  try {
    window.scrollTo(0, 0);
  } catch (e) {
    /* no scrolling here (e.g. a test page); nothing depends on it */
  }
}
function drawNav() {
  const nav = $("#nav"),
    S = st.story;
  [...nav.children].forEach((c) => {
    if (!c.classList.contains("storyname")) c.remove();
  });
  nav.append(el("h2", {}, t("Chapters")));
  const ol = el("ol", { class: "navlist" });
  S.chapters.forEach((pg, j) =>
    ol.append(
      el(
        "li",
        {},
        el(
          "button",
          {
            type: "button",
            class: "navbtn",
            "aria-current": j === S.cur ? "page" : false,
            onclick: () => goPage(j),
          },
          el("b", {}, pageName(j)),
          el("span", { class: "navsub" }, navSub(pg, j)),
        ),
      ),
    ),
  );
  nav.append(ol);
  const foot = el("div", { class: "navfoot" });
  foot.append(
    el(
      "button",
      {
        id: "exportstory",
        class: "alt",
        disabled: !chapters().some((p) => p.result),
        onclick: exportStory,
      },
      t("Export story (.md)"),
    ),
  );
  foot.append(
    el(
      "button",
      {
        id: "saveproj",
        class: "alt",
        onclick: () =>
          downloadText(
            storyFile() + "_project.json",
            projectFile(),
            "application/json",
          ),
      },
      t("Save project"),
    ),
    el(
      "button",
      {
        id: "loadproj",
        class: "alt",
        disabled: !!st.busy,
        onclick: () => $("#projfile").click(),
      },
      t("Load project"),
    ),
  );
  if (!st.armed)
    foot.append(
      el(
        "button",
        {
          id: "reset",
          class: "danger",
          disabled: !!st.busy,
          onclick: () => {
            st.armed = true;
            drawNav();
          },
        },
        t("Reset everything…"),
      ),
    );
  else
    foot.append(
      el(
        "div",
        {
          class: "guard",
          role: "alertdialog",
          "aria-label": t("Confirm reset"),
        },
        el(
          "p",
          { class: "hint" },
          t(
            "This erases every card, note and chapter in this browser. Save the project first if you want to keep it.",
          ),
        ),
        el(
          "div",
          { class: "row" },
          el(
            "button",
            {
              id: "resetno",
              class: "alt",
              onclick: () => {
                st.armed = false;
                drawNav();
              },
            },
            t("Cancel"),
          ),
          el(
            "button",
            { id: "resetyes", class: "danger solid", onclick: resetAll },
            t("Erase everything"),
          ),
        ),
      ),
    );
  nav.append(foot);
}
function resetAll() {
  if (st.busy) return;
  st.story = newStory();
  st.report = null;
  st.armed = false;
  st.ask = null;
  st.banner = "";
  $("#slug").value = "";
  save("slug", "");
  draw(false);
  saveProject();
}

function inputSection(pg) {
  const sec = el("section", { class: "box", id: "examplebox" });
  /* the section folds away; the choice is kept in the browser, so it survives redraws and reloads */
  const body = el("div", { class: "exbody" });
  const tog = el(
    "button",
    { type: "button", class: "exhead", "aria-controls": "exbody" },
    el("span", { class: "chev", "aria-hidden": "true" }),
    el("h2", {}, t("Example chapter (optional)")),
  );
  body.id = "exbody";
  const fold = (c) => {
    body.hidden = c;
    sec.classList.toggle("closed", c);
    tog.setAttribute("aria-expanded", String(!c));
  };
  fold(load("exfold") === "1");
  tog.addEventListener("click", () => {
    const c = !body.hidden;
    fold(c);
    save("exfold", c ? "1" : "0");
  });
  sec.append(el("div", { class: "head" }, tog));
  body.append(
    el(
      "p",
      { class: "hint", id: "modehint" },
      t(
        "Paste a chapter from any story to give the model something to work from. Each card below has its own switch for using it. The limit shown is the tightest of the cards that use it, and the chapter counts against each of their limits.",
      ),
    ),
  );
  const ta = el("textarea", {
    id: "chapter",
    rows: 10,
    placeholder: t("Paste one chapter here."),
    "aria-label": t("Example chapter"),
  });
  ta.value = st.story.chapter;
  ta.addEventListener("input", () => {
    st.story.chapter = ta.value;
    updateCounters();
  });
  body.append(ta, el("div", { class: "count", id: "chcount" }));
  /* what the example is for: one choice */
  const fs = el(
    "fieldset",
    { class: "uses", id: "exuses" },
    el("legend", {}, t("What is the example for?")),
  );
  EXAMPLE_USES.forEach((u) => {
    const rb = el("input", {
      type: "radio",
      name: "exuse",
      id: "use-" + (u.k || "same"),
      value: u.k,
    });
    rb.checked = (st.story.use || "") === u.k;
    rb.addEventListener("change", () => {
      if (rb.checked) {
        st.story.use = u.k;
        draw();
      }
    });
    fs.append(
      el(
        "label",
        { class: "chk" },
        rb,
        el("span", { class: "usename" }, t(u.t)),
        el("span", { class: "ro" }, " — " + t(u.d)),
      ),
    );
  });
  body.append(fs);
  sec.append(body);
  return sec;
}
/* ---------- one tab per card ----------
   Only the open card is drawn, so the page is never one long column of four cards. Which card is open is remembered per
   story and not saved with the project. Until someone picks one it is the first card not made yet (Style once all four exist),
   and generate.js moves on to the next tab after a card is first made. */
const ACTIVE_STAGE = new WeakMap();
const firstUnmade = () => {
  const i = STAGES.findIndex((s) => !st.story.cards[s.k]);
  return i < 0 ? 0 : i;
};
function activeStage() {
  const i = ACTIVE_STAGE.get(st.story);
  return Number.isInteger(i) && i >= 0 && i < STAGES.length
    ? i
    : firstUnmade();
}
function openStage(i) {
  ACTIVE_STAGE.set(st.story, i);
  draw();
  const b = document.querySelector('#mid .tabs [aria-selected="true"]');
  if (b) b.focus(); // a redraw drops focus; keep it on the tabs so the arrow keys keep working
}
function stageTabs(act) {
  const bar = el("div", {
      class: "tabs",
      role: "tablist",
      "aria-label": t("Cards"),
    }),
    n = STAGES.length;
  STAGES.forEach((s, i) => {
    const done = !!st.story.cards[s.k],
      on = i === act,
      busy = st.busy === s.k;
    const say =
      t(s.t) +
      (done ? " — " + t("complete") : "") +
      (busy ? " — " + t("generating") : "");
    bar.append(
      el(
        "button",
        {
          type: "button",
          role: "tab",
          id: "tab-" + s.k,
          class:
            "tab" +
            (on ? " on" : "") +
            (done ? " done" : "") +
            (busy ? " busy" : ""),
          "data-k": s.k,
          "aria-selected": String(on),
          "aria-controls": "panel-" + s.k,
          "aria-label": say,
          title: say,
          tabindex: on ? "0" : "-1",
          onclick: () => openStage(i),
          onkeydown: (ev) => {
            const to =
              ev.key === "ArrowRight"
                ? (i + 1) % n
                : ev.key === "ArrowLeft"
                  ? (i + n - 1) % n
                  : ev.key === "Home"
                    ? 0
                    : ev.key === "End"
                      ? n - 1
                      : null;
            if (to != null) {
              ev.preventDefault();
              openStage(to);
            }
          },
        },
        el(
          "span",
          { class: "tabmark", "aria-hidden": "true" },
          busy ? "…" : done ? "✓" : "",
        ),
        el("span", { class: "tablabel" }, t(s.t)),
      ),
    );
  });
  return bar;
}
function drawStages(root) {
  const hide = SCH.hidden || [],
    act = activeStage();
  refContext(st.story.cards);
  root.append(stageTabs(act));
  STAGES.forEach((s, i) => {
    if (i !== act) return;
    const has = !!st.story.cards[s.k],
      prev = i === 0 || !!st.story.cards[STAGES[i - 1].k],
      busy = st.busy === s.k;
    const sec = el("section", {
      class: "box stage" + (has ? " done" : "") + (!prev ? " locked" : ""),
      "data-card": s.k,
      role: "tabpanel",
      id: "panel-" + s.k,
      "aria-labelledby": "tab-" + s.k,
    });
    const tags = el("span", { class: "tags" });
    if (st.story.stale[s.k])
      tags.append(
        el(
          "span",
          { class: "tag stale" },
          t("Built from an earlier version of a previous card"),
        ),
      );
    else if (has)
      tags.append(
        el(
          "span",
          { class: "tag" },
          t("Ready to check"),
        ),
      );
    if (s.k === "style" && narratorStale())
      tags.append(
        el("span", { class: "tag stale" }, t("Narrator written from earlier style settings")),
      );
    const broken = has ? scanRefs(st.story.cards[s.k], [s.k], []) : [];
    if (broken.length)
      tags.append(
        el(
          "span",
          { class: "tag bad" },
          t("broken links: {n}", { n: broken.length }),
        ),
      );
    const extra =
      st.limits && s.k === "characters"
        ? " " +
          t(
            "A generation writes up to {n} characters. Add as many as you like and choose up to {m} for each chapter.",
            { n: st.limits.max_characters, m: st.limits.max_cast || 6 },
          )
        : st.limits && s.k === "outline"
          ? " " + t("Up to {n} chapters.", { n: st.limits.max_chapters })
          : "";
    const cardBtns = el(
      "span",
      { class: "row", style: "margin:0" },
      el(
        "button",
        {
          class: "sm",
          disabled: !!st.busy,
          title: t("Import this card"),
          onclick: () => $("#importfile").click(),
        },
        t("Import card"),
      ),
      s.k === "characters"
        ? null
        : el(
            "button",
            {
              class: "sm",
              disabled: !has,
              title: t("Export this card"),
              onclick: () => exportSingleCard(s.k),
            },
            t("Export card"),
          ),
    );
    sec.append(
      el("div", { class: "head" }, el("h2", {}, t(s.t)), tags, cardBtns),
      el("p", { class: "hint" }, t(s.d) + extra),
    );
    const usingEx = usesExample(s.k) && !!st.story.chapter.trim();
    if (st.story.cur === 0) {
      const cb = el("input", {
        type: "checkbox",
        id: "ex-" + s.k,
        "data-k": s.k,
      });
      cb.checked = usesExample(s.k);
      cb.addEventListener("change", () => {
        st.story.useEx[s.k] = cb.checked;
        draw();
      });
      sec.append(
        el(
          "label",
          { class: "chk useex" },
          cb,
          el("span", {}, t("Use the example chapter for this card")),
          st.story.chapter.trim()
            ? null
            : el(
                "span",
                { class: "ro" },
                " " + t("(paste an example chapter above first)"),
              ),
        ),
      );
    }
    const nt = el("textarea", {
      rows: has ? 3 : 5,
      placeholder: usingEx
        ? t(
            "Optional extra direction for this card. Leave blank to infer it all from the chapter.",
          )
        : t(HINTS[s.k]),
      "aria-label": t("{card} notes", { card: t(s.t) }),
    });
    nt.value = st.story.notes[s.k] || "";
    nt.addEventListener("input", () => {
      st.story.notes[s.k] = nt.value;
      updateCounters();
    });
    const notesOpen =
      st.story.notesOpen && s.k in st.story.notesOpen
        ? st.story.notesOpen[s.k]
        : !has;
    const det = el(
      "details",
      { class: "notes", open: notesOpen ? "open" : false },
      el("summary", {}, t("Your notes for this card")),
      nt,
      el("div", { class: "count nc", "data-k": s.k }),
    );
    det.addEventListener("toggle", () => {
      st.story.notesOpen[s.k] = det.open;
      scheduleSave();
    });
    sec.append(det);
    if (st.story.err[s.k])
      sec.append(
        el("div", { class: "msg err", role: "alert" }, msg(st.story.err[s.k])),
      );
    if (!has) {
      sec.append(
        el(
          "button",
          {
            class: "go gen",
            "data-k": s.k,
            "data-lock": !prev || st.busy ? "1" : "0",
            disabled: !prev || !!st.busy,
            onclick: () => generate(i),
          },
          busy
            ? [t("Generating…"), el("span", { class: "timer" })]
            : [
                t("Generate {what}", { what: t(s.t).toLowerCase() }),
                tookTag(st.story.took && st.story.took[s.k]),
              ],
        ),
      );
      if (!prev)
        sec.append(
          el(
            "span",
            { class: "ro" },
            "  " +
              t("Generate {what} first.", {
                what: t(STAGES[i - 1].t).toLowerCase(),
              }),
          ),
        );
    } else {
      const w = st.story.warn[s.k] || [];
      if (w.length)
        sec.append(
          el(
            "div",
            { class: "msg warn" },
            t("Check these:"),
            el(
              "ul",
              {},
              w.map((x) => el("li", {}, msg(x))),
            ),
          ),
        );
      if (broken.length)
        sec.append(
          el(
            "div",
            { class: "msg err", role: "alert" },
            t("These fields point at something that no longer exists:"),
            el(
              "ul",
              {},
              broken.map((b) => el("li", {}, brokenLine(b))),
            ),
          ),
        );
      FLAGS = flagsOf(st.story.warn[s.k]);
      try {
        sec.append(
          withHide(hide, () =>
            editor(st.story.cards[s.k], (SCH.enums || {})[s.k], undefined, s.k),
          ),
        );
      } finally {
        FLAGS = [];
      }
      const fb = el("textarea", {
        rows: 1,
        class: "fbnote",
        placeholder: t("What should change? (optional)"),
        "aria-label": t("Note for regeneration"),
      });
      const grow = () => {
        fb.style.height = "auto";
        fb.style.height = Math.min(fb.scrollHeight + 2, 320) + "px";
      };
      fb.value = st.story.cardDraft[s.k] || "";
      if (fb.value) setTimeout(grow, 0);
      fb.addEventListener("input", () => {
        st.story.cardDraft[s.k] = fb.value;
        grow();
      });
      sec.append(
        el(
          "div",
          { class: "rerun" },
          fb,
          el(
            "button",
            {
              class: "gen alt",
              "data-k": s.k,
              "data-lock": st.busy ? "1" : "0",
              disabled: !!st.busy,
              onclick: () => generate(i, fb.value.trim()),
            },
            busy
              ? [t("Generating…"), el("span", { class: "timer" })]
              : [
                  t("Regenerate with note"),
                  tookTag(st.story.took && st.story.took[s.k]),
                ],
          ),
          el(
            "button",
            {
              class: "danger clr",
              "data-k": s.k,
              disabled: !!st.busy,
              title: t(
                "Remove this card so it can be generated again from scratch. Your notes stay.",
              ),
              onclick: () => clearCard(i),
            },
            t("Clear card"),
          ),
        ),
      );
    }
    if (busy) sec.append(progBlock(true));
    root.append(sec);
  });
}
function askNode(j) {
  const k = j + 1;
  const box = el("div", {
    class: "pending",
    role: "alertdialog",
    "aria-label": t("Confirm rewrite"),
  });
  const note = (st.ask && st.ask.note) || "";
  box.append(
    el(
      "p",
      {},
      note
        ? t(
            "Rewrite chapter {k} with your note? The new version replaces this one.",
            { k },
          )
        : t("Rewrite chapter {k}? The new version replaces this one.", { k }),
    ),
  );
  if (note)
    box.append(
      el("p", { class: "hint asknote" }, t("Your note: {note}", { note })),
    );
  const cancel = el(
    "button",
    {
      id: "askno",
      class: "alt",
      onclick: () => {
        st.ask = null;
        draw();
      },
    },
    t("Cancel"),
  );
  box.append(
    el(
      "p",
      {},
      t(
        "Replacing adopts this generation's shared cards and overwrites future chapter beats. Keeping preserves the current cards and beats.",
      ),
    ),
  );
  box.append(
    el(
      "div",
      { class: "row" },
      el(
        "button",
        {
          id: "askreplace",
          class: "go",
          onclick: () => writeChapter("replace", note),
        },
        t("Rewrite and replace them"),
      ),
      el(
        "button",
        {
          id: "askkeep",
          class: "alt",
          onclick: () => writeChapter("keep", note),
        },
        t("Rewrite and keep them"),
      ),
      cancel,
    ),
  );
  return box;
}
/* the people this chapter is written about: tick up to the limit, the main character is fixed. The ticks follow the chapter's
   beat (who is present, who has an agenda) until the person changes them. */
/* people the beat names: present, agenda, or their name in the beat's own words */
function namedInBeat(b, chars) {
  if (!b) return new Set();
  const ids = new Set([...(b.present || []), ...(b.agendas || []).map((a) => a.character)]);
  const text = [b.opening, b.goal, b.obstacle, b.ends_on, b.turn, ...(b.events || [])]
    .join(" ")
    .toLowerCase();
  chars.forEach((c) => {
    const first = String(c.name || "").trim().split(/\s+/)[0].toLowerCase();
    if (/[\u3400-\u9fff]/.test(first) ? first.length >= 2 && text.includes(first) : first.length >= 3 && new RegExp("(^|[^\\p{L}])" + first.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "([^\\p{L}]|$)", "u").test(text))
      ids.add(c.id);
  });
  return ids;
}
function castBox(pg, j) {
  const k = j + 1,
    chars = st.story.cards.characters || [],
    lead = leadOf(),
    sel = castFor(pg, k),
    max = maxCast(),
    b = beatOf(k),
    inBeat = [...namedInBeat(b, chars)];
  const box = el(
    "div",
    { class: "castbox", id: "castbox" },
    el("div", { class: "lab" }, t("Characters in this chapter")),
    el(
      "p",
      { class: "hint" },
      t(
        "Choose up to {n}. The model only writes about these people, and the main character is always one of them.",
        { n: max },
      ),
    ),
  );
  const list = el("div", { class: "castlist" });
  chars.forEach((c) => {
    const on = sel.includes(c.id),
      isLead = c.id === lead,
      full = !on && sel.length >= max;
    const cb = el("input", {
      type: "checkbox",
      id: "cast-" + c.id,
      value: c.id,
    });
    cb.checked = on;
    cb.disabled = isLead || full || !!st.busy;
    cb.addEventListener("change", () => {
      pg.cast = cb.checked ? [...sel, c.id] : sel.filter((i) => i !== c.id);
      draw();
    });
    list.append(
      el(
        "label",
        { class: "chk" + (full ? " off" : "") },
        cb,
        el("span", { class: "castname" }, c.name || c.id),
        el(
          "span",
          { class: "ro" },
          (c.role ? " — " + c.role : "") +
            (isLead ? " · " + t("main character") : "") +
            (inBeat.includes(c.id) && !isLead && on
              ? " · " + t("in the chapter beat")
              : ""),
        ),
        !on && inBeat.includes(c.id)
          ? el(
              "span",
              { class: "castflag" },
              " · " +
                t("named in this chapter's plan, but not ticked, so they will not be written in"),
            )
          : null,
      ),
    );
  });
  box.append(
    list,
    el(
      "div",
      { class: "count", id: "castcount" },
      t("{n} of {max} chosen", { n: sel.length, max }),
    ),
  );
  if (Array.isArray(pg.cast) && inBeat.some((i) => !sel.includes(i)))
    box.append(
      el(
        "button",
        {
          class: "sm",
          type: "button",
          disabled: !!st.busy,
          onclick: () => {
            pg.cast = undefined;
            draw();
          },
        },
        t("Tick the people the chapter plan names"),
      ),
    );
  const left = ((b && b.present) || [])
    .filter((i) => !sel.includes(i))
    .map((i) => (chars.find((c) => c.id === i) || {}).name || i);
  if (left.length)
    box.append(
      el(
        "div",
        { class: "msg warn", id: "castwarn" },
        t(
          "The beat for this chapter includes {names}, who are not chosen. Writing will plan the beat again for the people you chose.",
          { names: left.join(", ") },
        ),
      ),
    );
  return box;
}
function drawMid() {
  const root = $("#mid"),
    S = st.story,
    j = S.cur,
    pg = cur(),
    k = j + 1,
    P = chapters(),
    prev = j > 0 ? P[j - 1] : null;
  root.innerHTML = "";
  const head = el("section", { class: "box" });
  head.append(
    el(
      "div",
      { class: "head" },
      el("h2", {}, t("Story cards")),
    ),
  );
  head.append(
    el(
      "p",
      { class: "hint" },
      t(
        "One shared set of cards for the whole story. The selected chapter determines which beat is used.",
      ),
    ),
  );
  if (j > 0 && resStale(j - 1))
    head.append(
      el(
        "div",
        { class: "msg warn" },
        t(
          "Chapter {j} is out of date because an earlier chapter was rewritten.",
          { j },
        ),
      ),
    );
  if (pg.msg)
    head.append(el("div", { class: "msg err", role: "alert" }, msg(pg.msg)));
  {
    const okWrite = haveCards() && (j === 0 || !!(prev && prev.result));
    const writing = st.busy === "chapter" && st.busyPg === pg;
    if (haveCards() && (st.story.cards.characters || []).length)
      head.append(castBox(pg, j));
    head.append(
      el(
        "div",
        { class: "row" },
        el(
          "button",
          {
            class: "go",
            id: "writebtn",
            disabled: !!st.busy || !okWrite,
            onclick: () => writeChapter(),
          },
          pg.result
            ? t("Rewrite chapter {k}", { k })
            : t("Write chapter {k}", { k }),
          pg.result && pg.result.secs != null ? tookTag(pg.result.secs) : null,
        ),
        el(
          "span",
          { class: "ro" },
          t(
            "The model keeps writing until the chapter reaches a natural ending.",
          ),
        ),
      ),
    );
    if (writing) {
      head.append(
        el(
          "div",
          { class: "hint chprog", "data-live": "1", role: "status" },
          t("Starting"),
        ),
      );
      head.append(progBlock(false));
    } // only on the page being written
    if (pg.result) {
      const fb = el("textarea", {
        rows: 1,
        class: "fbnote",
        id: "chnote",
        placeholder: t("What should change in this chapter? (optional)"),
        "aria-label": t("Note for rewriting the chapter"),
      });
      const grow = () => {
        fb.style.height = "auto";
        fb.style.height = Math.min(fb.scrollHeight + 2, 320) + "px";
      };
      pg.draft = pg.draft || {};
      fb.value = pg.draft.chapter || "";
      if (fb.value) setTimeout(grow, 0);
      fb.addEventListener("input", () => {
        pg.draft.chapter = fb.value;
        grow();
      });
      head.append(
        el(
          "div",
          { class: "rerun" },
          fb,
          el(
            "button",
            {
              class: "gen alt",
              id: "rewritenote",
              disabled: !!st.busy || !okWrite,
              onclick: () => writeChapter(undefined, fb.value.trim()),
            },
            t("Rewrite with note"),
            pg.result.secs != null ? tookTag(pg.result.secs) : null,
          ),
        ),
      );
    }
    const allBroken = brokenIn(st.story.cards);
    if (allBroken.length)
      head.append(
        el(
          "div",
          { class: "msg err", role: "alert" },
          t(
            "Broken links between cards ({n}). Fix the highlighted fields before writing.",
            { n: allBroken.length },
          ),
        ),
      );
    if (!okWrite)
      head.append(
        el(
          "p",
          { class: "hint" },
          j === 0
            ? t("Generate all four cards first.")
            : t("Write chapter {j} first.", { j }),
        ),
      );
    if (st.ask && st.ask.j === j && !st.busy) head.append(askNode(j));
    const beat = beatOf(k);
    if (beat) {
      const loc =
        (
          ((st.story.cards.world && st.story.cards.world.locations) || []).find(
            (l) => l.id === beat.location,
          ) || {}
        ).name || beat.location;
      head.append(
        el(
          "details",
          pg.result ? { class: "notes" } : { class: "notes", open: "open" },
          el("summary", {}, t("What chapter {k} has to cover", { k })),
          el(
            "p",
            { class: "hint" },
            t("Opens at {loc}, {when}. Events:", { loc, when: beat.when }),
          ),
          el(
            "ol",
            {},
            (beat.events || []).map((x) => el("li", {}, x)),
          ),
        ),
      );
    }
  }
  root.append(head);
  const rep = reportNode();
  if (rep) root.append(rep);
  if (j === 0) root.append(inputSection(pg));
  drawStages(root);
}

function drawRight() {
  const root = $("#right"),
    S = st.story,
    j = S.cur,
    pg = cur(),
    k = j + 1,
    r = pg.result;
  root.innerHTML = "";
  const tags = el("span", { class: "row", style: "margin:0" });
  if (r)
    tags.append(
      el("span", { class: "tag" }, r.words.toLocaleString() + " " + unitWord()),
    );
  if (resStale(j))
    tags.append(
      el(
        "span",
        { class: "tag stale" },
        t("Out of date: an earlier chapter was rewritten"),
      ),
    );
  if (narratorStale())
    tags.append(
      el("span", { class: "tag stale" }, t("Narrator written from earlier style settings")),
    );
  if (r && r.update_failed)
    tags.append(el("span", { class: "tag stale" }, t("Cards not updated")));
  root.append(
    el(
      "div",
      { class: "head" },
      el("h2", {}, t("Chapter {k} story", { k })),
      tags,
    ),
  );
  const writing = st.busy === "chapter" && st.busyPg === pg;
  if (writing && r)
    root.append(
      el(
        "p",
        { class: "hint" },
        t("The version below is replaced when this finishes."),
      ),
    ); // progress itself is shown beside the Write chapter button
  if (!r) {
    root.append(
      el(
        "p",
        { class: "hint" },
        t(
          "Chapter {k} has not been written yet. Once you write it, the story appears here.",
          { k },
        ),
      ),
    );
    return;
  }
  if (r.warnings.length)
    root.append(
      el(
        "div",
        { class: "msg warn" },
        t("Check these:"),
        el(
          "ul",
          {},
          r.warnings.map((w) => el("li", {}, msg(w))),
        ),
      ),
    );
  if (r.unintroduced.length)
    root.append(
      el(
        "div",
        { class: "msg warn" },
        t("Characters who appear without a card:"),
        el(
          "ul",
          {},
          r.unintroduced.map((u) =>
            el("li", {}, u.name + (u.role ? " (" + u.role + ")" : "")),
          ),
        ),
      ),
    );
  root.append(prose(r.text));
  root.append(
    el(
      "details",
      { class: "notes" },
      el(
        "summary",
        {},
        r.changes.length
          ? t("What this chapter changed in the cards")
          : t("This chapter changed nothing in the cards"),
      ),
      r.changes.length
        ? el(
            "ul",
            { class: "chg" },
            r.changes.map((x) =>
              el(
                "li",
                {},
                msg(x.text) +
                  (x.dropped && x.dropped.length
                    ? t(" (dropped from the card: {items})", {
                        items: x.dropped.join("; "),
                      })
                    : ""),
              ),
            ),
          )
        : null,
    ),
  );
  root.append(
    el(
      "div",
      { class: "row" },
      el(
        "button",
        {
          class: "sm",
          id: "dlchapter",
          onclick: () =>
            downloadText("chapter_" + pad(k) + ".md", r.text, "text/markdown"),
        },
        t("Download chapter (.md)"),
      ),
    ),
  );
}

function drawConn() {
  const c = st.conn,
    n = $("#conn");
  n.textContent = !c
    ? ""
    : c.k === "checking"
      ? t("Checking…")
      : c.k === "ok"
        ? c.model
          ? t("Connected ({model})", { model: c.model })
          : t("Connected")
        : t("Failed: {why}", { why: c.why });
}
function drawTop() {
  const b = $("#banner");
  b.innerHTML = "";
  if (st.banner)
    b.append(
      el(
        "div",
        { class: "msg err" },
        msg(st.banner) + " ",
        el(
          "button",
          {
            class: "sm",
            onclick: () => {
              st.banner = "";
              drawTop();
            },
          },
          t("Dismiss"),
        ),
      ),
    );
  const sb = $("#stopbtn");
  sb.hidden = !st.busy;
  sb.disabled = !!st.stopping || !st.jobId;
  sb.textContent = st.stopping ? t("Stopping…") : t("Stop");
  drawConn();
  syncTabIcon();
}
/* the parts of the page that are plain HTML: text carries data-i18n (or -ph / -aria for placeholders and labels) */
function applyStatic() {
  document.documentElement.lang = LANG === "zh" ? "zh-Hans" : "en";
  document.title = t("Pulpermill");
  document.querySelectorAll("[data-i18n]").forEach((n) => {
    n.textContent = t(n.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((n) => {
    n.placeholder = t(n.dataset.i18nPh);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((n) => {
    n.setAttribute("aria-label", t(n.dataset.i18nAria));
  });
  $("#lang-en").setAttribute("aria-pressed", String(LANG === "en"));
  $("#lang-zh").setAttribute("aria-pressed", String(LANG === "zh"));
}
function setLang(l) {
  LANG = l === "zh" ? "zh" : "en";
  save("lang", LANG);
  applyStatic();
  draw();
}
/* A redraw rebuilds the panels, which would take away the caret and the scroll position of someone typing or reading.
   So the focused field (found again by its place in the page, and only if it still holds the same text) and the scroll
   positions are put back afterwards. Moving to another page passes keep=false: nothing is carried over. */
const FIELD_SEL =
  "#mid textarea,#mid input,#mid select,#right textarea,#right input,#right select";
function snapView() {
  const a = document.activeElement,
    i = a ? [...document.querySelectorAll(FIELD_SEL)].indexOf(a) : -1,
    nl = document.querySelector("#nav .navlist"),
    r = $("#right");
  return {
    i,
    tag: a && a.tagName,
    type: a && a.type,
    value: a && a.value,
    s: a && a.selectionStart,
    e: a && a.selectionEnd,
    dir: a && a.selectionDirection,
    right: r ? r.scrollTop : 0,
    nav: nl ? nl.scrollTop : 0,
    y: window.scrollY,
  };
}
function restoreView(v) {
  if (v.i >= 0) {
    const f = [...document.querySelectorAll(FIELD_SEL)][v.i];
    if (f && f.tagName === v.tag && f.type === v.type && f.value === v.value) {
      f.focus({ preventScroll: true });
      try {
        if (v.s != null) f.setSelectionRange(v.s, v.e, v.dir || "none");
      } catch (e) {
        /* this kind of field has no caret to put back */
      }
    }
  }
  const nl = document.querySelector("#nav .navlist"),
    r = $("#right");
  if (r && r.scrollTop !== v.right) r.scrollTop = v.right;
  if (nl && nl.scrollTop !== v.nav) nl.scrollTop = v.nav;
  if (window.scrollY !== v.y) window.scrollTo(0, v.y);
}
function draw(keep = true) {
  const v = keep ? snapView() : null;
  drawTop();
  drawNav();
  drawMid();
  drawRight();
  updateCounters();
  refreshBar();
  scheduleSave();
  if (v) restoreView(v);
}
