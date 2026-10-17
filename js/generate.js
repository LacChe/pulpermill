/* Pulpermill page: Generating cards and writing chapters: starting jobs, stopping, collecting results. */
/* `who` is a character's id: write that one person again and keep the rest of the cast as it is. */
async function generate(i, feedback, who) {
  const s = STAGES[i];
  if (st.busy) return;
  if (over(s.k)) {
    const notes = st.story.notes[s.k] || "",
      sample = chText(s.k) + " " + notes,
      used = sample.trim().length,
      b = limitChars(budgetTokens(s.k), sample);
    st.story.err[s.k] = mk(
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
    st.story.cards,
    STAGES.slice(0, i).map((x) => x.k),
  ); // the cards this one is built from
  if (dep.length) {
    st.story.err[s.k] = mk(
      "The cards this one is built from have broken links ({n}). Fix the highlighted fields first.",
      { n: dep.length },
    );
    return draw();
  }
  const ch = chText(s.k).trim();
  if (!who && !(st.story.notes[s.k] || "").trim() && !ch) {
    st.story.err[s.k] = mk(
      st.story.chapter.trim()
        ? "Add notes for this card first, or switch the example chapter on for it."
        : "Add notes for this card, or paste an example chapter above.",
    );
    return draw();
  }
  if (
    st.story.cards[s.k] &&
    !confirm(
      who
        ? t(
            "Write {name} again? It replaces this character in the story's shared cards.",
            { name: personName(who) },
          )
        : t(
            "Regenerate the {card} card? It replaces the story's shared card.",
            { card: t(s.t).toLowerCase() },
          ),
    )
  )
    return;
  const earlier = {};
  STAGES.slice(0, i).forEach((x) => (earlier[x.k] = st.story.cards[x.k]));
  if (who) earlier[s.k] = st.story.cards[s.k]; // the whole cast: the others are shown to the model so the new card differs
  const mine = who
    ? (st.story.cards[s.k] || []).find((c) => c.id === who) || null
    : null;
  st.busy = s.k;
  st.busyChar = who || null;
  st.story.err[s.k] = "";
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
        notes: st.story.notes[s.k] || "",
        chapter: ch,
        chapter_use: ch ? st.story.use || "" : "",
        language: LANG,
        feedback: feedback || null,
        character: who || null,
        current: feedback ? (who ? mine : st.story.cards[s.k]) || null : null,
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
      st.story.err[s.k] = mk("Stopped before it finished. Nothing was changed.");
      st.busy = null;
      st.busyChar = null;
      st.jobId = null;
      st.stopping = false;
      return draw();
    }
    if (r.world_additions && r.world_additions.length && st.story.cards.world) {
      r.world_additions.forEach((a) => {
        if (!st.story.cards.world.locations.some((l) => l.id === a.id))
          st.story.cards.world.locations.push(a);
      });
    }
    delete st.story.cardDraft[who ? "char:" + who : s.k];
    const firstTime = !st.story.cards[s.k];
    st.story.cards[s.k] = r.card;
    if (s.k === "style") stampNarrator(r.card);
    st.story.warn[s.k] = r.warnings || [];
    st.story.took[s.k] = Math.round((Date.now() - t0) / 1000);
    st.story.stale[s.k] = false;
    STAGES.slice(i + 1).forEach((x) => {
      if (st.story.cards[x.k]) st.story.stale[x.k] = true;
    });
    if (s.k === "outline")
      ensureChapter(
        Math.max(
          1,
          ...(r.card.chapter_beats || []).map((b) => Number(b.chapter_num) || 1),
        ),
      );
    if (firstTime && activeStage() === i && i + 1 < STAGES.length)
      ACTIVE_STAGE.set(st.story, i + 1);
  } catch (e) {
    st.story.err[s.k] = e.gaveUp
      ? mk(
          "Lost contact with the backend for too long, so this card was not received. Check the backend, then generate it again.",
        )
      : emsg(e);
  }
  st.busy = null;
  st.busyChar = null;
  st.jobId = null;
  st.stopping = false;
  draw();
}

/* Clear one card (not the project) so it can be generated again from scratch. With no card on the page the
   plain Generate button comes back, which sends the notes as the author's direction and no change request. The notes stay. */
function clearCard(i) {
  const s = STAGES[i];
  if (st.busy || !st.story.cards[s.k]) return;
  if (
    !confirm(
      t(
        "Clear the {card} card for the whole story? Your notes stay, so you can generate it again from scratch.",
        { card: t(s.t).toLowerCase() },
      ),
    )
  )
    return;
  delete st.story.cards[s.k];
  st.story.warn[s.k] = [];
  st.story.err[s.k] = "";
  st.story.stale[s.k] = false;
  delete st.story.cardDraft[s.k];
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
    P = chapters();
  if (st.busy || k > totalOf() || !haveCards() || (j > 0 && !P[j - 1].result))
    return;
  const broken = brokenIn(S.cards);
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
  const prev = j > 0 ? P[j - 1].result : null,
    before = cleanCards(S.cards);
  const job = {
    id: null,
    j,
    last: k >= totalOf(),
    cast: castFor(pg, k),
    start: cardsForChapter(before, k),
    before,
    cardsSnap: cardsHash(S.cards),
    parent_id: prev ? prev.id : null,
    t0: Date.now(),
    choice: choice === "keep" ? "keep" : "replace",
    rewrite: !!pg.result,
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
    pg = S.chapters[job.j];
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
/* Commits the chapter text and, when chosen, replaces the story-wide cards with the returned state. */
function commitResult(job, r) {
  const S = st.story,
    P = chapters(),
    pg = P[job.j],
    k = job.j + 1;
  const res = {
    id: uid(),
    parent_id: job.parent_id,
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
  if (!r.cards_after || typeof r.cards_after !== "object")
    throw fail("The chapter response did not include updated cards.");
  if (job.choice !== "keep") {
    if (cardsHash(S.cards) !== job.cardsSnap)
      res.warnings.push(
        mk(
          "The shared cards changed while this chapter was being written, so your edits were kept and the generated cards were not applied.",
        ),
      );
    else if (job.rewrite && r.update_failed)
      res.warnings.push(
        mk("The cards were not updated, so the shared cards were left unchanged."),
      );
    else {
      const nextCards = clone(r.cards_after);
      if (!job.rewrite && nextCards.outline && job.before.outline) {
        const returned = nextCards.outline.chapter_beats || [],
          oldFuture = (job.before.outline.chapter_beats || []).filter(
            (b) => Number(b.chapter_num) > k,
          );
        // Normal progression keeps any already-planned future beats; a rewrite's replace/keep choice handles them explicitly.
        nextCards.outline.chapter_beats = [
          ...returned.filter((b) => Number(b.chapter_num) <= k),
          ...(oldFuture.length
            ? oldFuture
            : returned.filter((b) => Number(b.chapter_num) > k)),
        ];
      }
      S.cards = nextCards;
      if (S.cards.outline) {
        const beatNums = (S.cards.outline.chapter_beats || []).map((b) =>
          Number(b.chapter_num) || 1,
        );
        ensureChapter(Math.max(k < totalOf() ? k + 1 : 1, ...beatNums));
      }
    }
  }
  pg.result = res;
  pg.msg = "";
}
