"""Registry of cards, in chain order. Each entry: (model, groups, render order, rules)."""
from . import style, characters, world, entanglements, setup, outline, summaries, shifts

CARDS = {
    "style": (style.Style, style.GROUPS, style.RENDER_ORDER, style.RULES, style.CARD),
    "characters": (characters.Characters, characters.GROUPS, characters.RENDER_ORDER, characters.RULES, characters.CARD),
    "world": (world.World, world.GROUPS, world.RENDER_ORDER, world.RULES, world.CARD),
    "entanglements": (entanglements.Entanglements, entanglements.GROUPS, entanglements.RENDER_ORDER, entanglements.RULES, entanglements.CARD),
    "setup": (setup.Setup, setup.GROUPS, setup.RENDER_ORDER, setup.RULES, setup.CARD),
    "outline": (outline.Outline, outline.GROUPS, outline.RENDER_ORDER, outline.RULES, outline.CARD),
    "summary_events": (summaries.SummaryEvents, summaries.EVENTS_GROUPS, summaries.EVENTS_RENDER_ORDER, summaries.EVENTS_RULES, summaries.EVENTS_CARD),
    "shifts": (shifts.Shifts, shifts.GROUPS, shifts.RENDER_ORDER, shifts.RULES, shifts.CARD),
}
