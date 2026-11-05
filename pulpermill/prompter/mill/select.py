"""The `select` step of the `plan` call, used when the request has `choose`: one model call, before the brainstorm, that picks three different
combinations from the ties between the cast and every rule and object of the world. A combination is one tie and one rule or object (or just a
tie, when the world has none). The model answers by number from two numbered lists, never by id: the ids stay here, in code, and come back
as `combos`. The brainstorm writes one idea per combination and the plan step chooses one idea (plan.py).

Wording lives in text/en/plan.yaml. The reply's shape is plain JSON Schema, written here because a prompter never imports the backend.
plan.py imports this module, so the helpers of plan.py are imported inside the functions that need them."""
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompter.base import Step

from . import common

PICKS = 3                  # combinations asked for, and ideas the brainstorm writes
MAX_OUTPUT = 600           # three picks of one or two sentences each, with room to spare
ATTEMPTS = 2               # then the plan goes ahead on the page's own pair: choosing is a help, never a reason to fail a call
REASON_MAX = 400           # the most characters of a reason
REASON_STAND_IN = "word " * 90       # the longest a reason is shown to a model (400 characters), for the worst case


# ---- What may be chosen -------------------------------------------------------------------------------------------------------

def candidates(request: dict) -> tuple[list[dict], list[dict]]:
    """(the ties, the pressure options). The ties are those whose two ends are both people of the cast (a tie to a group is no candidate); the
    options are the rules and objects the page sent, in words with ids. Both keep the request's order, which the numbers in the prompt follow."""
    people = {c.get("id") for c in request.get("cast") or [] if isinstance(c, dict) and c.get("id")}
    ties = [t for t in request.get("ties") or [] if t.get("tie_from") in people and t.get("tie_to") in people]
    options = [o for o in request.get("pressure_options") or [] if isinstance(o, dict) and o.get("id")]
    return ties, options


def is_on(request: dict) -> bool:
    """True when the request asks to choose and there are at least three distinct pairs to choose from; otherwise the flow is the single-pair one."""
    if not request.get("choose"):
        return False
    ties, options = candidates(request)
    return len(ties) * max(1, len(options)) >= PICKS


def without_pair(request: dict) -> dict:
    """The request with no spotlight and no pressure, so that a prompt built from it shows no single pair."""
    return {**{k: v for k, v in request.items() if k != "pressure"}, "spotlight": ""}


# ---- In words -------------------------------------------------------------------------------------------------------------------

def _tie_text(tie: dict, names: dict[str, str], w: dict, n: int | None = None) -> str:
    """The tie in words with its edge, numbered when `n` is given (a line of the list the model chooses from)."""
    from . import plan
    words = plan.spotlight_in_words(tie, names)
    edge = r.s(words.get("edge"))
    text = w["tie_words"].format(tie_from=r.s(words.get("tie_from")), tie_to=r.s(words.get("tie_to")), bond=r.s(words.get("bond")),
                                 edge=w["tie_edge"].format(edge=edge) if edge else "")
    return w["tie_item"].format(n=n, tie=text) if n is not None else text


def _words_of(option: dict) -> dict:
    """An option as the contract's `pressure` has it: its words, without the id."""
    return {k: v for k, v in option.items() if k != "id"}


def _element(option: dict) -> str:
    return r.pressure_element(_words_of(option))


# ---- The prompt ---------------------------------------------------------------------------------------------------------------

def build_select_prompt(request: dict, factor: float = 1.0) -> str:
    """The select step's prompt: the same cards and history as the other planner prompts, with no single pair shown, then two numbered lists (the
    ties, and the rules and objects, in words) and the task."""
    from . import plan
    w = common.load_text("plan")
    c = plan._context(without_pair(request), factor)
    names, chapter, total, heads = c["names"], c["chapter"], c["total"], c["heads"]
    ties, options = candidates(request)
    role = w["select_role"].format(chapter=chapter, total=total) if total else w["select_role_unknown_total"].format(chapter=chapter)
    lists = [w["select_ties_lead"] + "\n" + "\n".join(_tie_text(t, names, w, n) for n, t in enumerate(ties, 1))]
    if options:
        lists.append(w["select_pressures_lead"] + "\n" + "\n".join(
            w["pressure_item"].format(n=n, kind=r.pressure_kind(_words_of(o)), element=_element(o)) for n, o in enumerate(options, 1)))
    language = plan.language_name(request.get("language"))
    task = [w["select_task" if options else "select_task_no_pressure"], w["select_output" if options else "select_output_no_pressure"].format(language=language)]
    blocks = [role, *c["blocks"], plan._section(heads["choices"], "\n\n".join(lists)), plan._section(heads["task"], "\n\n".join(task))]
    return "\n\n".join(b for b in blocks if b)


# ---- The reply ------------------------------------------------------------------------------------------------------------------

