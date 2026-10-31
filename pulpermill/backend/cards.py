"""Which cards a request carries, and under what keys. This is the one place besides reply assembly that reads the contract's own
request fields; everything else asks the schema. Values are the cards as the page sent them (effective state, with ids)."""
from dataclasses import dataclass
from typing import Any

from pulpermill.schema import CARDS


@dataclass(frozen=True)
class Sent:
    card: str                    # a card id
    target: str | None           # the id of the item the card is about (a Characters card), else None
    values: dict[str, Any]       # the card's values by field key


def list_fields(card: str) -> list[str]:
    """The keys of a card's repeating lists, from its schema."""
    return [k for k, f in CARDS[card][0].model_fields.items() if (f.json_schema_extra or {}).get("repeat")]


def cards_sent(request: dict) -> list[Sent]:
    """Every card whose items the model may point at: the card a fill or judge works on, or the cards a story request carries."""
    if request.get("card") and isinstance(request.get("values"), dict):
        return [Sent(request["card"], request.get("instance"), request["values"])]
    out = [Sent("characters", p.get("id"), p) for p in request.get("cast") or [] if isinstance(p, dict)]
    if isinstance(request.get("world"), dict):
        out.append(Sent("world", None, request["world"]))
    if "ties" in request or "holdings" in request:
        out.append(Sent("entanglements", None, {"ties": request.get("ties") or [], "holdings": request.get("holdings") or []}))
    return out


def label_key(card: str, field: str | None = None) -> str:
    """The field that names an item: `name` when there is one, else the first text field. For a list field, of its items; for a card
    (field None), of the card itself."""
    from typing import get_args
    model = CARDS[card][0]
    if field:
        model = get_args(model.model_fields[field].annotation)[0]
    keys = [k for k, f in model.model_fields.items() if k != "id"]
    if "name" in keys:
        return "name"
    texts = [k for k in keys if model.model_fields[k].annotation is str and not (model.model_fields[k].json_schema_extra or {}).get("ref")]
    return texts[0] if texts else keys[0]
