"""Repeat avoidance (Plan 7). Chapters repeat the same kind of beat with different surface details, so a chapter is described by a FINGERPRINT of
discrete labels that a model sets, and code compares the labels by equality only: the model never compares texts, and code never compares text.
An idea that matches the recent chapters on too many labels is too similar (`T` of the seven compared labels against any of the last `K` chapters).

This module holds the vocabulary (the one place the allowed values live; they are structural, never story content), the validator, the comparison
(`matches`, `screen`), the label call's grammar and its step (`label_step`). Wording lives in text/en/plan.yaml (the `label_*` keys). Nothing here
is wired into the flow yet (plan.py does that in the later steps)."""
from typing import Any, NamedTuple

from pulpermill.prompter.base import Step

from . import common

VERSION = "repeat-2"

K = 3          # an idea is compared with the last K earlier chapters
T = 4          # an idea is too similar when it matches one of them on at least T labels (a starting value, tuned on a real run; with `motive_kind` it is 4 of seven, not of six: tune it on a real run)

AIM_KINDS = ("obtain", "keep", "prevent", "persuade", "reach", "discover", "deliver", "repair", "escape", "protect", "other")
OBSTACLE_SOURCES = ("person", "group", "rule", "object", "place", "self", "time", "other")
TURNING_KINDS = ("refusal", "concession", "discovery", "reversal", "arrival", "loss", "bargain", "breakage", "confrontation", "other")
OUTCOMES = ("reached", "lost", "gave_up", "other")
CLOSING_HOOKS = ("new_task", "arrival", "discovery", "loss", "deadline", "decision", "nothing", "other")
MOTIVE_KINDS = ("recognition", "closeness", "protection", "avoidance", "duty", "order", "curiosity", "gain", "other")      # why the protagonist wants what they go after
NO_PARTY = "none"           # the obstacle_party of a chapter whose obstacle is no one on the list

VALUES = {"aim_kind": AIM_KINDS, "obstacle_source": OBSTACLE_SOURCES, "turning_kind": TURNING_KINDS, "outcome": OUTCOMES, "closing_hook": CLOSING_HOOKS, "motive_kind": MOTIVE_KINDS}
FIELDS = ("aim_kind", "obstacle_source", "obstacle_party", "turning_kind", "outcome", "closing_hook", "motive_kind")      # the seven labels code compares
NOTE = "turning_note"                                                                                       # one plain sentence: for the prompt table, never compared
KEYS = FIELDS + (NOTE,)
NEUTRAL = ("other", NO_PARTY)       # a label that says nothing never counts as a match
NOTE_MAX = 240                      # the longest turning_note kept, in characters

Fingerprint = dict[str, str]        # the eight keys of KEYS, each a string

LABEL_ATTEMPTS = 2                  # then no labels, no gate: labelling is a help to the plan, never a reason to fail a call
LABEL_MAX_OUTPUT = 700              # K entries of about 80 tokens (the note and seven short values, JSON included), with room to spare
TEXT_LIMIT = 1500                   # the most characters of one text the labeler reads
LABEL_STAND_IN = "word " * 300      # the longest text as the labeler can be shown it (1,500 characters), for the worst case
SAMPLING = "structured"


# ---- The fingerprint ------------------------------------------------------------------------------------------------------------

def clean(raw: Any, names: list[str] | None = None) -> Fingerprint:
    """A fingerprint with every key present and every value usable: a value outside its vocabulary, or a missing one, becomes `other`; an
    obstacle_party that is not one of `names` (or is missing) becomes `none`; the note is a trimmed string cut to NOTE_MAX (empty when missing)."""
    raw = raw if isinstance(raw, dict) else {}
    out: Fingerprint = {}
    for key, allowed in VALUES.items():
        value = raw.get(key)
        out[key] = value if isinstance(value, str) and value in allowed else "other"
    party = raw.get("obstacle_party")
    by_lower = {str(n).strip().lower(): str(n).strip() for n in names or [] if str(n).strip()}
    out["obstacle_party"] = by_lower.get(party.strip().lower(), NO_PARTY) if isinstance(party, str) else NO_PARTY
    note = raw.get(NOTE)
    out[NOTE] = " ".join(note.split())[:NOTE_MAX] if isinstance(note, str) else ""
    return {key: out[key] for key in KEYS}


def matched(a: Fingerprint, b: Fingerprint) -> tuple[str, ...]:
    """The names of the compared fields on which `a` and `b` are equal, in FIELDS order. A field whose value is `other` or `none` never matches."""
    return tuple(f for f in FIELDS if a.get(f) == b.get(f) and a.get(f) not in NEUTRAL and a.get(f) is not None)


def matches(a: Fingerprint, b: Fingerprint) -> int:
    """How many of the seven compared fields are equal and say something (not `other`, not `none`). The note is never compared."""
    return len(matched(a, b))


class Screen(NamedTuple):
    matches: int                    # the idea's highest `matches` against the last K earlier chapters (0 when it has no fingerprint or nothing to compare with)
    fields: tuple[str, ...]         # the names of the fields that matched in that best pairing


