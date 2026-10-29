"""The trial set (phase 6): four chapters of the Salt Coast story, each a different kind of chapter in a different voice. Every prompt
version is run against all four, three times each, and the results are read with the rubric (docs/prompts/06-reading-rubric.md).
They are made from the one sample story by changing the beat and the style, so the cards stay the same and only the chapter differs.
Change a trial and every earlier result stops being comparable: add a trial instead (T5) and keep the old ones."""
import copy

from test_render import generate_request

TRIALS = {
    "T1-pressure": "Chapter 5. A scene with dialogue and a hard choice: Suvi presses Pekka while Aino watches. First person, past, dry, close. "
                   "Tests the beat as a scene (not a list), subtext, a myth that must not be explained, and the planted lock.",
    "T2-quiet": "Chapter 6. A slow, easier chapter in the shop: Aino finally says what he came to say. Third person, present, deep, warm, lingering. "
                "Tests a style change you can see, interior life, and a chapter with no chase in it.",
    "T3-fast": "Chapter 7. A short fast chapter on the tide: Suvi races the clerk to the cellar. Third person, past, brisk, terse, external. "
               "Tests pace without a list of events, action that stays specific, and an ending that hooks.",
    "T4-opening": "Chapter 1. The first chapter: no earlier chapters, no last ending. Third person, past, close, wry. "
                  "Tests setting the normal life and the break, introducing people without a roll call, and not telling the whole story at once.",
}


def _clear_history(req):
    for key in ("earlier_events", "standing", "previous_ending", "open_plants"):
        req[key] = [] if key != "previous_ending" else ""
    return req


def trial(name: str) -> dict:
    req = copy.deepcopy(generate_request())
    beat, style = req["beat"], req["style"]
    if name == "T1-pressure":
        return req
    if name == "T2-quiet":
        req["chapter"] = 6
        style.update(person="third", tense="present", distance="deep", humor="none", pacing="lingering", rhythm="flowing",
                     imagery="lush", attitude="warm", narrator_note="", lens="She counts what people leave on the counter.")
        beat.update(id="b0000006", chapter=6, cast=["Suvi", "Aino"], where="The Shop", when_time="Wednesday evening, after closing",
                    when_gap="The next evening", collision_goal="Hear what Aino came to say", collision_block="Aino cannot say it while the shop is still warm with other people's talk",
                    choice_a="Let Aino leave with it unsaid", choice_b="Tell him she already knows about the letters",
                    turn="Aino admits he read her letters, and Suvi lets him stay", shift="easier",
                    ends_on="Suvi hangs the brass key back on its nail", reveal_rule="", reveal_learners=[], plant="", payoff=[],
                    offstage_did="", offstage_reach="", goal_change=None, goal_now="",
                    spotlight="Aino fears Suvi has seen him reading her letters.")
        req["previous_ending"] = "Pekka's door closed behind him with the sound of a thing put away for good. Aino was still on the step, hat in his hands."
        req["open_plants"], req["available_reveals"] = [req["open_plants"][0]], []
        req["standing"] = [{"character": "Suvi", "decided": "to hear him out"}, {"character": "Aino", "fears": "that Suvi has seen him reading her letters"}]
        req["earlier_events"].append({"chapter": 5, "happened": "Suvi pressed Pekka in front of Aino and learned the ledger is in the cellar. Aino now knows she is asking.",
                                      "changed": "Aino knows what Suvi is after.", "planted": ""})
        return req
    if name == "T3-fast":
        req["chapter"] = 7
        style.update(person="third", tense="past", distance="external", humor="none", pacing="brisk", rhythm="terse", imagery="literal",
                     attitude="clinical", narrator_note="", lens="", dialogue_note="")
        beat.update(id="b0000007", chapter=7, cast=["Suvi", "Pekka"], where="The Docks", when_time="Thursday, an hour before the spring tide",
                    when_gap="The next day", collision_goal="Reach the cellar before the clerk does", collision_block="The east gate is shut and the tide is coming in over the low road",
                    choice_a="Take the flooded low road and risk the ledger getting wet", choice_b="Wait for Pekka's boat and lose a quarter of an hour",
                    turn="Suvi reaches the cellar first, but the second lock is already open", shift="harder",
                    ends_on="The cellar door stands open and the ledger's shelf is empty", reveal_rule="", reveal_learners=[],
                    plant="", payoff=["A second lock on the cellar's inner door."], offstage_did="", offstage_reach="", goal_change=None, goal_now="",
                    spotlight="The board wants the ledger before the next first-day visit and will close the shop to get it.")
        req["earlier_events"] += [
            {"chapter": 5, "happened": "Suvi pressed Pekka in front of Aino and learned the ledger is in the cellar. Aino now knows she is asking.",
             "changed": "Aino knows what Suvi is after.", "planted": ""},
            {"chapter": 6, "happened": "Aino admitted in the shop that he had read her letters. Suvi let him stay and hung the key back on its nail.",
             "changed": "Aino and Suvi share the secret of the cellar.", "planted": ""}]
        req["previous_ending"] = "Aino's boots were already on the stairs. \"Friday is tomorrow,\" he said, \"and they are not going to wait for Friday.\""
        req["standing"] = [{"character": "Suvi", "decided": "to reach the cellar before anyone else"}]
        req["available_reveals"] = [r for r in req["available_reveals"] if r.get("truth")]
        return req
    if name == "T4-opening":
        _clear_history(req)
        req["chapter"] = 1
        style.update(person="third", tense="past", distance="close", humor="dry", pacing="balanced", attitude="wry", narrator_note="", lens="",
                     dialogue_note="")
        req["setup"] = {**req["setup"], "normal": "Suvi opens the harbour shop at six, counts the till twice, and knows every sailor's debt by heart.",
                        "disruption": "One morning the till is a crate's worth short, and the brass key is gone from its nail."}
        beat.update(id="b0000001", chapter=1, cast=["Suvi", "Aino"], where="The Shop", when_time="Monday, six in the morning", when_gap="",
                    collision_goal="Find out who has been in the shop at night", collision_block="Nothing is broken and the door was locked",
                    choice_a="Raise the miscount with the dock clerk now", choice_b="Say nothing and watch who comes in",
                    turn="Suvi decides to watch, and Aino lets slip that a ledger exists", shift="harder",
                    ends_on="The brass key is missing from its nail", reveal_rule="", reveal_learners=[], plant="The brass key goes missing from its nail.",
                    payoff=[], offstage_did="", offstage_reach="", goal_change=None, goal_now="",
                    spotlight="The board wants the ledger before the next first-day visit and will close the shop to get it.")
        req["available_reveals"] = []
        return req
    raise KeyError(name)


def all_trials() -> dict:
    return {name: trial(name) for name in TRIALS}
