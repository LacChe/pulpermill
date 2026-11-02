"""The `style_fit` call: one JSON step, {fits, message}. It compares the protagonist (sketch, fear, flaw, speech, behaviours) with the voice the
Style card chose, shown by the existing Style renderer as explanatory prose, and flags only a real conflict, not a preference."""
import json
from typing import Any

from pulpermill.prompts import render as r
from pulpermill.prompts import textfiles as tx
from pulpermill.prompter.base import Flow, Step

from . import common

VERSION = "style_fit-1"
MAX_OUTPUT = 400


def language_name(code: str | None) -> str:
    names = common.load_text("style_fit")["languages"]
    code = str(code or "en")
    return names.get(code) or names.get(code.split("-")[0]) or code


def build_prompt(request: dict, factor: float = 1.0) -> str:
    w = common.load_text("style_fit")
    person = request.get("protagonist") or {}
    name = r.s(person.get("name"))
    portrait = r.render_person(person, scope="fit")
    if portrait.strip() == "" or portrait.strip() == r.render_person({"name": name}, scope="fit").strip():
        portrait = w["protagonist_bare"].format(name=name)
    # The fit scope of the person renderer leaves the behaviours out; the voice question needs them (how the person acts under stress).
    frame = tx.prompt_text("frames")["portrait_behavior"]
    habits = [r.fill(frame, {"state": r.s(b.get("state")), "tendency": r.s(b.get("tendency"))}) for b in person.get("behaviors") or [] if r.s(b.get("state"))]
    if habits:
        portrait = (portrait if portrait != w["protagonist_bare"].format(name=name) else "") + "\n" + w["behaviors_lead"].format(name=name, items="; ".join(habits))
    return "\n\n".join([
        w["role"],
        w["voice_lead"] + "\n" + r.render_style(request.get("style") or {}, scope="writer"),
        w["person_lead"] + "\n" + common.clip(portrait, factor, floor=400),
        w["task"] + " " + w["preference"],
        w["output"].format(language=language_name(request.get("language"))),
    ])


def style_fit_problem(request: dict, value: Any) -> str | None:
    if isinstance(value, dict) and value.get("fits") is False and not r.s(value.get("message")):
        return common.load_text("style_fit")["problems"]["message_needed"].format(name=r.s((request.get("protagonist") or {}).get("name")) or "the protagonist")
    return None


class StyleFitFlow(Flow):
    def __init__(self, request: dict, kit: Any):
        self.request, self.kit = request, kit

    def _step(self) -> Step:
        g = self.kit.grammar
        return Step("style_fit", lambda f: build_prompt(self.request, f), "json", MAX_OUTPUT, g.obj({"fits": {"type": "boolean"}, "message": g.text()}),
                    lambda v: style_fit_problem(self.request, v), "structured", True)

    def next(self, results):
        return None if results else self._step()

    def reply(self, results):
        fits = results[0]["fits"]
        return {"fits": fits, "message": "" if fits else r.s(results[0].get("message"))}


def build_flow(request, kit) -> Flow:
    return StyleFitFlow(request, kit)


def script(request: dict, kit: Any) -> list[str]:
    return [json.dumps({"fits": True, "message": ""})]
