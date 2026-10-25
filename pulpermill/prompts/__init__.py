"""Turns the cards and records a request carries into the prose a model reads. No model, no server: text in, text out.
Wording lives in text/en/*.yaml (and the schema's own text files); length caps live in limits.yaml."""
from .render import (Report, render_style, render_cast, render_world, render_entanglements, render_setup, render_standing,
                     render_story_so_far, render_scene, render_earlier_beats, render_code_numbers, groups_in_play)
from .blocks import writer_blocks, planner_blocks, assemble

__all__ = ["Report", "render_style", "render_cast", "render_world", "render_entanglements", "render_setup",
           "render_standing", "render_story_so_far", "render_scene", "render_earlier_beats", "render_code_numbers",
           "groups_in_play", "writer_blocks", "planner_blocks", "assemble"]
