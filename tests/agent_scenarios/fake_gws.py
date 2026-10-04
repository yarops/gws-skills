#!/usr/bin/env python3
"""Stateful scenario double. Deliberately supports only the exercised API subset."""
import json
import os
from pathlib import Path
import sys


def main():
    args = sys.argv[1:]
    root = Path(os.environ['GWS_AGENT_FIXTURE'])
    with (root / 'calls.jsonl').open('a', encoding='utf-8') as out:
        out.write(json.dumps(args, ensure_ascii=False) + '\n')
    def option(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    p = json.loads(option('--params', '{}'))
    body = json.loads(option('--json', '{}'))
    state_path = root / 'state.json'
    state = json.loads(state_path.read_text())
    command = args[:3]
    result = {}
    if args == ['auth', 'status']:
        result = {'token_valid': True, 'has_refresh_token': True, 'client_config_exists': True}
    elif command == ['drive', 'files', 'list']:
        assert 'fixture-folder' in p['q'] and 'trashed = false' in p['q']
        files = [dict(id=key, name=value['name'], mimeType=value['mimeType'])
                 for key, value in state['files'].items()]
        if 'text/plain' in p['q']:
            files = [f for f in files if f['mimeType'] == 'text/plain']
        assert p.get('pageToken') in (None, 'page-2')
        result = {'files': files[1:] if p.get('pageToken') else files[:1]}
        if not p.get('pageToken'):
            result['nextPageToken'] = 'page-2'
    elif command == ['drive', 'files', 'get']:
        f = state['files'][p['fileId']]
        if p.get('alt') == 'media':
            target = Path(option('--output'))
            assert target.resolve().is_relative_to(Path.cwd() / 'downloads')
            assert not target.exists(), 'Refusing overwrite'
            target.write_bytes(f['content'].encode('utf-8'))
        else:
            result = dict(id=p['fileId'], name=f['name'], mimeType=f['mimeType'])
    elif command == ['sheets', 'spreadsheets', 'create']:
        assert 'spreadsheet' not in state, 'Duplicate create'
        props = body['sheets'][0]['properties']
        state['spreadsheet'] = dict(spreadsheetId='fixture-sheet',
            spreadsheetUrl='https://docs.google.com/spreadsheets/d/fixture-sheet/edit',
            properties=body['properties'], sheets=[{'properties': dict(props, sheetId=42)}])
        state['rows'] = []
        state['formatting'] = []
        result = state['spreadsheet']
    elif command == ['sheets', 'spreadsheets', 'get']:
        assert p['spreadsheetId'] == 'fixture-sheet'
        result = state['spreadsheet']
    elif command == ['sheets', 'spreadsheets', 'batchUpdate']:
        assert p['spreadsheetId'] == 'fixture-sheet'
        for request in body['requests']:
            if 'updateCells' in request:
                update = request['updateCells']
                assert update['start'] == {'sheetId': 42, 'rowIndex': 0, 'columnIndex': 0}
                state['rows'] = [[c['userEnteredValue']['stringValue']
                                  for c in update['rows'][0]['values']]] + state['rows'][1:]
            elif set(request) <= {'repeatCell', 'updateSheetProperties', 'autoResizeDimensions'}:
                state['formatting'].append(request)
            else:
                raise ValueError('Unsupported batch request')
    elif args[:4] == ['sheets', 'spreadsheets', 'values', 'append']:
        assert p['spreadsheetId'] == 'fixture-sheet'
        assert p['range'] in ("'Страницы'!A:C", 'Страницы!A:C')
        assert p['valueInputOption'] == 'RAW'
        state['rows'].extend(body['values'])
        result = {'updates': {'updatedRange': "'Страницы'!A2:C3", 'updatedRows': len(body['values'])}}
    elif args[:4] == ['sheets', 'spreadsheets', 'values', 'get'] or args[:2] == ['sheets', '+read']:
        sid = p.get('spreadsheetId', option('--spreadsheet'))
        cell_range = p.get('range', option('--range'))
        assert sid == 'fixture-sheet' and 'Страницы' in cell_range
        result = {'range': cell_range, 'values': state['rows']}
    else:
        raise ValueError('Unsupported command: ' + repr(args))
    state_path.write_text(json.dumps(state, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, ValueError, KeyError, TypeError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(7)
