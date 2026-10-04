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

## Поиск по имени

```powershell
$paramsJson = @{ q = "name contains 'report' and trashed = false"; pageSize = 20; fields = "nextPageToken,files(id,name,mimeType,webViewLink)" } | ConvertTo-Json -Depth 20 -Compress
gws.exe drive files list --params $paramsJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Файлы внутри папки

```powershell
$paramsJson = @{ q = "'FOLDER_ID' in parents and trashed = false"; pageSize = 100; fields = "nextPageToken,files(id,name,mimeType)" } | ConvertTo-Json -Depth 20 -Compress
gws.exe drive files list --params $paramsJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Метаданные файла

```powershell
$paramsJson = @{ fileId = "FILE_ID"; fields = "id,name,mimeType,parents,owners,modifiedTime,size,webViewLink" } | ConvertTo-Json -Depth 20 -Compress
gws.exe drive files get --params $paramsJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Загрузка файла

```powershell
gws.exe drive +upload ./report.csv --parent FOLDER_ID --name "Отчёт.csv"
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Скачивание файла

```powershell
$paramsJson = @{ fileId = "FILE_ID"; alt = "media" } | ConvertTo-Json -Depth 20 -Compress
gws.exe drive files get --output ./local/report.pdf --params $paramsJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Экспорт Google-файла

```powershell
$paramsJson = @{ fileId = "FILE_ID"; mimeType = "application/pdf" } | ConvertTo-Json -Depth 20 -Compress
gws.exe drive files export --output ./local/report.pdf --params $paramsJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Создание папки

```powershell
$bodyJson = @{ name = "Новая папка"; mimeType = "application/vnd.google-apps.folder"; parents = @("PARENT_ID") } | ConvertTo-Json -Depth 20 -Compress
gws.exe drive files create --json $bodyJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Перемещение файла

```powershell
$paramsJson = @{ fileId = "FILE_ID"; addParents = "NEW_FOLDER_ID"; removeParents = "OLD_FOLDER_ID" } | ConvertTo-Json -Depth 20 -Compress
gws.exe drive files update --params $paramsJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Доступ к файлу

```powershell
$paramsJson = @{ fileId = "FILE_ID" } | ConvertTo-Json -Depth 20 -Compress
$bodyJson = @{ role = "writer"; type = "user"; emailAddress = "someone@example.com" } | ConvertTo-Json -Depth 20 -Compress
gws.exe drive permissions create --params $paramsJson --json $bodyJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

## Схемы методов

```powershell
gws.exe schema drive.files.list --resolve-refs
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
gws.exe schema drive.permissions.create --resolve-refs
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```
