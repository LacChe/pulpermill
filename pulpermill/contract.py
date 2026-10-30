"""The conversation between the page and the backend: what the page sends and what comes back.
Shapes only. This file runs no model and starts no server; the backend validates every request with parse_request and
builds every reply from the models below, so a reply that leaves the backend is one the page can read.
The same examples are checked here (tests/schema/test_contract.py) and in the page's tests (tests/web/, reading
tests/shared/contract-vectors.json), so the two sides cannot drift apart without a test failing. The contract is frozen at
the end of P3 (P0, A7): a change needs a new dated amendment to the Decision Record.

Every call is a POST of one JSON object to <address>/api. The call is named inside it. Every reply is a JSON object
with "ok": true and the call's own fields, or "ok": false and an "error". The backend is stateless: a request carries
everything the call needs, and a failed or stopped call changes nothing."""
from typing import Annotated, Any, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

# The cards a fill can write. Outline needs a plan, not a fill, so it is not here.
FillableCard = Literal["style", "characters", "world", "entanglements", "setup"]
# The cards a person edits, for the calls that can be about any of them.
UserCard = Literal["style", "characters", "world", "entanglements", "setup", "outline"]

# What a backend may answer with. The page makes two more by itself, so a backend never sends them:
#   unreachable  nothing answered at all
#   timeout      no answer in time
BackendErrorKind = Literal["busy", "bad_request", "bad_output", "too_long", "stopped", "server", "unauthorized"]
PAGE_ERROR_KINDS = ("unreachable", "timeout")

# The HTTP status that goes with each error, so a plain HTTP client can tell them apart. The body is what the page
# reads first; the status is the fallback for a body that is not an answer.
HTTP_STATUS = {"busy": 503, "bad_request": 400, "bad_output": 502, "too_long": 413, "stopped": 409, "server": 500, "unauthorized": 401}


class Strict(BaseModel):
    """Nothing extra is allowed, so a field added on one side and forgotten on the other fails a test. Strict, so
    "yes" is not true and "1" is not 1: the page checks the same way."""
    model_config = ConfigDict(extra="forbid", strict=True)


# ---- Requests -----------------------------------------------------------------------------------------------------

class Envelope(Strict):
    """What every call but status starts with."""
    schema_version: int          # the project file format the page speaks; a backend that knows only older ones answers bad_request
    language: str                # the language the model writes in. Instructions to the model stay in English.
    job_id: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    # The page's own name for this call. With one, the backend keeps the call going if the connection drops and keeps its
    # answer for the page to fetch later (call "job"); a call that is stopped is stopped with call "cancel". Without one,
    # a dropped connection stops the call, as before.


class StatusRequest(Strict):
    """Asks whether the backend is free. The one call that is not a model call; the page may send it by itself."""
    call: Literal["status"]


_JOB_ID = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class JobRequest(Strict):
    """Asks what became of a call that carried this job_id: still running, finished (the reply is the call's own reply or
    error, exactly as the call would have answered), or unknown (never seen, forgotten, or the backend was restarted)."""
    call: Literal["job"]
    job_id: str = _JOB_ID


class CancelRequest(Strict):
    """Stops the running call that carried this job_id. Nothing is changed by a stopped call."""
    call: Literal["cancel"]
    job_id: str = _JOB_ID


class FillRequest(Envelope):
    """Fill one card from the writer's note and/or the example chapter. A fill of Entanglements concerns ties and holdings only."""
    call: Literal["fill"]
    card: FillableCard
    instance: str | None = None             # which character, for Characters; null for every other card
    note: str | None = None                 # the writer's note for this card, exactly as typed
    example_chapter: str | None = None
    values: dict[str, Any]                  # the card as it stands now, by field key
    related: dict[str, Any]                 # the cards this one reads, by card id: never the whole project

    @model_validator(mode="after")
    def _has_a_source_and_a_target(self):
        if not (self.note or "").strip() and not (self.example_chapter or "").strip():
            raise ValueError("a fill needs a note or an example chapter to fill from")
        if (self.card == "characters") != (self.instance is not None):
            raise ValueError("instance is given for Characters, and only for Characters")
        return self


class JudgeRule(Strict):
    id: str
    fields: list[str]                       # the card fields the rule is about


