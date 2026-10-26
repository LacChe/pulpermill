"""Checks a model reply against the JSON Schema its prompt carried, and says what is wrong in one short line.
Only the keywords the prompts use: type, enum, const, items, properties, required, anyOf, minItems, maxItems,
additionalProperties. (The grammar already forces these when decoding is constrained; this is for free-written JSON and
for the check after a cut-off reply.)"""
import json
import re

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict,
          "null": type(None)}


def problems(value, schema: dict, path: str = "reply") -> list[str]:
    out: list[str] = []
    if "anyOf" in schema:
        if not any(not problems(value, branch, path) for branch in schema["anyOf"]):
            out.append(f"{path} matches none of the allowed shapes")
        return out
    if "const" in schema and value != schema["const"]:
        out.append(f"{path} must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path} must be one of {schema['enum']}, not {value!r}")
    kind = schema.get("type")
    if kind:
        ok = isinstance(value, _TYPES[kind]) and not (kind in ("integer", "number") and isinstance(value, bool))
        if kind == "integer" and isinstance(value, float):
            ok = False
        if not ok:
            return out + [f"{path} must be of type {kind}"]
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(f"{path} needs at least {schema['minItems']} items")
        if len(value) > schema.get("maxItems", 10 ** 9):
            out.append(f"{path} may have at most {schema['maxItems']} items")
        for n, item in enumerate(value):
            out += problems(item, schema.get("items", {}), f"{path}[{n}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{path} is missing '{key}'")
        for key, item in value.items():
            if key in props:
                out += problems(item, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{path} has an unexpected '{key}'")
    return out


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _unfinished(body: str) -> bool:
    """True when the text ends inside a string or with an object or list still open: the reply stopped at max_tokens."""
    depth, in_string, escaped = 0, False, False
    for ch in body:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
    return in_string or depth > 0


def parse_json(text: str):
    """The JSON in a reply. Raises ValueError with a short plain message (a cut-off reply is one of these)."""
    body = text.strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        tail = " (the reply looks cut off)" if _unfinished(body) else ""
        raise ValueError(f"the reply is not valid JSON: {e.msg} at character {e.pos}{tail}") from None
