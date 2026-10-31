# Prompters

A prompter is the replaceable module that decides **wording**: what to ask the model and what shape the answer has. The backend's runner
(`pulpermill/backend/runner.py`) does everything mechanical: it fits and squeezes prompts to the context before the first token and answers
`too_long` early, applies the two-attempt rule and its retry line, handles cancel and progress (`{name, index, of}`), writes the run log,
maps the model's handles back to ids and assembles the contract's reply. A prompter must never need the runner to change.

Choose one by name: `Config.prompter` (default `stub`) is the folder name under `pulpermill/prompter/`. The folder exposes
`prompter()`, returning a `Prompter` whose `name` equals the folder name. An unknown name stops the server at startup, listing the known ones.
The run log records the prompter's `name` and `version` with every call, so change `version` whenever any wording changes.

The interface uses no story vocabulary: only the five calls, `fill`, `judge`, `style_fit`, `plan`, `generate` (`CALLS`).

## The interface (`base.py`)

```python
class Prompter:  name; version; flow(call, request: dict, kit) -> Flow
class Flow:      next(results) -> Step | None;  reply(results) -> dict;  worst_case() -> list[Step];  notes: dict
class Step:      name, text(squeeze) -> str, kind "text"|"json", max_output, grammar, check, sampling, language
```

* **`Prompter.flow(call, request, kit)`**: one Flow per request. `request` is the validated request as a plain dict.
* **`Flow.next(results)`**: the step to run now given the results so far (a list, empty at first); `None` when the call is done. A result is
  the parsed JSON of a `json` step and the text of a `text` step. A call may have any number of steps, chosen from earlier results.
* **`Flow.reply(results)`**: the call's reply, in the model's own references (see below). The runner adds `ok` and turns handles into ids.
* **`Flow.worst_case()`**: every step the call may run, each as heavy as it can get (a step that reads an earlier reply gets a stand-in of
  that reply's largest size). The runner fits them all together before the first token. Default: the first step only. `of` in the progress
  is the length of this list.
* **`Flow.notes`**: optional counts for the run log (numbers, booleans and short plain words are kept; anything else is dropped).
* **`Step`**:
  * `name`: letters, digits, `-`, `_`, at most 32. It is what `status` shows. Steps may share a name.
  * `text(squeeze)`: the prompt (one user turn). `squeeze` is 1.0 for the fullest prompt and smaller when the runner needs it shorter
    (steps of 0.85, 0.7, 0.55, 0.4, 0.3); the prompter decides what to cut. The renderers' `textfiles.squeeze(f)` scales the schema caps.
  * `kind`: `text` or `json`. A `json` step needs `grammar`, a JSON Schema (constrained decoding and the check of a free reply).
  * `max_output`: the most tokens the reply may take; the context keeps that much free. It belongs to the step, not to a budget file.
  * `check(value)`: optional; return `None` or one plain line saying what is wrong. The line is shown to the model on the retry.
  * `sampling`: `prose`, `thinking` or `structured`: the Config's sampling sets (the story language picks Chinese's own `prose`).
  * `language`: True when the reply is written in the story's language, so the runner checks it.

## The kit (what the runner offers)

* `kit.handles`: a short code for each list item the request sent, so the model points at an item without seeing an id. A handle is
  `<list key>.<position from 1>` (`ties.2`, `wants.1`), scoped to a card: `handles.scopes` has one per character in the cast, one for the
  world and one for the ties and holdings (for a fill or a judge, the one card). `scope.handles(key)` lists the handles of a list,
  `scope.of(key, item_id)` gives the handle of an item to show next to it, `scope.label` is the name the model uses for a character.
  Only what the request sent has a handle, and the model cannot point at anything else.
* `kit.grammar`: grammars that follow from the cards alone: `fill()` (the card's fields, all optional, links limited to the names the
  related cards sent), `plan_beat()` (the planner's fields of a beat), `shifts()` (a list of `{card, target, patch}`, one entry per card the
  request sent, a patch built from `shiftable_fields`: a scalar is its new value, a list is `add` / `replace` / `remove` operations on
  handles). The small pieces for any other shape: `text()`, `maybe(s)`, `one_of(names)`, `list_of(names, limit)`, `obj(props, required)`.
* `kit.shifts_problem(entries)`: `None`, or one line saying why the shifts cannot be turned into valid entries. Use it as the `check`
  of the step that writes shifts.

## Draft replies (what `Flow.reply` returns)

The contract's reply without `ok`, with handles where the contract has ids:

| call | draft |
| --- | --- |
| `fill` | `{"values": {field: value}}` |
| `judge` | `{"results": [{"rule": id, "hits": [{"field": key, "item": handle or None, "key": None}]}]}`, one result per rule asked (none for a rule with nothing to look at: give it no hits) |
| `style_fit` | `{"fits": bool, "message": str}` |
| `plan` | `{"beat": {field: value}}` |
| `generate` | `{"chapter_text": str, "events": {"happened", "changed"}, "shifts": [{"card", "target": a character's label or None, "patch": {...}}]}`; list operations name items by handle |

The runner refuses a draft that names a handle or card the request did not send (`bad_output`), drops a shift whose patch holds nothing,
and checks every patch with `validate_patch`.

## Testing a prompter

`stub/` is the model: trivial prompts, the correct grammar for every step, and `script(call, request, kit)` giving the texts a
`FakeEngine` must return, one per step, for a valid reply (`engine.script(*script(...))`). `tests/backend/test_conformance.py` runs every
request in `tests/shared/contract-vectors.json` through the real server, the runner and the stub that way.
