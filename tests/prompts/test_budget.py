"""Tests for the tokenizer, the token budgets and the golden prompts (phase 5). No model, no GPU.
The token tests need the Gemma tokenizer files (pulpermill/prompts/tokenizer/ or PULPERMILL_TOKENIZER) and skip without them.
Run from the repository root: python -m pytest tests/prompts"""
from pathlib import Path

import prompt_cases as cases
from test_render import generate_request

from pulpermill.prompts import budget, render, tokens
from pulpermill.prompts import prompts as P
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

def test_every_prompt_has_a_reply_room_in_the_budget():
    for name, prompt in cases.golden().items():
        assert budget.key(prompt.name) in budget.budgets()["max_output"], name
    b = budget.budgets()
    assert b["n_ctx"] > max(b["max_output"].values()) + b["margin"] + 2000


def test_a_section_of_prose_fits_the_writers_reply_room():
    if not have_tokenizer():
        return
    section = tokens.count(cases.chapter_text(1500))
    assert section * 1.3 < budget.budgets()["max_output"]["writer"], section          # ~1,500 words (a section's ceiling), plus 30% for a longer one


def test_the_sample_story_fits_every_prompt_with_room_to_spare():
    if not have_tokenizer():
        return
    for name, prompt in cases.tier("sample").items():
        m = budget.measure(prompt)
        assert m.ok and m.headroom > m.limit * 0.3, (name, m)


def test_a_medium_story_fits_after_a_squeeze():
    """Five people with a sentence or two in every field. The second section carries the whole first one (up to ~1,500 words), so it
    needs the harder squeeze; that is the price of the second section seeing everything the first showed (docs/prompts/07)."""
    if not have_tokenizer():
        return
    _, first, measures = budget.fit(lambda: cases.tier("medium")["writer-1-open"])
    assert first >= 0.7 and all(m.ok for m in measures)
    _, second, measures = budget.fit(lambda: cases.tier("medium")["writer-2-close"])
    assert second >= 0.4 and all(m.ok for m in measures)


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
    try:
        budget.fit(lambda: cases.tier("large")["writer-1-open"])
    except budget.PromptTooLong as e:                                   # documented in docs/prompts/05-budgets.md
        assert e.measure.tokens > e.measure.limit
    else:
        raise AssertionError("a story of eight full people was expected not to fit; update the doc if it does now")


def test_the_very_large_planner_prompt_fits_when_squeezed():
    if not have_tokenizer():
        return
    made, factor, measures = budget.fit(lambda: cases.tier("large")["planner-1-think"])
    assert factor < 1 and all(m.ok for m in measures)


def test_text_a_model_wrote_is_capped_wherever_it_comes_back_in():
    long = cases.prose(3000)
    assert len(render.render_standing([{"character": "Suvi", "believes": long, "decided": long}])) < 800
    plan = {"spotlight": {"what": long}, "open_plants": [{"text": long, "chapter": 2}],
            "available_reveals": [{"statement": long, "truth": long, "status": "false_belief"}], "legal_shifts": ["harder", "easier"]}
    assert len(render.render_code_numbers(plan)) < 2600


# ---- Golden prompts -------------------------------------------------------------------------------------------------

def test_the_golden_prompts_are_what_the_code_makes():
    """If this fails after a wording change on purpose: python tools/render_prompts.py, read the diff, commit the new files."""
    made = cases.golden()
    assert {f.stem for f in GOLDEN.glob("*.txt")} == set(made)
    for name, prompt in made.items():
        assert (GOLDEN / f"{name}.txt").read_text(encoding="utf-8") == cases.golden_file(prompt), name
