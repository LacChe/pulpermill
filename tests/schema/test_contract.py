"""The backend contract (pulpermill/contract.py) against the examples the page's tests also use
(tests/shared/contract-vectors.json), against the schema it sits on, and against the page's own lists that P3 did not change.
Reads web/*.js as text, so no JavaScript runs here. The page's lists of story calls and stages (web/logic.js STORY_CALLS and STAGES)
still name the removed calls until P5a rewrites them, so they are not compared here; the contract's own lists are."""
import json, re
from typing import get_args
import pytest
from pydantic import ValidationError
from helpers import REPO, CARDS, card
from pulpermill import contract
from pulpermill.contract import (
    BackendErrorKind, FillableCard, UserCard, HTTP_STATUS, PAGE_ERROR_KINDS, parse_request, parse_reply, error_reply,
    FillRequest, JobRequest, CancelRequest, JudgeRequest, StatusRequest, StyleFitRequest, ErrorReply, PlanRequest, GenerateRequest,
    ListOp, ShiftOut, Progress, StatusReply, JobReply, PlanReply, GenerateReply, EventsOut,
)
from pulpermill.schema.project import UserCard as ProjectUserCard, SCHEMA_VERSION
from pulpermill.schema.shifts import validate_patch, SHIFT_CARDS
from pulpermill.schema.outline import Beat
from pulpermill.schema.entanglements import Entanglements

STORY_CALLS = ("plan", "generate")
REMOVED_NAMES = ["goal", "story_goal", "goal_plan", "earlier_goals", "legal_shifts", "open_plants", "available_reveals", "use_counts", "standing",
                 "offstage", "latest_shifts", "Shift", "GoalChange", "Change", "NewKnowledge", "shown", "thinking", "STAGES", "end_story"]

VECTORS = json.loads((REPO / "tests" / "shared" / "contract-vectors.json").read_text(encoding="utf-8"))
LOGIC = (REPO / "web" / "logic.js").read_text(encoding="utf-8")
CLIENT = (REPO / "web" / "client.js").read_text(encoding="utf-8")


def js_list(source, name):
    body = re.search(rf"export const {name} = \[(.*?)\];", source, re.S).group(1)
    return re.findall(r'"(\w+)"', body)


def test_every_request_example_is_accepted_or_refused_as_marked():
    for case in VECTORS["requests"]:
        if case["valid"]:
            parse_request(case["data"])
        else:
            with pytest.raises(ValidationError):
                parse_request(case["data"])


def test_requests_parse_into_the_model_of_their_call():
    wanted = {"status": StatusRequest, "job": JobRequest, "cancel": CancelRequest, "fill": FillRequest, "judge": JudgeRequest, "style_fit": StyleFitRequest,
              "plan": PlanRequest, "generate": GenerateRequest}
    seen = set()
    for case in VECTORS["requests"]:
        if case["valid"]:
            parsed = parse_request(case["data"])
            assert isinstance(parsed, wanted[case["data"]["call"]]), case["name"]
            seen.add(case["data"]["call"])
    assert seen == set(wanted), "every call has a valid example"


def test_every_reply_example_is_accepted_or_refused_as_marked():
    for case in VECTORS["replies"]:
        if case["valid"]:
            parsed = parse_reply(case["call"], case["data"])
            assert isinstance(parsed, ErrorReply) == (case["data"].get("ok") is False), case["name"]
        else:
            with pytest.raises(ValidationError):
                parse_reply(case["call"], case["data"])


def test_the_replies_the_backend_builds_are_replies_the_page_reads():
    for kind in get_args(BackendErrorKind):
        body = error_reply(kind, "words")
        assert body == {"ok": False, "error": {"kind": kind, "detail": "words"}}
        parse_reply("fill", body)
    with pytest.raises(ValidationError):
        error_reply("unreachable")                      # only the page makes this one


def test_the_error_kinds_match_the_pages():
    page = set(js_list(LOGIC, "ERROR_KINDS"))
    assert page == set(get_args(BackendErrorKind)) | set(PAGE_ERROR_KINDS), sorted(page)


