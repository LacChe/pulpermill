"""C1 item 4: the spotlight tie is the one `beat.spotlight` names. The writer, events and shifts steps use exactly that tie even when the plan names
three people, or two ties join the same two people (name matching would find several). A request without the key, or with a key that is not among
its ties, falls back without raising. The shifts check judges that tie's edge only. No model, no network."""
import copy
import json

import pytest

from test_coverage_support import GENERATE, MARIT, SUVI, flow_for, generate_request, prompts, sections
from pulpermill.backend.kit import Kit
from pulpermill.prompter.mill import generate as gen

NELL = {**copy.deepcopy(MARIT), "id": "c0000003", "name": "Nell"}
EDGES = {"t1000001": "to keep the ledger from her sister", "t1000002": "to win back her sister's trust", "t1000003": "to hide the harbour debt from Suvi",
         "t1000004": "to stand between Nell and the auditor"}


def tie(ident, a, b, edge):
    return {"id": ident, "tie_from": a, "tie_to": b, "bond": "family", "edge": edge}


def crowded(spotlight="t1000002", plan="Suvi, Marit and Nell meet on the quay."):
    """Three people named in the plan; two ties join the same two people (Marit and Suvi, each way); the spotlight is the second of four."""
    def mutate(q):
        q["cast"] = [copy.deepcopy(SUVI), copy.deepcopy(MARIT), copy.deepcopy(NELL)]
        q["ties"] = [tie("t1000001", "c0000002", "c0000001", EDGES["t1000001"]), tie("t1000002", "c0000001", "c0000002", EDGES["t1000002"]),
                     tie("t1000003", "c0000002", "c0000003", EDGES["t1000003"]), tie("t1000004", "c0000003", "c0000001", EDGES["t1000004"])]
        q["holdings"] = []
        q["beat"].update(plan=plan, spotlight=spotlight)
        if spotlight is None:
            q["beat"].pop("spotlight")
    return generate_request(mutate)


def handle_of(request, ident):
    kit = Kit(request)
    return kit.handles.of_card("entanglements")[0].of("ties", ident)


def replace(handle, edge):
    return {"card": "entanglements", "patch": {"ties": [{"op": "replace", "id": handle, "values": {"edge": edge}}]}}


def run_steps(request):
    flow, kit = flow_for("generate", request)
    chapter = "The chapter text."
    events = {"happened": "Things happened between them.", "changed": "Something moved."}
    return flow, {"write": flow.next([]).text(1.0), "events": flow.next([chapter]).text(1.0), "shifts": flow.next([chapter, events]).text(1.0)}


def test_the_spotlight_is_the_tie_the_beat_names_in_every_step_even_when_name_matching_would_find_several():
    request = crowded()
    _, texts = run_steps(request)
    spot = EDGES["t1000002"]
    assert spot.split(" to ")[0][:25] in sections(texts["write"])["The tie in the spotlight"]
    for other in ("t1000001", "t1000003", "t1000004"):
        assert EDGES[other] not in sections(texts["write"])["The tie in the spotlight"], other
        assert EDGES[other] not in texts["events"], other
    assert spot in texts["events"], "the events step names the spotlight tie's edge"
    handle = handle_of(request, "t1000002")
    assert f"its edge was: {spot}" in texts["shifts"] and handle in texts["shifts"] and "Suvi toward Marit" in texts["shifts"]
    assert "t1000002" not in "".join(texts.values()), "the id is only used to pick the tie"


def test_the_choice_follows_the_key_not_the_names_two_requests_that_differ_only_in_the_key_pick_different_ties():
    first, second = crowded("t1000001"), crowded("t1000002")
    assert first["ties"] == second["ties"] and first["beat"]["plan"] == second["beat"]["plan"]
    a, b = run_steps(first)[1], run_steps(second)[1]
    assert EDGES["t1000001"] in a["events"] and EDGES["t1000002"] not in a["events"]
    assert EDGES["t1000002"] in b["events"] and EDGES["t1000001"] not in b["events"]
    assert "Marit toward Suvi" in sections(a["write"])["The tie in the spotlight"] and "Suvi toward Marit" in sections(b["write"])["The tie in the spotlight"]


@pytest.mark.parametrize("spotlight", [None, "t9999999", ""], ids=["no key", "key not among the ties", "empty key"])
def test_a_request_without_a_usable_key_falls_back_and_does_not_raise(spotlight):
    request = crowded(spotlight)
    flow, texts = run_steps(request)                                   # the three prompts build
    assert texts["write"] and texts["events"] and texts["shifts"]
    kit = Kit(request)
    replies = gen.script(request, kit)
    assert flow.next([replies[0], json.loads(replies[1])]).check(json.loads(replies[2])) is None      # the module's own valid reply is accepted
    assert "t9999999" not in "".join(texts.values())
    # the plan names all three people, so several ties are candidates and a reply that moves any named tie's edge passes
    handle = handle_of(request, "t1000003")
    check = flow.next([replies[0], json.loads(replies[1])]).check
    assert check({"shifts": [replace(handle, "to tell Suvi about the harbour debt")]}) is None


def test_the_shifts_check_judges_the_spotlight_ties_edge_only():
    request = crowded()
    flow, _ = run_steps(request)
    check = flow.next(["The chapter text.", {"happened": "Something happened here.", "changed": "Something moved."}]).check
    spot, other = handle_of(request, "t1000002"), handle_of(request, "t1000001")
    assert check({"shifts": [replace(spot, "to forgive her sister and let her stay")]}) is None                 # the spotlight's edge, new value
    for reply in ({"shifts": [replace(other, "to let the ledger go")]},                                          # another tie's edge is not enough, even a joined pair
                  {"shifts": [replace(spot, EDGES["t1000002"])]},                                                # the same value again
                  {"shifts": [replace(spot, EDGES["t1000002"].upper() + ".")]},                                  # the same value in other clothes
                  {"shifts": []}):
        problem = check(reply)
        assert problem and spot in problem and "\n" not in problem, reply
    ops = replace(other, "to let the ledger go")["patch"]["ties"] + replace(spot, "to forgive her sister")["patch"]["ties"]
    assert check({"shifts": [{"card": "entanglements", "patch": {"ties": ops}}]}) is None                       # one entry may move both ties


def test_no_more_than_seven_shift_entries_with_the_key_present():
    request = crowded()
    request["cast"] += [{**copy.deepcopy(MARIT), "id": f"c000000{n}", "name": name} for n, name in ((4, "Odo"), (5, "Pia"))]
    kit = Kit(request)
    assert kit.grammar.shifts()["maxItems"] == 7
    labels = [s.label for s in kit.handles.of_card("characters")]
    entries = [{"card": "characters", "target": l, "patch": {"sketch": "Changed."}} for l in labels]
    entries += [{"card": "world", "patch": {"everyday_life": "Changed."}}, replace(handle_of(request, "t1000002"), "to forgive her sister")]
    flow, _ = run_steps(request)
    check = flow.next(["The chapter text.", {"happened": "Something happened here.", "changed": "Something moved."}]).check
    assert len(entries) == 7 and check({"shifts": entries}) is None
    assert check({"shifts": entries + [{"card": "world", "patch": {"era_and_technology": "Changed again."}}]})
