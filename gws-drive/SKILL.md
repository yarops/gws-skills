---
name: gws-drive
description: Use the gws CLI (Google Workspace CLI) to manage Google Drive from the terminal — list/search files and folders, upload, download, create folders, move files between folders, share via permissions, delete. Trigger whenever the user wants to read, upload, organize, search, or share files in Google Drive from the command line, or mentions gws, Google Drive uploads/downloads/sharing, "залить файл на гугл диск", "найти файл на диске", "расшарить файл/папку" — even if they don't say "Google Drive API" explicitly.
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
gws drive files list --params '{"q": "name contains '\''report'\'' and trashed = false", "pageSize": 20}'
```

**Файлы внутри конкретной папки:**
```
gws drive files list --params '{"q": "'\''FOLDER_ID'\'' in parents", "pageSize": 100}'
```

**Метаданные одного файла:**
```
gws drive files get --params '{"fileId": "FILE_ID"}'
```

**Загрузить локальный файл:**
```
gws drive +upload ./report.csv --parent FOLDER_ID --name "Отчёт.csv"
```

**Скачать файл:**
```
gws drive files download --params '{"fileId": "FILE_ID"}' --output ./local/report.pdf
```
Ссылка на скачивание действительна 24 часа от момента создания — если истекла, просто выполни запрос заново.

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

Перед такими вызовами подтверди с пользователем, что и зачем удаляется — как с любым деструктивным действием, затрагивающим данные за пределами локального репозитория — и, где возможно, сначала прогони с `--dry-run`, чтобы проверить валидность запроса без реальной отправки.