def test_every_error_kind_has_an_http_status_the_page_maps_back():
    assert set(HTTP_STATUS) == set(get_args(BackendErrorKind))
    table = dict((int(code), kind) for code, kind in re.findall(r"(\d{3}): \"(\w+)\"", re.search(r"const STATUS_FAILURES = \{(.*?)\};", CLIENT, re.S).group(1)))
    for kind, status in HTTP_STATUS.items():
        assert table.get(status, "server") == kind, f"HTTP {status} should read as {kind} on the page"


def test_the_fillable_cards_match_the_pages_and_exist():
    assert list(get_args(FillableCard)) == js_list(LOGIC, "FILLABLE")
    assert set(get_args(FillableCard)) <= set(CARDS)


def test_the_cards_a_person_edits_are_the_same_everywhere():
    shown = [cid for cid in CARDS if not card(cid)[4].get("hidden")]
    assert list(get_args(UserCard)) == shown == list(get_args(ProjectUserCard))


def test_the_golden_fills_carry_only_the_cards_own_fields():
    golden = {c["golden"]: c["data"] for c in VECTORS["requests"] if c.get("golden")}
    setup_fields = set(card("setup")[0].model_fields)
    assert set(golden["fill_setup"]["values"]) <= setup_fields
    character_fields = set(card("characters")[0].model_fields)
    assert set(golden["fill_character"]["values"]) <= character_fields | {"id"}
    assert golden["fill_character"]["instance"] == golden["fill_character"]["values"]["id"]


def test_the_modules_public_names_are_what_the_docs_promise():
    for name in ["parse_request", "parse_reply", "error_reply", "HTTP_STATUS", "REPLIES"]:
        assert hasattr(contract, name)


# ---- P3: the story calls, list operations, shifts and the stage object ------------------------------------------------

