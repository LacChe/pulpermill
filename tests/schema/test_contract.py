"""The backend contract (pulpermill/contract.py) against the examples the page's tests also use
(tests/shared/contract-vectors.json), and against the page's own lists. Reads web/*.js as text, so no JavaScript runs here."""
import json, re
from typing import get_args
import pytest
from pydantic import ValidationError
from helpers import REPO, CARDS, card
from pulpermill import contract
from pulpermill.contract import (
    BackendErrorKind, FillableCard, UserCard, HTTP_STATUS, PAGE_ERROR_KINDS, parse_request, parse_reply, error_reply,
    FillRequest, JobRequest, CancelRequest, JudgeRequest, StatusRequest, StyleFitRequest, ErrorReply, OffstageRequest, PlanRequest, GenerateRequest,
    EndStoryRequest, STAGES,
)
from pulpermill.schema.project import UserCard as ProjectUserCard

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
              "offstage": OffstageRequest, "plan": PlanRequest, "generate": GenerateRequest, "end_story": EndStoryRequest}
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


def test_the_stages_a_busy_backend_may_name_match_the_pages():
    assert list(STAGES) == js_list(LOGIC, "STAGES")


def test_the_story_calls_match_the_pages_and_every_reply_has_a_model():
    assert set(js_list(LOGIC, "STORY_CALLS")) == {"offstage", "plan", "generate", "end_story"}
    assert set(contract.REPLIES) == {"status", "job", "cancel", "fill", "judge", "style_fit"} | set(js_list(LOGIC, "STORY_CALLS"))


def test_every_story_call_has_a_timeout_on_the_page():
    table = re.search(r"export const DEFAULT_TIMEOUTS = \{(.*?)\};", CLIENT, re.S).group(1)
    for call in js_list(LOGIC, "STORY_CALLS"):
        assert re.search(rf"\b{call}:\s*\d+", table), call


def test_a_status_that_names_an_unknown_stage_is_refused():
    with pytest.raises(ValidationError):
        parse_reply("status", {"ok": True, "state": "busy", "stage": "dreaming"})
