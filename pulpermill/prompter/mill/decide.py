"""The decider of the `plan` call (Plan 1): between the brainstorm and the plan, one separate call that judges the brainstorm's options on
explicit criteria, so the plan is built on the best one and not on whichever is listed first. This module holds what the decider needs; plan.py
wires it in. Wording lives in text/en/plan.yaml (the `decide_*` keys) and says nothing about any one story: the criteria are stated in
general terms and no sample text reaches the model.

`parse_options` splits the brainstorm into options. `order_of`, `step` and `decide` are the call: the options are shuffled (seeded by the
chapter and the options themselves, so a rerun shuffles the same way and the order is logged), lettered A, B, C and so on, and one model call
names each option's weakest point, scores it on three criteria and picks a letter. A reply that cannot be used falls back to the first
option, which is today's behavior. `parse_options` is the first piece: it splits the brainstorm's free text into options. Models write the same brainstorm in several shapes
(`**Option 1: Title (...)**`, `**Option 1 (Combination 1: ...)**`, three `**Combination N**` groups of three `**Option k:**` each, an
`**Overall Aim:**` line before the first option), so it goes by the words "Option" and "Combination" at the start of a line, not by one format."""
import random
import re
from dataclasses import dataclass
from typing import Any

from pulpermill.prompter.base import Step

from . import common

ON = True                  # the decider runs whenever the brainstorm gives at least two options; False leaves the flow as it was before the decider
OPTIONS_MAX = 9            # the most options one call judges (a brainstorm of three combinations of three); any more are left out
LABELS = "ABCDEFGHI"       # one letter per option, so OPTIONS_MAX letters
MAX_OUTPUT = 900           # per option a label, a sentence of up to WEAKEST_ASKED characters and three small scores: about 100 tokens at the most, 9 options
ATTEMPTS = 2               # then the first option stands: deciding is a help to the plan, never a reason to fail a call
WEAKEST_ASKED = 200        # what the prompt asks for
WEAKEST_MAX = 300          # what the check lets through (a retry costs a whole generation, so a little over what was asked is not refused)

_MARK = r"[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*|__)?[ \t]*"       # what may stand before a header word: indent, `#`s, bold
_OPTION = re.compile(rf"^{_MARK}Option[ \t]+(\d+)\b", re.I)
_GROUP = re.compile(rf"^{_MARK}Combination[ \t]+(\d+)\b", re.I)
_NAMED = re.compile(r"\bCombination[ \t]+(\d+)\b", re.I)
_RULE = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$")
_SENTENCE_END = ".!?…。！？"


def _finished(text: str) -> bool:
    """True when `text` ends a sentence (closing bold, quotes and brackets do not count). A reply cut off at its token cap does not."""
    return text.rstrip().rstrip("*_\"'”’)」』 \t\n")[-1:] in tuple(_SENTENCE_END)


def parse_options(text: str) -> list[tuple[int, str]]:
    """The brainstorm's options, in order, each as (its combination's number, its text with its header line). A combination's number is,
    in this order: the one its own header names ("Option 2: Combination 3 ..."), else that of the `Combination N` group header it stands
    under, else its own number. Text before the first option (a lead-in, an overall aim) and the group header lines are not part of any option.

    The last option is dropped when it was cut off mid-sentence (a brainstorm that hit its token cap). Fewer than 2 options left gives []:
    the caller then keeps the flow it has today."""
    options: list[tuple[int, list[str]]] = []
    group: int | None = None
    for line in str(text or "").splitlines():
        if _GROUP.match(line) and not _OPTION.match(line):
            group = int(_GROUP.match(line).group(1))
            options.append((0, []))          # closes the option before it: nothing after a group header belongs to that option
            continue
        found = _OPTION.match(line)
        if found:
            named = _NAMED.search(line)
            options.append((int(named.group(1)) if named else group or int(found.group(1)), [line]))
        elif options and options[-1][0] and not _RULE.match(line):
            options[-1][1].append(line)
    out = [(n, "\n".join(lines).strip()) for n, lines in options if n]
    if out and not _finished(out[-1][1]):
        out.pop()
    return out if len(out) >= 2 else []


# ---- Shuffling ------------------------------------------------------------------------------------------------------------------

def order_of(options: list[tuple[int, str]], request: dict) -> list[int]:
    """The order the options are shown in: the positions 0, 1, 2 ... of `options`, shuffled. The seed is the chapter and the options' own
    text, so the same call shuffles the same way (and a test can say what it will be); the order is logged in the run's notes."""
    order = list(range(min(len(options), OPTIONS_MAX)))
    seed = f"{request.get('chapter')}\n" + "\n".join(text for _, text in options[:OPTIONS_MAX])
    random.Random(seed).shuffle(order)
    return order


_NUMBERED = re.compile(r"\b(?:Option|Combination)[ \t]+\d+[ \t]*[:.\-–—]?", re.I)
_EMPTY_BOLD = re.compile(r"(\*\*|__)[ \t]*\1")


