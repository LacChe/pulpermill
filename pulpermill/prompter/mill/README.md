# mill

The prompter that holds the product's own wording for the five calls (`fill`, `judge`, `style_fit`, `plan`, `generate`). Choose it with
`Config.prompter = "mill"`; the default stays `stub` until the real-model run says otherwise (see `../DECISIONS.md`). The interface it
implements is in `../README.md` and `../base.py`.

## Layout
```
__init__.py   prompter() -> MillPrompter (name "mill"); VERSION = "mill-0.1"; script(call, request, kit) for the fake engine
mill.py       MillPrompter.flow(call, request, kit): finds the module for `call` by name; none, or still the scaffold: the stub's flow
common.py     load_text (wording files), text_digest, labelled (item + handle), clip (squeeze helper), stub_flow
fill.py judge.py style_fit.py plan.py generate.py    one module per call
text/en/<call>.yaml                                  that call's wording (empty until written)
```

## The contract between mill.py and a call module (the whole of it)
```python
VERSION = "plan-1"                      # optional; None or missing means "still the scaffold"
def build_flow(request, kit) -> Flow    # required
def script(request, kit) -> list[str]   # optional; the texts a FakeEngine must return, one per step, for a valid reply
```
`mill.py` imports `pulpermill.prompter.mill.<call>` on every request, so a module can be replaced without touching `mill.py` or any other
call's file. Each call is owned by one person at a time: B1 owns `plan.py`, `generate.py` and their yaml; B2 owns `fill.py`, `judge.py`,
`style_fit.py` and theirs.

## Adding wording to a call
1. Replace the body of `build_flow` in `<call>.py` with a Flow (`base.Flow`, `base.Step`). Use the kit's grammars and handles.
2. Put the wording in `text/en/<call>.yaml` and read it with `common.load_text("<call>")`. Instructions to the model are English;
   wording is positive; the model sees names, never ids.
3. Set `VERSION` and bump it with every change to the module's code. Wording edits need no bump by hand (below).
4. Add `script(request, kit)` so the fake engine can drive the call. Without it `mill.script` raises, and the conformance test names the call.
5. Run `python -m pytest tests/prompter tests/backend -q`.

## Version
`MillPrompter.version` is `mill-0.1` plus one piece for each call with its own wording: `+<call>:<module VERSION>:<digest>`, for example
`mill-0.1+plan:plan-1:a3f9c2`. The digest is six hex characters of `text/en/<call>.yaml` and changes by itself with any wording edit; the
module `VERSION` covers code. A call still on the stub's flow adds nothing. The run log records the name and this version with every call.
Change `VERSION` in `__init__.py` only for a change to the scaffold itself.

## Rules
Nothing here imports from `docs/` or needs a model. The mill never edits `pulpermill/backend/` or `pulpermill/prompts/` (it may read them).
