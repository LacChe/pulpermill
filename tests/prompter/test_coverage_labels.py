"""C1, design rule 2 and the id rule: structured values reach the model as full explanatory sentences, never as a bare option key or a
`field: value` label, and no prompt holds an id from its request. Every choice field is set to each of its options in turn and rendered by
every call that can carry it. No model, no network."""
import re

import pytest

from test_coverage_support import (FILL_TARGETS, VECTORS, Ref, allowlist, expected_text, ids_in, placements, prompts, schema_fields, vector,
                                   value_for)

FIELDS = [f for f in schema_fields() if not f.is_list]
CHOICES = [(f, option) for f in FIELDS if f.options and f.id not in allowlist() for option in f.options]
KEYS = sorted({f.key for f in FIELDS} | {f.item for f in FIELDS if f.item})


def raw_label(ref: Ref, option: str, text: str) -> list[str]:
    """The places where `option` is shown as a label instead of in words: `amount: sparse`, `amount = "sparse"`, `{"amount": "sparse"}`,
    `amount (sparse)`, a bare `(sparse)`, or the option alone on a line. The fill call's list of answer words is allowed to name an option in
    quotes when its own explanatory sentence follows it (`"sparse": Dialogue is sparse: ...`): the model must answer with those words."""
    key, opt = re.escape(ref.key), re.escape(option)
    patterns = [rf"\b{key}\s*[:=]\s*[\"'`]?{opt}\b", rf"[\"']{key}[\"']\s*:\s*[\"']{opt}[\"']", rf"\b{key}\s*\(\s*{opt}\s*\)",
                rf"\(\s*{opt}\s*\)", rf"^\s*[\"'`]?{opt}[\"'`]?[.,;:]?\s*$"]
    return [m.group(0).strip() for p in patterns for m in re.finditer(p, text, flags=re.I | re.M)]


def test_the_detector_sees_a_raw_label_and_lets_an_explained_answer_word_pass():
    ref = next(f for f in FIELDS if f.id == "style.amount")
    for bad in ("amount: sparse", 'amount = "sparse"', '{"amount": "sparse"}', "amount (sparse)", "Dialogue (sparse) is lean.", "line one\nsparse\nline two"):
        assert raw_label(ref, "sparse", bad), bad
    for fine in ('"sparse": Dialogue is sparse: characters say little.', "Dialogue is sparse: characters say little and narration carries the scene.",
                 "The sparse light of the quay."):
        assert not raw_label(ref, "sparse", fine), fine


@pytest.mark.parametrize("ref,option", CHOICES, ids=lambda x: x.id if isinstance(x, Ref) else x)
def test_rule2_an_option_reaches_the_prompts_as_its_explanatory_sentence_and_never_as_a_raw_label(ref, option):
    wanted = expected_text(ref, option, ref.options[option])
    explained = False
    for p in placements(ref, option):
        for step, text in prompts(p.call, p.request).items():
            assert not raw_label(ref, option, text), f"{ref.id}={option} is a raw label in the {p.call} call, step {step}: {raw_label(ref, option, text)}"
            explained = explained or wanted.lower() in text.lower()
    assert explained, f"{ref.id}={option}: the schema's sentence ({wanted!r}) is shown nowhere"


def test_rule2_outside_fill_and_judge_no_prompt_lists_a_field_as_a_key_colon_value_line():
    """Fill names its fields on purpose (the model answers by key). Judge shows each item under its handle (`wants.1:`, and for a single-value
    field its key: `fear:`), because the model points at what it judged by that handle; the text after it is the writer's own words. Every other
    call gets prose, and list items under handles such as `ties.1:`."""
    offending = []
    pattern = re.compile(rf"^\s*(?:{'|'.join(map(re.escape, KEYS))})\s*[:=]\s*\S", re.M | re.I)
    for ref in FIELDS:
        if ref.id in allowlist():
            continue
        value = list(ref.options)[0] if ref.options else value_for(ref)
        for p in placements(ref, value):
            if p.call in ("fill", "judge"):
                continue
            for step, text in prompts(p.call, p.request).items():
                offending += [(ref.id, p.call, step, m.group(0)) for m in pattern.finditer(text)]
    assert not offending, offending[:5]


def requests_to_check() -> list[tuple[str, dict]]:
    out = [(f"vector: {v['name']}", v["data"]) for v in VECTORS if v["valid"] and v["data"]["call"] in ("fill", "judge", "style_fit", "plan", "generate")]
    for ref in FIELDS:
        if ref.id in allowlist():
            continue
        values = list(ref.options) if ref.options else [value_for(ref)]
        out += [(f"{ref.id}={v}: {p.call}", p.request) for v in values for p in placements(ref, v)]
    return out


def test_no_prompt_holds_an_id_from_its_request():
    checked = 0
    for label, request in requests_to_check():
        ids = ids_in(request)
        for step, text in prompts(request["call"], request).items():
            for ident in ids:
                assert ident not in text, f"{label}: the id {ident} reaches the {request['call']} prompt (step {step})"
            checked += 1
    assert checked > 200 and sum(1 for _, r in requests_to_check() if ids_in(r)) > 100


def test_the_ids_of_a_story_request_are_found_for_every_kind_of_card():
    """The check above is only as good as its list of ids: it must see a character, a place, an object, a group, a rule, a term, a tie and a holding."""
    ids = ids_in(vector("a generate request"))
    for ident in ("c0000001", "p0000001", "o0000001", "g0000001", "r0000001", "t0000001", "t1000001", "h1000001", "w0000001", "h0000001"):
        assert ident in ids, ident


# The one exception to rule 2, declared here with its reason: in a fill step the model must answer a choice with one of its option words (the grammar
# only accepts those), so the fill prompt lists the answer words, each in quotes and beside its own explanatory sentence. It holds for the Style card
# and for the one other card that has choices (the character's sex). Nowhere else does a bare option word appear as an instruction.
FILL_ANSWER_WORDS = "the grammar of a fill step accepts only the option words, so the model is told them, each beside its explanation"


@pytest.mark.parametrize("ref,option", CHOICES, ids=lambda x: x.id if isinstance(x, Ref) else x)
def test_the_fill_answer_words_are_the_only_exception_and_each_stands_beside_its_explanation(ref, option):
    assert FILL_ANSWER_WORDS and ref.card in ("style", "characters")
    wanted = expected_text(ref, option, ref.options[option])
    fills = [p for p in placements(ref, option) if p.call == "fill" and p.request["card"] == ref.card]
    assert fills, f"{ref.id} has no fill of its own card"
    for p in fills:
        text = prompts("fill", p.request)["fill"]
        assert re.search(rf"[\"“]{re.escape(option)}[\"”]\s*:\s*", text), f"{ref.id}: the answer word {option!r} is not listed with its explanation"
        line = next(l for l in text.splitlines() if re.search(rf"[\"“]{re.escape(option)}[\"”]\s*:", l))
        assert wanted.lower() in line.lower(), (ref.id, option, line)
