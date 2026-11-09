"""The decider of the `plan` call: between the brainstorm and the plan, one separate call that judges the brainstorm's three options on one
criterion, `move` (which option moves the story forward the most), so the plan is built on the best one and not on whichever is listed first.
This module holds what the decider needs; plan.py wires it in. Wording lives in text/en/plan.yaml (the `decide_*` keys) and says nothing about
any one story: the criterion is stated in general terms and no sample text reaches the model.

`parse_options` splits the brainstorm into options. `order_of`, `step` and `decide` are the call: the options are shuffled (seeded by the
chapter and the options themselves, so a rerun shuffles the same way and the order is logged), lettered A, B, C, and one model call reasons
before it judges: first `held` (what the story holds now), then a short text per option (what it adds that is new, or repeats), then which
option is best and which is worst. The model gives no pick: `scores` turns the marks into points (best +1, worst -1) and `decide` picks the
highest total, with a random choice among equals. An option that names a person on no card (and in no earlier chapter's record) loses one
point first (`invented`). A reply that cannot be used falls back to a random option.
`parse_options` splits the brainstorm's free text into options. Models write the same brainstorm in several shapes
(`**Option 1: Title (...)**`, `**Option 1 (Combination 1: ...)**`, three `**Combination N**` groups of three `**Option k:**` each, an
`**Overall Aim:**` line before the first option), so it goes by the words "Option" and "Combination" at the start of a line, not by one format.
"""
import random
import re
from dataclasses import dataclass, field
from typing import Any

from pulpermill.prompter.base import Step
from pulpermill.prompts import render as r

from . import common

ON = True                  # the decider runs whenever the brainstorm gives at least two options; False leaves the flow as it was before the decider
OPTIONS_MAX = 3            # the most options one call judges: exactly the brainstorm's three (one per combination, the outcome fixed by the number)
LABELS = "ABC"             # one letter per option, so OPTIONS_MAX letters
MAX_OUTPUT = 2000          # the longest reply is `held` (HELD_MAX) and three texts (PHRASE_MAX), 2,400 characters. Scaled from the Gemma-tokenizer measurement of the old
                           # 1,800-character reply (about 450 tokens in English, about 990 in Chinese, JSON included) that is about 600 and about 1,320 tokens; 2,000
                           # is 1.5 times the larger, for rarer characters (a cut-off reply is invalid)
ATTEMPTS = 2               # then a random option stands: deciding is a help to the plan, never a reason to fail a call
HELD_MAX = 600             # the longest `held` (what the story holds now) the check lets through, and what the prompt asks for: a few sentences
PHRASE_ASK = 400           # the length the prompt asks for per option text (what it adds that is new, or repeats): a few sentences. A request, not a check
PHRASE_MAX = 600           # the longest option text the check lets through: models run over what they are asked, and a refusal costs a call, so the check allows
                           # half as much again as the prompt asks for. The prompt never states this number
SAMPLING = "structured"    # the step's sampling set; the run notes carry it, so runs before and after a change of set are told apart
CRITERIA = ("move",)       # one criterion: which option moves the story forward the most, from where the story stands now

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

def criteria_for(request: dict) -> tuple[str, ...]:
    """The criteria this call judges on: `move` for every chapter. What the story holds now differs in chapter 1 (the setup and the disruption,
    since there is no earlier chapter), but that lives in the wording (`decide_move_first`), not here."""
    return CRITERIA


_COMBINATION_NUMBER = re.compile(r"\b(?:Option|Combination)[ \t]+\d+\b", re.I)


def built_on(combo: dict, w: dict) -> str:
    """The lines under an option that say what it is built on: the tie (with its edge), the rule or object, and the reason they may collide. Never
    the combination's number, which would show where the option stood: the selector's reason may name it, so a number there is replaced."""
    lines = [w["decide_built_on_lead"], w["combo_tie"].format(tie=combo["tie_words"])]
    if combo.get("pressure"):
        lines.append(w["combo_pressure"].format(kind=r.pressure_kind(combo["pressure"]), element=combo["pressure_words"]))
    lines.append(w["combo_reason"].format(reason=_COMBINATION_NUMBER.sub("this one", str(combo.get("reason") or ""))))
    return "\n".join(lines)


