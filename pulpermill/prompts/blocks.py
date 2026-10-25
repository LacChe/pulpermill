"""The rendered material for each call, in its fixed order, as named blocks. The craft text at the top, the task and the
reminder at the end are added in phase 4 (the prompt files); this is everything in between, and what the golden prompts
in phase 5 are made from."""
from . import textfiles as tx
from .render import (Report, render_style, render_cast, render_world, render_entanglements, render_setup, render_standing,
                     render_story_so_far, render_scene, render_earlier_beats, render_code_numbers, groups_in_play, s)


def _cast_names(cast: list[dict]) -> list[str]:
    return [s(p.get("name")) for p in cast]


def _sex_of(cast: list[dict], name: str) -> str:
    return next((s(p.get("sex")) for p in cast if s(p.get("name")) == name), "other")


def writer_blocks(req: dict, report: Report | None = None) -> list[tuple[str, str]]:
    """Blocks 2 to 9 of the chapter writer's prompt (inventory, 5.1): style, world, people, entanglements, where they stand
    now, the story so far, the last chapter's ending, the scene. Empty blocks are left out."""
    lim = tx.limits()["events"]
    cast = req.get("cast") or []
    ent = req.get("entanglements") or {}
    beat = req.get("beat") or {}
    setup = req.get("setup") or {}
    protagonist = s(setup.get("protagonist"))
    chapter = int(req.get("chapter") or 1)
    story = [render_setup(setup, req.get("goal"), chapter, req.get("chapter_count"), report=report),
             render_story_so_far(req.get("earlier_events") or [], chapter, keep_full=lim["full_chapters_writer"], report=report)]
    ending = s(req.get("previous_ending"))
    blocks = [
        ("style", render_style(req.get("style") or {}, scope="writer", report=report)),
        ("world", render_world(req.get("world") or {}, scope="writer", place=s(beat.get("where")) or None,
                               in_play=groups_in_play(ent), report=report)),
        ("people", render_cast(cast, scope="writer", report=report)),
        ("entanglements", render_entanglements(ent, _cast_names(cast), scope="writer", report=report)),
        ("standing", render_standing(req.get("standing") or [])),
        ("story", "\n\n".join(x for x in story if x)),
        ("last_ending", (tx.prompt_text("frames")["previous_ending_lead"] + "\n" + ending) if ending else ""),
        ("scene", render_scene(beat, protagonist=protagonist, sex=_sex_of(cast, protagonist),
                               open_plants=req.get("open_plants"), available_reveals=req.get("available_reveals"), report=report)),
    ]
    return [(name, text) for name, text in blocks if text]


def planner_blocks(req: dict, report: Report | None = None) -> list[tuple[str, str]]:
    """Blocks 2 to 10 of the planner's prompt (inventory, 5.2). The retry block and the task are added in phase 4."""
    lim = tx.limits()["events"]
    fr = tx.prompt_text("frames")
    cast = req.get("cast") or []
    chapter = int(req.get("chapter") or 1)
    setup = req.get("setup") or {}
    tone = render_style(req.get("style") or {}, scope="planner", report=report)
    story = [render_setup(setup, req.get("goal"), chapter, req.get("chapter_count"), report=report),
             render_story_so_far(req.get("earlier_events") or [], chapter, keep_full=lim["full_chapters_planner"], report=report),
             render_earlier_beats(req.get("earlier_beats") or [])]
    off = req.get("offstage") or {}
    offstage = fr["planner_offstage"].format(did=s(off.get("did")), reach=s(off.get("reach"))) if s(off.get("did")) else ""
    blocks = [
        ("tone", (tone + "\n" + fr["planner_tone_lead"]) if tone else ""),
        ("world", render_world(req.get("world") or {}, scope="planner", report=report)),
        ("people", render_cast(cast, scope="planner", report=report)),
        ("entanglements", render_entanglements(req.get("entanglements") or {}, _cast_names(cast), scope="planner", report=report)),
        ("standing", render_standing(req.get("latest_shifts") or [])),
        ("story", "\n\n".join(x for x in story if x)),
        ("offstage", offstage),
        ("code", render_code_numbers(req, report=report)),
    ]
    return [(name, text) for name, text in blocks if text]


def assemble(blocks: list[tuple[str, str]]) -> str:
    """The blocks as one text, each under its heading (a block with no heading stands alone)."""
    titles = tx.prompt_text("frames")["titles"]
    parts = []
    for name, text in blocks:
        title = titles.get(name, "")
        parts.append(f"{title}\n{text}" if title else text)
    return "\n\n".join(parts)
