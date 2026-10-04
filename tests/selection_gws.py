#!/usr/bin/env python3
"""Bounded implicit skill selection evaluation; one model turn per case."""
import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

from agent_gws import ROOT, FILES, HEADERS, ROWS, evaluate, run

CASES = ROOT / 'tests/selection_scenarios/cases.json'
SKILLS = ('gws-drive', 'gws-sheets')


def load_cases():
    cases = json.loads(CASES.read_text())
    if len(cases) != 12 or len({c['id'] for c in cases}) != 12:
        raise ValueError('Expected twelve unique cases')
    for skill in SKILLS:
        for expected in ([], [skill]):
            if sum(c['target'] == skill and c['expected'] == expected for c in cases) != 3:
                raise ValueError('Expected three positive and three negative cases per skill')
    for case in cases:
        if any(s in case['prompt'] for s in SKILLS) or 'SKILL.md' in case['prompt']:
            raise ValueError('Prompts must not name skills or their paths')
    return cases


def setup_case(case, work, fixture):
    (work / 'notes.txt').write_text('alpha\nbeta\n')
    (work / 'data.csv').write_text('name,value\na,2\nb,3\n')
    if case['check'] in ('sheets-read', 'sheets-append'):
        state = json.loads((fixture / 'state.json').read_text())
        state.update(spreadsheet={'spreadsheetId': 'fixture-sheet',
                     'properties': {'title': 'Агент: тест'},
                     'sheets': [{'properties': {'sheetId': 42, 'title': 'Страницы',
                                 'gridProperties': {'columnCount': 3}}}]},
                     rows=[HEADERS] + (ROWS if case['check'] == 'sheets-read' else []),
                     formatting=[])
        (fixture / 'state.json').write_text(json.dumps(state, ensure_ascii=False))
    return case['prompt']


def check_discovery(response, work):
    entries = [e for e in response.get('data', []) if e.get('cwd') == str(work)]
    if len(entries) != 1:
        return False
    entry = entries[0]
    skills = {s['name']: s for s in entry.get('skills', [])}
    return not entry.get('errors') and all(
        s in skills and skills[s].get('enabled') is True
        and skills[s].get('description')
        and Path(skills[s].get('path', '')).resolve() ==
        (work / '.agents/skills' / s / 'SKILL.md').resolve()
        for s in SKILLS)


def discovery(exec_command, env, work, report, timeout=20):
    # Reuse the exact -c overrides from exec; no model request is sent.
    command = [exec_command[0], '--no-daemon', '-C', str(work), 'app-server', '--stdio']
    for i, value in enumerate(exec_command):
        if value == '-c':
            command.extend(['-c', exec_command[i + 1]])
    transcript = []
    result = {'passed': False}
    with (report / 'discovery-stderr.log').open('w') as stderr:
        process = subprocess.Popen(command, cwd=work, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=stderr,
                                   start_new_session=True)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        buffer = b''
        deadline = time.monotonic() + timeout
        def send(message):
            process.stdin.write((json.dumps(message) + '\n').encode())
            process.stdin.flush()
        def receive(request_id):
            nonlocal buffer
            while time.monotonic() < deadline:
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    message = json.loads(line)
                    transcript.append(message)
                    if message.get('id') == request_id:
                        if 'error' in message:
                            raise ValueError(str(message['error']))
                        return message['result']
                if selector.select(max(0, deadline - time.monotonic())):
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        raise ValueError('App-server exited before skills/list response')
                    buffer += chunk
            raise TimeoutError('skills/list timeout')
        try:
            send({'id': 1, 'method': 'initialize', 'params': {
                'clientInfo': {'name': 'gws-selection-test', 'version': '1'},
                'capabilities': {'experimentalApi': True}}})
            receive(1)
            send({'method': 'initialized', 'params': {}})
            send({'id': 2, 'method': 'skills/list', 'params': {
                'cwds': [str(work)], 'forceReload': True}})
            response = receive(2)
            result.update(passed=check_discovery(response, work), response=response)
        except (ValueError, OSError, TimeoutError) as error:
            result['error'] = str(error)
        finally:
            selector.close()
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            process.stdin.close()
            process.stdout.close()
    (report / 'discovery.json').write_text(json.dumps(
        {'command': command, 'events': transcript, **result}, ensure_ascii=False, indent=2))
    return result


