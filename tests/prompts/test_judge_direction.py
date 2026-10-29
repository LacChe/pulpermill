"""Which answer breaks a judge rule is worked out from the rule's own text, and the prompt says it plainly."""
import glob
import yaml

from pulpermill.prompts.prompts import judge_question

# Rules whose question is asked the other way round: "yes" means the item breaks the rule.
YES_BREAKS = {"object_unowned", "power_no_current_goals"}


def _all_rules():
    for path in glob.glob("pulpermill/schema/text/en/*.yaml"):
        for rule_id, body in ((yaml.safe_load(open(path)) or {}).get("rules") or {}).items():
            if isinstance(body, dict) and body.get("judge_prompt"):
                yield path, rule_id, body["judge_prompt"]


def test_lens_question_breaks_on_no_and_loses_the_rewrite_request():
    question, breaks = judge_question("Does this text describe a habit of attention? Answer yes or no. If no, suggest a rewrite as a habit of attention.")
    assert breaks == "no"
    assert question == "Does this text describe a habit of attention?"


def test_reversed_questions_break_on_yes():
    assert judge_question("Does any group's text state what it wants? Answer yes or no for each. Rewrite any that do so that they describe only what the group is.")[1] == "yes"
    assert judge_question("Does this text name a particular person? Answer yes or no. If yes, rewrite it.")[1] == "yes"


def test_every_rule_has_a_question_and_no_answer_instruction_is_left():
    found = list(_all_rules())
    assert len(found) >= 35
    for path, rule_id, text in found:
        question, breaks = judge_question(text)
        assert question.endswith("?"), (path, rule_id)
        assert "Answer yes or no" not in question and "rewrite" not in question.lower(), (path, rule_id)
        assert breaks in ("yes", "no")


def test_exactly_the_reversed_rules_break_on_yes():
    said_yes = {rule_id for _, rule_id, text in _all_rules() if judge_question(text)[1] == "yes"}
    assert said_yes == YES_BREAKS
