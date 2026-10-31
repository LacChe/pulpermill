"""The generic runner: runs a prompter's Flow, one model call per Step, and everything mechanical around it.

- Before the first token, every step the flow may run (flow.worst_case()) is measured and squeezed to the fullest factor at which all
  of them fit; a call that cannot fit is answered `too_long` at once, not after the first step has been written.
- Two attempts per step. The second carries one short line about what was wrong with the first (not the first reply itself).
  Then `bad_output`. A reply fails when it is not valid JSON in the step's grammar (a reply cut off at max_output is one of these),
  when the step's own check says so, or when it is not in the language asked for.
- Stop (Cancelled) passes straight through and is never retried.
- Progress is `{name, index, of}`; the run record gets the prompter's name and version, the squeeze, and every step's attempts.
- The flow's reply, in the model's handles, is turned into the contract's reply by assemble.py."""
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pulpermill.prompter.base import Flow, Step
from pulpermill.prompts import budget, tokens

from . import assemble, language as lang, shape
from .errors import BackendError
from .handles import Unresolved
from .kit import Kit
from .pipelines.context import RunContext

log = logging.getLogger("pulpermill")

MAX_ATTEMPTS = 2
PROBLEM_CHARS = 300
RETRY_LINE = ("Your previous reply could not be used: {problem}\n"
              "Reply again from the start, in exactly the format asked for above.")


class Unusable(Exception):
    """A reply that cannot be used; the message says why, in a line a model can act on."""


@dataclass
class Attempt:
    number: int
    constrained: bool
    seconds: float
    problem: str | None = None          # None when this attempt's reply was used
    run: dict | None = None             # the engine's own record (tokens, prefill and generation seconds), when it keeps one


@dataclass
class Result:
    value: Any
    measure: budget.Measure
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def retried(self) -> bool:
        return len(self.attempts) > 1


def measure(ctx: RunContext, item: budget.Sized) -> budget.Measure:
    """How much of the context the prompt takes. Uses the page's own tokenizer files when they are installed (what the tests and the
    budgets are written against) and the engine's count when they are not."""
    if tokens.available():
        return budget.measure(item)
    return budget.Measure(item.name, ctx.engine.count_tokens(item.text), budget.input_limit(item.max_output), item.max_output)


def too_long(e: budget.PromptTooLong) -> BackendError:
    return BackendError("too_long", str(e))


def check_n_ctx(engine) -> None:
    """The prompts are sized to budgets.yaml's n_ctx; an engine loaded with another would let a prompt through that does not fit."""
    wanted, loaded = budget.budgets()["n_ctx"], (engine.info() or {}).get("n_ctx")
    if isinstance(loaded, int) and loaded != wanted:
        raise RuntimeError(f"The engine was loaded with n_ctx {loaded} but pulpermill/prompts/budgets.yaml says {wanted}. "
                           "Change both, on purpose, after measuring.")


def short(problem: str) -> str:
    one = " ".join(str(problem).split())
    return one if len(one) <= PROBLEM_CHARS else one[:PROBLEM_CHARS - 1].rstrip() + "…"


def fit(ctx: RunContext, flow: Flow) -> tuple[float, int]:
    """The squeeze at which every step the flow may run fits, and how many steps that is. Costs no inference."""
    steps = flow.worst_case()
    if not steps:
        return 1.0, 0
    try:
        _, factor, _ = budget.fit(lambda f: [budget.Sized(s.name, s.text(f), s.max_output) for s in steps],
                                  measurer=lambda item: measure(ctx, item))
    except budget.PromptTooLong as e:
        raise too_long(e) from None
    return factor, len(steps)


def _parser(step: Step, language: str | None):
    def parse(text: str):
        if step.kind == "text":
            if not text.strip():
                raise Unusable("the reply was empty")
            value, strings = text, text
        else:
            try:
                value = shape.parse_json(text)
            except ValueError as e:
                raise Unusable(str(e)) from None
            found = shape.problems(value, step.grammar)
            if found:
                raise Unusable(found[0])
            strings = None
        own = step.check(value) if step.check else None
        if own:
            raise Unusable(own)
        if step.language and language:
            wrong = lang.check(strings, language) if strings is not None else lang.check_value(value, language)
            if wrong:
                raise Unusable(f"{wrong}; write in the language the story is told in")
        return value
    return parse


def run_step(ctx: RunContext, step: Step, factor: float, language: str | None, progress: dict | None = None) -> Result:
    """One step through the two-attempt rule at the squeeze the call was fitted to."""
    prompt = step.text(factor)
    item = budget.Sized(step.name, prompt, step.max_output)
    m = measure(ctx, item)
    if not m.ok:
        raise too_long(budget.PromptTooLong(m))
    parse = _parser(step, language)
    result = Result(None, m)
    entry = {"step": step.name, "prompt_tokens": m.tokens, "attempts": []}
    ctx.notes.setdefault("passes", []).append(entry)       # the run's record: what ran, in order, and how each attempt went
    constrain_first = step.kind == "json" and ctx.config.constrain == "always"
    problem = None
    for number in range(1, MAX_ATTEMPTS + 1):
        ctx.cancel.raise_if_cancelled()
        current = prompt
        if problem is not None:
            noted = prompt.rstrip() + "\n\n" + RETRY_LINE.format(problem=short(problem))
            if measure(ctx, budget.Sized(step.name, noted, step.max_output)).ok:     # a note that does not fit is left out
                current = noted
        constrained = step.kind == "json" and (constrain_first or number > 1)
        if progress:
            ctx.set_stage(progress)
        started = time.monotonic()
        text = ctx.engine.generate(current, step.max_output, constraint=step.grammar if constrained else None, cancel=ctx.cancel,
                                   params=ctx.config.sampling(step.sampling, language))
        attempt = Attempt(number, constrained, time.monotonic() - started, run=dict(getattr(ctx.engine, "last_run", None) or {}) or None)
        result.attempts.append(attempt)
        entry["attempts"].append({"constrained": constrained, "seconds": round(attempt.seconds, 2), "run": attempt.run})
        try:
            result.value = parse(text)
            return result
        except Unusable as e:
            problem = attempt.problem = short(e)
            entry["attempts"][-1]["problem"] = problem
    raise BackendError("bad_output", problem or "")


def run_flow(ctx: RunContext, flow: Flow, language: str | None) -> list[Any]:
    """Fits the whole call, then runs the flow's steps in order. Returns the results, one per step."""
    factor, planned = fit(ctx, flow)
    ctx.notes["squeeze"] = factor
    results: list[Any] = []
    index = 1
    while (step := flow.next(results)) is not None:
        progress = {"name": step.name, "index": index, "of": planned if index <= planned else None}
        results.append(run_step(ctx, step, factor, language, progress).value)
        index += 1
    if getattr(flow, "notes", None):
        ctx.notes["flow"] = dict(flow.notes)
    return results


def run_call(request, ctx: RunContext) -> dict:
    """The contract's reply for one request, through the configured prompter."""
    req = request.model_dump()
    kit = Kit(req)
    ctx.notes["prompter"] = {"name": ctx.prompter.name, "version": ctx.prompter.version}
    flow = ctx.prompter.flow(request.call, req, kit)
    results = run_flow(ctx, flow, request.language)
    try:
        return assemble.reply(request.call, flow.reply(results), kit.handles)
    except Unresolved as e:
        log.error("call=%s the prompter's reply could not be assembled: %s", request.call, e)
        raise BackendError("bad_output", "") from None