def grade(case, work, fixture, events):
    selected = set()
    evidence = []
    for event in events:
        item = event.get('item', {})
        if (event.get('type') != 'item.completed' or item.get('type') != 'command_execution'
                or item.get('exit_code') != 0):
            continue
        # Only successful commands whose output contains the actual skill body
        # count. Listing paths, echoing names and assistant claims do not count.
        output = item.get('aggregated_output', '')
        for skill in SKILLS:
            body = (work / '.agents/skills' / skill / 'SKILL.md').read_text()
            marker = body.split('---', 2)[2].strip().splitlines()[0]
            if marker in output and 'description: ' in output and 'name: ' + skill in output:
                selected.add(skill)
                evidence.append({'skill': skill, 'command': item.get('command'),
                                 'event_id': item.get('id')})
    calls_path = fixture / 'calls.jsonl'
    calls = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
    state = json.loads((fixture / 'state.json').read_text())
    check = case['check']
    execution_checks = None
    if check in ('drive', 'sheets'):
        behavior = evaluate(check, work, fixture, events)
        result = {'task_completed': behavior['passed']}
        execution_checks = {'instructions': behavior['instructions'], 'result': behavior['result']}
    elif check == 'drive-list':
        result = {'pagination': any('page-2' in ' '.join(c) for c in calls),
                  'listed': any(c[:3] == ['drive', 'files', 'list'] for c in calls)}
    elif check == 'drive-metadata':
        result = {'metadata_requested': any(c[:3] == ['drive', 'files', 'get']
                  and json.loads(c[c.index('--params') + 1]).get('fileId') == 'file-a'
                  for c in calls if '--params' in c)}
    elif check == 'sheets-read':
        result = {'read': any(c[:4] == ['sheets', 'spreadsheets', 'values', 'get']
                             or c[:2] == ['sheets', '+read'] for c in calls),
                  'unchanged': state.get('rows') == [HEADERS] + ROWS}
    elif check == 'sheets-append':
        appends = [c for c in calls if c[:4] == ['sheets', 'spreadsheets', 'values', 'append']]
        result = {'rows': state.get('rows') == [HEADERS] + ROWS,
                  'raw': len(appends) == 1 and json.loads(appends[0][appends[0].index('--params') + 1]).get('valueInputOption') == 'RAW'}
    else:
        result = {'no_google_calls': not calls}
    selection_passed = selected == set(case['expected'])
    return {'selected': sorted(selected), 'expected': case['expected'],
            'selection_evidence': evidence, 'selection_passed': selection_passed,
            'result': result, 'execution_checks': execution_checks, 'calls': calls,
            'passed': selection_passed and all(result.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-agent', action='store_true')
    parser.add_argument('--case', choices=[c['id'] for c in load_cases()])
    parser.add_argument('--suite', action='store_true')
    parser.add_argument('--report-dir', required=True)
    parser.add_argument('--codex')
    parser.add_argument('--model', default='gpt-6.1-sol')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--token-stop-threshold', dest='max_tokens', type=int, default=250000)
    args = parser.parse_args()
    if not args.run_agent or bool(args.case) == args.suite:
        parser.error('Require --run-agent and exactly one of --case or --suite')
    if not 1 <= args.timeout <= 300 or not 1 <= args.max_tokens <= 250000:
        parser.error('Limits: 1..300 seconds, 1..250000 tokens per case')
    report = Path(args.report_dir).resolve()
    report.mkdir(parents=True, exist_ok=False)
    reports = []
    misses = {s: 0 for s in SKILLS}
    stop_reason = None
    cases = [c for c in load_cases() if args.suite or c['id'] == args.case]
    for case in cases:
        args.selection_case = case
        args.scenario = 'drive' if case['target'] == 'gws-drive' else 'sheets'
        args.report_dir = str(report / case['id'])
        run(args)
        outcome = json.loads((Path(args.report_dir) / 'report.json').read_text())
        reports.append({'id': case['id'], 'passed': outcome['passed'],
                        'selection_passed': outcome.get('selection_passed'),
                        'selected': outcome.get('selected'),
                        'reported_tokens': outcome.get('reported_tokens')})
        if outcome.get('stop_reason') == 'skill_discovery' or not outcome.get('completed'):
            stop_reason = outcome.get('stop_reason') or 'incomplete_turn'
            break
        for skill in case['expected']:
            misses[skill] = misses[skill] + 1 if skill not in outcome['selected'] else 0
            if misses[skill] >= 2:
                stop_reason = 'two_consecutive_positive_misses:' + skill
        if outcome.get('token_threshold_exceeded'):
            stop_reason = 'token_threshold'
        if stop_reason:
            break
    summary = {'cases': reports, 'planned': len(cases), 'executed': len(reports),
               'stop_reason': stop_reason,
               'selection_passed': len(reports) == len(cases) and all(r['selection_passed'] for r in reports),
               'passed': len(reports) == len(cases) and all(r['passed'] for r in reports)}
    (report / 'suite.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
