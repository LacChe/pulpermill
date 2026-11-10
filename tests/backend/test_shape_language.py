"""shape.py and language.py on their own."""
import pytest

from pulpermill.backend import language, shape

SCHEMA = {"type": "object", "properties": {"fits": {"type": "boolean"}, "message": {"type": "string"}},
          "required": ["fits", "message"], "additionalProperties": False}
ENGLISH = ("She walked down to the river and the water was cold against her feet, and she did not look back at the house "
           "that had been her home for all of those years, because there was nothing left in it for her to keep.")
FRENCH = ("Elle descendit jusqu'à la rivière et l'eau était froide contre ses pieds, et elle ne regarda pas la maison qui "
          "avait été la sienne pendant toutes ces années, parce qu'il n'y avait plus rien dans cette maison pour elle.")
CHINESE = "她走到河边，水很冷，她没有回头看那座已经住了很多年的房子，因为那里面再也没有什么值得她留下的东西了。"


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


def test_parse_json_accepts_raw_newlines_and_tabs_inside_strings_and_still_refuses_the_rest():
    raw = '{"plan": "Act 1: one\nAct 2: two\tend"}'                  # real newline and tab characters, as a model writes them
    assert "\n" in raw and "\t" in raw and "\\n" not in raw
    expected = {"plan": "Act 1: one\nAct 2: two\tend"}
    assert shape.parse_json(raw) == expected and shape.parse_json("```json\n" + raw + "\n```") == expected
    with pytest.raises(ValueError):
        shape.parse_json("")
    with pytest.raises(ValueError) as cut:
        shape.parse_json('{"plan": "Act 1: one\nAct 2')
    assert "the reply looks cut off" in str(cut.value)
    with pytest.raises(ValueError):
        shape.parse_json('{"plan": "one",}')


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


# ---- Chinese is held to a stricter line, and a Latin-script language to a sprinkle of Han at most ----------------------

ENGLISH_SENTENCE = " She did not look back at the house that had been her home."          # thirteen words, in the middle of Chinese
NAMES_IN_CHINESE = "Suvi对Ola说，你怎么还不走，我已经等了你很久，" * 6                         # many names, little else Latin


def test_chinese_passes_with_names_in_it_even_when_the_names_are_many():
    assert language.check(CHINESE, "zh") is None
    assert language.check(CHINESE + " “Élodie Marchetti”" + CHINESE, "zh") is None
    assert language.check(NAMES_IN_CHINESE, "zh") is None                  # 8 Latin letters to 16 Han in every clause, all of them names


def test_an_english_paragraph_is_not_chinese():
    assert language.check(ENGLISH, "zh") == "the text is not written in Chinese"
    assert language.check(CHINESE * 4 + ENGLISH + CHINESE * 4, "zh") == "the text is not written in Chinese"


def test_one_english_sentence_in_the_middle_of_chinese_fails_though_the_share_is_high():
    text = CHINESE * 8 + ENGLISH_SENTENCE + CHINESE * 2
    han = sum(1 for c in text if "\u3400" <= c <= "\u9fff")
    assert han / sum(1 for c in text if c.isalpha()) > 0.8                # the old, looser line would have let it through
    assert language.check(text, "zh") == "the text has a passage that is not written in Chinese"


def test_a_short_English_phrase_or_a_list_of_names_is_not_a_passage():
    assert language.check(CHINESE * 3 + " she did not look back " + CHINESE * 3, "zh") is None        # five words
    assert language.check(CHINESE * 3 + " Suvi, Ola, Mira, Tomas, Jun, Eli " + CHINESE * 3, "zh") is None   # six, all names


def test_a_latin_script_language_may_hold_a_name_in_han_but_not_a_chinese_sentence():
    assert language.check(ENGLISH + " Li Wei (李伟) nodded.", "en") is None
    assert language.check(ENGLISH * 2 + CHINESE, "en") == "the text has Chinese, Japanese or Korean characters in it, which en does not use"
    assert language.check(FRENCH * 2 + CHINESE, "fr")


def test_a_short_chinese_string_in_a_reply_is_read_though_chinese_has_no_spaces():
    short = "她走到河边水很冷她没有回头看那座房子"                                     # 18 Han characters, under 40 characters
    assert list(language.strings_in({"a": short, "b": "苏维走了"})) == [short]
    reply = {"a": short, "b": short, "c": short}
    assert language.check_value(reply, "en") and language.check_value(reply, "zh") is None


def test_check_value_only_reads_the_longer_strings():
    reply = {"fits": False, "name": "Élodie", "message": FRENCH}
    assert language.check_value(reply, "en") and language.check_value(reply, "fr") is None
    assert list(language.strings_in({"a": "Mira", "b": ["short", FRENCH]})) == [FRENCH]
