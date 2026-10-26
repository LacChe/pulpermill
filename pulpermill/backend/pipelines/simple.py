"""The simple calls: fill, judge and style_fit. Each builds its Prompt(s) with pulpermill.prompts, runs them through the shared
two-attempt call (structured.py) and assembles the contract's reply with the prompts package's own assemblers."""
from pulpermill.prompts import assemble_judge_reply, fill_prompt, judge_prompts, style_fit_prompt

from . import structured as st
from .context import RunContext


def _req(request) -> dict:
    """The validated request as the plain dict the prompt builders read."""
    return request.model_dump()


def fill(request, ctx: RunContext) -> dict:
    req = _req(request)
    prompt = fill_prompt(req)
    result = st.run_json(ctx, prompt, request.language, validate=lambda v: None if isinstance(v, dict) else "the reply must be an object")
    return {"ok": True, "values": result.value}


def judge(request, ctx: RunContext) -> dict:
    """One model pass per rule asked (a rule the prompts have nothing to ask about gets no pass and no result)."""
    prompts = judge_prompts(_req(request))
    for prompt in prompts:                         # every prompt is measured first: a too-long one fails before any inference
        st.fit_check(ctx, prompt)
    answers = [st.run_json(ctx, prompt, request.language).value for prompt in prompts]
    return assemble_judge_reply(prompts, answers)


def style_fit(request, ctx: RunContext) -> dict:
    prompt = style_fit_prompt(_req(request))
    value = st.run_json(ctx, prompt, request.language).value
    fits = bool(value["fits"])
    return {"ok": True, "fits": fits, "message": "" if fits else str(value.get("message", "")).strip()}
