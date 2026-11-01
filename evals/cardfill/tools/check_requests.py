"""Checks requests against the backend contract, with no backend running.
Reads a JSON list of requests on stdin, parses each with pulpermill.contract.parse_request (the same check the server makes),
prints one line per request that fails, and exits 1 if any did. Used by `node tools/run_cardfill.mjs --dry`."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from pydantic import ValidationError  # noqa: E402
from pulpermill.contract import parse_request  # noqa: E402

requests = json.load(sys.stdin)
bad = 0
for i, entry in enumerate(requests):
    label, request = entry["label"], entry["request"]
    try:
        parse_request(request)
    except ValidationError as e:
        bad += 1
        first = e.errors()[0]
        print(f"BAD {label}: {'.'.join(str(p) for p in first['loc'])}: {first['msg']}")
print(f"checked {len(requests)} requests, {bad} refused")
sys.exit(1 if bad else 0)
