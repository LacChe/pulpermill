/* Pulpermill page: Generating cards and writing chapters: starting jobs, stopping, collecting results. */
/* `who` is a character's id: write that one person again and keep the rest of the cast as it is. */
async function generate(i, feedback, who) {
  const pg = cur(),
    s = STAGES[i],
    j = st.story.cur;
  if (st.busy) return;
  if (over(s.k)) {
    const notes = pg.notes[s.k] || "",
      sample = chText(s.k) + " " + notes,
      used = sample.trim().length,
      b = limitChars(budgetTokens(s.k), sample);
    pg.err[s.k] = mk(
      chText(s.k)
        ? "Too much text for this card: {used} characters ({ch} of them the example chapter), and the model can take {limit} here. Shorten the {what}."
        : "Too much text for this card: {used} characters, and the model can take {limit} here. Shorten the {what}.",
      {
        used: used.toLocaleString(),
        ch: chText(s.k).length.toLocaleString(),
        limit: b.toLocaleString(),
        what: mk(
          tokensEst(chText(s.k)) > budgetTokens(s.k) * 0.6
            ? "example chapter"
            : "notes",
        ),
      },
    );
    return draw();
  }
  const dep = brokenIn(
    pg.cards,
    STAGES.slice(0, i).map((x) => x.k),
  ); // the cards this one is built from
  if (dep.length) {
    pg.err[s.k] = mk(
      "The cards this one is built from have broken links ({n}). Fix the highlighted fields first.",
      { n: dep.length },
    );
    return draw();
  }
  const ch = chText(s.k).trim();
  if (!who && !(pg.notes[s.k] || "").trim() && !ch) {
    pg.err[s.k] = mk(
      pg.chapter.trim()
        ? "Add notes for this card first, or switch the example chapter on for it."
        : "Add notes for this card, or paste an example chapter above.",
    );
    return draw();
  }
  if (
    pg.cards[s.k] &&
    (j > 0 || pg.result) &&
    !confirm(
      who
        ? t(
            "Write {name} again for chapter {k}? It replaces this character as they stand on this page.",
            { name: personName(who), k: j + 1 },
          )
        : t(
            "Regenerate the {card} card for chapter {k}? It replaces the card as it stands on this page.",
            { card: t(s.t).toLowerCase(), k: j + 1 },
          ),
    )
  )
    return;
  const earlier = {};
  STAGES.slice(0, i).forEach((x) => (earlier[x.k] = pg.cards[x.k]));
  if (who) earlier[s.k] = pg.cards[s.k]; // the whole cast: the others are shown to the model so the new card differs
  const mine = who
    ? (pg.cards[s.k] || []).find((c) => c.id === who) || null
    : null;
  st.busy = s.k;
  st.busyChar = who || null;
  st.busyPg = pg;
  pg.err[s.k] = "";
  st.prog = null;
  draw();
  const t0 = Date.now();
  noteProg("card", {}, t0);
  try {
    const res = await api("/generate", {
      method: "POST",
      body: JSON.stringify({
        stage: s.k,
        mode: ch ? "chapter" : "notes",
        notes: pg.notes[s.k] || "",
        chapter: ch,
        chapter_use: ch ? pg.use || "" : "",
        language: LANG,
        feedback: feedback || null,
        character: who || null,
        current: feedback ? (who ? mine : pg.cards[s.k]) || null : null,
        cards: earlier,
      }),
    });
    if (res.error)
      throw Object.assign(new Error(res.error), { m: apiErr(res) });
    st.jobId = res.job;
    st.stopping = false;
    drawTop();
    let r;
    for (;;) {
      await sleep(2500);
      document
        .querySelectorAll(".timer")
        .forEach(
          (n) =>
            (n.textContent = " " + Math.round((Date.now() - t0) / 1000) + "s"),
        );
      r = await pollJob(res.job);
      if (r.status === "error")
        throw Object.assign(new Error(r.error), { m: apiErr(r) });
      if (r.status === "done" || r.status === "cancelled") break;
      noteProg("card", r, t0);
    }
    if (r.status === "cancelled") {
      pg.err[s.k] = mk("Stopped before it finished. Nothing was changed.");
      st.busy = null;
      st.busyChar = null;
      st.busyPg = null;
      st.jobId = null;
      st.stopping = false;
      return draw();
    }
    if (r.world_additions && r.world_additions.length && pg.cards.world) {
      r.world_additions.forEach((a) => {
        if (!pg.cards.world.locations.some((l) => l.id === a.id))
          pg.cards.world.locations.push(a);
      });
    }
    if (pg.draft) pg.draft[who ? "char:" + who : s.k] = "";
    const firstTime = !pg.cards[s.k]; // a card made for the first time moves the view on; regenerating one stays put
    pg.cards[s.k] = r.card;
    if (s.k === "style") stampNarrator(r.card);
    pg.warn[s.k] = r.warnings || [];
    pg.took = pg.took || {};
    pg.took[s.k] = Math.round((Date.now() - t0) / 1000);
    pg.stale[s.k] = false;
    STAGES.slice(i + 1).forEach((x) => {
      if (pg.cards[x.k]) pg.stale[x.k] = true;
    });
    if (firstTime && activeStage(pg) === i && i + 1 < STAGES.length)
      ACTIVE_STAGE.set(pg, i + 1); // move on to the next tab now that this one's done
  } catch (e) {
    pg.err[s.k] = e.gaveUp
      ? mk(
          "Lost contact with the backend for too long, so this card was not received. Check the backend, then generate it again.",
        )
      : emsg(e);
  }
  st.busy = null;
  st.busyChar = null;
  st.busyPg = null;
  st.jobId = null;
  st.stopping = false;
  draw();
}

