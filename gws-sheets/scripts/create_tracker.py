#!/usr/bin/env python3
"""Create styled Google Sheets trackers. Python 3.9+, gws; no shell required."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def chunk_limit():
    # Windows has a much smaller process command-line limit. Leave room for
    # JSON quoting, formatting requests, executable path and spreadsheet ID.
    return 6000 if sys.platform == 'win32' else 60000


def cell(header):
    return {'userEnteredValue': {'stringValue': header}}


def parse(args):
    resume = ''
    if args and args[0] == '--resume':
        if len(args) < 3 or not args[1]:
            raise ValueError('Использование: --resume ID HEADERS_JSON [TAB_NAME] или --resume ID --config FILE')
        resume, args = args[1], args[2:]
    if args and args[0] == '--config':
        if len(args) != 2:
            raise ValueError('Использование: [--resume ID] --config FILE')
        config = json.loads(Path(args[1]).read_text(encoding='utf-8-sig'))
    else:
        if not resume:
            if not 2 <= len(args) <= 3 or not args[0]:
                raise ValueError('Использование: TITLE HEADERS_JSON [TAB_NAME] или --config FILE')
            title, args = args[0], args[1:]
        else:
            title = 'resume'
        if not 1 <= len(args) <= 2:
            raise ValueError('Нужны HEADERS_JSON [TAB_NAME]')
        config = {'title': title, 'sheets': [{'title': args[1] if len(args) == 2 else 'Sheet1',
                                             'headers': json.loads(args[0])}]}
    if not isinstance(config, dict) or not isinstance(config.get('title'), str) or not config['title']:
        raise ValueError('Нужно непустое title')
    sheets = config.get('sheets')
    if not isinstance(sheets, list) or not sheets:
        raise ValueError('Нужен непустой массив sheets')
    names = set()
    for sheet in sheets:
        if not isinstance(sheet, dict) or not isinstance(sheet.get('title'), str) or not sheet['title']:
            raise ValueError('Каждому листу нужно непустое title')
        name = sheet['title'].casefold()
        if name in names:
            raise ValueError('Названия листов должны быть уникальны')
        names.add(name)
        headers = sheet.get('headers')
        if not isinstance(headers, list) or not 1 <= len(headers) <= 18278 or not all(isinstance(h, str) and h for h in headers):
            raise ValueError('Нужен непустой JSON-массив непустых строк (до 18278 колонок)')
        if any(len(encode(cell(h)).encode('utf-8')) > chunk_limit() for h in headers):
            raise ValueError('Заголовок слишком длинный: JSON одной ячейки превышает допустимый размер')
    return resume, config


def formatting(style, sheet_id, count):
    requests = copy.deepcopy(style['requests'])
    for request in requests:
        if 'repeatCell' in request:
            request['repeatCell']['range'].update(sheetId=sheet_id, startColumnIndex=0, endColumnIndex=count)
        elif 'updateSheetProperties' in request:
            request['updateSheetProperties']['properties']['sheetId'] = sheet_id
        elif 'autoResizeDimensions' in request:
            request['autoResizeDimensions']['dimensions'].update(sheetId=sheet_id, endIndex=count)
        else:
            raise ValueError('Неизвестный запрос в шаблоне')
    return requests


def batches(headers, sheet_id, style):
    chunks, current, size = [], [], 0
    for header in headers:
        value = cell(header)
        value_size = len(encode(value).encode('utf-8')) + 1
        if current and size + value_size > chunk_limit():
            chunks.append(current)
            current, size = [], 0
        current.append(value)
        size += value_size
    chunks.append(current)
    offset = 0
    for index, chunk in enumerate(chunks):
        requests = [{'updateCells': {'start': {'sheetId': sheet_id, 'rowIndex': 0, 'columnIndex': offset},
                                    'rows': [{'values': chunk}], 'fields': 'userEnteredValue'}}]
        if index == len(chunks) - 1:
            requests += formatting(style, sheet_id, len(headers))
        yield {'requests': requests}
        offset += len(chunk)


def integer(value):
    return type(value) in (int, float) and value >= 0 and value == int(value)


def targets(config, response):
    result = []
    for sheet in config['sheets']:
        matches = [s['properties'] for s in response['sheets'] if s['properties']['title'] == sheet['title']]
        if len(matches) != 1:
            raise ValueError('Вкладка не найдена или неоднозначна')
        properties = matches[0]
        sheet_id, columns = properties['sheetId'], properties['gridProperties']['columnCount']
        if not integer(sheet_id) or not integer(columns) or columns < len(sheet['headers']):
            raise ValueError('Некорректный sheetId или недостаточно колонок')
        result.append((int(sheet_id), sheet['headers']))
    return result


def main(args):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    spreadsheet_id, url = '', ''
    api_started = False
    try:
        spreadsheet_id, config = parse(args)
        style = json.loads((Path(__file__).resolve().parent.parent / 'assets/header_style.json').read_text(encoding='utf-8'))
        if not isinstance(style.get('requests'), list) or not style['requests']:
            raise ValueError('Некорректный шаблон оформления')
        formatting(style, 0, 1)  # Reject unsupported templates before creating a file.
        executable = shutil.which('gws')
        if not executable:
            raise ValueError('Не найден gws')
        if Path(executable).suffix.lower() in ('.cmd', '.bat'):
            raise ValueError('Нужен исполняемый gws (на Windows gws.exe), а не .cmd/.bat-обёртка')

        def call(method, **payloads):
            command = [executable, 'sheets', 'spreadsheets', method]
            for flag, payload in payloads.items():
                command.extend(['--' + flag, encode(payload)])
            if sys.platform == 'win32' and len(subprocess.list2cmdline(command).encode('utf-16-le')) // 2 >= 30000:
                raise ValueError('Команда слишком длинная для Windows; уменьшите конфигурацию')
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if completed.stderr:
                print(completed.stderr.decode('utf-8', errors='replace'), file=sys.stderr, end='')
            if completed.returncode:
                raise subprocess.CalledProcessError(completed.returncode, command)
            return json.loads(completed.stdout.decode('utf-8-sig')) if method != 'batchUpdate' else None

        api_started = True
        if spreadsheet_id:
            response = call('get', params={'spreadsheetId': spreadsheet_id,
                                          'fields': 'spreadsheetId,spreadsheetUrl,sheets(properties)'})
        else:
            response = call('create', json={'properties': {'title': config['title']}, 'sheets': [
                {'properties': {'title': sheet['title'], 'gridProperties': {'columnCount': len(sheet['headers'])}}}
                for sheet in config['sheets']]})
        returned_id = response.get('spreadsheetId')
        if not isinstance(returned_id, str) or not returned_id:
            raise ValueError('Ответ не содержит spreadsheetId')
        if spreadsheet_id and returned_id != spreadsheet_id:
            raise ValueError('ID ответа не соответствует запрошенной таблице')
        spreadsheet_id = returned_id
        url = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit'
        returned_url = response.get('spreadsheetUrl')
        if not isinstance(returned_url, str) or not returned_url:
            raise ValueError('Ответ не содержит spreadsheetUrl')
        url = returned_url
        print(f'Таблица: {url} (ID: {spreadsheet_id})', file=sys.stderr)
        for sheet_id, headers in targets(config, response):
            for batch in batches(headers, sheet_id, style):
                call('batchUpdate', params={'spreadsheetId': spreadsheet_id}, json=batch)
        print(url)
        return 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError, subprocess.CalledProcessError) as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        if api_started:
            if spreadsheet_id:
                print(f'Не удалось завершить настройку. ID: {spreadsheet_id}', file=sys.stderr)
                print(f'URL: {url or "https://docs.google.com/spreadsheets/d/" + spreadsheet_id + "/edit"}', file=sys.stderr)
                print('Продолжите через --resume с той же конфигурацией или заголовками и вкладкой; новая таблица не нужна.', file=sys.stderr)
            else:
                print('Создание не подтверждено. Перед повтором проверьте Drive: при сетевом сбое файл мог быть создан.', file=sys.stderr)
        return error.returncode if isinstance(error, subprocess.CalledProcessError) and error.returncode > 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
