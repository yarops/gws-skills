#!/usr/bin/env python3
"""Opt-in real gws smoke tests. No agent or model calls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


class Run:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self.report = {"status": "running", "resources": [], "checks": [], "commands": []}
        self.save()

    def save(self):
        (self.directory / "report.json").write_text(json.dumps(self.report, ensure_ascii=False, indent=2))

    def command(self, args):
        entry = {"argv": args}
        self.report["commands"].append(entry)
        self.save()
        try:
            result = subprocess.run(args, text=True, capture_output=True, timeout=45)
        except subprocess.TimeoutExpired as error:
            entry.update({"timeout": True, "stdout": self.decode(error.stdout), "stderr": self.decode(error.stderr)})
            self.save()
            raise RuntimeError("Command timed out; do not retry creation blindly") from error
        entry.update({"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        self.save()
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout

    @staticmethod
    def decode(value):
        return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")

    def api(self, *args, params=None, body=None):
        command = ["gws", *args]
        if params is not None:
            command += ["--params", json.dumps(params, ensure_ascii=False)]
        if body is not None:
            command += ["--json", json.dumps(body, ensure_ascii=False)]
        return json.loads(self.command(command))

    def resource(self, file_id, kind):
        if not any(r["id"] == file_id for r in self.report["resources"]):
            self.report["resources"].append({"id": file_id, "kind": kind, "trashed": False})
            self.save()
        return file_id

    def check(self, name, condition):
        self.report["checks"].append({"name": name, "passed": bool(condition)})
        self.save()
        if not condition:
            raise RuntimeError(f"Verification failed: {name}")

    def tracker(self, *args):
        try:
            return self.command(["bash", str(ROOT / "gws-sheets/scripts/create_tracker.sh"), *args])
        finally:
            # Recover a known ID even when configuration failed or timed out.
            entry = self.report["commands"][-1]
            match = re.search(r"\(ID: ([A-Za-z0-9_-]+)\)", entry.get("stderr", ""))
            if match:
                self.resource(match[1], "spreadsheet")

    def cleanup(self):
        errors = []
        for resource in reversed(self.report["resources"]):
            try:
                self.api("drive", "files", "update", params={"fileId": resource["id"]}, body={"trashed": True})
                state = self.api("drive", "files", "get", params={"fileId": resource["id"], "fields": "id,trashed"})
                if state.get("trashed") is not True:
                    raise RuntimeError("Trash state was not confirmed")
                resource["trashed"] = True
            except Exception as error:
                errors.append(f"{resource['id']}: {error}")
            self.save()
        self.report["cleanup_errors"] = errors
        self.save()
        return errors

    def execute(self):
        suffix = uuid.uuid4().hex[:12]
        folder = self.resource(self.api("drive", "files", "create", body={
            "name": f"gws-skills-test-{suffix}", "mimeType": "application/vnd.google-apps.folder"})["id"], "folder")
        content = "CLI integration fixture: кириллица, quotes \" and newline\n".encode()
        source = self.directory / "fixture.txt"
        source.write_bytes(content)
        uploaded = json.loads(self.command(["gws", "drive", "+upload", str(source), "--parent", folder, "--name", "fixture.txt"]))
        file_id = self.resource(uploaded["id"], "uploaded-file")
        listing = self.api("drive", "files", "list", params={
            "q": f"'{folder}' in parents and trashed = false", "fields": "nextPageToken,files(id,name)", "pageSize": 100})
        self.check("uploaded file appears in folder", any(f["id"] == file_id for f in listing.get("files", [])))
        target = self.directory / "downloaded.txt"
        self.command(["gws", "drive", "files", "get", "--params", json.dumps({"fileId": file_id, "alt": "media"}), "--output", str(target)])
        self.check("downloaded bytes match upload", target.read_bytes() == content)

        headers = ["URL", '=SUM(A1:A2)', 'Статус "Q4"']
        tab = "Клиент's данные"
        tracker_url = self.tracker(f"gws-skills-test-{suffix}", json.dumps(headers, ensure_ascii=False), tab).strip()
        sheet_id = next(r["id"] for r in self.report["resources"] if r["kind"] == "spreadsheet")
        self.check("tracker returns its spreadsheet URL", tracker_url == f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
        self.api("drive", "files", "update", params={"fileId": sheet_id, "addParents": folder})
        a1 = "'" + tab.replace("'", "''") + "'"
        values = self.api("sheets", "spreadsheets", "values", "get", params={"spreadsheetId": sheet_id, "range": f"{a1}!A1:C1", "valueRenderOption": "FORMULA"})
        self.check("headers read back literally", values.get("values") == [headers])
        meta = self.api("sheets", "spreadsheets", "get", params={
            "spreadsheetId": sheet_id, "ranges": [f"{a1}!A1:C1"],
            "fields": "sheets(properties,data(rowData(values(userEnteredValue,userEnteredFormat))))"})
        sheet = next(s for s in meta["sheets"] if s["properties"]["title"] == tab)
        self.check("header row is frozen", sheet["properties"]["gridProperties"].get("frozenRowCount") == 1)
        cells = sheet["data"][0]["rowData"][0]["values"]
        self.check("formula-looking header has stringValue", cells[1]["userEnteredValue"] == {"stringValue": headers[1]})
        self.check("all headers have expected formatting", all(
            c["userEnteredFormat"]["textFormat"].get("bold") is True and
            c["userEnteredFormat"].get("horizontalAlignment") == "LEFT" for c in cells))
        rows = [["https://example.com/one", "001", "готово"], ["https://example.com/two", "=1+1", "новое"]]
        appended = self.api("sheets", "spreadsheets", "values", "append", params={
            "spreadsheetId": sheet_id, "range": f"{a1}!A:C", "valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}, body={"values": rows})
        self.check("append reports two rows", appended["updates"].get("updatedRows") == 2)
        values = self.api("sheets", "spreadsheets", "values", "get", params={"spreadsheetId": sheet_id, "range": f"{a1}!A1:C3", "valueRenderOption": "FORMULA"})
        self.check("append preserves headers and literal row values", values.get("values") == [headers, *rows])
        self.tracker("--resume", sheet_id, json.dumps(headers, ensure_ascii=False), tab)
        values = self.api("sheets", "spreadsheets", "values", "get", params={"spreadsheetId": sheet_id, "range": f"{a1}!A1:C3", "valueRenderOption": "FORMULA"})
        self.check("resume preserves appended data", values.get("values") == [headers, *rows])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Create test Google files, then trash known fixtures")
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    if not args.live:
        parser.error("Real API calls require --live; use unittest for offline tests")
    directory = args.report_dir or ROOT / "test-skills" / ("integration-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    run = Run(directory.resolve())
    failed = False
    try:
        # Connectivity/permissions preflight before any creation.
        run.api("drive", "files", "list", params={"pageSize": 1, "fields": "files(id)"})
        run.execute()
    except Exception as error:
        failed = True
        run.report["error"] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        cleanup_errors = run.cleanup()
        run.report["status"] = "failed" if failed or cleanup_errors else "passed"
        run.save()
        print(f"{run.report['status']}: {directory / 'report.json'}")
    return 1 if failed or cleanup_errors else 0


if __name__ == "__main__":
    sys.exit(main())
