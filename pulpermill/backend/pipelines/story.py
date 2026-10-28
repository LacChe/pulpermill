"""The story calls: generate, plan, offstage and end_story. Each builds its prompts with pulpermill.prompts and runs them
through the shared call (structured.py). Everything a call needs is checked for length before the first token, so a story
that cannot fit is answered `too_long` at once and not after fifteen minutes of writing."""
from typing import Callable

from pulpermill.prompts import (assemble_end_story_reply, assemble_generate_reply, budget, end_story_prompts, events_prompt,
                                needs_extra, offstage_prompt, planner_beat_prompt, planner_think_prompt, shifts_prompt,
                                textfiles as tx, writer_plan, writer_prompt)
from pulpermill.prompts import chapter_checks

from . import structured as st
from .context import RunContext

# A paragraph of ordinary prose, repeated to stand in for a chapter when the prompts are measured before it is written.
FILLER = ("The morning came in grey over the roofs, and the street below was already loud with carts and shutters and the "
          "shouting of people who had somewhere to be. She stood at the window a while, listening, and then went down. ")


def stand_in(words: int) -> str:
    one = FILLER.split()
    return " ".join((one * (words // len(one) + 1))[:words])


def fitted(build: Callable, start: float = 1.0):
    """budget.fit, from squeeze `start` on, with `too_long` as the failure. Returns (what build made, factor)."""
    squeezes = tuple(f for f in budget.SQUEEZES if f <= start) or budget.SQUEEZES[-1:]
    try:
        made, factor, _ = budget.fit(build, squeezes)
    except budget.PromptTooLong as e:
        raise st.too_long(e) from None
    return made, factor


def _req(request) -> dict:
    return request.model_dump()


# ---- generate -------------------------------------------------------------------------------------------------------

def _generate_prompts(req: dict, chapter_text: str, events: dict | None, target: int) -> list:
    """The heaviest prompt of each pass, for measuring: every section's, then Events and Shifts on a whole chapter."""
    plan = writer_plan(extra=True)
    sections = [writer_prompt(req, plan, i, stand_in(target), target) for i in range(len(plan))]
    return [*sections, events_prompt(req, chapter_text), shifts_prompt(req, chapter_text, events)]


def generate(request, ctx: RunContext) -> dict:
    req, language = _req(request), request.language
    lim = tx.limits()["chapter"]
    target = lim["target_words"]
    worst = stand_in(budget.budgets()["chapter_words_worst_case"])
    _, factor = fitted(lambda: _generate_prompts(req, worst, {"happened": stand_in(120)}, target))
    ctx.notes["squeeze"] = factor
    with tx.squeeze(factor):
        sections = _write(ctx, req, language, target)
        chapter = "\n\n".join(sections)
        ctx.notes["words_per_section"] = [len(chapter_checks.words(t)) for t in sections]
        ctx.notes["words"] = len(chapter_checks.words(chapter))
        ctx.notes["flags"] = [str(f) for f in chapter_checks.run_checks(chapter, req, target)]     # pointers for a reader; never a failure
        events_p, _ = fitted(lambda: events_prompt(req, chapter), factor)
        events = st.run_json(ctx, events_p, None).value
        shifts_p, _ = fitted(lambda: shifts_prompt(req, chapter, events), factor)
        shifts = st.run_json(ctx, shifts_p, None).value
    return assemble_generate_reply(chapter, events, shifts, shifts_p.meta["handles"])


def _write(ctx: RunContext, req: dict, language: str, target: int) -> list[str]:
    """The chapter section by section, as tools/run_trials.py::run_chapter does it. Free text, no early stop."""
    plan = writer_plan()
    sections: list[str] = []
    extra = False
    i = 0
    while i < len(plan):
        if not extra and i == len(plan) - 1 and needs_extra(len(chapter_checks.words(" ".join(sections))), i):
            plan, extra = writer_plan(extra=True), True
        prompt = writer_prompt(req, plan, i, "\n\n".join(sections), target)
        sections.append(st.run_text(ctx, prompt, language, params=ctx.config.prose_for(language)).value.strip())
        i += 1
    return sections


# ---- plan -----------------------------------------------------------------------------------------------------------

def plan(request, ctx: RunContext) -> dict:
    req, language = _req(request), request.language
    think_p, factor = fitted(lambda: planner_think_prompt(req))
    ctx.notes["squeeze"] = factor
    thinking = st.run_text(ctx, think_p, None, params=ctx.config.thinking).value.strip()
    with tx.squeeze(factor):
        beat_p, _ = fitted(lambda: planner_beat_prompt(req, thinking), factor)
    beat = st.run_json(ctx, beat_p, None).value
    return {"ok": True, "thinking": thinking, "beat": beat}


# ---- offstage -------------------------------------------------------------------------------------------------------

def offstage(request, ctx: RunContext) -> dict:
    req = _req(request)
    prompt, factor = fitted(lambda: offstage_prompt(req))
    ctx.notes["squeeze"] = factor

    def both(value):
        return None if all(str(value.get(k, "")).strip() for k in ("did", "reach")) else "both 'did' and 'reach' need a sentence"
    value = st.run_json(ctx, prompt, request.language, validate=both).value
    return {"ok": True, "did": value["did"].strip(), "reach": value["reach"].strip()}


# ---- end_story ------------------------------------------------------------------------------------------------------

def end_story(request, ctx: RunContext) -> dict:
    req = _req(request)
    prompts, factor = fitted(lambda: end_story_prompts(req))
    ctx.notes["squeeze"] = factor
    outputs = []
    with tx.squeeze(factor):
        for prompt in prompts:
            outputs.append(st.run_json(ctx, prompt, request.language, validate=lambda v: None if isinstance(v, dict) else "the reply must be an object").value)
    return assemble_end_story_reply(prompts, outputs, req)
