"""Tests for the tokenizer and the generic token budgets: measure, fit, squeeze (the parked story prompts' tests are marked). No model, no GPU.
The token tests need the Gemma tokenizer files (pulpermill/prompts/tokenizer/ or PULPERMILL_TOKENIZER) and skip without them.
Run from the repository root: python -m pytest tests/prompts"""
from pathlib import Path

import prompt_cases as cases
from test_render import generate_request, parked

from pulpermill.prompts import budget, render, tokens
from pulpermill.prompts import textfiles as tx

try:
    import pytest
except ImportError:                                                # the plain runner used where pytest is not installed
    pytest = None

GOLDEN = Path(__file__).resolve().parents[2] / "docs" / "prompts" / "samples" / "prompts"


def have_tokenizer() -> bool:
    if tokens.available():
        return True
    if pytest:
        pytest.skip("the Gemma tokenizer files are not installed")
    return False


# ---- The tokenizer --------------------------------------------------------------------------------------------------

def test_the_chat_template_tokens_are_the_models_own():
    if not have_tokenizer():
        return
    g = tokens.gemma()
    assert g.encode("<start_of_turn>user\nHello, world!<end_of_turn>\n<start_of_turn>model\n", bos=True) == \
        [2, 105, 2364, 107, 9259, 236764, 1902, 236888, 106, 107, 105, 4368, 107]


def test_chat_text_trims_the_prompt_like_the_template_does():
    assert tokens.chat_text("  Hello.\n\n") == "<start_of_turn>user\nHello.<end_of_turn>\n<start_of_turn>model\n"


def test_odd_text_never_becomes_unknown():
    if not have_tokenizer():
        return
    g = tokens.gemma()
    ids = g.encode("café — “quoted” 你好 😀 \t\n\n\n  end")
    assert ids and g.unk not in ids and max(ids) < 262144
    assert g.encode("") == []


def test_a_special_token_in_the_text_is_one_token():
    if not have_tokenizer():
        return
    assert tokens.gemma().encode("a<end_of_turn>b")[1] == 106


def test_a_long_piece_is_counted_without_trouble():
    if not have_tokenizer():
        return
    n = tokens.count(cases.chapter_text(4000))
    assert 4000 * 1.1 < n < 4000 * 1.8, n


# ---- The budgets ----------------------------------------------------------------------------------------------------

def test_budgets_keep_only_the_context_and_the_margin():
    """What a step may write belongs to the step (the prompter sets it); the budget file holds what is the model's."""
    assert set(budget.budgets()) == {"n_ctx", "margin"}


def test_the_input_limit_leaves_room_for_the_reply_and_the_margin():
    b = budget.budgets()
    assert budget.input_limit(1000) == b["n_ctx"] - 1000 - b["margin"]
    assert budget.input_limit(3200) < budget.input_limit(900)


def test_measure_says_what_the_prompt_takes_and_what_is_left():
    if not have_tokenizer():
        return
    m = budget.measure(budget.Sized("x", "word " * 100, 1000))
    assert 100 < m.tokens < 130 and m.limit == budget.input_limit(1000) and m.max_output == 1000
    assert m.ok and m.headroom == m.limit - m.tokens
    assert not budget.measure(budget.Sized("x", "word " * (m.limit + 10), 1000)).ok


def test_the_sample_story_fits_with_room_to_spare():
    if not have_tokenizer():
        return
    m = budget.measure(cases.render_story(cases.tier_request("sample")))
    assert m.ok and m.headroom > m.limit * 0.3, m


def test_a_medium_story_fits_as_it_is():
    if not have_tokenizer():
        return
    _, factor, measures = budget.fit(lambda f: cases.render_story(cases.tier_request("medium"), f))
    assert factor == 1.0 and all(m.ok for m in measures)


def test_a_very_large_story_fits_only_after_a_squeeze():
    if not have_tokenizer():
        return
    request = cases.tier_request("large")
    assert not budget.measure(cases.render_story(request)).ok
    made, factor, measures = budget.fit(lambda f: cases.render_story(request, f))
    assert factor < 1 and all(m.ok for m in measures)


