#!/usr/bin/env python3
"""Explicit, bounded behavioral evaluation; never calls real gws or Google."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / 'tests/agent_scenarios'
HEADERS = ['URL', '=1+1', 'Статус']
ROWS = [['https://example.com/а', '=2+2', 'готово'],
        ['https://example.com/b', 'текст', 'в работе']]
FILES = {'file-a': {'name': 'Отчёт.txt', 'mimeType': 'text/plain', 'content': 'Первая строка\n'},
         'file-b': {'name': 'notes.txt', 'mimeType': 'text/plain', 'content': 'Second file\n'},
         'file-c': {'name': 'ignore.bin', 'mimeType': 'application/octet-stream', 'content': 'skip'}}


def prepare(base, scenario, selection_case=None):
    work = base / 'work'
    work.mkdir()
    (work / 'downloads').mkdir()
    fixture = base / 'fixture'
    fixture.mkdir()
    (fixture / 'state.json').write_text(json.dumps({'files': FILES}, ensure_ascii=False))
    binary = base / 'bin'
    binary.mkdir()
    fake = binary / 'gws'
    fake.write_text('#!' + sys.executable + '\n' +
                    (SCENARIOS / 'fake_gws.py').read_text().split('\n', 1)[1])
    fake.chmod(0o755)
    for utility in ('bash', 'sh', 'jq', 'python3', 'cat', 'ls', 'mkdir', 'dirname', 'pwd', 'sed', 'rg', 'env'):
        source = shutil.which(utility)
        if source:
            (binary / utility).symlink_to(source)
    for skill in ('gws-drive', 'gws-sheets'):
        shutil.copytree(ROOT / skill, work / '.agents/skills' / skill)
    (work / 'AGENTS.md').write_text(
        'Это изолированный тест. Работай только в текущей директории. '
        'Для операций Google используй только gws из PATH. Не обращайся к сети, '
        'реальным CLI, credentials или файлам вне рабочей директории. '
        'Не читай и не изменяй тестовое состояние, журналы или подставной gws. '
        'Не изменяй скилы. Выполни задачу самостоятельно без делегирования.\n')
    spec = json.loads((SCENARIOS / (scenario + '.json')).read_text())
    prompt = spec['prompt'] + '\nСкил находится в ' + str(work / '.agents/skills' / spec['skill'] / 'SKILL.md')
    if selection_case is not None:
        from selection_gws import setup_case
        prompt = setup_case(selection_case, work, fixture)
    env = {'PATH': str(binary), 'LANG': 'C.UTF-8', 'GWS_AGENT_FIXTURE': str(fixture)}
    return work, fixture, prompt, env


def evaluate(scenario, work, fixture, events, skill_root=None):
    state = json.loads((fixture / 'state.json').read_text())
    calls_path = fixture / 'calls.jsonl'
    calls = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
    instructions = {'auth_first': bool(calls) and calls[0] == ['auth', 'status']}
    def params(call):
        try:
            value = json.loads(call[call.index('--params') + 1]) if '--params' in call else {}
            return value if isinstance(value, dict) else {}
        except (IndexError, json.JSONDecodeError):
            return {}
    if scenario == 'drive':
        instructions['allowed_commands'] = all(c == ['auth', 'status'] or c[:3] in
                                               (['drive', 'files', 'list'], ['drive', 'files', 'get'])
                                               for c in calls)
        lists = [c for c in calls if c[:3] == ['drive', 'files', 'list']]
        downloads = [c for c in calls if c[:3] == ['drive', 'files', 'get'] and params(c).get('alt') == 'media']
        instructions.update(pagination=any(params(c).get('pageToken') == 'page-2' for c in lists),
                            download_method=len(downloads) == 2 and all('--output' in c for c in downloads))
        expected = {f['name']: f['content'].encode() for f in FILES.values() if f['mimeType'] == 'text/plain'}
        actual = {p.name: p.read_bytes() for p in (work / 'downloads').iterdir() if p.is_file()}
        result = {'names_and_bytes': actual == expected}
    else:
        instructions['allowed_commands'] = all(c == ['auth', 'status'] or c[:3] in
            (['sheets', 'spreadsheets', 'create'], ['sheets', 'spreadsheets', 'get'],
             ['sheets', 'spreadsheets', 'batchUpdate']) or c[:4] in
            (['sheets', 'spreadsheets', 'values', 'append'], ['sheets', 'spreadsheets', 'values', 'get'])
            or c[:2] == ['sheets', '+read'] for c in calls)
        commands = [e.get('item', {}).get('command', '') for e in events
                    if e.get('type') == 'item.completed'
                    and e.get('item', {}).get('type') == 'command_execution'
                    and e.get('item', {}).get('exit_code') == 0]
        script = str((skill_root or work) / '.agents/skills/gws-sheets/scripts/create_tracker.sh')
        # Require an executable position in a successful shell command, not a
        # mention in an agent message or `cat script`.
        pattern = r'(?:^|[;&]|\s-l?c\s+[\x27\x22])\s*[\x27\x22]?(?:bash\s+)?[\x27\x22]?(?:' + re.escape(script) + r'|\$\{?SKILL_DIR\}?/scripts/create_tracker\.sh)[\x27\x22]?\s'
        instructions['tracker_script'] = any(
            re.search(pattern, c + ' ') and (script in c or str(Path(script).parent.parent) in c)
            for c in commands)
        appends = [c for c in calls if c[:4] == ['sheets', 'spreadsheets', 'values', 'append']]
        instructions['raw_append'] = len(appends) == 1 and params(appends[0]).get('valueInputOption') == 'RAW'
        last_write = max((i for i, c in enumerate(calls) if c[:4] == ['sheets', 'spreadsheets', 'values', 'append']), default=len(calls))
        instructions['read_after_write'] = any(c[:4] == ['sheets', 'spreadsheets', 'values', 'get'] or c[:2] == ['sheets', '+read'] for c in calls[last_write + 1:])
        expected_format = json.loads((ROOT / 'gws-sheets/assets/header_style.json').read_text())['requests']
        for r in expected_format:
            if 'repeatCell' in r:
                r['repeatCell']['range'].update(sheetId=42, startColumnIndex=0, endColumnIndex=3)
            elif 'updateSheetProperties' in r:
                r['updateSheetProperties']['properties']['sheetId'] = 42
            else:
                r['autoResizeDimensions']['dimensions'].update(sheetId=42, endIndex=3)
        spreadsheet = state.get('spreadsheet', {})
        result = {'rows': state.get('rows') == [HEADERS] + ROWS,
                  'title': spreadsheet.get('properties', {}).get('title') == 'Агент: тест',
                  'tab': spreadsheet.get('sheets', [{}])[0].get('properties', {}).get('title') == 'Страницы',
                  'formatting': state.get('formatting') == expected_format}
    return {'instructions': instructions, 'result': result,
            'passed': all(instructions.values()) and all(result.values()), 'calls': calls}


def run(args):
    codex = str(Path(args.codex).resolve()) if args.codex else shutil.which('codex')
    if not codex:
        raise ValueError('Codex executable not found')
    launcher = Path(codex).read_bytes()[:65536]
    if launcher.startswith(b'#!') and re.search(rb'\bCODEX_HOME\s*=', launcher):
        raise ValueError('Launcher overrides CODEX_HOME; pass the actual executable with --codex')
    source_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    auth = source_home / 'auth.json'
    if not auth.is_file() and not os.environ.get('OPENAI_API_KEY'):
        raise ValueError('Codex auth.json or OPENAI_API_KEY required')
    report = Path(args.report_dir).resolve()
    report.mkdir(parents=True, exist_ok=False)
    summary = {'scenario': args.scenario, 'timeout_seconds': args.timeout,
               'token_stop_threshold': args.max_tokens, 'model': args.model,
               'skill_sha256': {s: hashlib.sha256((ROOT / s / 'SKILL.md').read_bytes()).hexdigest()
                                for s in ('gws-drive', 'gws-sheets')}}
    summary['resource_sha256'] = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for s in ('gws-drive', 'gws-sheets') for p in sorted((ROOT / s).rglob('*')) if p.is_file()}
    with tempfile.TemporaryDirectory(prefix='gws-agent-') as tmp:
        base = Path(tmp)
        selection_case = getattr(args, 'selection_case', None)
        work, fixture, prompt, env = prepare(base, args.scenario, selection_case)
        home = base / 'codex-home'
        home.mkdir(mode=0o700)
        if auth.is_file():
            shutil.copyfile(auth, home / 'auth.json')
            (home / 'auth.json').chmod(0o600)
        env['CODEX_HOME'] = str(home)
        if os.environ.get('OPENAI_API_KEY'):
            env['OPENAI_API_KEY'] = os.environ['OPENAI_API_KEY']
        # Codex CLI needs system utilities; agent command PATH is overridden separately.
        cli_env = dict(env, PATH=os.environ.get('PATH', os.defpath))
        shell_settings = 'shell_environment_policy.set={' + ', '.join(
            json.dumps(k) + '=' + json.dumps(v) for k, v in env.items() if k != 'OPENAI_API_KEY') + '}'
        command = [codex, '--no-daemon', '-a', 'never', 'exec', '--ignore-user-config',
                   '--ignore-rules', '--ephemeral', '--skip-git-repo-check', '--json',
                   '-s', 'workspace-write', '-C', str(work), '-m', args.model,
                   '-c', 'model_reasoning_effort="low"',
                   '-c', 'shell_environment_policy.inherit="none"',
                   '-c', shell_settings,
                   '-c', 'features.multi_agent=false',
                   '-c', 'features.apps=false', '-c', 'features.plugins=false',
                   '-c', 'features.browser_use=false', '-c', 'features.computer_use=false',
                   '-c', 'features.shell_snapshot=false',
                   '-c', 'features.skip_host_skill_discovery=true',
                   '-c', 'web_search="disabled"', '-']
        (report / 'prompt.txt').write_text(prompt)
        (report / 'command.json').write_text(json.dumps(command, ensure_ascii=False, indent=2))
        if selection_case is not None:
            from selection_gws import discovery, grade
            preflight = discovery(command, cli_env, work, report)
            summary.update(case=selection_case, discovery=preflight)
            if not preflight['passed']:
                summary.update(passed=False, stop_reason='skill_discovery', completed=False)
                (report / 'report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
                print(json.dumps({'passed': False, 'report': str(report / 'report.json')}))
                return 1
        started = time.monotonic()
        events = []
        with (report / 'events.jsonl').open('w') as stdout, (report / 'stderr.log').open('w') as stderr:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                       env=cli_env, start_new_session=True, text=True)
            try:
                process.stdin.write(prompt)
                process.stdin.close()
                reason = None
                while process.poll() is None:
                    if time.monotonic() - started > args.timeout:
                        reason = 'timeout'
                        break
                    usage = read_events(report / 'events.jsonl')
                    tokens = sum(e.get('usage', {}).get('input_tokens', 0) + e.get('usage', {}).get('output_tokens', 0) for e in usage if e.get('type') == 'turn.completed')
                    if tokens >= args.max_tokens:
                        reason = 'token_threshold'
                        break
                    time.sleep(0.25)
            finally:
                # Also stop descendants if the CLI exits unexpectedly.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        events = read_events(report / 'events.jsonl')
        summary.update(elapsed_seconds=round(time.monotonic() - started, 2),
                       returncode=process.returncode, stop_reason=reason,
                       usage=[e['usage'] for e in events if 'usage' in e],
                       completed=any(e.get('type') == 'turn.completed' for e in events))
        summary['reported_tokens'] = sum(u.get('input_tokens', 0) + u.get('output_tokens', 0)
                                         for u in summary['usage'])
        summary['token_threshold_exceeded'] = summary['reported_tokens'] > args.max_tokens
        summary.update(grade(selection_case, work, fixture, events) if selection_case is not None
                       else evaluate(args.scenario, work, fixture, events))
        summary['behavior_passed'] = summary['passed']
        summary['passed'] = (summary['behavior_passed'] and summary['completed']
                             and process.returncode == 0 and reason is None
                             and not summary['token_threshold_exceeded'])
        shutil.copyfile(fixture / 'state.json', report / 'state.json')
        if (fixture / 'calls.jsonl').exists():
            shutil.copyfile(fixture / 'calls.jsonl', report / 'calls.jsonl')
        shutil.copytree(work / 'downloads', report / 'downloads')
    (report / 'report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'passed': summary['passed'], 'report': str(report / 'report.json')}, ensure_ascii=False))
    return 0 if summary['passed'] else 1


def read_events(path):
    result = []
    for line in path.read_text().splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # Ignore an incomplete line while CLI is still writing.
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-agent', action='store_true', help='Explicitly authorize one model run')
    parser.add_argument('--scenario', choices=('drive', 'sheets'), required=True)
    parser.add_argument('--report-dir', required=True)
    parser.add_argument('--codex', help='Actual Codex binary; wrappers must preserve CODEX_HOME')
    parser.add_argument('--model', default='gpt-6.1-sol')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--token-stop-threshold', dest='max_tokens', type=int, default=250000,
                        help='Soft threshold for reported input+output tokens, including cached input')
    args = parser.parse_args()
    if not args.run_agent:
        parser.error('Model runs require --run-agent')
    if not 1 <= args.timeout <= 300 or not 1 <= args.max_tokens <= 250000:
        parser.error('Limits: 1..300 seconds and 1..250000 reported tokens')
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
