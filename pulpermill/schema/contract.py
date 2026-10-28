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


# ---- The story calls ----------------------------------------------------------------------------------------------
# The page does the code work (spotlight, legal shifts, open plants, available reveals, which cards are in play) and
# sends the result; the backend renders prose from it, runs the model and answers in words. Cards and records inside
# these requests are the project's own values, copied, with their ids, filtered to the cast and what is in play.

Shift = Literal["harder", "easier"]


class OffstageRequest(Envelope):
    """Plan, only when the page says an offstage change is due: what do background groups and places do this chapter?"""
    call: Literal["offstage"]
    chapter: int
    chapter_count: int
    cast: list[dict[str, Any]]
    world: dict[str, Any]                   # the groups and places that may change, with the places' use counts
    entanglements: dict[str, Any]           # only the ties, holdings and pressures those touch
    latest_events: dict[str, Any] | None = None    # the last written chapter's Events entry; none for chapter 1


class PlanRetry(Strict):
    """A first attempt the page's block rules refused, sent back with the rules' words so the second attempt can fix it."""
    thinking: str
    beat: dict[str, Any]
    problems: list[str]


class PlanRequest(Envelope):
    """Think, then fill the beat. One call; the reply carries both the thinking and the beat."""
    call: Literal["plan"]
    chapter: int
    chapter_count: int
    style: dict[str, Any]
    setup: dict[str, Any]
    goal: str | None = None                 # the current goal, worked out by the page; none while a new one is needed, or once it ended
    goal_state: Literal["needs_goal", "ended"] | None = None   # why there is no goal: the story goes on and needs one, or it winds down
    story_goal: str | None = None           # Setup's goal, when the chapters have moved off it
    goal_plan: dict[str, Any] | None = None  # {state, due, age, since, earlier_goals, last_end, directions}: the goal arc's advice
    cast: list[dict[str, Any]]
    world: dict[str, Any]
    entanglements: dict[str, Any]
    spotlight: dict[str, Any]               # the pressure the page chose
    legal_shifts: list[Shift]
    open_plants: list[dict[str, Any]]       # [{text, chapter}]; a payoff is answered with a plant's text
    available_reveals: list[dict[str, Any]]
    use_counts: dict[str, Any]
    earlier_beats: list[dict[str, Any]]
    earlier_events: list[dict[str, Any]]
    latest_shifts: list[dict[str, Any]]
    offstage: dict[str, Any] | None = None  # {did, reach} from an offstage call
    retry: PlanRetry | None = None


class GenerateRequest(Envelope):
    """Write the chapter, then the Events pass, then the Shifts and Entanglements pass. One call, all or nothing."""
    call: Literal["generate"]
    chapter: int
    chapter_count: int
    style: dict[str, Any]
    setup: dict[str, Any]                   # normal and disruption only in chapter 1
    goal: str | None = None
    goal_state: Literal["needs_goal", "ended"] | None = None
    cast: list[dict[str, Any]]
    world: dict[str, Any]
    entanglements: dict[str, Any]
    standing: list[dict[str, Any]]          # "where they stand now": the latest shift values per cast member
    earlier_events: list[dict[str, Any]]
    previous_ending: str | None = None
    beat: dict[str, Any]                    # the beat in words, not ids
    open_plants: list[dict[str, Any]]
    available_reveals: list[dict[str, Any]]


class EndStoryRequest(Envelope):
    """After the last chapter: update Characters and World from what the records say happened."""
    call: Literal["end_story"]
    style: dict[str, Any]
    setup: dict[str, Any]
    characters: list[dict[str, Any]]
    world: dict[str, Any]
    events: list[dict[str, Any]]
    shifts: list[dict[str, Any]]


Request = Annotated[Union[StatusRequest, JobRequest, CancelRequest, FillRequest, JudgeRequest, StyleFitRequest, OffstageRequest, PlanRequest,
                          GenerateRequest, EndStoryRequest], Field(discriminator="call")]
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


# What a busy backend may say it is doing, so the page can show progress by asking status. Not a promise of order.
Stage = Literal["offstage", "think", "beat", "retry", "write", "events", "shifts", "update"]
STAGES = ("offstage", "think", "beat", "retry", "write", "events", "shifts", "update")


class StatusReply(Strict):
    ok: Literal[True]
    state: Literal["idle", "busy"]
    stage: Stage | None = None              # only when busy, and only if the backend knows


class JobReply(Strict):
    """A call that has not finished: the answer to `job` while it runs, or when the backend does not know it."""
    ok: Literal[True]
    state: Literal["running", "unknown"]
    stage: Stage | None = None


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


class OffstageReply(Strict):
    """What the background did and how it reaches the protagonist. Both, or the page refuses the move."""
    ok: Literal[True]
    did: str
    reach: str


class PlanReply(Strict):
    """The planner's free-text thinking (shown to the writer) and the beat's fields by key. Links are words: a place's
    name, character names, a rule's statement, and a payoff is the wording of an open plant that was sent."""
    ok: Literal[True]
    thinking: str
    beat: dict[str, Any]


class EventsOut(Strict):
    """What the chapter text shows happened. Links are names or the wording that was sent."""
    happened: str
    changed: str | None = None
    planted: str | None = None
    paid_off: list[str] = []
    reveals_landed: list[str] = []
    behaviors_seen: list[str] = []
    things_seen: list[str] = []
    goal_landed: bool = False


class ShiftOut(Strict):
    """One character who moved. At least one of the five is given; the page refuses an empty entry."""
    character: str
    believes: str | None = None
    fears: str | None = None
    wants: str | None = None
    refuses: str | None = None
    decided: str | None = None


class Change(Strict):
    """A proposed change to one live Entanglements field. `item` is the id the page sent; the backend never makes one."""
    section: Literal["ties", "holdings", "knowledge", "pressures"]
    item: str
    field: str
    value: Any                              # a name for a link, a list of names for several, words for text


class NewKnowledge(Strict):
    """A proposed new Knowledge entry: someone who has come to know, suspect or be misled about something that has no line
    yet, or someone who joins a line that already exists. For a new line exactly one of `rule` (the wording of a World rule) and
    `fact` (free text) is meant; the page drops an entry that gives both or neither, and one whose person or rule it cannot find.
    For an existing line `entry` is its id as the page sent it (the backend turns the handle back into it) and `rule` and `fact`
    are empty. The backend never makes an id."""
    person: str
    status: Literal["knows", "suspects", "misled"]
    rule: str | None = None
    fact: str | None = None
    belief: str | None = None               # for "misled": the false thing they believe instead
    entry: str | None = None                # the id of an existing Knowledge line this person joins


class GenerateReply(Strict):
    ok: Literal[True]
    chapter_text: str
    events: EventsOut
    shifts: list[ShiftOut]
    changes: list[Change]
    new_knowledge: list[NewKnowledge] = []      # optional: a reply without it is a reply with none
    shown: list[str] = []                       # optional: ids of the pressures, knowledge, ties and holdings the chapter actually showed


class EndStoryReply(Strict):
    """Characters (each with the id it was sent) and World, as they are after the story. The page forces fixed fields back."""
    ok: Literal[True]
    characters: list[dict[str, Any]]
    world: dict[str, Any]


REPLIES: dict[str, type[Strict]] = {
    "status": StatusReply, "job": JobReply, "cancel": CancelReply, "fill": FillReply, "judge": JudgeReply, "style_fit": StyleFitReply,
    "offstage": OffstageReply, "plan": PlanReply, "generate": GenerateReply, "end_story": EndStoryReply,
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