/* Clear one card (not the project) so it can be generated again from scratch. With no card on the page the
   plain Generate button comes back, which sends the notes as the author's direction and no change request. The notes stay. */
function clearCard(i) {
  const pg = cur(),
    s = STAGES[i],
    j = st.story.cur;
  if (st.busy || !pg.cards[s.k]) return;
  if (
    !confirm(
      t(
        "Clear the {card} card for chapter {k}? Your notes for it stay, so you can generate it again from scratch.",
        { card: t(s.t).toLowerCase(), k: j + 1 },
      ),
    )
  )
    return;
  delete pg.cards[s.k];
  pg.warn[s.k] = [];
  pg.err[s.k] = "";
  pg.stale[s.k] = false;
  if (pg.draft) pg.draft[s.k] = ""; // a change request for a card that no longer exists
  draw();
}

function setProg(r, t0) {
  st.step = r.step || st.step;
  noteProg("chapter", r, t0);
  const secs = Math.round((Date.now() - t0) / 1000),
    clock =
      Math.floor(secs / 60) + "m " + String(secs % 60).padStart(2, "0") + "s";
  let line;
  if (st.stopping)
    line = t("Stopping… waiting for the backend to confirm it is ready");
  else if (r.step === "writing" && r.words)
    line = t("Writing the chapter: about {n} words · {clock}", {
      n: r.words.toLocaleString(),
      clock,
    });
  else
    line =
      t(
        {
          starting: "Starting",
          writing: "Writing the chapter",
          extracting: "Reading the chapter for changes to the cards",
          summarizing: "Summarizing the chapter",
          planning: "Planning this chapter",
          next: "Planning the next chapter",
        }[r.step] || "Working",
      ) +
      " · " +
      clock;
  document.querySelectorAll(".chprog").forEach((n) => {
    if (n.dataset.live === "1") n.textContent = line;
  });
}
async function writeChapter(choice, note) {
  const S = st.story,
    j = S.cur,
    pg = cur(),
    k = j + 1,
    P = pages(),
    nxt = P[j + 1];
  if (st.busy || isEnding(j) || !haveCards(pg) || (j > 0 && !P[j - 1].result))
    return;
  const broken = brokenIn(pg.cards);
  if (broken.length) {
    pg.msg = mk(
      "The cards have broken links ({n}). Fix the highlighted fields before writing chapter {k}.",
      { n: broken.length, k },
    );
    return draw();
  }
  if (pg.result && !choice) {
    st.ask = { j, note: (note || "").trim() };
    return draw();
  } // rewriting: ask first
  st.ask = null;
  pg.msg = "";
  const prev = j > 0 ? P[j - 1].result : null;
  const job = {
    id: null,
    j,
    last: k >= totalOf(pg),
    cast: castFor(pg, k),
    start: cleanCards(pg.cards),
    parent_id: prev ? prev.id : null,
    t0: Date.now(),
    next: choice === "keep" ? "keep" : "replace",
    nextSnap: nxt ? snap(nxt) : null,
  };
  if (pg.draft) pg.draft.chapter = ""; // the note is being used now
  S.job = job;
  st.busy = "chapter";
  st.busyPg = pg;
  draw();
  try {
    if (!(SCH.nullable || []).length) await loadSchema();
    const res = await api("/chapter", {
      method: "POST",
      body: JSON.stringify({
        chapter_num: k,
        cards: job.start,
        cast: job.cast,
        language: LANG,
        summaries: P.slice(0, j).map((p) => p.result.summary),
        prev_text: prev ? prev.text : "",
        note: (note || "").trim() || null,
      }),
    });
    if (res.error)
      throw Object.assign(new Error(res.error), { m: apiErr(res) });
    job.id = res.job;
    await pollChapter(job);
  } catch (e) {
    pg.msg = emsg(e);
    S.job = null;
    st.busy = null;
    st.busyPg = null;
    st.jobId = null;
    st.stopping = false;
    draw();
  }
}
async function stopGeneration() {
  if (!st.busy || !st.jobId || st.stopping) return;
  if (
    st.busy === "chapter" &&
    (st.step === "extracting" ||
      st.step === "summarizing" ||
      st.step === "next") &&
    !confirm(
      t(
        "The chapter is already written. Stopping now throws it away. Stop anyway?",
      ),
    )
  )
    return;
  st.stopping = true;
  drawTop();
  document.querySelectorAll(".chprog").forEach((n) => {
    if (n.dataset.live === "1")
      n.textContent = t(
        "Stopping… waiting for the backend to confirm it is ready",
      );
  });
  try {
    const r = await api("/cancel/" + st.jobId, { method: "POST" });
    if (!r.ok) {
      st.stopping = false;
      drawTop();
    } // it had already finished: the result arrives through the normal polling
  } catch (e) {
    st.stopping = false;
    st.banner = mk("Could not reach the backend to stop it ({why}).", {
      why: e.message,
    });
    drawTop();
  }
}
async function pollChapter(job) {
  const S = st.story,
    pg = S.pages[job.j];
  S.job = job;
  st.busy = "chapter";
  st.busyPg = pg;
  st.jobId = job.id;
  st.stopping = false;
  st.step = "starting";
  saveProject();
  draw();
  let gaveUp = false,
    r = { step: "starting" };
  try {
    for (;;) {
      setProg(r, job.t0);
      await sleep(2500);
      r = await pollJob(job.id);
      if (r.status === "error")
        throw Object.assign(new Error(r.error), { m: apiErr(r) });
      if (r.status === "done" || r.status === "cancelled") break;
    }
    if (r.status === "cancelled")
      pg.msg = mk("Stopped. Nothing from this attempt was kept.");
    else {
      commitResult(job, r);
    }
  } catch (e) {
    pg.msg = e.gaveUp
      ? mk(
          "Lost contact with the backend for too long. The chapter may still finish there: reload this page once the connection is back to pick it up.",
        )
      : emsg(e);
    gaveUp = !!e.gaveUp;
  }
  if (!gaveUp) S.job = null; // after giving up the job stays saved, so a reload can pick it up again
  st.busy = null;
  st.busyPg = null;
  st.jobId = null;
  st.stopping = false;
  saveProject();
  draw();
}
/* Keeps the chapter. The cards it returns become the next page's cards (a new page, or the ending, if there is none yet).
   If a next page exists, what happens to it was chosen before writing: replace it, or keep it as it is. The new ending cards
   are not stored anywhere else, so a page that is kept simply never sees them. */
