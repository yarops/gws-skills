"""Portable tracker tests: standard library only, no executable CLI required."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'gws-sheets/scripts/create_tracker.py'
spec = importlib.util.spec_from_file_location('tracker', SCRIPT)
tracker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tracker)


class PortableTrackerTests(unittest.TestCase):
    def test_direct_argv_preserves_unicode_quotes_and_metacharacters(self):
        response = {'spreadsheetId': 'id', 'spreadsheetUrl': 'https://example.test/id',
                    'sheets': [{'properties': {'title': 'Лист', 'sheetId': 0,
                                              'gridProperties': {'columnCount': 1}}}]}
        calls = []

        def execute(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, json.dumps(response).encode(), b'')

        with patch.object(tracker.shutil, 'which', return_value='C:/Program Files/gws.exe'), \
                patch.object(tracker.subprocess, 'run', side_effect=execute), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tracker.main(['Название $() "', '["=SUM(A1:A2)"]', 'Лист']), 0)
        command, kwargs = calls[0]
        self.assertEqual(command[0], 'C:/Program Files/gws.exe')
        self.assertNotIn('shell', kwargs)
        self.assertEqual(json.loads(command[-1])['properties']['title'], 'Название $() "')
        values = json.loads(calls[1][0][-1])['requests'][0]['updateCells']['rows'][0]['values']
        self.assertEqual(values, [{'userEnteredValue': {'stringValue': '=SUM(A1:A2)'}}])

    def test_windows_chunking_and_oversized_cell_validation(self):
        with patch.object(tracker.sys, 'platform', 'win32'):
            with self.assertRaises(ValueError):
                tracker.parse(['T', json.dumps(['x' * 6000])])
            headers = ['Я"' * 20] * 500
            style = {'requests': [{'updateSheetProperties': {'properties': {}}}]}
            batches = list(tracker.batches(headers, 0, style))
            actual = []
            for batch in batches:
                actual.extend(v['userEnteredValue']['stringValue']
                              for v in batch['requests'][0]['updateCells']['rows'][0]['values'])
                command = ['C:/Program Files/gws.exe', '--json', tracker.encode(batch)]
                self.assertLess(len(subprocess.list2cmdline(command).encode('utf-16-le')) // 2, 30000)
            self.assertGreater(len(batches), 1)
            self.assertEqual(actual, headers)

    def test_batch_wrapper_is_rejected_before_api(self):
        with patch.object(tracker.shutil, 'which', return_value='gws.cmd'), \
                patch.object(tracker.subprocess, 'run') as execute, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tracker.main(['T', '["x"]']), 1)
            execute.assert_not_called()
