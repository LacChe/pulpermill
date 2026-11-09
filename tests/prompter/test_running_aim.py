"""The running aim (advance.py): the aims of the earlier chapters and how each ended, read from a `plan` request. Pure: no model. The judges that once
read the chain (aim, edge, edge-check, pressure) are gone, and so is any step or note they made; a test greps the mill's code and wording so none comes back."""
import copy
import json
from pathlib import Path

from pulpermill.prompter.mill import advance

ROOT = Path(__file__).resolve().parents[2]
MILL = ROOT / "pulpermill" / "prompter" / "mill"
VECTORS = json.loads((ROOT / "tests/shared/contract-vectors.json").read_text())["requests"]


def request(**changes) -> dict:
    data = copy.deepcopy(next(v["data"] for v in VECTORS if v["valid"] and v["name"] == "a plan request"))
    data.update(chapter=4, earlier_beats=[{"chapter": 1, "aim": "Bake sun loaves.", "plan": "p"}, {"chapter": 2, "aim": "Get wood.", "plan": "p"},
                                          {"chapter": 3, "aim": "", "plan": "p"}, {"chapter": 4, "aim": "Not before this chapter.", "plan": "p"}],
                earlier_events=[{"chapter": 1, "happened": "h1", "changed": "c1"}, {"chapter": 2, "happened": "h2", "changed": ""}, {"chapter": 3, "happened": "h3", "changed": "c3"}])
    data.update(changes)
    return data


def test_the_earlier_aims_are_the_aims_of_the_chapters_before_this_one_oldest_first_and_a_chapter_with_no_aim_is_left_out():
    assert advance.earlier_aims(request()) == [(1, "Bake sun loaves."), (2, "Get wood.")]
    assert advance.earlier_aims(request(chapter=1)) == [] and advance.earlier_aims({}) == []


def test_the_chain_joins_each_aim_with_its_chapters_changed_line_and_a_chapter_with_a_line_but_no_aim_is_left_out():
    assert advance.chain(request()) == [{"chapter": 1, "aim": "Bake sun loaves.", "changed": "c1"}, {"chapter": 2, "aim": "Get wood.", "changed": ""}]


def test_a_squeeze_drops_the_oldest_links_and_always_keeps_the_newest():
    links = advance.chain(request(), 0.5)
    assert [link["chapter"] for link in links] == [2]
    assert [link["chapter"] for link in advance.chain(request(), 0.01)] == [2]


def test_no_judge_or_note_of_the_removed_judges_is_left_in_the_code_or_the_wording():
    removed = ("advance_aim", "advance_edge", "advance_pressure", "edge_check", "aim_replanned", "aim_judge_fallback", "pressure_judge_fallback",
               "aim_gate", "aim_same_obstacle", "edge_judge_fallback", "edge_resent")
    here = Path(__file__).resolve()
    texts = {str(p): p.read_text(encoding="utf-8") for folder in (MILL,) for p in folder.rglob("*") if p.is_file() and p.suffix in (".py", ".yaml") and p.resolve() != here}
    found = {word: [path for path, text in texts.items() if word in text] for word in removed}
    assert not any(found.values()), {word: paths for word, paths in found.items() if paths}
    assert not (MILL / "text" / "en" / "advance.yaml").exists()
