#!/usr/bin/env python3
"""Offline gws double. Logs argv; never invokes a real CLI or network."""
import json
import os
import sys

args = sys.argv[1:]
for flag in ("--params", "--json", "--json-values"):
    if flag in args:
        json.loads(args[args.index(flag) + 1])
with open(os.environ["GWS_TEST_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args, ensure_ascii=False) + "\n")
method = args[3] if args[:3] == ["sheets", "spreadsheets", "values"] else (args[2] if len(args) > 2 else "")
with open(os.environ["GWS_TEST_LOG"], encoding="utf-8") as log:
    method_calls = sum(json.loads(line)[:3] == args[:3] for line in log)
if method == os.environ.get("GWS_TEST_FAIL") and method_calls >= int(os.environ.get("GWS_TEST_FAIL_AT", "1")):
    print("Simulated API failure", file=sys.stderr)
    sys.exit(7)
if args[:3] in (["sheets", "spreadsheets", "create"], ["sheets", "spreadsheets", "get"]):
    response = os.environ.get("GWS_TEST_RESPONSE")
    if response is None:
        payload = json.loads(args[args.index("--json") + 1]) if "--json" in args else {}
        tab = payload.get("sheets", [{}])[0].get("properties", {}).get("title", "Sheet1")
        response = json.dumps({
            "spreadsheetId": "test-sheet-id",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/test-sheet-id/edit",
            "sheets": [{"properties": {"sheetId": 42, "title": tab, "gridProperties": {"columnCount": 18278}}}],
        })
    print(response)
else:
    print("{}")