class JudgeRequest(Envelope):
    """The model-judged rules for one card. `rules` holds only the ones that need asking about now."""
    call: Literal["judge"]
    card: UserCard
    instance: str | None = None
    rules: list[JudgeRule]
    values: dict[str, Any]
    related: dict[str, Any]


class StyleFitRequest(Envelope):
    """Does the protagonist's personality allow the person, tense and voice the Style card chose?"""
    call: Literal["style_fit"]
    style: dict[str, Any]
    protagonist: dict[str, Any]


# ---- The story calls ----------------------------------------------------------------------------------------------
# The page does the code work (picking the spotlight tie, the cast, what is in play, and the effective state: each card's base
# values plus its shifts, P0 A6) and sends the result. The backend renders prose from it, runs the model and answers in words.
# It never applies a shift and never makes an id. Cards and records inside these requests are the project's own values,
# copied, with their ids, already reduced to what is in play (how they are reduced is the page's choice, not the contract's).


class PlanRetry(Strict):
    """A first attempt the page's block rules refused, sent back with the rules' words so the second attempt can fix it."""
    beat: dict[str, Any]
    problems: list[str]


class _StoryRequest(Envelope):
    """What `plan` and `generate` share: where we are, the voice, who is in the chapter and how they are tied."""
    chapter: int
    chapter_count: int
    style: dict[str, Any]
    setup: dict[str, Any]                   # `generate` sends the opening (normal, disruption) only in chapter 1
    protagonist: str                        # the protagonist's character id
    cast: list[dict[str, Any]]              # effective Characters cards, with ids
    world: dict[str, Any]                   # effective World values: places and objects, the groups in play, rules, terms
    ties: list[dict[str, Any]]              # the ties among the cast, plus ties from a cast member to a group, with ids
    holdings: list[dict[str, Any]]          # holdings of cast members and of the groups in play, with ids


class PlanRequest(_StoryRequest):
    """Fill the beat's planner fields: where, when_time, aim and plan."""
    call: Literal["plan"]
    spotlight: str                          # the id of the spotlight tie, one of `ties`
    earlier_beats: list[dict[str, Any]]     # earlier beats in words: chapter, where, when, aim, plan
    earlier_events: list[dict[str, Any]]    # earlier Events entries: chapter, happened, changed
    retry: PlanRetry | None = None

    @model_validator(mode="after")
    def _spotlight_is_one_of_the_ties(self):
        if self.spotlight not in {t.get("id") for t in self.ties}:
            raise ValueError("spotlight must be the id of one of the ties sent")
        return self


class GenerateRequest(_StoryRequest):
    """Write the chapter, then say what happened and what changed. One call, all or nothing."""
    call: Literal["generate"]
    earlier_events: list[dict[str, Any]]
    previous_ending: str | None = None      # the end of the last chapter, or null for chapter 1
    beat: dict[str, Any]                    # the beat in words, not ids, including its aim and plan


Request = Annotated[Union[StatusRequest, JobRequest, CancelRequest, FillRequest, JudgeRequest, StyleFitRequest, PlanRequest,
                          GenerateRequest], Field(discriminator="call")]
_request = TypeAdapter(Request)


def parse_request(data: Any):
    """A request the backend can act on, or pydantic.ValidationError (answer bad_request)."""
    return _request.validate_python(data)


# ---- Replies ------------------------------------------------------------------------------------------------------

class ErrorBody(Strict):
    kind: BackendErrorKind
    detail: str = ""                        # displayed to the writer for server and bad_request only; plain words


class ErrorReply(Strict):
    """Any call can fail. Nothing was changed, and the writer presses the button again."""
    ok: Literal[False]
    error: ErrorBody


class Progress(Strict):
    """What a busy backend says it is doing, so the page can show progress by asking status. `name` is any short word the
    backend likes; the page shows a generic label for one it does not know. `index` is the step number, from 1, and `of` is
    the number of steps when that is known."""
    name: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    index: int = Field(ge=1)
    of: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _index_is_within_of(self):
        if self.of is not None and self.index > self.of:
            raise ValueError("index cannot be larger than of")
        return self


class StatusReply(Strict):
    ok: Literal[True]
    state: Literal["idle", "busy"]
    stage: Progress | None = None           # only when busy, and only if the backend knows


class JobReply(Strict):
    """A call that has not finished: the answer to `job` while it runs, or when the backend does not know it."""
    ok: Literal[True]
    state: Literal["running", "unknown"]
    stage: Progress | None = None


