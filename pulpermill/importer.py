"""Importing cards from files. Validates against the schema, keeps whatever is valid, and reports the rest. Nothing here raises on bad input: every problem becomes a line in the report."""

import copy
import types
import typing
from pydantic import BaseModel, ValidationError

from .runtime import logger
from .schema import (
    CharacterCard, M, PlotOutline, StyleCard, WorldBible, check_characters, check_outline, check_style, check_world,
    slugify
)


CARD_MODELS = {"style": StyleCard, "characters": CharacterCard, "world": WorldBible, "outline": PlotOutline}


WRAPPER_KEYS = ("style", "characters", "world", "outline", "plot")   # "plot" is what StoryProject calls the outline


META_KEYS = {"format", "version", "chapter", "saved", "slug", "note"}


SCORE_MIN = 2           # a loose card file must share at least this many field names with one card type


_KINDS = {dict: M("an object"), list: M("a list"), str: M("text"), int: M("a number"), float: M("a number"),
          bool: M("true/false"), type(None): M("null")}


KIND = {"style": M("style"), "characters": M("characters"), "world": M("world"), "outline": M("setup")}


def _kind(v):
    return _KINDS.get(type(v)) or type(v).__name__


def _model_of(ann):
    """(model class, is_list) when the annotation is a model, a list of models, or an Optional of one; else (None, False)."""
    origin, args = typing.get_origin(ann), typing.get_args(ann)
    if origin is typing.Annotated:
        return _model_of(args[0])
    if origin in (typing.Union, types.UnionType):
        for a in args:
            if a is not type(None):
                m = _model_of(a)
                if m[0]:
                    return m
        return None, False
    if origin in (list, typing.List):
        return (_model_of(args[0])[0] if args else None), True
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return ann, False
    return None, False


def unknown_paths(cls, data, path=()):
    """Field names in `data` that `cls` (or a model nested inside it) does not have."""
    out = []
    if not isinstance(data, dict):
        return out
    for k, v in data.items():
        if k not in cls.model_fields:
            out.append("›".join(map(str, path + (k,))).replace("›", " › "))
            continue
        m, is_list = _model_of(cls.model_fields[k].annotation)
        if m is None:
            continue
        if is_list and isinstance(v, list):
            for i, x in enumerate(v):
                out += unknown_paths(m, x, path + (k, f"#{i + 1}"))
        elif not is_list:
            out += unknown_paths(m, v, path + (k,))
    return out


def _name_of(node):
    if isinstance(node, dict):
        for k in ("name", "id", "fact"):
            if isinstance(node.get(k), str) and node[k].strip():
                return node[k].strip()[:40]
    return None


def _path_text(data, loc):
    parts, node = [], data
    for p in loc:
        try:
            node = node[p]
        except (KeyError, IndexError, TypeError):
            parts.append(f"#{p + 1}" if isinstance(p, int) else str(p))
            continue
        if isinstance(p, int):
            nm = _name_of(node)
            parts.append(f"#{p + 1}" + (f" ({nm})" if nm else ""))
        else:
            parts.append(str(p))
    return " › ".join(parts)


def _drop(data, loc):
    out = copy.deepcopy(data)
    parent = out
    for p in loc[:-1]:
        parent = parent[p]
    del parent[loc[-1]]
    return out


