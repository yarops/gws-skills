---
name: gws-sheets
description: Use the gws CLI (Google Workspace CLI) to read and write Google Sheets from the terminal — create spreadsheets, read/write ranges, append rows, and apply the bundled consistent header styling via scripts/create_tracker.sh. Trigger whenever the user wants to create a tracking table/tracker, export data to Google Sheets, read values from an existing sheet, or build a spreadsheet with a consistent look, or mentions gws, "гугл таблица", "сделай таблицу для трекинга/учёта", "залей данные в гугл шит" — even if they don't say "Google Sheets API" explicitly.
---

# gws sheets

Та же CLI, сервис `sheets`:
```
gws sheets <resource> <method> [--params '<JSON>'] [--json '<JSON>']
```
Хелперы: `gws sheets +read --spreadsheet ID --range "Sheet1!A1:D10"` (только чтение) и `gws sheets +append --spreadsheet ID --values 'a,b,c'` / `--json-values '[["a","b"],["c","d"]]'` (один простой ряд через `--values`, несколько через `--json-values`).

## Перед первым вызовом в сессии

Как и для Drive — проверь `gws auth status`; если токен невалиден и нет refresh-токена, попроси пользователя самому выполнить `gws auth login`.

## Создать таблицу с готовым оформлением (рекомендуемый путь)

Для любой новой рабочей/трекинговой таблицы используй `scripts/create_tracker.sh` вместо ручной сборки `batchUpdate` — так оформление заголовка одинаковое во всех таблицах, созданных через этот скилл, и не нужно каждый раз заново собирать JSON-схему форматирования:

```
scripts/create_tracker.sh "SEO: сведение контента по ключам" "URL,Title,H1,Текущие ключи,Кластер,Частотность,Приоритет,Статус" "Страницы"
```

Аргументы: название таблицы, заголовки колонок через запятую, необязательное название листа (по умолчанию `Sheet1`). Скрипт создаёт spreadsheet, пишет строку заголовков, применяет стиль из `assets/header_style.json` (жирный белый текст на тёмном фоне, закреплённая первая строка) и печатает `spreadsheetUrl` в stdout — покажи эту ссылку пользователю.

Если нужен другой визуальный стиль на постоянной основе — заведи ещё один файл-шаблон в `assets/` (например `header_style_light.json`), а не правь JSON на лету для одного запуска — так стиль остаётся переиспользуемым, а не одноразовым хаком.

## Прямая работа с готовой таблицей

**Прочитать диапазон:**
```
gws sheets +read --spreadsheet SPREADSHEET_ID --range "Страницы!A1:H100"
```

**Дописать строки в конец:**
```
gws sheets +append --spreadsheet SPREADSHEET_ID --json-values '[["https://example.com/page","Title","..."]]'
```

**Перезаписать диапазон** (например, обновить статус у конкретных строк):
```
gws sheets spreadsheets values update \
  --params '{"spreadsheetId": "SPREADSHEET_ID", "range": "Страницы!G2:G2", "valueInputOption": "USER_ENTERED"}' \
  --json '{"values": [["готово"]]}'
```
`valueInputOption=USER_ENTERED` — значения интерпретируются как если бы их вписал человек (формулы, даты и т.п. распознаются). `RAW` — записываются буквально как строки без интерпретации.

**Прочитать несколько диапазонов за один вызов:**
```
gws sheets spreadsheets values batchGet --params '{"spreadsheetId": "SPREADSHEET_ID", "ranges": ["Страницы!A1:H1", "Страницы!A50:H60"]}'
```

## ID таблицы

Это длинная строка в URL между `/d/` и `/edit`: `https://docs.google.com/spreadsheets/d/`**`1aBcD...xyz`**`/edit`. После `spreadsheets create` (или `create_tracker.sh`) ID и прямая ссылка уже есть в ответе (`spreadsheetId`, `spreadsheetUrl`) — не нужно выдирать их из URL руками.

## Нестандартные операции / форматирование

Примеры выше не покрывают весь API. Для сложных `batchUpdate`-запросов (условное форматирование, объединение ячеек, диаграммы и т.п.) сначала посмотри точную схему, а не угадывай названия полей:
```
gws schema sheets.spreadsheets.batchUpdate --resolve-refs
```

## Осторожно

У Sheets API нет отмены операций через API. `batchUpdate` с запросами типа `deleteSheet`/`deleteRange`/`deleteDimension`, а также `values update`/`+append` по диапазону, где уже есть данные пользователя (перезапишет их без следа) — подтверждай с пользователем перед реальным вызовом и проверяй через `--dry-run`, где это применимо.
