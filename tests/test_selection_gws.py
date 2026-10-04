"""Offline checks for discovery gates and implicit-selection grading."""
import json
from pathlib import Path
import tempfile
import unittest

from agent_gws import prepare
from selection_gws import check_discovery, grade, load_cases


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cases = load_cases()
        self.work, self.fixture, self.prompt, _ = prepare(
            Path(self.tmp.name), 'drive', self.cases[0])

    def event(self, output, command='cat SKILL.md', exit_code=0):
        return {'type': 'item.completed', 'item': {
            'type': 'command_execution', 'command': command,
            'aggregated_output': output, 'exit_code': exit_code}}

    def test_prompt_has_no_explicit_invocation(self):
        self.assertEqual(self.prompt, self.cases[0]['prompt'])
        self.assertNotIn('SKILL.md', self.prompt)
        self.assertNotIn('gws-drive', self.prompt)

    def test_mentions_and_failed_reads_do_not_count(self):
        body = (self.work / '.agents/skills/gws-drive/SKILL.md').read_text()
        for events in ([self.event('gws-drive SKILL.md')],
                       [self.event(body, exit_code=1)],
                       [{'type': 'item.completed', 'item': {
                           'type': 'agent_message', 'text': body}}]):
            self.assertFalse(grade(self.cases[0], self.work, self.fixture, events)['selection_passed'])
        result = grade(self.cases[0], self.work, self.fixture, [self.event(body)])
        self.assertTrue(result['selection_passed'])
        self.assertFalse(result['passed'])  # Selection does not imply execution.

    def test_negative_detects_unwanted_selection_and_google_calls(self):
        case = next(c for c in self.cases if not c['expected'])
        self.assertTrue(grade(case, self.work, self.fixture, [])['passed'])
        body = (self.work / '.agents/skills/gws-sheets/SKILL.md').read_text()
        self.assertFalse(grade(case, self.work, self.fixture, [self.event(body)])['passed'])
        (self.fixture / 'calls.jsonl').write_text(json.dumps(['auth', 'status']) + '\n')
        self.assertFalse(grade(case, self.work, self.fixture, [])['passed'])

    def test_discovery_checks_enabled_paths_and_errors(self):
        response = {'data': [{'cwd': str(self.work), 'errors': [], 'skills': [
            {'name': s, 'enabled': True, 'description': 'test',
             'path': str(self.work / '.agents/skills' / s / 'SKILL.md')}
            for s in ('gws-drive', 'gws-sheets')]}]}
        self.assertTrue(check_discovery(response, self.work))
        response['data'][0]['skills'][0]['enabled'] = False
        self.assertFalse(check_discovery(response, self.work))
        response['data'][0]['skills'][0]['enabled'] = True
        response['data'][0]['skills'][0]['path'] = '/wrong/SKILL.md'
        self.assertFalse(check_discovery(response, self.work))
        response['data'][0]['skills'][0]['path'] = str(self.work / '.agents/skills/gws-drive/SKILL.md')
        response['data'][0]['errors'] = [{'message': 'bad metadata'}]
        self.assertFalse(check_discovery(response, self.work))
