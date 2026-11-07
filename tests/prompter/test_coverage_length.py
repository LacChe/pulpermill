"""C1 item 6 (from A7): the length of a chapter and the range of a story. The writer prompt's last line states the 1,200-word cap; the `write`
step leaves room for 1,200 English words and 2,400 Chinese characters, measured with the real tokenizer; the overshoot check passes a chapter at the
cap and refuses one far over it; the Setup fill tells the model to choose 5 to 10 chapters when the note names no number and to keep a stated one;
every trial story holds a chapter count from 10 to 20. No model, no network."""
import json
import re
from pathlib import Path

import pytest
import yaml

from test_coverage_support import PID, SUVI, MARIT, fill_request, flow_for, generate_request, prompts
from pulpermill.prompter.mill import generate as gen
from pulpermill.prompts import tokens

ROOT = Path(__file__).resolve().parents[2]
TRIALS = ROOT / "evals" / "trials"

EN_SAMPLE = ("The ferry was late again, and Suvi stood at the rail with the ledger under her coat. \"You could have sent word,\" Marit said, not turning "
             "round. The harbour smelled of tar and cold rope, and somewhere below them a winch began to grind. Suvi counted the lamps along the quay, "
             "one, two, three, and the fourth was dark. \"I did send word,\" she said. \"You just didn't read it.\" ")
ZH_SAMPLE = "渡船又晚点了，苏薇站在栏杆边，外套下藏着那本账册。“你本可以捎个信的，”玛丽特没有回头。码头上弥漫着焦油和冷绳的气味，脚下的绞盘吱嘎作响。"


def words_of(n: int) -> str:
    words = EN_SAMPLE.split()
    return " ".join((words * (n // len(words) + 1))[:n])


def han_of(n: int) -> str:
    han = [c for c in ZH_SAMPLE if "\u4e00" <= c <= "\u9fff"]
    return "".join((han * (n // len(han) + 1))[:n])


def request(language: str = "en") -> dict:
    return generate_request(lambda q: q.update(language=language))


def test_the_writer_prompts_last_line_states_the_cap_in_words_and_in_characters():
    last = prompts("generate", request())["write"].rstrip().splitlines()[-1]
    assert "at most 1,200 words" in last or "up to 1,200 words" in last, last
    last_zh = prompts("generate", request("zh"))["write"].rstrip().splitlines()[-1]
    assert "2,400 Chinese characters" in last_zh and "1,200 words" not in last_zh, last_zh


def test_the_real_tokenizer_is_available_for_the_measure():
    assert tokens.available(), "the tokenizer files must ship with the repo; the length test measures with them"


@pytest.mark.parametrize("language, sample, size", [("en", words_of(1200), "1,200 English words"), ("zh", han_of(2400), "2,400 Chinese characters")])
def test_the_write_step_leaves_room_for_a_chapter_at_the_cap(language, sample, size):
    flow, _ = flow_for("generate", request(language))
    step = flow.next([])
    needed = tokens.count(sample)
    assert step.name == "write" and step.max_output >= needed, f"{size} take {needed} tokens; the step allows {step.max_output}"
    assert step.max_output < 3 * needed, "the allowance is a safety net, not a licence to run on"


@pytest.mark.parametrize("language, small, at_cap, over", [("en", words_of(300), words_of(1200), words_of(1501)),
                                                          ("zh", han_of(600), han_of(2400), han_of(3001))])
def test_the_overshoot_check_passes_a_chapter_at_the_cap_and_refuses_one_far_over_it(language, small, at_cap, over):
    flow, _ = flow_for("generate", request(language))
    check = flow.next([]).check
    assert check(small) is None and check(at_cap) is None
    problem = check(over)
    assert problem and "\n" not in problem and ("1,200 words" in problem or "2,400 Chinese characters" in problem), problem
    assert check(words_of(1800) if language == "en" else han_of(3600))
    assert not check(" ".join(["word"] * 3)), "a short chapter is never refused"


def setup_prompt(note: str) -> str:
    return prompts("fill", {**fill_request("setup", {"protagonist": PID}, {"characters": [SUVI, MARIT]}), "note": note})["fill"]


def test_the_setup_fill_chooses_five_to_ten_when_the_note_states_no_number_and_keeps_a_stated_one():
    for note in ("A quiet story about a lighthouse keeper.", "Make it eight chapters.", "7 chaps"):
        prompt = setup_prompt(note)
        assert "choose a whole number from 5 to 10" in prompt and "chapter_count is exactly that number" in prompt, note
        assert "10 to 20" not in prompt
        assert note in prompt
    schema = fill_request("setup", {"protagonist": PID}, {"characters": [SUVI, MARIT]})
    flow, kit = flow_for("fill", schema)
    grammar = flow.next([]).grammar
    assert "chapter_count" in json.dumps(grammar)


def test_the_scripted_setup_fill_chooses_a_count_from_ten_to_twenty_and_keeps_a_stated_one():
    from pulpermill.prompter import mill
    for note, expected in (("A quiet story about a lighthouse keeper.", None), ("Make it eight chapters.", 8), ("make it 15 chapters", 15)):
        request = {**fill_request("setup", {}, {"characters": [SUVI, MARIT]}), "note": note}
        flow, kit = flow_for("fill", request)
        count = int(json.loads(mill.script("fill", request, kit)[0])["chapter_count"])
        assert count == expected if expected else 10 <= count <= 20, (note, count)


def test_every_trial_story_has_a_chapter_count_from_ten_to_twenty():
    counts = {}
    for path in sorted((TRIALS / "stories").glob("*.yaml")):
        story = yaml.safe_load(path.read_text(encoding="utf-8"))
        found = re.findall(r"^\s*chapter_count:\s*(\d+)", path.read_text(encoding="utf-8"), flags=re.M)
        assert found, f"{path.name} states no chapter_count"
        counts[path.stem] = [int(n) for n in found]
    for path in sorted((TRIALS / "projects").glob("*.json")):
        project = json.loads(path.read_text(encoding="utf-8"))
        counts[path.stem + "(project)"] = [int(project["setup"]["chapter_count"])]
    for entry in json.loads((TRIALS / "manifest.json").read_text(encoding="utf-8")):
        counts[entry["id"] + "(manifest)"] = [int(entry["chapters"])]
    assert len(counts) >= 18
    for name, found in counts.items():
        assert all(10 <= n <= 20 for n in found), f"{name}: chapter_count {found} is outside 10 to 20"
