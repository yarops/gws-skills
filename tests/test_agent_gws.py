"""Offline checks for behavioral fixtures and graders; no model calls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent_gws import HEADERS, ROWS, ROOT, evaluate, prepare, run


class AgentScenarioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work, self.fixture, _, self.env = prepare(Path(self.tmp.name), 'sheets')

    def gws(self, *args):
        return subprocess.run([str(Path(self.tmp.name) / 'bin/gws'), *args], cwd=self.work,
                              env=self.env, capture_output=True, text=True)

    def test_empty_state_cannot_pass(self):
        for scenario in ('drive', 'sheets'):
            self.assertFalse(evaluate(scenario, self.work, self.fixture, [])['passed'])

    def test_drive_pagination_and_bytes(self):
        self.assertEqual(self.gws('auth', 'status').returncode, 0)
        for token in (None, 'page-2'):
            params = {'q': "'fixture-folder' in parents and trashed = false and mimeType = 'text/plain'"}
            if token:
                params['pageToken'] = token
            response = self.gws('drive', 'files', 'list', '--params', json.dumps(params))
            self.assertEqual(response.returncode, 0, response.stderr)
            for f in json.loads(response.stdout)['files']:
                download = self.gws('drive', 'files', 'get', '--params',
                                    json.dumps({'fileId': f['id'], 'alt': 'media'}),
                                    '--output', str(self.work / 'downloads' / f['name']))
                self.assertEqual(download.returncode, 0, download.stderr)
        self.assertTrue(evaluate('drive', self.work, self.fixture, [])['passed'])
        (self.work / 'downloads/notes.txt').write_text('corrupted')
        self.assertFalse(evaluate('drive', self.work, self.fixture, [])['passed'])

    def test_tracker_append_read_and_grader(self):
        self.gws('auth', 'status')
        script = self.work / '.agents/skills/gws-sheets/scripts/create_tracker.sh'
        run = subprocess.run([str(script), 'Агент: тест', json.dumps(HEADERS), 'Страницы'],
                             cwd=self.work, env=self.env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        params = {'spreadsheetId': 'fixture-sheet', 'range': "'Страницы'!A:C", 'valueInputOption': 'RAW'}
        append = self.gws('sheets', 'spreadsheets', 'values', 'append', '--params', json.dumps(params),
                          '--json', json.dumps({'values': ROWS}))
        self.assertEqual(append.returncode, 0, append.stderr)
        self.gws('sheets', '+read', '--spreadsheet', 'fixture-sheet', '--range', 'Страницы!A1:C3')
        events = [{'type': 'item.completed', 'item': {'type': 'command_execution',
                   'command': str(script), 'exit_code': 0}}]
        self.assertTrue(evaluate('sheets', self.work, self.fixture, events)['passed'])
        self.assertFalse(evaluate('sheets', self.work, self.fixture, [])['passed'])
        mention = [{'type': 'item.completed', 'item': {'type': 'command_execution',
                   'command': 'cat ' + str(script), 'exit_code': 0}}]
        self.assertFalse(evaluate('sheets', self.work, self.fixture, mention)['passed'])
        state = json.loads((self.fixture / 'state.json').read_text())
        state['formatting'][0]['repeatCell']['range']['sheetId'] = 0
        (self.fixture / 'state.json').write_text(json.dumps(state))
        self.assertFalse(evaluate('sheets', self.work, self.fixture, events)['passed'])

    def test_unsupported_command_and_overwrite_rejected(self):
        self.assertNotEqual(self.gws('drive', 'files', 'delete', '--params', '{"fileId":"file-a"}').returncode, 0)
        target = self.work / 'downloads/existing.txt'
        target.write_text('keep')
        self.assertNotEqual(self.gws('drive', 'files', 'get', '--params',
                                    '{"fileId":"file-a","alt":"media"}', '--output', str(target)).returncode, 0)
        self.assertEqual(target.read_text(), 'keep')


class AgentRunnerTests(unittest.TestCase):
    def test_explicit_flag_required(self):
        result = subprocess.run([os.sys.executable, '-B', str(ROOT / 'tests/agent_gws.py'),
                                 '--scenario', 'drive', '--report-dir', '/unused'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--run-agent', result.stderr)

    def test_timeout_and_usage_reports_without_models(self):
        for kind in ('timeout', 'usage'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                auth_home = base / 'auth'
                auth_home.mkdir()
                (auth_home / 'auth.json').write_text('{}')
                cli = base / 'fake-codex'
                payload = ('import time; time.sleep(30)' if kind == 'timeout' else
                           'print(\'{"type":"turn.completed","usage":{"input_tokens":123,"output_tokens":7}}\', flush=True)')
                cli.write_text('#!' + os.sys.executable + '\nimport sys\nsys.stdin.read()\n' + payload + '\n')
                cli.chmod(0o755)
                args = SimpleNamespace(codex=str(cli), report_dir=str(base / 'report'),
                                       scenario='drive', timeout=1, max_tokens=100, model='test')
                with patch.dict(os.environ, {'CODEX_HOME': str(auth_home), 'OPENAI_API_KEY': ''}):
                    self.assertEqual(run(args), 1)
                report = json.loads((base / 'report/report.json').read_text())
                self.assertFalse(report['passed'])
                command = json.loads((base / 'report/command.json').read_text())
                self.assertFalse(Path(command[command.index('-C') + 1]).exists())
                if kind == 'timeout':
                    self.assertEqual(report['stop_reason'], 'timeout')
                    self.assertFalse(report['completed'])
                else:
                    self.assertEqual(report['reported_tokens'], 130)
                    self.assertTrue(report['token_threshold_exceeded'])
                    self.assertTrue(report['completed'])
