"""Deterministic offline tests; requires Python 3, bash and jq only."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "gws-sheets/scripts/create_tracker.py"
URL = "https://docs.google.com/spreadsheets/d/test-sheet-id/edit"


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.log = self.work / "calls.jsonl"
        # Isolated PATH: neither an installed gws nor an agent can be called.
        for name in ("bash", "jq", "dirname", "python3"):
            source = shutil.which(name)
            if source is None:
                self.fail(f"Install required test dependency: {name}")
            (self.work / name).symlink_to(source)
        fake = self.work / "gws"
        fake.write_text(f"#!{shutil.which('python3')}\n" +
                        (ROOT / "tests/fake_gws.py").read_text().split("\n", 1)[1])
        fake.chmod(0o755)
        self.env = {"PATH": str(self.work), "HOME": str(self.work),
                    "LANG": "C.UTF-8", "GWS_TEST_LOG": str(self.log)}

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def run_tracker(self, *args, **env):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              cwd=self.work, env=self.env | env, text=True,
                              capture_output=True, timeout=15)

    def payload(self, call, flag="--json"):
        return json.loads(call[call.index(flag) + 1])


class SkillFilesTests(OfflineCase):
    def test_metadata_and_local_resources(self):
        for name in ("gws-drive", "gws-sheets"):
            with self.subTest(skill=name):
                text = (ROOT / name / "SKILL.md").read_text()
                metadata = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
                self.assertIsNotNone(metadata)
                self.assertRegex(metadata[1], rf"(?m)^name: {name}$")
                self.assertRegex(metadata[1], r"(?m)^description: \S.+$")
                for resource in re.findall(r"`((?:scripts|assets)/[^`\s]+)`", text):
                    self.assertTrue((ROOT / name / resource).is_file(), resource)

    def test_documented_commands_parse_and_have_valid_json(self):
        count = 0
        for name in ("gws-drive", "gws-sheets"):
            text = (ROOT / name / "SKILL.md").read_text()
            for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
                # Syntax placeholders are not executable examples.
                if not block.startswith("gws ") or "<resource>" in block:
                    continue
                with self.subTest(skill=name, command=block):
                    result = subprocess.run([str(self.work / "bash"), "-c", block],
                                            env=self.env, cwd=self.work, capture_output=True,
                                            text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    count += 1
        self.assertGreaterEqual(count, 15)


class TrackerTests(OfflineCase):
    def config_file(self, config):
        path = self.work / "tracker config.json"
        path.write_text(json.dumps(config, ensure_ascii=False))
        return str(path)

    def test_config_creates_and_styles_three_sheets(self):
        config = {"title": "План", "sheets": [
            {"title": "Статьи", "headers": ["URL", "Статус"]},
            {"title": "Ключи", "headers": ["=literal"]},
            {"title": "Сводка", "headers": ["Имя", "Значение", "Дата"]}]}
        result = self.run_tracker("--config", self.config_file(config))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, URL + "\n")
        calls = self.calls()
        create = self.payload(calls[0])
        self.assertEqual(create["properties"]["title"], config["title"])
        self.assertEqual(len(create["sheets"]), 3)
        self.assertEqual(len(calls), 4)
        for i, sheet in enumerate(config["sheets"]):
            self.assertEqual(create["sheets"][i]["properties"], {
                "title": sheet["title"], "gridProperties": {"columnCount": len(sheet["headers"])}})
            requests = self.payload(calls[i + 1])["requests"]
            self.assertEqual(requests[0]["updateCells"]["start"]["sheetId"], 42 + i)
            self.assertEqual(requests[0]["updateCells"]["rows"][0]["values"],
                             [{"userEnteredValue": {"stringValue": h}} for h in sheet["headers"]])
            self.assertEqual(requests[1]["repeatCell"]["range"]["endColumnIndex"], len(sheet["headers"]))
            self.assertEqual(requests[2]["updateSheetProperties"]["properties"]["sheetId"], 42 + i)

    def test_config_failure_and_resume_by_title(self):
        config = {"title": "T", "sheets": [
            {"title": "A", "headers": ["a"]}, {"title": "B", "headers": ["b", "c"]}]}
        path = self.config_file(config)
        result = self.run_tracker("--config", path, GWS_TEST_FAIL="batchUpdate", GWS_TEST_FAIL_AT="2")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "")
        self.assertIn("--resume", result.stderr)
        self.log.write_text("")
        response = {"spreadsheetId": "test-sheet-id", "spreadsheetUrl": URL, "sheets": [
            {"properties": {"sheetId": 8, "title": "B", "gridProperties": {"columnCount": 2}}},
            {"properties": {"sheetId": 0, "title": "A", "gridProperties": {"columnCount": 1}}}]}
        result = self.run_tracker("--resume", "test-sheet-id", "--config", path,
                                  GWS_TEST_RESPONSE=json.dumps(response))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c[2] for c in self.calls()], ["get", "batchUpdate", "batchUpdate"])
        self.assertEqual([self.payload(c)["requests"][0]["updateCells"]["start"]["sheetId"]
                          for c in self.calls()[1:]], [0, 8])
        self.log.write_text("")
        response["sheets"].pop(0)
        result = self.run_tracker("--resume", "test-sheet-id", "--config", path,
                                  GWS_TEST_RESPONSE=json.dumps(response))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([c[2] for c in self.calls()], ["get"])

    def test_invalid_configs_never_call_gws(self):
        for config in ({}, {"title": "T", "sheets": []},
                       {"title": "T", "sheets": [{"title": "A", "headers": []}]},
                       {"title": "T", "sheets": [{"title": "A", "headers": ["a"]},
                                                  {"title": "a", "headers": ["b"]}]},
                       {"title": "T", "sheets": [{"title": "A", "headers": ["a"]},
                                                  {"title": "B", "headers": ["x" * 60000]}]}):
            with self.subTest(config=str(config)[:100]):
                self.assertNotEqual(self.run_tracker("--config", self.config_file(config)).returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_create_defaults(self):
        result = self.run_tracker("Tracker", '["URL","Status"]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, URL + "\n")
        calls = self.calls()
        self.assertEqual([c[:3] for c in calls], [
            ["sheets", "spreadsheets", "create"], ["sheets", "spreadsheets", "batchUpdate"]])
        create = self.payload(calls[0])
        self.assertEqual(create["properties"]["title"], "Tracker")
        self.assertEqual(create["sheets"][0]["properties"],
                         {"title": "Sheet1", "gridProperties": {"columnCount": 2}})
        self.assertEqual(self.payload(calls[1], "--params"), {"spreadsheetId": "test-sheet-id"})
        requests = self.payload(calls[1])["requests"]
        cells = requests[0]["updateCells"]
        self.assertEqual(cells["start"], {"sheetId": 42, "rowIndex": 0, "columnIndex": 0})
        self.assertEqual(cells["fields"], "userEnteredValue")
        self.assertEqual(cells["rows"][0]["values"], [
            {"userEnteredValue": {"stringValue": "URL"}},
            {"userEnteredValue": {"stringValue": "Status"}}])
        style = requests[1]["repeatCell"]
        self.assertEqual(style["range"], {"sheetId": 42, "startRowIndex": 0,
                                         "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 2})
        self.assertTrue(style["cell"]["userEnteredFormat"]["textFormat"]["bold"])
        freeze = requests[2]["updateSheetProperties"]
        self.assertEqual(freeze["properties"], {"sheetId": 42, "gridProperties": {"frozenRowCount": 1}})
        self.assertEqual(freeze["fields"], "gridProperties.frozenRowCount")
        self.assertEqual(requests[3]["autoResizeDimensions"]["dimensions"],
                         {"sheetId": 42, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 2})

    def test_special_characters_and_formula_headers_are_literal(self):
        title = 'Отчёт "Q4" $(touch SHOULD_NOT_EXIST)'
        tab = "Клиент's данные!"
        headers = ['=SUM(A1:A2)', '"кавычки"', "строка\nдва", "$(touch SHOULD_NOT_EXIST)", "a,b"]
        result = self.run_tracker(title, json.dumps(headers), tab)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(self.payload(calls[0])["properties"]["title"], title)
        self.assertEqual(self.payload(calls[0])["sheets"][0]["properties"]["title"], tab)
        values = self.payload(calls[1])["requests"][0]["updateCells"]["rows"][0]["values"]
        self.assertEqual(values, [{"userEnteredValue": {"stringValue": h}} for h in headers])
        self.assertFalse((self.work / "SHOULD_NOT_EXIST").exists())

    def test_invalid_headers_never_call_gws(self):
        for headers in ("broken", "{}", "[]", '[""]', '[1]', '[null]', '[true]', '[["x"]]', '["ok", ""]',
                        json.dumps(["x"] * 18279)):
            with self.subTest(headers=headers[:50]):
                result = self.run_tracker("Tracker", headers)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.calls(), [])

    def test_invalid_argument_counts_never_call_gws(self):
        for args in ((), ("Title",), ("T", '["x"]', "S", "extra"),
                     ("--resume",), ("--resume", "id"), ("--resume", "", '["x"]'), ("", '["x"]')):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_tracker(*args).returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_missing_dependencies_never_call_gws(self):
        for dependency in ("gws",):
            with self.subTest(dependency=dependency):
                original = self.work / dependency
                backup = self.work / (dependency + ".saved")
                original.rename(backup)
                try:
                    result = self.run_tracker("T", '["x"]')
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(dependency, result.stderr)
                    self.assertEqual(self.calls(), [])
                finally:
                    backup.rename(original)

    def test_resume_reads_existing_file_without_creating_duplicate(self):
        result = self.run_tracker("--resume", "test-sheet-id", '["x"]')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual([c[2] for c in calls], ["get", "batchUpdate"])
        self.assertEqual(self.payload(calls[0], "--params")["spreadsheetId"], "test-sheet-id")

    def test_maximum_supported_column_count(self):
        headers = ["x"] * 18278
        result = self.run_tracker("Wide tracker", json.dumps(headers))
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(self.payload(calls[0])["sheets"][0]["properties"]["gridProperties"]["columnCount"], 18278)
        offset = 0
        for call in calls[1:]:
            requests = self.payload(call)["requests"]
            cells = requests[0]["updateCells"]
            self.assertEqual(cells["start"]["columnIndex"], offset)
            offset += len(cells["rows"][0]["values"])
            self.assertLess(len(call[call.index("--json") + 1].encode()), 65000)
        self.assertEqual(offset, 18278)
        self.assertEqual(self.payload(calls[-1])["requests"][1]["repeatCell"]["range"]["endColumnIndex"], 18278)

    def test_resume_selects_named_tab_and_accepts_sheet_id_zero(self):
        response = {"spreadsheetId": "test-sheet-id", "spreadsheetUrl": URL,
                    "sheets": [{"properties": {"sheetId": 99, "title": "Other", "gridProperties": {"columnCount": 1}}},
                               {"properties": {"sheetId": 0, "title": "Целевая", "gridProperties": {"columnCount": 2}}}]}
        result = self.run_tracker("--resume", "test-sheet-id", '["a","b"]', "Целевая",
                                  GWS_TEST_RESPONSE=json.dumps(response))
        self.assertEqual(result.returncode, 0, result.stderr)
        cells = self.payload(self.calls()[1])["requests"][0]["updateCells"]
        self.assertEqual(cells["start"]["sheetId"], 0)

    def test_chunking_counts_utf8_bytes_and_preserves_all_headers(self):
        headers = ['Я"\n' * 100] * 150
        result = self.run_tracker("T", json.dumps(headers, ensure_ascii=False))
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()[1:]
        self.assertGreater(len(calls), 1)
        actual = []
        for call in calls:
            self.assertLess(len(call[call.index("--json") + 1].encode()), 65000)
            requests = self.payload(call)["requests"]
            cells = requests[0]["updateCells"]
            self.assertEqual(cells["start"]["columnIndex"], len(actual))
            actual.extend(v["userEnteredValue"]["stringValue"] for v in cells["rows"][0]["values"])
        self.assertEqual(actual, headers)
        self.assertTrue(all(len(self.payload(c)["requests"]) == 1 for c in calls[:-1]))
        self.assertEqual(len(self.payload(calls[-1])["requests"]), 4)

    def test_overlong_single_header_is_rejected_before_creation(self):
        result = self.run_tracker("T", json.dumps(["x" * 60000]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("слишком длинный", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_failure_in_second_chunk_stops_and_allows_resume(self):
        headers = json.dumps(["x"] * 5000)
        result = self.run_tracker("T", headers, GWS_TEST_FAIL="batchUpdate", GWS_TEST_FAIL_AT="2")
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("--resume", result.stderr)
        self.assertEqual(len(self.calls()), 3)
        self.log.write_text("")
        resumed = self.run_tracker("--resume", "test-sheet-id", headers)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(self.calls()[0][2], "get")
        self.assertNotIn("create", [c[2] for c in self.calls()])
        self.assertEqual(self.payload(self.calls()[1])["requests"][0]["updateCells"]["start"]["columnIndex"], 0)

    def test_api_failures_preserve_exit_code_and_do_not_report_success(self):
        for method in ("create", "get", "batchUpdate"):
            with self.subTest(method=method):
                args = ("--resume", "test-sheet-id", '["x"]') if method == "get" else ("T", '["x"]')
                result = self.run_tracker(*args, GWS_TEST_FAIL=method)
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(result.stdout, "")
                if method == "create":
                    self.assertIn("Перед повтором проверьте Drive", result.stderr)
                else:
                    self.assertIn("--resume", result.stderr)
                    self.assertIn("test-sheet-id", result.stderr)

    def test_bad_api_responses_do_not_write(self):
        base = {"spreadsheetId": "test-sheet-id", "spreadsheetUrl": URL,
                "sheets": [{"properties": {"sheetId": 42, "title": "Sheet1",
                                          "gridProperties": {"columnCount": 2}}}]}
        cases = ["bad json", "{}"]
        for field in ("spreadsheetId", "spreadsheetUrl", "sheets"):
            response = dict(base)
            del response[field]
            cases.append(json.dumps(response))
        for properties in (
            {"sheetId": 42, "title": "Other", "gridProperties": {"columnCount": 2}},
            {"sheetId": -1, "title": "Sheet1", "gridProperties": {"columnCount": 2}},
            {"sheetId": 0.5, "title": "Sheet1", "gridProperties": {"columnCount": 2}},
            {"sheetId": 42, "title": "Sheet1", "gridProperties": {"columnCount": 0}},
        ):
            cases.append(json.dumps(base | {"sheets": [{"properties": properties}]}))
        cases.append(json.dumps(base | {"sheets": base["sheets"] * 2}))
        for response in cases:
            with self.subTest(response=response):
                if self.log.exists():
                    self.log.write_text("")
                result = self.run_tracker("--resume", "test-sheet-id", '["x"]', GWS_TEST_RESPONSE=response)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(self.calls()), 1)
                self.assertNotIn("batchUpdate", [c[2] for c in self.calls()])


class IntegrationGuardTests(OfflineCase):
    def test_live_flag_is_required(self):
        report = self.work / "report"
        result = subprocess.run([sys.executable, "-B", str(ROOT / "tests/integration_gws.py"),
                                 "--report-dir", str(report)], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("require --live", result.stderr)
        self.assertFalse(report.exists())
        self.assertEqual(self.calls(), [])

    def test_preflight_failure_prevents_creation_and_is_reported(self):
        report = self.work / "report"
        result = subprocess.run([sys.executable, "-B", str(ROOT / "tests/integration_gws.py"),
                                 "--live", "--report-dir", str(report)],
                                env=self.env | {"GWS_TEST_FAIL": "list"},
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual([c[:3] for c in self.calls()], [["drive", "files", "list"]])
        saved = json.loads((report / "report.json").read_text())
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["resources"], [])
        self.assertIn("Simulated API failure", saved["error"])


if __name__ == "__main__":
    unittest.main()