def test_fit_takes_a_list_and_every_prompt_must_fit():
    if not have_tokenizer():
        return
    small, big = budget.Sized("a", "word " * 50, 1000), budget.Sized("b", "word " * (budget.input_limit(1000) + 100), 1000)
    assert budget.fit(lambda f: [small, small])[1] == 1.0
    assert budget.fit(lambda f: [small, big] if f == 1.0 else [small, budget.Sized("b", "word " * 100, 1000)])[1] == 0.85


def test_squeezing_shortens_every_length_and_leaves_the_counts_alone():
    base = tx.limits()
    with tx.squeeze(0.5):
        small = tx.limits()
        assert small["characters"]["sketch"] == base["characters"]["sketch"] // 2
        assert small["characters"]["max_behaviors"] == base["characters"]["max_behaviors"]
        assert small["events"]["full_chapters_writer"] == base["events"]["full_chapters_writer"]
        assert small["chapter"] == base["chapter"]
    assert tx.limits() == base and tx.limits()["characters"]["sketch"] == 700


def test_a_squeezed_prompt_is_shorter_and_says_what_it_cut():
    req = cases.inflate(generate_request(), cast=3, chars=2400)
    report, small_report = render.Report(), render.Report()
    full = render.render_cast(req["cast"], report=report)
    with tx.squeeze(0.5):
        small = render.render_cast(req["cast"], report=small_report)
    assert len(small) < len(full) * 0.8 and small_report.clips


def test_fit_gives_up_with_too_long_when_nothing_fits():
    if not have_tokenizer():
        return
    request = cases.tier_request("huge")
    try:
        budget.fit(lambda f: cases.render_story(request, f))
    except budget.PromptTooLong as e:
        assert e.measure.tokens > e.measure.limit
    else:
        raise AssertionError("a story of forty full people was expected not to fit")


# ---- The caps are on the schema -------------------------------------------------------------------------------------

def test_every_cap_on_the_schema_reaches_the_dictionary_the_renderers_read_and_nothing_else_is_lost():
    import yaml
    from pulpermill.schema import CARDS
    limits = tx.limits()
    capped = {(card, key) for card, (model, *_rest) in CARDS.items() for key, f in model.model_fields.items() if (f.json_schema_extra or {}).get("cap")}
    assert ("characters", "sketch") in capped and ("world", "name") in capped
    assert limits["characters"]["sketch"] == 700 and limits["world"]["place_description"] == 450 and limits["entanglements"]["edge"] == 300
    assert limits["events"]["happened"] == 1100 and limits["setup"]["normal"] == 700 and limits["characters"]["behavior_tendency"] == 280
    left = yaml.safe_load((Path(tx.__file__).parent / "limits.yaml").read_text())
    for section, keys in tx._FIELD_CAPS.items():
        assert not set(keys) & set(left.get(section, {})), section             # a cap lives in one place


def test_fixed_fields_have_no_cap():
    from pulpermill.schema import CARDS
    for card, (model, *_rest) in CARDS.items():
        for key, f in model.model_fields.items():
            meta = f.json_schema_extra or {}
            assert not (meta.get("fixed") and meta.get("cap")), (card, key)


@parked("old text is capped by the parked standing and code renderers, which read removed fields")
def test_text_a_model_wrote_is_capped_wherever_it_comes_back_in():
    long = cases.prose(3000)
    assert len(render.render_standing([{"character": "Suvi", "believes": long, "decided": long}])) < 800
    plan = {"spotlight": {"what": long}, "open_plants": [{"text": long, "chapter": 2}],
            "available_reveals": [{"statement": long, "truth": long, "status": "false_belief"}], "legal_shifts": ["harder", "easier"]}
    assert len(render.render_code_numbers(plan)) < 2600


@parked("the golden prompts are the old story prompts, which read the old request shapes")
def test_the_golden_prompts_are_what_the_code_makes():
    """If this fails after a wording change on purpose: python tools/render_prompts.py, read the diff, commit the new files."""
    made = cases.parked_golden()
    assert {f.stem for f in GOLDEN.glob("*.txt")} == set(made)
