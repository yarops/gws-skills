# Команды Bash/zsh

Выполняй примеры в Bash/zsh. Перед API проверь `gws auth status` и следуй правилам
авторизации из SKILL.md. После ошибки прекращай зависимые действия; при запуске
нескольких команд в Bash используй `set -e`, а для цепочек — `&&`.

Пользовательские строки сериализуй через Python или `jq --arg`;
не вставляй их конкатенацией в текст shell-команды. Для Sheets установи
`SKILL_DIR` в абсолютный каталог прочитанного SKILL.md. Python-помощнику нужны
Python 3.9+ и gws; `jq` нужен только примерам, использующим его.

## Создание одного листа (Bash: аргументы; PowerShell: конфигурация)

```bash
python3 "$SKILL_DIR/scripts/create_tracker.py" "SEO: сведение контента по ключам" '["URL","Title","H1","Текущие ключи","Кластер","Частотность","Приоритет","Статус"]' "Страницы"
```

## Восстановление одного листа

```bash
python3 "$SKILL_DIR/scripts/create_tracker.py" --resume SPREADSHEET_ID '["URL","Title","H1","Текущие ключи","Кластер","Частотность","Приоритет","Статус"]' "Страницы"
```

## Создание нескольких листов

```bash
python3 "$SKILL_DIR/scripts/create_tracker.py" --config ./tracker.json
```

## Восстановление нескольких листов

```bash
python3 "$SKILL_DIR/scripts/create_tracker.py" --resume SPREADSHEET_ID --config ./tracker.json
```

## Чтение диапазона

```bash
gws sheets +read --spreadsheet SPREADSHEET_ID --range "Страницы!A1:H100"
```

## Добавление строк

```bash
gws sheets spreadsheets values append \
  --params '{"spreadsheetId": "SPREADSHEET_ID", "range": "'\''Страницы'\''!A:H", "valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}' \
  --json '{"values": [["https://example.com/page","Title","..."]]}'
```

## Перезапись диапазона

```bash
gws sheets spreadsheets values update \
  --params '{"spreadsheetId": "SPREADSHEET_ID", "range": "Страницы!H2:H2", "valueInputOption": "USER_ENTERED"}' \
  --json '{"values": [["готово"]]}'
```

## Чтение нескольких диапазонов

```bash
gws sheets spreadsheets values batchGet --params '{"spreadsheetId": "SPREADSHEET_ID", "ranges": ["Страницы!A1:H1", "Страницы!A50:H60"]}'
```

## Схема метода

```bash
gws schema sheets.spreadsheets.batchUpdate --resolve-refs
```
