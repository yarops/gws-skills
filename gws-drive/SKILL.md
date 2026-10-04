---
name: gws-drive
description: Manage files and folders in Google Drive through the gws CLI — search, upload, download, move, and share. Use when Google Drive is the source or destination of files, including Russian requests about гугл диск. For cell values and spreadsheet formatting, use the Sheets skill.
---

# gws drive

`gws` — локальная CLI-обёртка над Google API (бинарник `gws`, авторизован через OAuth2). Форма вызова для Drive:

```
gws drive <resource> <method> [--params '<JSON>'] [--json '<JSON>'] [--format json|table|yaml|csv]
```

`--params` — query/path-параметры (например `fileId`, `q`), `--json` — тело запроса (для `create`/`update`/`copy`). Для загрузки файла есть хелпер `gws drive +upload <file> [--parent ID] [--name NAME]` — он сам определяет MIME-тип и собирает multipart-запрос, используй его вместо ручного `files create` с загрузкой контента.

## Перед первым вызовом в сессии

Проверь `gws auth status`. Если `token_valid: false`, но `has_refresh_token: true` — `gws` обновит токен сам при следующем вызове, ничего делать не нужно. Если `has_refresh_token: false` или `client_config_exists: false` — авторизация не настроена/не может обновиться; скажи пользователю самому выполнить `gws auth login` (открывает браузер для OAuth) — это разовое интерактивное действие пользователя, не пытайся выполнить его от его имени без явной просьбы.

## Частые задачи

**Найти файлы по имени:**
```
gws drive files list --params '{"q": "name contains '\''report'\'' and trashed = false", "pageSize": 20, "fields": "nextPageToken,files(id,name,mimeType,webViewLink)"}'
```

**Файлы внутри конкретной папки:**
```
gws drive files list --params '{"q": "'\''FOLDER_ID'\'' in parents and trashed = false", "pageSize": 100, "fields": "nextPageToken,files(id,name,mimeType)"}'
```

Не считай одну страницу полным списком. Если есть `nextPageToken`, передай его как `pageToken` в следующий запрос. `--page-all` выдаёт NDJSON (по JSON на страницу), но по умолчанию ограничен 10 страницами: задай подходящий `--page-limit` и проверь, что в последней странице нет `nextPageToken`. Для полного подсчёта обработай все страницы.

**Метаданные одного файла:**
```
gws drive files get --params '{"fileId": "FILE_ID", "fields": "id,name,mimeType,parents,owners,modifiedTime,size,webViewLink"}'
```

**Загрузить локальный файл:**
```
gws drive +upload ./report.csv --parent FOLDER_ID --name "Отчёт.csv"
```

**Скачать файл:**
```
gws drive files get --params '{"fileId": "FILE_ID", "alt": "media"}' --output ./local/report.pdf
```
Для Google Docs/Sheets/Slides используй экспорт, выбрав поддерживаемый MIME-тип:
```
gws drive files export --params '{"fileId": "FILE_ID", "mimeType": "application/pdf"}' --output ./local/report.pdf
```
`files download` возвращает длительную операцию, а не байты файла: если нужен именно этот метод, обработай статус операции и полученный URL скачивания. Перед записью проверь, что локальная папка существует и выбранный путь не перезапишет нужный файл.

**Создать папку:**
```
gws drive files create --json '{"name": "Новая папка", "mimeType": "application/vnd.google-apps.folder", "parents": ["PARENT_ID"]}'
```

**Переместить файл в другую папку** (у Drive нет отдельного метода "move" — это patch по родителям):
```
gws drive files update --params '{"fileId": "FILE_ID", "addParents": "NEW_FOLDER_ID", "removeParents": "OLD_FOLDER_ID"}'
```

**Расшарить файл/папку:**
```
gws drive permissions create --params '{"fileId": "FILE_ID"}' --json '{"role": "writer", "type": "user", "emailAddress": "someone@example.com"}'
```
`role`: `reader` / `writer` / `commenter` / `owner`. `type`: `user` / `group` / `domain` / `anyone`.

## Если нужного метода нет среди примеров

Не угадывай названия полей JSON — посмотри точную схему метода перед вызовом:
```
gws schema drive.files.list --resolve-refs
gws schema drive.permissions.create --resolve-refs
```
Без `--resolve-refs` схема короче, но вложенные `$ref` не раскрыты.

## Вывод

По умолчанию `--format json`. Для быстрого просмотра человеком — `--format table`. Для выгрузки в файл или дальнейшей обработки — `--format csv`.

## Осторожно — необратимые операции

- `gws drive files delete` удаляет файл **навсегда**, минуя корзину.
- `gws drive files emptyTrash` безвозвратно чистит всю корзину пользователя.

Для обычного удаления предпочитай корзину: `files update` с телом `{"trashed": true}`. Для безвозвратного удаления нужна явная авторизация на конкретные файлы или очистку корзины; если она уже получена, не спрашивай повторно. `--dry-run` проверяет запрос локально, но не права доступа и не фактический результат. После изменения проверь метаданные или права доступа.