class CancelReply(Strict):
    ok: Literal[True]
    state: Literal["cancelled", "unknown"]


class FillReply(Strict):
    """The card's fields by key. A field the model has nothing for is left out or empty, and the page leaves what
    the writer wrote there alone. A field that links to another card's entry is named in words ("Suvi"), never by id:
    the page turns the words into ids. A list is a list of objects without ids."""
    ok: Literal[True]
    values: dict[str, Any]


class Hit(Strict):
    field: str                              # a field of the card
    item: str | None = None                 # the id of the list item, as sent in `values`
    key: str | None = None                  # the box inside that item


class JudgeResult(Strict):
    rule: str
    hits: list[Hit]                         # where the rule is broken; an empty list means it passed


class JudgeReply(Strict):
    """One result per rule asked about. A rule with no result is not counted as passed."""
    ok: Literal[True]
    results: list[JudgeResult]


class StyleFitReply(Strict):
    ok: Literal[True]
    fits: bool
    message: str = ""                       # when it does not fit: what to look at, in the writer's language


class PlanReply(Strict):
    """The beat's planner fields by key: where, when_time, aim and plan. A link is a word (a place's name). The plan text is
    part of the beat."""
    ok: Literal[True]
    beat: dict[str, Any]


class EventsOut(Strict):
    """What the chapter text shows happened."""
    happened: str
    changed: str | None = None


class ListOp(Strict):
    """One operation on a list field inside a patch. `id` names an existing item exactly as it was sent; the backend turns
    what the model referred to into those ids and never makes one. `values` holds the item's values, with words, not ids,
    for links; the page turns the words into ids and gives each `add` its id when the shift lands."""
    op: Literal["add", "replace", "remove"]
    id: str | None = Field(default=None, min_length=1)
    values: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _is_consistent(self):
        if self.op == "add":
            if self.id is not None:
                raise ValueError("add names no id: the page gives the new item its id")
            if not self.values:
                raise ValueError("add needs values")
        elif self.op == "replace":
            if self.id is None:
                raise ValueError("replace needs the id of an existing item")
            if not self.values:
                raise ValueError("replace needs values")
        else:
            if self.id is None:
                raise ValueError("remove needs the id of an existing item")
            if self.values is not None:
                raise ValueError("remove takes no values")
        return self


# A patch value is a scalar's new value, or, for a list field, a list of operations.
PatchValue = Union[list[ListOp], str, int, float, bool, None]


class ShiftOut(Strict):
    """What changed for one card, as a sparse copy of that card (P0, A1 to A3). The page stores it as a shift and checks the
    patch against the card (validate_patch in pulpermill/schema/shifts.py); the contract carries its shape only."""
    card: Literal["characters", "world", "entanglements"]
    target: str | None = None               # the character id as sent, for Characters; null for World and Entanglements
    patch: dict[str, PatchValue]            # a partial card: a scalar is its new value, a list field is a list of ListOp

    @model_validator(mode="after")
    def _target_matches_card(self):
        if (self.card == "characters") != (self.target is not None):
            raise ValueError("target is the character id for Characters, and null for World and Entanglements")
        if not self.patch:
            raise ValueError("a patch holds nothing")
        return self


class GenerateReply(Strict):
    ok: Literal[True]
    chapter_text: str
    events: EventsOut
    shifts: list[ShiftOut]


REPLIES: dict[str, type[Strict]] = {
    "status": StatusReply, "job": JobReply, "cancel": CancelReply, "fill": FillReply, "judge": JudgeReply, "style_fit": StyleFitReply,
    "plan": PlanReply, "generate": GenerateReply,
}
_error = TypeAdapter(ErrorReply)


def parse_reply(call: str, data: Any):
    """A reply for `call` as the page reads it: an ErrorReply or the call's own reply. ValidationError if it is neither."""
    if isinstance(data, dict) and data.get("ok") is False:
        return _error.validate_python(data)
    return TypeAdapter(REPLIES[call]).validate_python(data)


def error_reply(kind: BackendErrorKind, detail: str = "") -> dict[str, Any]:
    """The body to send for a failure, with HTTP_STATUS[kind] as its status."""
    return ErrorReply(ok=False, error=ErrorBody(kind=kind, detail=detail)).model_dump()