def salvage(cls, data, label):
    """Validate `data` as `cls`. When something is wrong, drop the smallest piece that fixes it (an optional field, or one
    item of a list) and keep going, rather than rejecting the whole card. A required field that is wrong rejects the item
    that contains it. Returns (validated model or None, warnings, error or None)."""
    warnings = []
    if not isinstance(data, dict):
        return None, warnings, M("expected an object, found {kind}", kind=_kind(data))
    data = copy.deepcopy(data)
    unknown = unknown_paths(cls, data)
    if unknown:
        warnings.append(M("{label}: ignored unrelated field(s): {fields} (+{n} more)", label=label, fields=", ".join(unknown[:5]), n=len(unknown) - 5)
                        if len(unknown) > 5 else
                        M("{label}: ignored unrelated field(s): {fields}", label=label, fields=", ".join(unknown)))
    for _ in range(300):
        try:
            return cls.model_validate(data), warnings, None
        except ValidationError as ve:
            first = ve.errors()[0]
            loc, msg = tuple(first["loc"]), first["msg"]
            dropped = False
            for depth in range(len(loc), 0, -1):
                prefix = loc[:depth]
                try:
                    trial = _drop(data, prefix)
                except (KeyError, IndexError, TypeError):
                    continue
                try:
                    cls.model_validate(trial)
                except ValidationError as v2:
                    if any(x["type"] == "missing" and tuple(x["loc"]) == prefix for x in v2.errors()):
                        continue                  # a required field: dropping it only moves the problem up a level
                warnings.append(M("{label}: dropped {path} ({why})", label=label, path=_path_text(data, prefix), why=msg))
                data, dropped = trial, True
                break
            if not dropped:
                return None, warnings, M("{path}: {why}", path=_path_text(data, loc) or M("the card"), why=msg)
    return None, warnings, M("too many problems to repair")


def classify(d):
    """Which card a loose JSON object is, judged by how many of its field names belong to each card; None if unclear."""
    scores = {k: len(set(d) & set(c.model_fields)) for k, c in CARD_MODELS.items()}
    best = max(scores.values())
    top = [k for k, v in scores.items() if v == best]
    return top[0] if best >= SCORE_MIN and len(top) == 1 else None


def _load_characters(raw, label, warnings):
    out, seen = [], set()
    for i, item in enumerate(raw):
        tag = M("{label}: character #{n}", label=label, n=i + 1)
        if not isinstance(item, dict):
            warnings.append(M("{tag} is {kind}, not an object; skipped", tag=tag, kind=_kind(item)))
            continue
        item = copy.deepcopy(item)
        if _name_of(item):
            tag = M("{label}: character #{n} ({name})", label=label, n=i + 1, name=_name_of(item))
        if not (isinstance(item.get("id"), str) and item["id"].strip()) and isinstance(item.get("name"), str) and item["name"].strip():
            item["id"] = slugify(item["name"])           # a character written as a draft has no id yet
            warnings.append(M("{tag}: had no id, so it was given '{id}'", tag=tag, id=item["id"]))
        obj, w, err = salvage(CharacterCard, item, tag)
        warnings.extend(w)
        if err:
            warnings.append(M("{tag}: not imported ({why})", tag=tag, why=err))
            continue
        d = obj.model_dump(mode="json")
        if d["id"] in seen:
            warnings.append(M("{tag}: id '{id}' is already used by an earlier character; skipped", tag=tag, id=d["id"]))
            continue
        seen.add(d["id"])
        out.append(d)
    return out


def soft_checks(c):
    """The same consistency checks the generator runs, over whichever cards are present. Advice only."""
    def parse(cls, v):
        try:
            return cls.model_validate(v)
        except ValidationError:                     # a card that does not fit is left out of the checks (advice only)
            return None
    chars = [x for x in (parse(CharacterCard, v) for v in (c.get("characters") or [])) if x]
    world, style, plot = parse(WorldBible, c.get("world")), parse(StyleCard, c.get("style")), parse(PlotOutline, c.get("outline"))
    out = []
    try:
        if style and chars:
            out += check_style(style, [x.name for x in chars])
        if chars:
            out += check_characters(chars, ({l.id for l in world.locations} | {o.id for o in world.objects}) if world else set())
        if world and chars:
            out += check_world(world, {x.id for x in chars})
        if plot and world and chars:
            out += check_outline(plot, {x.id for x in chars}, world)
    except Exception as e:
        logger.warning("consistency checks failed during import: %s", e)
    return out[:12] + ([M("...and {n} more", n=len(out) - 12)] if len(out) > 12 else [])