def grammar(n_ties: int, n_options: int) -> dict:
    """Exactly three picks, `reason` first so that the model thinks before it chooses; numbers within the lists. With no options a pick has no `pressure`."""
    pick: dict[str, Any] = {"reason": {"type": "string"}, "tie": {"type": "integer", "enum": list(range(1, n_ties + 1))}}
    if n_options:
        pick["pressure"] = {"type": "integer", "enum": list(range(1, n_options + 1))}
    item = {"type": "object", "properties": pick, "required": list(pick), "additionalProperties": False}
    return {"type": "object", "properties": {"picks": {"type": "array", "items": item, "minItems": PICKS, "maxItems": PICKS}},
            "required": ["picks"], "additionalProperties": False}


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def select_problem(value: Any, n_ties: int, n_options: int) -> str | None:
    """None when the three picks are usable, else one plain line saying what to fix: not three picks, a reason missing or too long, a number
    outside its list, or two picks that are the same tie with the same rule or object."""
    p = common.load_text("plan")["problems"]
    picks = value.get("picks") if isinstance(value, dict) else None
    if not isinstance(picks, list) or len(picks) != PICKS or not all(isinstance(x, dict) for x in picks):
        return p["select_count"]
    seen: dict[tuple, int] = {}
    for n, pick in enumerate(picks, 1):
        reason = r.s(pick.get("reason"))
        if not reason or len(reason) > REASON_MAX:
            return p["select_reason"].format(n=n)
        tie, rule = pick.get("tie"), pick.get("pressure")
        in_range = _whole(tie) and 1 <= tie <= n_ties and ((_whole(rule) and 1 <= rule <= n_options) if n_options else rule in (None, 0))
        if not in_range:
            rules = p["select_range_rules"].format(n_pressures=n_options) if n_options else ""
            return p["select_range"].format(n=n, n_ties=n_ties, rules=rules)
        key = (tie, rule if n_options else None)
        if key in seen:
            return p["select_same"].format(a=seen[key], b=n)
        seen[key] = n
    return None


def step(request: dict, on_fallback) -> Step:
    """The select step: JSON, thinking sampling (the lowest-temperature set tends to take the first items of a list). Its last resort is `{}`,
    which makes no model call and leaves the flow on the page's own pair (`on_fallback` notes it)."""
    ties, options = candidates(request)

    def none():
        on_fallback()
        return {}
    return Step("select", lambda f: build_select_prompt(request, f), "json", MAX_OUTPUT, grammar(len(ties), len(options)),
                lambda value: select_problem(value, len(ties), len(options)), "thinking", False, attempts=ATTEMPTS, fallback=none)


# ---- Combinations ---------------------------------------------------------------------------------------------------------------

def combos(request: dict, value: Any) -> list[dict] | None:
    """The three combinations of a good result, in the order picked, or None (a fallback `{}`, or a result that does not pass its own check).
    Each is {tie_id, tie_words, pressure_id, pressure, pressure_words, reason}: ids from the request for the reply, words for prompts.
    `pressure` is the element as the contract's `pressure` has it (no id), or None."""
    from . import plan
    ties, options = candidates(request)
    if select_problem(value, len(ties), len(options)):
        return None
    names, w = plan.names_of(request), common.load_text("plan")
    out = []
    for pick in value["picks"]:
        tie = ties[pick["tie"] - 1]
        option = options[pick["pressure"] - 1] if options else None
        out.append({"tie_id": tie["id"], "tie_words": _tie_text(tie, names, w), "pressure_id": option["id"] if option else None,
                    "pressure": _words_of(option) if option else None, "pressure_words": _element(option) if option else "", "reason": r.s(pick.get("reason"))})
    return out


def combos_text(combos: list[dict], w: dict | None = None) -> str:
    """The combinations block of the brainstorm and plan prompts: a lead line, then each combination's tie, rule or object and reason, in words."""
    w = w or common.load_text("plan")
    parts = [w["combos_lead"]]
    for n, c in enumerate(combos, 1):
        lines = [w["combo_head"].format(n=n), w["combo_tie"].format(tie=c["tie_words"])]
        if c.get("pressure"):
            lines.append(w["combo_pressure"].format(kind=r.pressure_kind(c["pressure"]), element=c["pressure_words"]))
        lines.append(w["combo_reason"].format(reason=c["reason"]))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def stand_in(request: dict) -> list[dict]:
    """Three combinations as large as they can get, for the worst case: the longest ties and the longest rules or objects, each with the longest reason."""
    from . import plan
    ties, options = candidates(request)
    names, w = plan.names_of(request), common.load_text("plan")
    tie_words = sorted((_tie_text(t, names, w) for t in ties), key=len, reverse=True) or [""]
    longest = sorted(options, key=lambda o: len(_element(o)), reverse=True)
    out = []
    for n in range(PICKS):
        option = longest[n % len(longest)] if longest else None
        out.append({"tie_id": "", "tie_words": tie_words[n % len(tie_words)], "pressure_id": None, "pressure": _words_of(option) if option else None,
                    "pressure_words": _element(option) if option else "", "reason": REASON_STAND_IN})
    return out


def counts(combos: list[dict]) -> tuple[int, int]:
    """(how many different ties, how many different rules or objects) the combinations use: numbers for the run log, never text."""
    return len({c["tie_id"] for c in combos}), len({c["pressure_id"] for c in combos if c["pressure_id"]})