function commitResult(job, r) {
  const P = pages(),
    pg = P[job.j],
    nxt = P[job.j + 1];
  const res = {
    id: uid(),
    parent_id: job.parent_id,
    start_hash: startHash(job.start),
    text: r.text,
    summary: r.summary,
    words: r.words,
    changes: r.changes || [],
    warnings: (r.warnings || []).slice(),
    unintroduced: r.unintroduced || [],
    update_failed: !!r.update_failed,
    at: Date.now(),
    secs: Math.round((Date.now() - job.t0) / 1000),
  };
  const nextName = isEnding(job.j + 1)
    ? mk("the ending cards")
    : mk("chapter {k}'s cards", { k: job.j + 2 });
  if (!nxt) {
    const np = newPage();
    fillPage(np, r.cards_after);
    np.cast = (job.cast || []).slice();
    P.push(np);
  } // the next chapter starts with the same people chosen
  else if (job.next === "replace") {
    if (r.update_failed)
      res.warnings.push(
        mk("The cards were not updated, so {what} were left as they were.", {
          what: nextName,
        }),
      );
    else if (snap(nxt) !== job.nextSnap)
      res.warnings.push(
        mk(
          "You edited {what} while this chapter was being written, so your edits were kept and the new ending cards were not applied.",
          { what: nextName },
        ),
      );
    else {
      fillPage(nxt, r.cards_after);
      if (!Array.isArray(nxt.cast)) nxt.cast = (job.cast || []).slice();
    }
  }
  pg.result = res;
  pg.msg = "";
}
