"""The `style_fit` call. Scaffold: runs the stub's flow until this module gets its own wording. Replace the body of build_flow, set VERSION,
and add the wording to text/en/style_fit.yaml (see README.md in this folder)."""
from . import common

VERSION = None      # None while this module is only the scaffold; the owner of the wording sets it (e.g. "style_fit-1") and bumps it with code changes


def build_flow(request, kit):
    return common.stub_flow("style_fit", request, kit)