def _item(w: dict, label: str, text: str, combo: dict | None) -> str:
    item = w["decide_item"].format(label=label, text=unnumbered(text))
    return item + "\n" + built_on(combo, w) if combo else item


def build_decide_prompt(request: dict, options: list[tuple[int, str]], order: list[int], factor: float = 1.0, criteria: tuple[str, ...] | None = None,
                        combos: list[dict] | None = None) -> str:
    """The decider's prompt: the role (the job and the criterion), the setup and the story so far (the two things `move` is judged against; no
    style, cast, world, ties or combination section), then the options under their letters in `order`, then the task. With `combos` (choose
    mode) each option is followed by the lines of the combination it was written for, `combos[number - 1]`, where `number` is the combination
    number `parse_options` gave it: the tie with its edge, the rule or object and the reason. Without them (plain mode) the options carry no such
    lines. `request` is the plan's own, so the context comes out as the plan's; only its setup and history sections are used."""
    from . import plan
    w = common.load_text("plan")
    criteria = criteria or criteria_for(request)
    c = plan._context(request, factor)
    role = w["decide_role"].format(chapter=c["chapter"], total=c["total"]) if c["total"] else w["decide_role_unknown_total"].format(chapter=c["chapter"])

    def combo_of(i: int) -> dict | None:
        return combos[options[i][0] - 1] if combos is not None and 1 <= options[i][0] <= len(combos) else None
    shown = "\n\n".join(_item(w, LABELS[n], options[i][1], combo_of(i)) for n, i in enumerate(order))
    first = c["chapter"] == 1
    names = ", ".join(criteria[:-1]) + f" and {criteria[-1]}" if len(criteria) > 1 else criteria[0]
    output = w["decide_output"].format(criteria=names, language=plan.language_name(request.get("language")), held_limit=HELD_MAX, limit=PHRASE_ASK)
    task = [w["decide_task"], w["decide_combos"] if combos is not None else "", *(w[f"decide_{k}_first" if first else f"decide_{k}"] for k in criteria), output]
    blocks = [role, c["setup_block"], c["history_block"], plan._section(c["heads"]["decide"], shown), plan._section(c["heads"]["task"], "\n\n".join(x for x in task if x))]
    return "\n\n".join(b for b in blocks if b)


# ---- The reply ------------------------------------------------------------------------------------------------------------------

def grammar(n: int, criteria: tuple[str, ...] = CRITERIA) -> dict:
    """One object per criterion: `held` (what the story holds now) first, then a text for each lettered option, then `best` and `worst` (the
    letters of the best and the worst option on that criterion): the model reasons before it judges. No pick and no scores: the code makes those."""
    labels = list(LABELS[:n])
    entry = {"held": {"type": "string"}, **{label: {"type": "string"} for label in labels}, "best": {"type": "string", "enum": labels}, "worst": {"type": "string", "enum": labels}}
    one = {"type": "object", "properties": entry, "required": list(entry), "additionalProperties": False}
    return {"type": "object", "properties": {k: one for k in criteria}, "required": list(criteria), "additionalProperties": False}


def decide_problem(value: Any, n: int, criteria: tuple[str, ...] = CRITERIA) -> str | None:
    """None when the reply is usable, else one plain line saying what to fix: a criterion, `held` or a text missing, `held` or a text empty or too
    long, or a best and worst that are not two different letters of the options shown."""
    p = common.load_text("plan")["problems"]
    labels = tuple(LABELS[:n])
    entries = [value.get(k) if isinstance(value, dict) else None for k in criteria]
    if not all(isinstance(e, dict) and "held" in e and all(label in e for label in labels) for e in entries):
        return p["decide_shape"]
    if any(not isinstance(e["held"], str) or not e["held"].strip() or len(e["held"]) > HELD_MAX for e in entries):
        return p["decide_phrase"]
    if any(not isinstance(e[label], str) or not e[label].strip() or len(e[label]) > PHRASE_MAX for e in entries for label in labels):
        return p["decide_phrase"]
    if any(e.get("best") not in labels or e.get("worst") not in labels or e["best"] == e["worst"] for e in entries):
        return p["decide_best_worst"]
    return None


