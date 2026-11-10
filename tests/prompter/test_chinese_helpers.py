"""Step 6: the length, sentence and echo checks of the prompter work for Chinese text, and English behaves as it did."""
from pulpermill.prompter.mill import common, generate as gen, plan

END = "她把钥匙放回窗台，转身走进了雨里，再也没有回头看那座空荡荡的院子。"
HAPPENED = "苏薇在雨夜回到旧院，发现门锁已经被人换过，于是翻墙进去。"


def test_size_is_latin_words_plus_half_the_han_characters():
    assert common.size("one two three") == 3
    assert common.size("一二三四") == 2
    assert common.size("她带着 phone 走了") == 3.5
    assert common.size("") == 0


def test_a_normal_chinese_happened_passes_and_an_empty_one_fails():
    assert gen.events_problem({"happened": HAPPENED, "changed": "她离开了院子。"}) is None
    assert gen.events_problem({"happened": "", "changed": "她离开了院子。"})
    assert gen.events_problem({"happened": "好", "changed": "她离开了院子。"})
    assert gen.events_problem({"happened": HAPPENED, "changed": ""})


def test_sentences_split_on_chinese_stops_with_closing_quotes():
    text = "他说：“走吧。”她没有动。你呢？我留下！"
    assert common._sentences(text) == ["他说：“走吧。”", "她没有动。", "你呢？", "我留下！"]
    assert common._sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]


def test_an_opening_that_repeats_the_last_sentence_is_caught_and_trimmed():
    ending = "夜深了。" + END
    opening = END + "第二天清晨，院子里来了一个陌生人。" + "他提着灯。" * 300
    assert common.echoes_ending(opening, ending)
    kept, dropped = common.trim_echo(opening, ending)
    assert dropped == 1 and kept.startswith("第二天清晨")
    assert not common.echoes_ending("第二天清晨，院子里来了一个陌生人。他提着灯。", ending)


def test_a_short_chinese_phrase_is_not_an_echo():
    assert not common.echoes_ending("她转身走了。", "她转身走了。")
    assert common.trim_echo("她转身走了。他来了。", "她转身走了。", min_words=1)[1] == 0


def test_a_chinese_text_too_short_after_trimming_is_returned_whole():
    opening = END + "第二天清晨。"
    assert common.trim_echo(opening, END) == (opening, 0)


def test_a_long_changed_is_cut_at_a_sentence_end_or_with_a_full_stop():
    sentence = "她终于决定留下来守住那座旧院。"                   # 15 characters
    text = sentence * 20
    cut = gen._words(text, 100)
    assert cut.endswith("。") and len(cut) <= 200 and len(cut) >= 100
    unbroken = "她" * 500
    assert gen._words(unbroken, 100) == "她" * 200 + "。"
    assert gen._words(HAPPENED, 100) == HAPPENED
    assert gen._words("one two three", 2) == "one two."


def test_repair_events_keeps_two_chinese_sentences():
    out = gen.repair_events({"happened": HAPPENED, "changed": "她留下了。她想守住院子。院子终于安静了。"})
    assert out["changed"] == "她留下了。 她想守住院子。"


def test_two_near_identical_chinese_aims_are_similar_and_unrelated_ones_are_not():
    a, b = plan._words("夺回被抵押的祖屋地契"), plan._words("夺回被抵押的祖屋地契书")
    c = plan._words("说服盐商放弃码头的租约")
    assert len(a & b) / len(a | b) >= 0.8
    assert len(a & c) / len(a | c) < 0.8
    assert plan._words("Win back the deeds") == {"back", "deeds"}


def test_a_short_chinese_aim_is_not_called_too_short():
    assert not plan.aim_is_abstract("夺回被抵押的祖屋地契")
    assert plan.aim_is_abstract("好")
