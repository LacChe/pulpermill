"""The conversation between the page and the backend: what the page sends and what comes back.
Shapes only. This file runs no model and starts no server; the backend validates every request with parse_request and
builds every reply from the models below, so a reply that leaves the backend is one the page can read.
The written description is docs/backend-contract.md. The same examples are checked here and in the page's tests
(web/tests/contract-vectors.json), so the two sides cannot drift apart without a test failing.

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
BackendErrorKind = Literal["busy", "bad_request", "bad_output", "too_long", "stopped", "server"]
PAGE_ERROR_KINDS = ("unreachable", "timeout")

# The HTTP status that goes with each error, so a plain HTTP client can tell them apart. The body is what the page
# reads first; the status is the fallback for a body that is not an answer.
HTTP_STATUS = {"busy": 503, "bad_request": 400, "bad_output": 502, "too_long": 413, "stopped": 409, "server": 500}


class Strict(BaseModel):
    """Nothing extra is allowed, so a field added on one side and forgotten on the other fails a test. Strict, so
    "yes" is not true and "1" is not 1: the page checks the same way."""
    model_config = ConfigDict(extra="forbid", strict=True)


# ---- Requests -----------------------------------------------------------------------------------------------------

class Envelope(Strict):
    """What every call but status starts with."""
    schema_version: int          # the project file format the page speaks; a backend that knows only older ones answers bad_request
    language: str                # the language the model writes in. Instructions to the model stay in English.


class StatusRequest(Strict):
    """Asks whether the backend is free. The one call that is not a model call; the page may send it by itself."""
    call: Literal["status"]


class FillRequest(Envelope):
    """Fill one card from the writer's note and/or the example chapter."""
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


Request = Annotated[Union[StatusRequest, FillRequest, JudgeRequest, StyleFitRequest], Field(discriminator="call")]
_request = TypeAdapter(Request)


def parse_request(data: Any):
    """A request the backend can act on, or pydantic.ValidationError (answer bad_request)."""
    return _request.validate_python(data)


# ---- Replies ------------------------------------------------------------------------------------------------------

class ErrorBody(Strict):
    kind: BackendErrorKind
    detail: str = ""                        # shown to the writer for server and bad_request only; plain words


class ErrorReply(Strict):
    """Any call can fail. Nothing was changed, and the writer presses the button again."""
    ok: Literal[False]
    error: ErrorBody


class StatusReply(Strict):
    ok: Literal[True]
    state: Literal["idle", "busy"]


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


REPLIES: dict[str, type[Strict]] = {
    "status": StatusReply, "fill": FillReply, "judge": JudgeReply, "style_fit": StyleFitReply,
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
