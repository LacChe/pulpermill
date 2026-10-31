"""The model call every pipeline shares: check that the prompt fits, run it, check the reply, and retry once if the reply
could not be used. Pipelines build their Prompts with pulpermill.prompts and hand them here.

The rules (plan, M3):
- A prompt that cannot fit is answered `too_long` before any inference.
- Two attempts in total. The second one carries one short line about what was wrong with the first (the template
  `retry.yaml`), and not the first reply itself. Then `bad_output`.
- A reply fails when it is not valid JSON in the prompt's shape (a reply cut off at max_tokens is one of these), when the
  caller's own check fails, or when it is not in the language asked for.
- Stop (Cancelled) passes straight through and is never retried."""
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from pulpermill.prompts import budget, textfiles as tx, tokens
from pulpermill.prompts.prompts import Prompt

from .. import language as lang
from .. import shape
from ..errors import BackendError
from .context import RunContext

MAX_ATTEMPTS = 2
PROBLEM_CHARS = 300


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
    prompt: Prompt
    measure: budget.Measure
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def retried(self) -> bool:
        return len(self.attempts) > 1


def measure(ctx: RunContext, prompt: Prompt) -> budget.Measure:
    """How much of the context the prompt takes. Uses the page's own tokenizer files when they are installed (what the
    tests and the budgets are written against) and the engine's count when they are not."""
    if tokens.available():
        return budget.measure(prompt)
    key = budget.key(prompt.name)
    return budget.Measure(prompt.name, ctx.engine.count_tokens(prompt.text), budget.input_limit(prompt.name),
                          budget.budgets()["max_output"][key])


def fit_check(ctx: RunContext, prompt: Prompt) -> budget.Measure:
    """`too_long` (413) when the prompt and its reply cannot fit the context. Costs no inference."""
    m = measure(ctx, prompt)
    if not m.ok:
        raise too_long(budget.PromptTooLong(m))
    return m


def too_long(e: budget.PromptTooLong) -> BackendError:
    return BackendError("too_long", str(e))


def short(problem: str) -> str:
    one = " ".join(str(problem).split())
    return one if len(one) <= PROBLEM_CHARS else one[:PROBLEM_CHARS - 1].rstrip() + "…"


def with_note(prompt: Prompt, problem: str) -> Prompt:
    """The prompt for the second attempt: the same text, then the retry note (wording in templates/en/retry.yaml)."""
    note = tx.template("retry")["note"].format(problem=short(problem)).strip()
    return replace(prompt, text=prompt.text.rstrip() + "\n\n" + note)


def run_prompt(ctx: RunContext, prompt: Prompt, parse: Callable[[str], Any], *, constrain_first: bool | None = None,
               params: Any = None) -> Result:
    """Run one prompt through the two-attempt rule. `parse(text)` returns the usable value or raises Unusable.
    `constrain_first` False writes the first attempt free; the retry is then constrained (a prompt with no schema never is).
    `params` is the sampling for this call: the config's `structured` for a prompt with a schema, its `prose` otherwise."""
    m = fit_check(ctx, prompt)
    if constrain_first is None:
        constrain_first = ctx.config.constrain == "always"
    result = Result(None, prompt, m)
    entry = {"prompt": prompt.name, "version": prompt.version, "prompt_tokens": m.tokens, "attempts": []}
    ctx.notes.setdefault("passes", []).append(entry)       # the run's record: what ran, in order, and how each attempt went
    problem = None
    for number in range(1, MAX_ATTEMPTS + 1):
        ctx.cancel.raise_if_cancelled()
        current = prompt
        if problem is not None:
            noted = with_note(prompt, problem)
            if measure(ctx, noted).ok:           # a note that does not fit is left out; the reminder still stands
                current = noted
        constrained = prompt.schema is not None and (constrain_first or number > 1)
        if prompt.stage:
            ctx.set_stage(prompt.stage)
        started = time.monotonic()
        text = ctx.engine.generate(current.text, m.max_output, constraint=prompt.schema if constrained else None,
                                   cancel=ctx.cancel, params=params or (ctx.config.structured if prompt.schema is not None else ctx.config.prose))
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


def json_parser(prompt: Prompt, language: str | None, validate: Callable[[Any], str | None] | None = None) -> Callable[[str], Any]:
    """Reads a reply as the prompt's JSON. `validate(value)` may return a problem of the caller's own (content the schema
    cannot say); the language of the longer sentences is checked last."""
    def parse(text: str):
        try:
            value = shape.parse_json(text)
        except ValueError as e:
            raise Unusable(str(e)) from None
        if prompt.schema is not None:
            found = shape.problems(value, prompt.schema)
            if found:
                raise Unusable(found[0])
        own = validate(value) if validate else None
        if own:
            raise Unusable(own)
        wrong = lang.check_value(value, language) if language else None
        if wrong:
            raise Unusable(f"{wrong}; write in the language the story is told in")
        return value
    return parse


def text_parser(language: str | None) -> Callable[[str], str]:
    def parse(text: str):
        if not text.strip():
            raise Unusable("the reply was empty")
        wrong = lang.check(text, language) if language else None
        if wrong:
            raise Unusable(f"{wrong}; write in the language the story is told in")
        return text
    return parse


def run_json(ctx: RunContext, prompt: Prompt, language: str | None, validate: Callable[[Any], str | None] | None = None,
             constrain_first: bool | None = None, params: Any = None) -> Result:
    """`language` None skips the language check (for a call whose prompt does not ask for a language)."""
    return run_prompt(ctx, prompt, json_parser(prompt, language, validate), constrain_first=constrain_first, params=params)


def run_text(ctx: RunContext, prompt: Prompt, language: str | None, params: Any = None) -> Result:
    return run_prompt(ctx, prompt, text_parser(language), constrain_first=False, params=params)
