"""A Chinese story's free text is limited by the grammar to Han text, and its fill prompt ends with a language rule before the reply format."""
import json
import re

from pulpermill.backend import grammar
from pulpermill.backend.kit import Kit
from pulpermill.prompter.mill import fill


def req(language="zh-Hans", note="冷峻克制，第三人称，过去式。", card="style"):
    return {"call": "fill", "card": card, "language": language, "note": note, "example_chapter": "", "related": {}, "values": {}}


def strings(node):
    if isinstance(node, dict):
        if node.get("type") == "string":
            yield node
        for v in node.values():
            yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)


def test_every_free_text_string_of_a_chinese_fill_is_limited_to_han_and_the_answer_words_are_not():
    g = grammar.fill(req())
    free = [s for s in strings(g) if "enum" not in s]
    assert free and all("pattern" in s for s in free)
    assert all("pattern" not in s for s in strings(g) if "enum" in s)
    assert g["properties"]["person"]["enum"] == ["first", "third"]
    pattern = g["properties"]["lens"]["pattern"]
    assert re.fullmatch(pattern, "她看着窗台上新擦过的痕迹，一言不发。")
    assert not re.fullmatch(pattern, "The narrator notices small comforts.")
    assert "(?" not in pattern, "the grammar builder does not read non-capturing groups"


def test_a_latin_name_is_allowed_only_when_the_writers_own_text_has_it():
    plain = grammar.fill(req())["properties"]["lens"]["pattern"]
    assert not re.fullmatch(plain, "Pim 坐在窗边。")
    named = grammar.fill(req(note="冷峻克制，紧贴 Pim 的视角。"))["properties"]["lens"]["pattern"]
    assert re.fullmatch(named, "Pim 坐在窗边。")
    assert not re.fullmatch(named, "Pim is sitting by the window.")


def test_other_languages_are_left_alone():
    for language in ("en", "fr", None):
        assert "pattern" not in json.dumps(grammar.fill(req(language=language)))


def test_the_language_rule_comes_just_before_the_reply_format_and_only_for_a_story_not_in_english():
    zh = req()
    prompt = fill.build_prompt(zh, Kit(zh))
    rule = prompt.index("Language of the reply: ")
    assert "Simplified Chinese" in prompt[rule:] and prompt.index("The card is still empty.") < rule < prompt.index("Reply with a JSON object holding every field")
    assert prompt.rstrip().endswith("a note to the writer.")
    en = req(language="en")
    assert "Language of the reply" not in fill.build_prompt(en, Kit(en))