def step(request: dict, options: list[tuple[int, str]], order: list[int], on_fallback, criteria: tuple[str, ...] | None = None,
         combos: list[dict] | None = None) -> Step:
    """The decide step: JSON at the low-temperature set (the shuffle, not the sampling, keeps one position from winning by habit), a cap sized
    for the longest reply (see MAX_OUTPUT), two attempts. Its last resort is `{}`, which makes no model call and picks a random option (`on_fallback` notes it)."""
    n = len(order)
    criteria = criteria or criteria_for(request)

    def none():
        on_fallback()
        return {}
    return Step("decide", lambda f: build_decide_prompt(request, options, order, f, criteria, combos), "json", MAX_OUTPUT, grammar(n, criteria),
                lambda value: decide_problem(value, n, criteria), SAMPLING, False, attempts=ATTEMPTS, fallback=none)


# ---- Invented names -------------------------------------------------------------------------------------------------------------

PENALTY = 1                # the points an option loses for naming a person on no card: a penalty, never an elimination
_BOLD_HEAD = re.compile(r"^[ \t#]*(\*\*|__).*?\1[ \t]*")      # a header's bold span: its label and title, whose capitals are not names


def _body(text: str) -> str:
    """The option's text without its header's label and title (\"**Option 2: A Title**\"): a title's capitalised words would read as names. Words
    after a bold header on the same line stay."""
    head, _, rest = text.partition("\n")
    return (_BOLD_HEAD.sub("", head, count=1) if _OPTION.match(head) else head) + ("\n" + rest if rest else "")


def invented(request: dict, options: list[tuple[int, str]]) -> list[bool]:
    """One flag per option, in the brainstorm's order: True when the option's own text (without its header's title) names a person on no card and in no earlier chapter's
    record (the same inputs `plan.plan_names` uses). A story in a language the detector does not read has no flags."""
    allowed = [request.get(k) for k in ("cast", "world", "ties", "holdings", "setup", "style")]
    earlier = common.earlier_records(request, beats=True)
    return [bool(common.minor_people(request, [_body(text)], allowed, earlier)[1]) for _, text in options]


# ---- The pick -------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    combo: int                                  # the picked option's original combination number
    position: int                               # its place in the brainstorm's options, from 1
    fell_back: bool                             # True when the reply could not be used and a random option stands
    order: tuple[int, ...]                      # the places of the options in the order they were shown, from 1
    scores: tuple[int, ...] = ()                # the totals by place in the brainstorm, from 1
    tied: int = 0                               # how many options shared the top total
    marks: dict[str, tuple[str, str]] = field(default_factory=dict)       # per criterion, the best and the worst: shown letter + brainstorm place, "A1"
    invented: int = 0                           # how many options named a person on no card and so lost a point
    places: tuple[int, ...] = ()                # when only some of the brainstorm's options were judged: the place (from 1) of each judged option, in the order given; empty means all of them, places 1 to n
    single: bool = False                        # True when one option was left and no call was made: it was chosen directly

    def notes(self) -> dict[str, Any]:
        """For the run log: numbers and short plain words only. It carries everything needed to adjust after a run, without the trace: the
        totals by place, and per criterion the best and the worst as the letter shown and the place it had (a habit of favoring a screen
        position shows in the letters, a habit of favoring an outcome in the places). The phrases stay in the trace."""
        places = self.places or tuple(range(1, len(self.order) + 1))
        out: dict[str, Any] = {"decide": "fallback" if self.fell_back else "single" if self.single else "on", "decide_options": len(self.order), "decide_order": "-".join(map(str, self.order)),
                               "decide_pick": self.position, "decide_combo": self.combo, "decide_sampling": SAMPLING}
        out.update({f"decide_s{place}": total for place, total in zip(places, self.scores)})
        out["decide_tied"] = self.tied
        out["decide_invented"] = self.invented
        for criterion, (best, worst) in self.marks.items():
            out[f"decide_{criterion}_best"], out[f"decide_{criterion}_worst"] = best, worst
        return out


