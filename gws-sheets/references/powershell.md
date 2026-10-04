# Команды PowerShell 7.3+

Перед API проверь версию и передачу аргументов:

```powershell
$PSVersionTable.PSVersion
$PSNativeCommandArgumentPassing
Get-Command gws.exe -CommandType Application -ErrorAction Stop
```

Нужны PowerShell 7.3+ и режим `Windows` либо `Standard`. Если версия старее,
найди `pwsh` через `Get-Command pwsh -CommandType Application -ErrorAction Stop`
и выполни нужный блок в отдельном процессе `pwsh -NoProfile -Command { ... }`.
Внутри блока проверь версию и задай `$PSNativeCommandArgumentPassing = 'Standard'`.
Для режима Legacy также используй отдельный блок с Standard. Не меняй профиль
или глобальные настройки. Если подходящего pwsh нет, сообщи требуемую зависимость.
Используй исполняемый gws.exe, а не .cmd/.bat-обёртку.

Общие настройки действуют только в текущем блоке/сеансе:

```powershell
$ErrorActionPreference = 'Stop'
gws.exe auth status
if ($LASTEXITCODE -ne 0) { throw "gws auth status: $LASTEXITCODE" }
```

Следуй правилам авторизации из SKILL.md. Проверяй `$LASTEXITCODE` сразу после
каждого внешнего вызова; `$ErrorActionPreference` сам по себе не гарантирует
остановку при ненулевом коде внешней программы. Не повторяй append/create после
сетевой ошибки без проверки результата. JSON собирай объектами и массивами через
`ConvertTo-Json -Depth 20 -Compress`. Не используй Invoke-Expression.

Для помощника проверь `py -3 --version` (нужен Python 3.9+); если py недоступен,
проверь `python --version` и замени `py -3` на `python`. Путь `$SkillDir` определяй
по прочитанному SKILL.md. Конфигурацию сохраняй UTF-8 без BOM показанным способом.
Для нескольких листов используй структуру конфигурации из SKILL.md. Восстановление
требует того же файла конфигурации. Все примеры самостоятельны после задания
`$SkillDir` и подготовки нужного tracker.json.

## Создание одного листа (Bash: аргументы; PowerShell: конфигурация)

```powershell
# Установи абсолютный путь по местоположению прочитанного SKILL.md.
$SkillDir = "C:/path/to/gws-sheets"
$config = @{ title = "SEO: сведение контента по ключам"; sheets = @(
    @{ title = "Страницы"; headers = @("URL", "Title", "H1", "Текущие ключи", "Кластер", "Частотность", "Приоритет", "Статус") }
)}
$configJson = $config | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText((Join-Path (Get-Location).Path "tracker.json"), $configJson, [System.Text.UTF8Encoding]::new($false))
py -3 "$SkillDir/scripts/create_tracker.py" --config ./tracker.json
if ($LASTEXITCODE -ne 0) { throw "create_tracker: $LASTEXITCODE" }
```

## Восстановление одного листа

```powershell
py -3 "$SkillDir/scripts/create_tracker.py" --resume SPREADSHEET_ID --config ./tracker.json
if ($LASTEXITCODE -ne 0) { throw "create_tracker: $LASTEXITCODE" }
```

## Создание нескольких листов

```powershell
py -3 "$SkillDir/scripts/create_tracker.py" --config ./tracker.json
if ($LASTEXITCODE -ne 0) { throw "create_tracker: $LASTEXITCODE" }
```

## Восстановление нескольких листов

```powershell
py -3 "$SkillDir/scripts/create_tracker.py" --resume SPREADSHEET_ID --config ./tracker.json
if ($LASTEXITCODE -ne 0) { throw "create_tracker: $LASTEXITCODE" }
```

## Чтение диапазона

```powershell
gws.exe sheets +read --spreadsheet SPREADSHEET_ID --range "Страницы!A1:H100"
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Добавление строк

```powershell
$paramsJson = @{ spreadsheetId = "SPREADSHEET_ID"; range = "'Страницы'!A:H"; valueInputOption = "RAW"; insertDataOption = "INSERT_ROWS" } | ConvertTo-Json -Depth 20 -Compress
$bodyJson = @{ values = @(,@("https://example.com/page", "Title", "...")) } | ConvertTo-Json -Depth 20 -Compress
gws.exe sheets spreadsheets values append --params $paramsJson --json $bodyJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Перезапись диапазона

```powershell
$paramsJson = @{ spreadsheetId = "SPREADSHEET_ID"; range = "Страницы!H2:H2"; valueInputOption = "USER_ENTERED" } | ConvertTo-Json -Depth 20 -Compress
$bodyJson = @{ values = @(,@("готово")) } | ConvertTo-Json -Depth 20 -Compress
gws.exe sheets spreadsheets values update --params $paramsJson --json $bodyJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Чтение нескольких диапазонов

```powershell
$paramsJson = @{ spreadsheetId = "SPREADSHEET_ID"; ranges = @("Страницы!A1:H1", "Страницы!A50:H60") } | ConvertTo-Json -Depth 20 -Compress
gws.exe sheets spreadsheets values batchGet --params $paramsJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Схема метода

```powershell
gws.exe schema sheets.spreadsheets.batchUpdate --resolve-refs
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```
