"""Check documented shell examples against an offline native argument receiver."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which('pwsh')


def blocks(skill, shell):
    text = (ROOT / skill / 'references' / (shell + '.md')).read_text(encoding='utf-8')
    return re.findall(r'```[^\n]*\n(.*?)```', text, re.S)


def payloads(args):
    return {flag: json.loads(args[args.index(flag) + 1])
            for flag in ('--params', '--json') if flag in args}


class ShellDocumentationTests(unittest.TestCase):
    def test_references_resolve(self):
        for skill in ('gws-drive', 'gws-sheets'):
            text = (ROOT / skill / 'SKILL.md').read_text(encoding='utf-8')
            for reference in re.findall(r'\]\((references/[^)]+)\)', text):
                self.assertTrue((ROOT / skill / reference).is_file())
            self.assertTrue(blocks(skill, 'bash'))
            self.assertTrue(blocks(skill, 'powershell'))

    @unittest.skipUnless(PWSH, 'PowerShell unavailable; Windows CI runs these checks')
    def test_powershell_json_matches_bash_examples(self):
        with tempfile.TemporaryDirectory(prefix='shell examples ') as tmp:
            work = Path(tmp)
            log = work / 'calls.jsonl'
            env = dict(os.environ, GWS_TEST_LOG=str(log), PYTHONUTF8='1')
            python = str(Path(sys.executable)).replace("'", "''")
            fake = str(ROOT / 'tests/fake_gws.py').replace("'", "''")
            # A PowerShell function forwards to a native Python executable.
            # JSON validation happens in that process, after native arg passing.
            prefix = f"""
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion -lt [version]'7.3') {{ throw 'Need PowerShell 7.3+' }}
$PSNativeCommandArgumentPassing = 'Standard'
function gws.exe {{ & '{python}' '{fake}' @args }}
"""
            expected = {
                'gws-drive': [
                    {'--params': {'q': "name contains 'report' and trashed = false", 'pageSize': 20,
                                  'fields': 'nextPageToken,files(id,name,mimeType,webViewLink)'}},
                    {'--params': {'q': "'FOLDER_ID' in parents and trashed = false", 'pageSize': 100,
                                  'fields': 'nextPageToken,files(id,name,mimeType)'}},
                    {'--params': {'fileId': 'FILE_ID', 'fields': 'id,name,mimeType,parents,owners,modifiedTime,size,webViewLink'}},
                    {}, {'--params': {'fileId': 'FILE_ID', 'alt': 'media'}},
                    {'--params': {'fileId': 'FILE_ID', 'mimeType': 'application/pdf'}},
                    {'--json': {'name': 'Новая папка', 'mimeType': 'application/vnd.google-apps.folder', 'parents': ['PARENT_ID']}},
                    {'--params': {'fileId': 'FILE_ID', 'addParents': 'NEW_FOLDER_ID', 'removeParents': 'OLD_FOLDER_ID'}},
                    {'--params': {'fileId': 'FILE_ID'}, '--json': {'role': 'writer', 'type': 'user', 'emailAddress': 'someone@example.com'}},
                    {}, {}],
                'gws-sheets': [{},
                    {'--params': {'spreadsheetId': 'SPREADSHEET_ID', 'range': "'Страницы'!A:H", 'valueInputOption': 'RAW', 'insertDataOption': 'INSERT_ROWS'},
                     '--json': {'values': [['https://example.com/page', 'Title', '...']]}},
                    {'--params': {'spreadsheetId': 'SPREADSHEET_ID', 'range': 'Страницы!H2:H2', 'valueInputOption': 'USER_ENTERED'},
                     '--json': {'values': [['готово']]}},
                    {'--params': {'spreadsheetId': 'SPREADSHEET_ID', 'ranges': ['Страницы!A1:H1', 'Страницы!A50:H60']}}, {}]}
            for skill in expected:
                log.write_text('')
                for block in blocks(skill, 'powershell'):
                    if not re.search(r'^gws.exe (drive|sheets|schema) ', block, re.M):
                        continue
                    script = work / 'example.ps1'
                    script.write_text(prefix + block, encoding='utf-8-sig')
                    result = subprocess.run([PWSH, '-NoProfile', '-File', str(script)], cwd=work,
                                            env=env, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                calls = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
                self.assertEqual([payloads(c) for c in calls], expected[skill])
                if skill == 'gws-drive':
                    self.assertEqual(calls[3][-1], 'Отчёт.csv')

            # User values become data in the documented object/serializer path.
            value = 'Отчёт "Q4" client\'s $(Set-Content SHOULD_NOT_EXIST x)'
            operation = next(b for b in blocks('gws-drive', 'powershell')
                             if 'gws.exe drive files create' in b)
            operation = operation.replace('name = "Новая папка"', 'name = $UserName')
            script = work / 'special characters.ps1'
            script.write_text(prefix + "$UserName = '" + value.replace("'", "''") + "'\n" + operation,
                              encoding='utf-8-sig')
            log.write_text('')
            result = subprocess.run([PWSH, '-NoProfile', '-File', str(script)], cwd=work,
                                    env=env, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            call = json.loads(log.read_text(encoding='utf-8').strip())
            self.assertEqual(payloads(call)['--json']['name'], value)
            self.assertFalse((work / 'SHOULD_NOT_EXIST').exists())

    @unittest.skipUnless(PWSH, 'PowerShell unavailable; Windows CI runs these checks')
    def test_powershell_tracker_config_and_failure_stops_chain(self):
        with tempfile.TemporaryDirectory(prefix='tracker config ') as tmp:
            work = Path(tmp)
            receiver = work / 'receiver.py'
            receiver.write_text('import json, sys\nfrom pathlib import Path\nPath("argv.json").write_text(json.dumps(sys.argv[1:]))\n', encoding='utf-8')
            python = str(Path(sys.executable)).replace("'", "''")
            fake = str(receiver).replace("'", "''")
            block = next(b for b in blocks('gws-sheets', 'powershell') if '$config = ' in b)
            script = work / 'example.ps1'
            prefix = f"$ErrorActionPreference = 'Stop'\n$PSNativeCommandArgumentPassing = 'Standard'\nfunction py {{ & '{python}' '{fake}' @args }}\n"
            script.write_text(prefix + block, encoding='utf-8-sig')
            result = subprocess.run([PWSH, '-NoProfile', '-File', str(script)], cwd=work, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            config = json.loads((work / 'tracker.json').read_text(encoding='utf-8'))
            self.assertEqual(config['sheets'][0]['headers'][0], 'URL')
            args = json.loads((work / 'argv.json').read_text())
            self.assertEqual(args[-2:], ['--config', './tracker.json'])
            self.assertIn('create_tracker.py', args[-3])
            operation = next(b for b in blocks('gws-sheets', 'powershell') if 'gws.exe sheets spreadsheets values append' in b)
            prefix = f"$ErrorActionPreference = 'Stop'\n$PSNativeCommandArgumentPassing = 'Standard'\nfunction gws.exe {{ & '{python}' -c 'import sys; sys.exit(7)' }}\n"
            script.write_text(prefix + operation + '\nSet-Content SHOULD_NOT_EXIST x', encoding='utf-8-sig')
            result = subprocess.run([PWSH, '-NoProfile', '-File', str(script)], cwd=work, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((work / 'SHOULD_NOT_EXIST').exists())