def unnumbered(text: str) -> str:
    """An option's text without the numbers its header gives it ("Option 2", "Combination 3"), which would show the model where the option
    stood in the brainstorm and so undo the shuffle. The header's other words stay."""
    head, _, rest = text.partition("\n")
    head = _EMPTY_BOLD.sub("", _NUMBERED.sub("", head))
    head = re.sub(r"^([#\s]*(?:\*\*|__)?)[\s:.\-–—]+", r"\1", head).strip()
    head = re.sub(r"\([ \t]*\)", "", re.sub(r"\([ \t]+", "(", head))
    head = re.sub(r"[ \t]{2,}", " ", re.sub(r"[ \t]+(\*\*|__)$", r"\1", head)).strip()
    return head + ("\n" + rest if rest else "")


# ---- The prompt -----------------------------------------------------------------------------------------------------------------

def build_decide_prompt(request: dict, options: list[tuple[int, str]], order: list[int], factor: float = 1.0) -> str:
    """The decider's prompt: the same cards and history as the plan (the spotlight is whatever `request` carries, so a flow that chose
    combinations passes the request without a pair), then the options under their letters in `order`, then the task."""
    from . import plan
    w = common.load_text("plan")
    c = plan._context(request, factor)
    role = w["decide_role"].format(chapter=c["chapter"], total=c["total"]) if c["total"] else w["decide_role_unknown_total"].format(chapter=c["chapter"])
    shown = "\n\n".join(w["decide_item"].format(label=LABELS[n], text=unnumbered(options[i][1])) for n, i in enumerate(order))
    task = [w["decide_task"], w["decide_chain"] if c["chain"] else "", w["decide_output"]]
    blocks = [role, *c["blocks"], plan._section(c["heads"]["decide"], shown), plan._section(c["heads"]["task"], "\n\n".join(x for x in task if x))]
    return "\n\n".join(b for b in blocks if b)


# ---- The reply ------------------------------------------------------------------------------------------------------------------

def grammar(n: int) -> dict:
    """One entry per option, `weakest` before the scores so the model names the weak point before it scores, then the pick."""
    labels = list(LABELS[:n])
    entry = {"label": {"type": "string", "enum": labels}, "weakest": {"type": "string"}, "loss": {"type": "integer", "enum": [1, 2, 3]},
             "irreversible": {"type": "boolean"}, "opposed": {"type": "boolean"}}
    item = {"type": "object", "properties": entry, "required": list(entry), "additionalProperties": False}
    return {"type": "object", "properties": {"options": {"type": "array", "items": item, "minItems": n, "maxItems": n}, "pick": {"type": "string", "enum": labels}},
            "required": ["options", "pick"], "additionalProperties": False}


def decide_problem(value: Any, n: int) -> str | None:
    """None when the reply is usable, else one plain line saying what to fix: not one entry for every letter, or a weak point missing or too long."""
    p = common.load_text("plan")["problems"]
    entries = value.get("options") if isinstance(value, dict) else None
    if not isinstance(entries, list) or sorted(str(e.get("label")) for e in entries if isinstance(e, dict)) != list(LABELS[:n]):
        return p["decide_labels"]
    if any(not str(e.get("weakest") or "").strip() or len(str(e["weakest"])) > WEAKEST_MAX for e in entries):
        return p["decide_weakest"]
    return None


def step(request: dict, options: list[tuple[int, str]], order: list[int], on_fallback) -> Step:
    """The decide step: JSON at the low-temperature set (the shuffle, not the sampling, keeps the first option from winning by habit), a small
    token cap, two attempts. Its last resort is `{}`, which makes no model call and leaves the first option standing (`on_fallback` notes it)."""
    n = len(order)

    def none():
        on_fallback()
        return {}
    return Step("decide", lambda f: build_decide_prompt(request, options, order, f), "json", MAX_OUTPUT, grammar(n),
                lambda value: decide_problem(value, n), "structured", False, attempts=ATTEMPTS, fallback=none)


# ---- The pick -------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    combo: int              # the picked option's original combination number
    position: int           # its place in the brainstorm's options, from 1
    fell_back: bool         # True when the reply could not be used and the first option stands
    order: tuple[int, ...]  # the places of the options in the order they were shown, from 1

    def notes(self) -> dict[str, Any]:
        """For the run log: numbers and short plain words only (the weak points are in the trace, in the step's reply)."""
        return {"decide": "fallback" if self.fell_back else "on", "decide_options": len(self.order), "decide_order": "-".join(map(str, self.order)),
                "decide_pick": self.position, "decide_combo": self.combo}


def decide(options: list[tuple[int, str]], order: list[int], value: Any) -> Decision:
    """The picked option's original combination number, from the step's result: the letter it picked is a place in `order`. A result that is
    not usable (the fallback `{}`, or no letter among those shown) picks the first option."""
    shown = tuple(i + 1 for i in order)
    label = value.get("pick") if isinstance(value, dict) else None
    if isinstance(label, str) and label in LABELS[:len(order)]:
        place = order[LABELS.index(label)]
        return Decision(options[place][0], place + 1, False, shown)
    return Decision(options[0][0], 1, True, shown)


def stand_in(words: int) -> list[tuple[int, str]]:
    """The most options of the longest size a brainstorm of `words` tokens can hold, for the worst case: the step reads them in full."""
    return [(n, "word " * (words // OPTIONS_MAX)) for n in range(1, OPTIONS_MAX + 1)]