def names_in(x):
    """Every key and every string value in a vector, so a removed name cannot hide anywhere."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from names_in(v)
    elif isinstance(x, list):
        for v in x:
            yield from names_in(v)


def test_every_call_has_a_valid_and_an_invalid_request_and_reply_example():
    for call in contract.REPLIES:
        requests = [c for c in VECTORS["requests"] if isinstance(c["data"], dict) and c["data"].get("call") == call]
        replies = [c for c in VECTORS["replies"] if c["call"] == call]
        assert any(c["valid"] for c in requests), f"request {call} has no valid example"
        assert any(not c["valid"] for c in requests), f"request {call} has no invalid example"
        assert any(c["valid"] for c in replies), f"reply {call} has no valid example"
        assert any(not c["valid"] for c in replies), f"reply {call} has no invalid example"


def test_the_replies_cover_exactly_the_calls_the_contract_has():
    assert set(contract.REPLIES) == {"status", "job", "cancel", "fill", "judge", "style_fit"} | set(STORY_CALLS)
    assert {c["call"] for c in VECTORS["replies"]} == set(contract.REPLIES)


def test_no_removed_name_remains_in_the_contract_or_the_vectors():
    source = (REPO / "pulpermill" / "contract.py").read_text(encoding="utf-8")
    for name in REMOVED_NAMES:
        assert not re.search(rf"\b{name}\b", source), f"{name} is still in contract.py"
    assert not re.search(r"^Stage\s*=|^STAGES\s*=", source, re.M), "the fixed stage list is gone"
    everywhere = set(names_in(VECTORS["requests"])) | set(names_in(VECTORS["replies"])) | set(names_in(VECTORS["project_notes"]))
    assert not (set(REMOVED_NAMES) & everywhere), sorted(set(REMOVED_NAMES) & everywhere)


def test_the_envelope_speaks_the_projects_schema_version():
    assert SCHEMA_VERSION == 3
    for case in VECTORS["requests"]:
        if case["valid"] and case["data"].get("call") not in ("status", "job", "cancel"):
            assert case["data"]["schema_version"] == SCHEMA_VERSION, case["name"]


# The one valid story request the page never builds: it shows that the backend accepts a retry that is null. Every other valid
# story request is built by the page (tests/web/logic.test.mjs) and so is golden, under a name.
HAND_WRITTEN = {"a plan request with the retry left null"}


def test_the_story_requests_the_page_builds_are_golden_and_the_others_keep_their_names():
    for case in VECTORS["requests"]:
        if case["data"].get("call") in STORY_CALLS and case["valid"]:
            if case["name"] in HAND_WRITTEN:
                assert case.get("golden") is False, case["name"]
            else:
                assert isinstance(case.get("golden"), str) and case["golden"], f"{case['name']}: the page builds this request, so it is golden"
        if case.get("golden") not in (None, False):
            assert isinstance(case["golden"], str)


def test_the_story_requests_carry_the_fields_the_spec_lists():
    plan = {"call", "schema_version", "language", "job_id", "chapter", "chapter_count", "style", "setup", "protagonist", "cast", "world", "ties",
            "holdings", "spotlight", "earlier_beats", "earlier_events", "retry"}
    generate = {"call", "schema_version", "language", "job_id", "chapter", "chapter_count", "style", "setup", "protagonist", "cast", "world", "ties",
                "holdings", "earlier_events", "previous_ending", "beat"}
    assert set(PlanRequest.model_fields) == plan
    assert set(GenerateRequest.model_fields) == generate
    assert set(contract.PlanRetry.model_fields) == {"beat", "problems"}


def test_the_story_replies_carry_the_fields_the_spec_lists():
    assert set(PlanReply.model_fields) == {"ok", "beat"}
    assert set(GenerateReply.model_fields) == {"ok", "chapter_text", "events", "shifts"}
    assert set(EventsOut.model_fields) == {"happened", "changed"}
    assert set(ShiftOut.model_fields) == {"card", "target", "patch"}
    assert set(ListOp.model_fields) == {"op", "id", "values"}
    assert set(Progress.model_fields) == {"name", "index", "of"}
    assert set(StatusReply.model_fields) == {"ok", "state", "stage"} and set(JobReply.model_fields) == {"ok", "state", "stage"}


def test_a_plans_beat_keys_are_the_beats_planner_fields():
    planner = {n for n, f in Beat.model_fields.items() if (f.json_schema_extra or {}).get("filled_by") == "planner"}
    assert planner == {"where", "when_time", "aim", "plan"}
    for case in VECTORS["replies"]:
        if case["call"] == "plan" and case["valid"]:
            assert set(case["data"]["beat"]) <= planner, case["name"]
    for case in VECTORS["requests"]:
        if case["data"].get("call") == "plan" and case["valid"] and case["data"].get("retry"):
            assert set(case["data"]["retry"]["beat"]) <= planner, case["name"]


def test_the_shift_cards_are_the_ones_the_schema_can_shift():
    assert set(get_args(ShiftOut.model_fields["card"].annotation)) == set(SHIFT_CARDS)


def test_every_valid_shift_in_the_vectors_has_a_patch_the_schema_accepts_apart_from_the_new_ids_and_link_words():
    """The contract carries the shape; validate_patch checks a patch against its card. A valid reply's patch passes it when an add is
    given the id the page will give it and the link words are left as they are (they are words in a reply, ids once stored)."""
    seen = 0
    for case in VECTORS["replies"]:
        if case["call"] != "generate" or not case["valid"]:
            continue
        for shift in case["data"]["shifts"]:
            patch = json.loads(json.dumps(shift["patch"]))
            for ops in patch.values():
                if isinstance(ops, list):
                    for op in ops:
                        if op["op"] == "add":
                            op["id"] = "n0000001"
            problems = validate_patch(shift["card"], patch)
            blocking = [p for p in problems if p.code not in ("bad_option",)]
            assert not blocking, (case["name"], blocking)
            seen += 1
    assert seen >= 6


@pytest.mark.parametrize("op,id,values,ok", [
    ("add", None, {"a": "b"}, True), ("add", "i1", {"a": "b"}, False), ("add", None, None, False), ("add", None, {}, False),
    ("replace", "i1", {"a": "b"}, True), ("replace", None, {"a": "b"}, False), ("replace", "i1", None, False), ("replace", "i1", {}, False),
    ("remove", "i1", None, True), ("remove", None, None, False), ("remove", "i1", {"a": "b"}, False), ("remove", "", None, False),
    ("set", "i1", {"a": "b"}, False),
])
def test_a_list_operation_must_be_internally_consistent(op, id, values, ok):
    data = {"op": op}
    if id is not None: data["id"] = id
    if values is not None: data["values"] = values
    if ok:
        ListOp(**data)
    else:
        with pytest.raises(ValidationError):
            ListOp(**data)


def test_list_operations_and_shifts_are_strict():
    with pytest.raises(ValidationError):
        ListOp(op="remove", id="i1", field="name")
    with pytest.raises(ValidationError):
        ShiftOut(card="world", target=None, patch={"name": "x"}, chapter=2)
    with pytest.raises(ValidationError):
        ListOp.model_validate({"op": 1, "values": {"a": "b"}})           # strict: 1 is not an op


@pytest.mark.parametrize("card,target,ok", [
    ("characters", "c0000001", True), ("characters", None, False), ("world", None, True), ("world", "c0000001", False),
    ("entanglements", None, True), ("entanglements", "c0000001", False), ("setup", None, False), ("style", None, False), ("outline", None, False),
])
def test_a_shift_names_a_target_for_characters_and_for_nothing_else(card, target, ok):
    data = {"card": card, "target": target, "patch": {"x": "y"}}
    if ok:
        ShiftOut(**data)
    else:
        with pytest.raises(ValidationError):
            ShiftOut(**data)


def test_a_patch_can_carry_a_scalar_or_a_list_of_operations_and_nothing_else():
    ShiftOut(card="world", patch={"history": "Gaslight arrived.", "places": [{"op": "remove", "id": "p1"}]})
    with pytest.raises(ValidationError):
        ShiftOut(card="world", patch={"places": [{"op": "remove"}]})
    with pytest.raises(ValidationError):
        ShiftOut(card="world", patch={"places": {"op": "remove", "id": "p1"}})
    with pytest.raises(ValidationError):
        ShiftOut(card="world", patch={})


def test_a_fill_of_entanglements_concerns_ties_and_holdings_only():
    assert set(Entanglements.model_fields) - {"id"} == {"ties", "holdings"}
    cases = [c for c in VECTORS["requests"] if c["data"].get("call") == "fill" and c["data"].get("card") == "entanglements" and c["valid"]]
    assert cases
    for c in cases:
        assert set(c["data"]["values"]) <= {"ties", "holdings"}


def test_a_status_stage_is_an_object_with_a_name_a_step_and_maybe_a_count():
    ok = parse_reply("status", {"ok": True, "state": "busy", "stage": {"name": "anything", "index": 1}})
    assert ok.stage == Progress(name="anything", index=1, of=None)
    for stage in ("write", {"name": "write"}, {"name": "write", "index": 0}, {"name": "write", "index": 3, "of": 2}, {"name": "two words", "index": 1}, {"name": "", "index": 1}):
        with pytest.raises(ValidationError):
            parse_reply("status", {"ok": True, "state": "busy", "stage": stage})
        with pytest.raises(ValidationError):
            parse_reply("job", {"ok": True, "state": "running", "stage": stage})


def test_the_backend_never_has_to_know_a_stage_name_in_advance():
    for name in ("think", "beat", "draft", "x", "step-2", "Step_3"):
        parse_reply("status", {"ok": True, "state": "busy", "stage": {"name": name, "index": 1, "of": 5}})


def test_a_job_id_in_a_story_request_is_checked_like_any_other():
    plan = next(c["data"] for c in VECTORS["requests"] if c["data"].get("call") == "plan" and c["valid"])
    parse_request({**plan, "job_id": "plan-ch2-0001"})
    with pytest.raises(ValidationError):
        parse_request({**plan, "job_id": "short"})


def test_every_story_call_has_a_timeout_on_the_page():
    table = re.search(r"export const DEFAULT_TIMEOUTS = \{(.*?)\};", CLIENT, re.S).group(1)
    for call in STORY_CALLS:
        assert re.search(rf"\b{call}:\s*\d+", table), call


def test_the_contract_runs_no_model_and_starts_no_server():
    source = (REPO / "pulpermill" / "contract.py").read_text(encoding="utf-8")
    imports = re.findall(r"^(?:from|import)\s+(\S+)", source, re.M)
    assert set(imports) <= {"typing", "pydantic"}, imports
