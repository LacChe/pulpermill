"""The shared model call: too_long before inference, the two-attempt rule, the retry note, the language check."""
import json

import pytest

from pulpermill.backend import language, shape
from pulpermill.backend.config import Config
from pulpermill.backend.engine import FakeEngine
from pulpermill.backend.engine.base import CancelFlag
from pulpermill.backend.errors import BackendError, Cancelled
from pulpermill.backend.pipelines import RunContext, structured as st
from pulpermill.prompts import budget, textfiles as tx
from pulpermill.prompts.prompts import Prompt

SCHEMA = {"type": "object", "properties": {"fits": {"type": "boolean"}, "message": {"type": "string"}},
          "required": ["fits", "message"], "additionalProperties": False}
GOOD = json.dumps({"fits": True, "message": ""})
ENGLISH = ("She walked down to the river and the water was cold against her feet, and she did not look back at the house "
           "that had been her home for all of those years, because there was nothing left in it for her to keep.")
FRENCH = ("Elle descendit jusqu'à la rivière et l'eau était froide contre ses pieds, et elle ne regarda pas la maison qui "
          "avait été la sienne pendant toutes ces années, parce qu'il n'y avait plus rien dans cette maison pour elle.")
CHINESE = "她走到河边，水很冷，她没有回头看那座已经住了很多年的房子，因为那里面再也没有什么值得她留下的东西了。"


def make(engine=None, **config):
    engine = engine or FakeEngine()
    stages: list = []
    ctx = RunContext(engine, CancelFlag(), stages.append, Config(**config))
    return ctx, engine, stages


def prompt(schema=SCHEMA, text="Decide whether it fits.", name="style_fit"):
    return Prompt(name=name, version="t-0", text=text, schema=schema, stage="think")


def test_valid_first_reply_is_used_once_and_constrained():
    ctx, engine, stages = make()
    engine.script(GOOD)
    r = st.run_json(ctx, prompt(), "en")
    assert r.value == {"fits": True, "message": ""}
    assert not r.retried and engine.calls == 1
    assert engine.constraints == [SCHEMA]
    assert stages == ["think"]


def test_bad_json_retries_once_with_the_problem_and_without_the_first_reply():
    ctx, engine, _ = make()
    engine.script("this is not json at all", GOOD)
    r = st.run_json(ctx, prompt(), "en")
    assert r.retried and [a.problem is None for a in r.attempts] == [False, True]
    second = engine.prompts[1]
    assert second.startswith("Decide whether it fits.")
    assert "could not be used" in second and "not valid JSON" in second
    assert "this is not json at all" not in second
    assert "could not be used" not in engine.prompts[0]


def test_two_failures_are_bad_output():
    ctx, engine, _ = make()
    engine.script('{"fits": "yes", "message": ""}', "{}")
    with pytest.raises(BackendError) as e:
        st.run_json(ctx, prompt(), "en")
    assert e.value.kind == "bad_output" and engine.calls == 2


def test_a_cut_off_reply_is_a_shape_failure():
    ctx, engine, _ = make()
    engine.script('{"fits": true, "message": "It is a good', GOOD)
    r = st.run_json(ctx, prompt(), "en")
    assert r.retried and "cut off" in r.attempts[0].problem


def test_the_callers_own_check_counts_as_a_shape_failure():
    ctx, engine, _ = make()
    engine.script(GOOD, GOOD)
    with pytest.raises(BackendError):
        st.run_json(ctx, prompt(), "en", validate=lambda v: "fits must be false here")
    assert "fits must be false here" in engine.prompts[1]


def test_repair_mode_writes_free_first_and_constrains_the_retry():
    ctx, engine, _ = make(constrain="repair")
    engine.script("oops", GOOD)
    st.run_json(ctx, prompt(), "en")
    assert engine.constraints == [None, SCHEMA]
    ctx, engine, _ = make(constrain="repair")
    engine.script(GOOD)
    st.run_json(ctx, prompt(), "en")
    assert engine.constraints == [None] and engine.calls == 1


def test_a_prompt_without_a_schema_is_never_constrained():
    ctx, engine, _ = make()
    engine.script(ENGLISH)
    r = st.run_text(ctx, prompt(schema=None, name="writer"), "en")
    assert r.value == ENGLISH and engine.constraints == [None]


def test_too_long_is_answered_before_any_inference():
    ctx, engine, _ = make()
    huge = "word " * (budget.input_limit("style_fit") + 500)
    with pytest.raises(BackendError) as e:
        st.run_json(ctx, prompt(text=huge), "en")
    assert e.value.kind == "too_long" and engine.calls == 0


def test_stop_is_not_retried():
    ctx, engine, _ = make()
    engine.fail_next(Cancelled())
    with pytest.raises(Cancelled):
        st.run_json(ctx, prompt(), "en")
    assert engine.calls == 1


def test_stop_between_attempts_ends_the_call():
    ctx, engine, _ = make()
    engine.script("nope")
    ctx.cancel.set()
    with pytest.raises(Cancelled):
        st.run_json(ctx, prompt(), "en")
    assert engine.calls == 0


