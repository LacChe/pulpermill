"""Shared vocabulary for every card. Conventions are recorded in CONVENTIONS.md."""
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field

# Input types are real HTML: <input type=text|number|checkbox>, <textarea>, <select>, <select multiple>.
# Structures that are not a single HTML control (lists, pairs, options fed by another card)
# are added with Characters, where they are first needed, as separate attributes.
InputType = Literal["text", "textarea", "number", "select", "select-multiple", "checkbox"]

# How a field reaches the model.
#   rule  : chosen option becomes a fixed rule sentence (expansion text)
#   axis  : chosen option becomes descriptive prose (expansion text)
#   note  : free text passed through exactly as written
#   free  : free text passed through after a lead-in sentence containing {value}
#   items : a repeating list of single-box items, joined into {items} in a lead-in sentence
#   pairs : a repeating list of multi-box items, each rendered by an item_template, joined into {items}
# Text templates may use {value}, {items}, and {name} (the card's own name field, if it has one).
#   snapshot: a whole copy of another card, kept as a record and never sent to the model
#   card  : (project file only) a whole card held by the project; the field says which with card_of
#   patch : (shifts only) a sparse copy of another card, holding only what changed; its shape comes from that card's
#           schema (see shifts.py), so it is not a single HTML control and has no input type
Kind = Literal["rule", "axis", "note", "free", "items", "pairs", "snapshot", "card", "patch"]


# Every repeating list holds at most this many items (stories run 5 to 10 chapters, so list
# types can rotate between chapters). Beyond the cap the value is rejected.
MAX_ITEMS = 5


def spec(input: InputType | None, group: str | None, kind: Kind, required: bool = True, default: Any = None, **extra: Any):
    """Declare a field. Required by default. No text length limits (those depend on model context, decided in the pipeline); repeating lists are capped at MAX_ITEMS unless declared uncapped=True.

    Extra flags used so far:
      fixed=True   a fact the story must never change (always sent in full)
      identity=True  (list item fields) says which item this is: set when the item is added and never changed by a shift
      repeat=True  a repeating list; 'input' is None and the item model declares the inputs
      counted=True list items carry use counts in project state (so each item needs an id)
      filled_by="planner"|"code"  who fills it first (beats only so far); everything stays human editable
      max_selected=N  a multi-select that may pick at most N
      limited_by="code"  choices the code may disable (legal options)
      uncapped=True a repeating list exempt from the MAX_ITEMS cap (deliberate, one at a time)
    Fields inside an item model have group=None.
    """
    meta = {"input": input, "group": group, "kind": kind, **extra}
    kwargs: dict[str, Any] = {}
    if extra.get("repeat") and not extra.get("uncapped"):
        meta["max_items"] = MAX_ITEMS
        kwargs["max_length"] = MAX_ITEMS
    if extra.get("max_selected"):                       # a multi-select that may pick at most this many
        kwargs["max_length"] = extra["max_selected"]
    return Field(... if required else default, json_schema_extra=meta, **kwargs)


def new_id() -> str:
    return uuid4().hex[:8]


class Item(BaseModel):
    """One entry in a repeating list. The id is made by the system and never typed, so counts survive edits."""
    id: str = Field(default_factory=new_id)


class TextItem(Item):
    text: str = spec("text", None, "note")


# ---- Rules -----------------------------------------------------------------
# Three severities, one meaning each:
#   reject : the value cannot be stored (not an allowed option, wrong type, too long)
#   block  : can be saved as a draft, but generation cannot start until fixed (a required field is empty)
#   warn   : advice only; the human may ignore it
# reject and block are built in for every field (enforced by the checks engine, which is not in this repo yet), so cards only declare 'warn' rules.
Severity = Literal["reject", "block", "warn"]


class Rule(BaseModel):
    id: str                          # also the key for its messages in text/<lang>/<card>.yaml
    severity: Severity
    fields: list[str]                # fields the rule looks at
    when: str                        # plain-English description of when it fires (for the spec reader)
    check: str = ""                  # name of a code check in the checks engine (not in this repo yet); empty if needs_model
    params: dict[str, Any] = {}      # settings for the code check (e.g. min / max item counts)
    context: list[str] = []          # outside data the check needs, supplied by the project
    needs_model: bool = False        # judgment call: a model pass answers it (judge_prompt in the text file)