def screen(idea_prints: list[Fingerprint | None], earlier_prints: list[Fingerprint | None]) -> list[Screen]:
    """For each idea its best match against `earlier_prints[-K:]`. Earlier chapters with no fingerprint (None) are skipped, and so is an idea
    with none (it scores 0). When two chapters match equally, the more recent one is the pairing whose field names are returned."""
    recent = [p for p in list(earlier_prints)[-K:] if p]
    out = []
    for idea in idea_prints:
        best = Screen(0, ())
        if idea:
            for old in reversed(recent):             # newest first, so a tie keeps the most recent chapter
                fields = matched(idea, old)
                if len(fields) > best.matches:
                    best = Screen(len(fields), fields)
        out.append(best)
    return out


def too_similar(result: Screen) -> bool:
    return result.matches >= T


# ---- The label call ---------------------------------------------------------------------------------------------------------------

def grammar(count: int) -> dict:
    """{prints: [one entry per text]}: each entry is the text's number `n`, then its note (so the model says what turned before it labels), then
    the labels. Only the number of entries is fixed by the check, not by the grammar (a list of exactly `count` would force a reply for a text
    that was not there). The fixed vocabularies are enums; the party is a free string that `clean` checks against the names."""
    text = {"type": "string"}
    entry: dict[str, Any] = {"n": {"type": "integer"}, NOTE: text}
    for key in FIELDS:
        entry[key] = {"type": "string", "enum": list(VALUES[key])} if key in VALUES else text
    one = {"type": "object", "properties": entry, "required": list(entry), "additionalProperties": False}
    return {"type": "object", "properties": {"prints": {"type": "array", "items": one, "minItems": count, "maxItems": count}},
            "required": ["prints"], "additionalProperties": False}


def label_problem(value: Any, count: int) -> str | None:
    """None when the reply holds one entry for each text, else one plain line saying what to fix. The values inside an entry are not refused:
    `clean` turns any unusable one into `other`."""
    prints = value.get("prints") if isinstance(value, dict) else None
    if not isinstance(prints, list) or len(prints) != count or not all(isinstance(p, dict) for p in prints):
        return common.load_text("plan")["problems"]["label_count"].format(count=count)
    return None


def read(value: Any, items: list[tuple[int, str]], names: list[str]) -> list[Fingerprint | None]:
    """The fingerprints of a label reply, one for each of `items` in their order. An entry is matched to its text by its number `n`; when the
    numbers are not usable the entries are taken in order. A reply that cannot be read (the fallback `{}`) gives None for every text."""
    if label_problem(value, len(items)) is not None:
        return [None] * len(items)
    prints = value["prints"]
    by_number = {p.get("n"): p for p in prints if isinstance(p.get("n"), int) and not isinstance(p.get("n"), bool)}
    numbers = [n for n, _ in items]
    keyed = len(by_number) == len(prints) and set(by_number) == set(numbers)
    return [clean(by_number[n] if keyed else prints[i], names) for i, n in enumerate(numbers)]


def build_label_prompt(request: dict, items: list[tuple[int, str]], names: list[str], factor: float = 1.0) -> str:
    """The labeler's prompt: the role, the texts under their numbers, the names the obstacle may be one of, then the task (each field in words
    with its allowed values) and the answer instruction. No story cards, no setup: the labeler reads only the texts it is to label."""
    from . import plan
    w = common.load_text("plan")
    heads = w["headings"]
    shown = "\n\n".join(w["label_item"].format(n=n, text=common.clip(str(text or "").strip()[:TEXT_LIMIT], factor)) for n, text in items)
    named = "\n".join(names) if names else w["label_no_names"]
    fields = [w["label_aim_kind"].format(values=", ".join(AIM_KINDS)),
              w["label_obstacle_source"].format(values=", ".join(OBSTACLE_SOURCES)),
              w["label_obstacle_party"].format(none=NO_PARTY),
              w["label_turning_kind"].format(values=", ".join(TURNING_KINDS)),
              w["label_outcome"].format(values=", ".join(OUTCOMES)),
              w["label_closing_hook"].format(values=", ".join(CLOSING_HOOKS)),
              w["label_motive_kind"].format(values=", ".join(MOTIVE_KINDS)),
              w["label_note"].format(language=plan.language_name(request.get("language")))]
    task = [w["label_task"], *fields, w["label_output"].format(count=len(items))]
    blocks = [w["label_role"], plan._section(heads["label_texts"], shown), plan._section(heads["label_names"], named),
              plan._section(heads["task"], "\n\n".join(task))]
    return "\n\n".join(b for b in blocks if b)


def label_step(request: dict, items: list[tuple[int, str]], names: list[str]) -> Step:
    """The label step: one JSON call that labels every text of `items` (each a number and its text) and returns one fingerprint for each, at the
    structured set, with a small number of attempts. Its last resort is `{}`, which makes no model call and reads as no labels: no table and no
    gate, never an error. Read the result with `read(value, items, names)`."""
    count = len(items)
    return Step("label", lambda f: build_label_prompt(request, items, names, f), "json", LABEL_MAX_OUTPUT, grammar(count),
                lambda value: label_problem(value, count), SAMPLING, False, attempts=LABEL_ATTEMPTS, fallback=lambda: {})