def test_a_reply_in_the_wrong_language_is_retried_once():
    longer = {"fits": False, "message": ENGLISH}
    ctx, engine, _ = make()
    engine.script(json.dumps({"fits": False, "message": CHINESE * 2}), json.dumps(longer))
    r = st.run_json(ctx, prompt(), "en")
    assert r.retried and "Chinese" not in r.value["message"]
    assert "language" in engine.prompts[1]
    ctx, engine, _ = make()
    engine.script(json.dumps({"fits": False, "message": ENGLISH}), json.dumps({"fits": False, "message": ENGLISH}))
    with pytest.raises(BackendError) as e:
        st.run_json(ctx, prompt(), "zh-Hans")
    assert e.value.kind == "bad_output"


def test_free_text_in_the_wrong_language_is_retried():
    ctx, engine, _ = make()
    engine.script(FRENCH, ENGLISH)
    r = st.run_text(ctx, prompt(schema=None, name="writer"), "en")
    assert r.value == ENGLISH and r.retried


def test_empty_text_is_retried():
    ctx, engine, _ = make()
    engine.script("   ", ENGLISH)
    assert st.run_text(ctx, prompt(schema=None, name="writer"), "en").retried


def test_the_note_is_left_out_when_it_would_not_fit():
    """Counted with the engine's own count (one word, one token in the fake), as when the tokenizer files are absent."""
    ctx, engine, _ = make()
    p = prompt(text="word " * (budget.input_limit("style_fit") - 2))
    real = st.tokens.available
    st.tokens.available = lambda: False
    try:
        engine.script("bad", GOOD)
        r = st.run_json(ctx, p, "en")
    finally:
        st.tokens.available = real
    assert r.retried and "could not be used" not in engine.prompts[1]


def test_the_engines_count_is_used_when_the_tokenizer_files_are_absent():
    ctx, engine, _ = make()
    real = st.tokens.available
    st.tokens.available = lambda: False
    try:
        engine.script(GOOD)
        with pytest.raises(BackendError) as e:
            st.run_json(ctx, prompt(text="word " * (budget.input_limit("style_fit") + 5)), "en")
        assert e.value.kind == "too_long" and engine.calls == 0
    finally:
        st.tokens.available = real


def test_the_problem_is_short_and_one_line():
    long = "bad\n" + "x " * 600
    note = st.with_note(prompt(), long).text
    assert "\n\n" in note and len(note) < 600 and note.count("…") == 1


def test_the_retry_template_has_a_version_and_a_slot():
    t = tx.template("retry")
    assert t["version"].startswith("retry-") and "{problem}" in t["note"]


# ---- shape and language on their own ----------------------------------------------------------------------------------

def test_shape_says_what_is_wrong_in_plain_words():
    assert shape.problems({"fits": True, "message": ""}, SCHEMA) == []
    assert shape.problems({"fits": True}, SCHEMA) == ["reply is missing 'message'"]
    assert "unexpected 'extra'" in shape.problems({"fits": True, "message": "", "extra": 1}, SCHEMA)[0]
    assert shape.problems(True, {"type": "integer"}) == ["reply must be of type integer"]
    assert shape.problems(["a", "b", "c"], {"type": "array", "items": {"enum": ["a", "b"]}, "maxItems": 2})[0].startswith("reply may have")
    assert shape.problems(None, {"anyOf": [{"type": "string"}, {"type": "null"}]}) == []
    assert shape.problems(3, {"anyOf": [{"type": "string"}, {"type": "null"}]}) == ["reply matches none of the allowed shapes"]


def test_parse_json_takes_a_fenced_reply():
    assert shape.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        shape.parse_json("")


def test_language_check():
    assert language.check(ENGLISH, "en") is None
    assert language.check(FRENCH, "fr") is None
    assert "french" not in (language.check(FRENCH, "en") or "") and language.check(FRENCH, "en")
    assert language.check(ENGLISH, "fr") and language.check(ENGLISH, "de")
    assert language.check(CHINESE, "zh-Hans") is None and language.check(CHINESE, "zh-Hant") is None
    assert language.check(ENGLISH, "zh-Hans") and language.check(CHINESE, "en")
    assert language.check(CHINESE, "ja")                       # Han with no kana is not Japanese
    assert language.check("彼女は川へ下りていったが、水はとても冷たくて、振り返らなかった。それはもう何も残っていなかったからだ。", "ja") is None
    assert language.check("그녀는 강가로 내려갔고 물은 차가웠으며 그녀는 뒤를 돌아보지 않았다 집에는 남은 것이 없었다", "ko") is None
    assert language.check(ENGLISH, "ko")


def test_short_text_and_unknown_languages_pass():
    assert language.check("Yes.", "zh-Hans") is None
    assert language.check(ENGLISH, "xx") is None


def test_a_few_foreign_words_and_names_do_not_trip_it():
    mixed = ENGLISH + " She whispered, “Mon Dieu, c’est fini,” to nobody, and Élodie Marchetti did not answer her."
    assert language.check(mixed, "en") is None


def test_check_value_only_reads_the_longer_strings():
    reply = {"fits": False, "name": "Élodie", "message": FRENCH}
    assert language.check_value(reply, "en") and language.check_value(reply, "fr") is None
    assert list(language.strings_in({"a": "Mira", "b": ["short", FRENCH]})) == [FRENCH]
