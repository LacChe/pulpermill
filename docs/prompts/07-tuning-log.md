# Tuning log (phase 7)

One entry per change, newest last. Each says what the evidence was, what changed, and how to check it. The evidence for the first
round is the test-3 run (cozy fantasy, 6 chapters) and `Pulpermill_revision_brief_why_test-3_stalled.md`. Prompt versions are in the
template files; every result is recorded with them.

## Step 1: a two-section chapter (`writer-0.2`)

**Evidence.** Chapters ran 2,919 to 3,565 words whatever the beat held. About twelve long paragraphs appeared twice word for word, and
the same exchange recurred inside chapters. Sections were cut mid-word at the token limit ("It wasn'"). The extra-section text told
the writer to "take it further" when a chapter was short. Each later section saw only the last ~300 words.

**What changed.**
- A chapter is two sections: `open_press` (open the scene, meet the obstacle, let the pressure build) and `choice_close` (play the
  choice out with its cost, show what is different, end on the beat's moment). The plant and reveal hints sit with the first, the
  payoff and the "anything not yet on the page" hint with the second.
- Length is a ceiling: "up to about 1500 words, and ends sooner when the scene has done its work". `limits.yaml: chapter.target_words`
  (3,000) is now the ceiling for the whole chapter, shared by the sections.
- The padding is gone: the extra section, `needs_extra`, `short_ratio`, `tail_words` and the 3/4-section roles.
- The second section is shown the whole first section, labelled "The first section of the chapter, as written", with "let every
  paragraph show something the passage has not shown yet". The reminder's `fresh` line now covers images, gestures and turns of talk,
  not only images and gestures.
- `max_output.writer` is 2,400 tokens (a 1,500-word section is about 2,000).
- A section cut at the token limit is cut back to its last whole sentence (`chapter_checks.whole_sentences`, used by the backend's
  `_write` and by `run_chapter`). A new code check, `repeat-paragraph`, flags a paragraph written twice.
- Tests: the section tests, the backend story tests and the trial runner tests now describe two sections. The golden prompt
  `writer-4-close.txt` is replaced by `writer-2-close.txt`.

**Cost.** The second section carries the whole first one (up to ~2,000 tokens). The Salt Coast prompts still fit comfortably (3,900 and
5,400 tokens against 9,600), but a five-person story with a sentence or two in every field needs its caps squeezed to 0.7 for the first
section and 0.4 for the second (see `samples/budget-report.md`). If that squeeze is too hard, the lever is `n_ctx`: the load log of the
test-3 session shows 1.8 GB and 4.7 GB of VRAM free at 12,288, so 16,384 may fit. Measure before changing it.

**Not changed here (still open from the brief).** The `lingering` pacing directive ("a full paragraph on at least two moments") and the
craft line "let the scene take the time it needs" still push towards length. They are the next thing to look at if chapters run long
with two sections.

**How to check.** Chapter length varies with the beat's weight; no duplicate paragraphs; no section ends mid-word; the second section
does not retell the first. Run the four trials (`tests/trials/`) three times each and read them with `06-reading-rubric.md`, rows 2, 7 and 9
first.
