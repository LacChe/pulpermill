"""The fill limits (budgets.yaml: fill_note, fill_chapter): a note and an example chapter at their limits fit beside the heaviest fill prompt
the schema allows; one token over is refused (too_long) and never cut; and the page's numbers (web/logic.js) are the same."""
import copy
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "tests" / "prompts"))

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

import story_sizes as ss  # noqa: E402
import test_fill_wording as w  # noqa: E402
from pulpermill.prompter.mill import fill  # noqa: E402
from pulpermill.prompts import budget, tokens  # noqa: E402

pytestmark = pytest.mark.skipif(not tokens.available(), reason="the Gemma tokenizer files are not installed")

B = budget.budgets()


def text_of(n_tokens: int) -> str:
    """Prose of exactly `n_tokens` tokens."""
    words, text = ss.prose(60000).split(), ""
    lo, hi = 0, len(words)
    while lo < hi:                                  # the most words that stay within n_tokens
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if tokens.count(" ".join(words[:mid])) <= n_tokens else (lo, mid - 1)
    return " ".join(words[:lo])


def heaviest_related(card: str) -> dict:
    """The cards this one reads, as full as the schema allows: 8 people with every list at its maximum, a full world, 12 ties."""
    rel, counter = copy.deepcopy(w.RELATED[card]), [0]
    people = ss._clone(copy.deepcopy(w.CHARS), 8)        # a copy: the people are changed below, and the other tests share w.CHARS
    for p in people:
        p.update({k: ss.prose(300, i) for i, k in enumerate(["sketch", "fear", "flaw", "competence", "vulnerability", "speech", "history"])})
        p["wants"] = [{"id": f"w{i}", "text": ss.prose(120, i)} for i in range(5)]
        p["values"] = [{"id": f"v{i}", "text": ss.prose(120, i)} for i in range(5)]
        p["behaviors"] = [{"id": f"b{i}", "state": ss.prose(60, i), "tendency": ss.prose(90, i)} for i in range(5)]
    world = copy.deepcopy(w.WORLD)
    for key, value in list(world.items()):
        if isinstance(value, list):
            world[key] = ss._clone(value, 5)
    if "characters" in rel:
        rel["characters"] = people
    if "world" in rel:
        rel["world"] = ss._stuff(world, counter, 600)
    if "entanglements" in rel:
        rel["entanglements"] = ss._stuff({"ties": ss._clone(w.TIES["ties"], 12), "holdings": []}, counter, 300)
    return rel


@pytest.mark.parametrize("card", w.CARDS)
def test_a_note_and_a_chapter_at_their_limits_fit_the_heaviest_prompt_without_any_squeeze(card):
    request = w.req(card, note=text_of(B["fill_note"]), chapter=text_of(B["fill_chapter"]), related=heaviest_related(card))
    prompt = fill.build_prompt(request, w.Kit(request), 1.0)
    m = budget.measure(budget.Sized("fill", prompt, fill.MAX_OUTPUT))
    assert m.ok, f"{card}: {m.tokens} tokens, {m.limit} allowed"
    assert request["example_chapter"] in prompt and request["note"] in prompt        # nothing of the writer's was cut


@pytest.mark.parametrize("which,key", [("note", "fill_note"), ("chapter", "fill_chapter")])
def test_a_text_over_its_limit_is_refused_not_cut(which, key):
    over = text_of(B[key] + 40)
    request = w.req("world", **({"note": over} if which == "note" else {"note": None, "chapter": over}))
    with pytest.raises(budget.PromptTooLong) as e:
        fill.build_prompt(request, w.Kit(request))
    assert e.value.measure.tokens > B[key] == e.value.measure.limit


def test_the_page_shows_the_same_limits():
    js = (ROOT / "web" / "logic.js").read_text(encoding="utf-8")
    found = re.search(r"FILL_LIMITS = \{ note: (\d+), chapter: (\d+) \}", js)
    assert found and (int(found.group(1)), int(found.group(2))) == (B["fill_note"], B["fill_chapter"])


def test_over_its_limit_the_server_answers_too_long_before_any_inference_though_the_prompt_would_fit_the_context():
    from pulpermill.backend.config import Config
    from pulpermill.backend.engine import FakeEngine
    from server_harness import post, running, wait_idle
    request = w.req("world", note="Nine chapters.", chapter="word " * (B["fill_chapter"] + 1000))      # a prompt far inside the context
    engine = FakeEngine()
    with running(config=Config(prompter="mill"), engine=engine, run=None) as (base_url, _):
        response = post(base_url, request)
        assert response.status_code == 413 and response.json()["error"]["kind"] == "too_long"
        assert "example chapter" in response.json()["error"]["detail"] and wait_idle(base_url)
    assert engine.calls == 0