def scores(value: Any, n: int, criteria: tuple[str, ...] = CRITERIA) -> list[int]:
    """The points of each shown letter: +1 for each criterion it is best on, -1 for each it is worst on."""
    total = [0] * n
    for k in criteria:
        entry = value.get(k) if isinstance(value, dict) else None
        if isinstance(entry, dict):
            for key, points in (("best", 1), ("worst", -1)):
                if entry.get(key) in tuple(LABELS[:n]):
                    total[LABELS.index(entry[key])] += points
    return total


def decide(options: list[tuple[int, str]], order: list[int], value: Any, criteria: tuple[str, ...] = CRITERIA, flagged: list[bool] | None = None,
           places: list[int] | None = None) -> Decision:
    """The picked option, from the step's result: the highest total, and among equal totals one chosen at random. `flagged` (from `invented`, one
    flag per option in the brainstorm's order) takes a point off each option that names a person on no card, before the winner is chosen. A result
    that is not usable (the fallback `{}`, or a reply the check would refuse) picks a random option and sets `fell_back`: nothing was compared, so
    nothing is penalized, though the count of flagged options is still noted. `places` (the brainstorm's place, from 1, of each of `options`) says
    which of the brainstorm's options these are when some were dropped before the call: the picked place, the order shown and the marks then use
    the brainstorm's places, never the ones among the survivors; `flagged` stays one flag per option given."""
    n = len(order)
    kept = list(places) if places else list(range(1, len(options) + 1))
    shown = tuple(kept[i] for i in order)
    flags = [bool(flagged[i]) if flagged and i < len(flagged) else False for i in range(len(options))]
    count = sum(flags[i] for i in order)
    if decide_problem(value, n, criteria) is not None:
        place = random.choice(order)
        return Decision(options[place][0], kept[place], True, shown, (0,) * n, n, invented=count, places=tuple(kept) if places else ())
    by_letter = [total - PENALTY * flags[order[k]] for k, total in enumerate(scores(value, n, criteria))]
    top = max(by_letter)
    letter = random.choice([k for k, total in enumerate(by_letter) if total == top])
    place = order[letter]
    by_place = [0] * n
    for k, total in enumerate(by_letter):
        by_place[order[k]] = total
    marks = {k: tuple(f"{value[k][side]}{kept[order[LABELS.index(value[k][side])]]}" for side in ("best", "worst")) for k in criteria}
    return Decision(options[place][0], kept[place], False, shown, tuple(by_place), by_letter.count(top), marks, count, tuple(kept) if places else ())


def only(options: list[tuple[int, str]], place: int, places: list[int] | None = None, flagged: list[bool] | None = None) -> Decision:
    """The decision when one option is left: it is chosen directly and no call is made. `place` is its index in `options`; `places` as for `decide`."""
    kept = list(places) if places else list(range(1, len(options) + 1))
    count = int(bool(flagged[place])) if flagged and place < len(flagged) else 0
    return Decision(options[place][0], kept[place], False, (kept[place],), (0,), 1, invented=count, places=(kept[place],), single=True)


def stand_in(words: int) -> list[tuple[int, str]]:
    """The three options, each as long as the brainstorm allows, for the worst case: the step reads them in full."""
    return [(n, "word " * (words // OPTIONS_MAX)) for n in range(1, OPTIONS_MAX + 1)]