def import_cards(items, existing):
    """items: [(file name, parsed JSON)]. existing: the page's current cards (only used to merge single character files and for
    the consistency checks). Returns {cards: only the cards that were imported, imported: [...], warnings: [...], checks: [...]}."""
    warnings, found = [], {}
    chars = {"replace": None, "src": None, "loose": []}

    def put(kind, value, name):
        if kind == "characters":
            if not isinstance(value, list):
                warnings.append(M("{name}: 'characters' should be a list of characters, found {kind}; skipped", name=name, kind=_kind(value)))
                return
            if chars["replace"] is not None:
                warnings.append(M("{name}: a character list was already given in {src}; using this one instead", name=name, src=chars["src"]))
            chars["replace"], chars["src"] = value, name
            return
        if not isinstance(value, dict):
            warnings.append(M("{name}: '{kind}' should be an object, found {found}; skipped", name=name, kind=KIND[kind], found=_kind(value)))
            return
        if kind in found:
            warnings.append(M("{name}: a {kind} card was already given in {src}; using this one instead", name=name, kind=KIND[kind], src=found[kind][1]))
        found[kind] = (value, name)

    def extras(name, data, used):
        extra = [k for k in data if k not in used and k not in META_KEYS]
        if extra:
            warnings.append(M("{name}: ignored unrelated top-level field(s): {fields}", name=name, fields=", ".join(map(str, extra[:6]))))

    def handle(name, data, depth=0):
        if isinstance(data, list):
            put("characters", data, name)
            return
        if not isinstance(data, dict):
            warnings.append(M("{name}: expected a JSON object or list, found {kind}; skipped", name=name, kind=_kind(data)))
            return
        if data.get("format") == "pulpermill-project":
            warnings.append(M("{name}: this is a whole-project file; use Load project to open it. Skipped.", name=name))
            return
        wrapped = [k for k in WRAPPER_KEYS if k in data]
        if wrapped:
            for k in wrapped:
                put("outline" if k == "plot" else k, data[k], name)
            extras(name, data, wrapped)
            return
        if depth == 0 and isinstance(data.get("cards"), dict):
            handle(name, data["cards"], 1)
            extras(name, data, ["cards"])
            return
        kind = classify(data)
        if kind is None:
            warnings.append(M("{name}: not recognised as a style, character, world or setup card (its fields: {fields}); skipped",
                              name=name, fields=", ".join(map(str, sorted(data)[:6])) or M("none")))
        elif kind == "characters":
            chars["loose"].append((name, data))
        else:
            put(kind, data, name)

    for name, data in items:
        try:
            handle(name or "file", data)
        except Exception as e:                      # a file must never take the importer down
            logger.warning("import: %s could not be read as cards: %s: %s", name, type(e).__name__, e)
            warnings.append(M("{name}: could not be read as cards ({why}); skipped", name=name, why=f"{type(e).__name__}: {e}"))

    cards, imported = {}, []
    for kind in ("style", "world", "outline"):
        if kind in found:
            value, name = found[kind]
            obj, w, err = salvage(CARD_MODELS[kind], value, M("{name}: {kind}", name=name, kind=KIND[kind]))
            warnings.extend(w)
            if err:
                warnings.append(M("{name}: {kind} not imported ({why})", name=name, kind=KIND[kind], why=err))
                continue
            cards[kind] = obj.model_dump(mode="json")
            imported.append(KIND[kind])

    if chars["replace"] is not None or chars["loose"]:
        existing_chars = [c for c in ((existing or {}).get("characters") or []) if isinstance(c, dict)]
        replacing = chars["replace"] is not None
        final = _load_characters(chars["replace"], chars["src"], warnings) if replacing else list(existing_chars)
        touched = len(final) if replacing else 0
        for name, d in chars["loose"]:
            for c in _load_characters([d], name, warnings):
                at = next((i for i, x in enumerate(final) if x.get("id") == c["id"]), None)
                if at is None:
                    final.append(c)
                else:
                    final[at] = c
                touched += 0 if replacing else 1
        if final and touched:
            cards["characters"] = final
            imported.append(M("characters ({n})", n=len(final)) if replacing else
                            M("characters ({touched} added or updated, {n} in the cast)", touched=touched, n=len(final)))
        else:
            warnings.append(M("No valid characters were found, so the cast was left as it was."))

    merged = {k: v for k, v in (existing or {}).items() if v}
    merged.update(cards)
    return {"cards": cards, "imported": imported, "warnings": warnings, "checks": soft_checks(merged) if cards else []}
