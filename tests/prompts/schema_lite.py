"""A small JSON Schema checker for the keywords the prompts use (type, enum, const, items, properties, required, anyOf,
minItems, maxItems, additionalProperties). The jsonschema package is not in CI, and this is all the schemas need."""


def errors(value, schema, path="$"):
    out = []
    if "anyOf" in schema:
        if not any(not errors(value, branch, path) for branch in schema["anyOf"]):
            out.append(f"{path}: matches none of the choices")
        return out
    if "const" in schema and value != schema["const"]:
        out.append(f"{path}: not {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} is not one of {schema['enum']}")
    kind = schema.get("type")
    checks = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict, "null": type(None)}
    if kind and not isinstance(value, checks[kind]) or (kind == "integer" and isinstance(value, bool)):
        return out + [f"{path}: expected {kind}"]
    if kind == "array":
        if len(value) < schema.get("minItems", 0):
            out.append(f"{path}: too few items")
        if len(value) > schema.get("maxItems", 10 ** 9):
            out.append(f"{path}: too many items")
        for n, item in enumerate(value):
            out += errors(item, schema.get("items", {}), f"{path}[{n}]")
    if kind == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{path}.{key}: missing")
        for key, item in value.items():
            if key in props:
                out += errors(item, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{path}.{key}: not allowed")
    return out


def valid(value, schema) -> bool:
    return not errors(value, schema)
