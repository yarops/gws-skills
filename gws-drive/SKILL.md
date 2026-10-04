---
name: gws-drive
description: Manage files and folders in Google Drive through the gws CLI — search, upload, download, move, and share. Use when Google Drive is the source or destination of files, including Russian requests about гугл диск. For cell values and spreadsheet formatting, use the Sheets skill.
---

# gws drive

`gws` — локальная CLI-обёртка над Google API (бинарник `gws`, авторизован через OAuth2). Форма вызова для Drive:

```
gws drive <resource> <method> [--params JSON] [--json JSON] [--format json|table|yaml|csv]
```

`--params` — query/path-параметры (например `fileId`, `q`), `--json` — тело запроса (для `create`/`update`/`copy`). Для загрузки файла есть хелпер `gws drive +upload <file> [--parent ID] [--name NAME]` — он сам определяет MIME-тип и собирает multipart-запрос, используй его вместо ручного `files create` с загрузкой контента.

## Окружение и оболочка

Перед выполнением команд выбери оболочку **инструмента выполнения агента** по
его контексту или настройкам. Не определяй её только по ОС, `$SHELL`, встроенному
терминалу приложения или окружению дочернего Python-процесса. Если сведений нет,
проверь настроенный исполняемый файл оболочки доступным read-only инструментом;
если определить его невозможно, уточни оболочку до выполнения команд.

- Bash/zsh, включая WSL и Git Bash: прочитай [команды Bash](references/bash.md).
- PowerShell: прочитай [команды PowerShell](references/powershell.md); нужны 7.3+
  и корректная передача аргументов внешним программам.
- cmd, fish и другие оболочки: используй явный запуск доступного Bash/zsh или
  PowerShell 7.3+, затем прочитай соответствующий справочник. Не переноси примеры
  в неизвестную оболочку механически.

Читай только выбранный справочник. При смене среды выполнения выбери его заново.
Методы API и JSON одинаковы; кавычки, переменные и переносы строк зависят от shell.
Не используй `eval`, `Invoke-Expression` или конкатенацию пользовательского текста
в исполняемую команду. Для динамического JSON используй сериализатор.

## Перед первым вызовом в сессии

Проверь `gws auth status`. Если `token_valid: false`, но `has_refresh_token: true` — `gws` обновит токен сам при следующем вызове, ничего делать не нужно. Если `has_refresh_token: false` или `client_config_exists: false` — авторизация не настроена/не может обновиться; скажи пользователю самому выполнить `gws auth login` (открывает браузер для OAuth) — это разовое интерактивное действие пользователя, не пытайся выполнить его от его имени без явной просьбы.

## Частые задачи

**Найти файлы по имени:**
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

**Файлы внутри конкретной папки:**
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

Не считай одну страницу полным списком. Если есть `nextPageToken`, передай его как `pageToken` в следующий запрос. `--page-all` выдаёт NDJSON (по JSON на страницу), но по умолчанию ограничен 10 страницами: задай подходящий `--page-limit` и проверь, что в последней странице нет `nextPageToken`. Для полного подсчёта обработай все страницы.

**Метаданные одного файла:**
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

**Загрузить локальный файл:**
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

**Скачать файл:**
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

Для Google Docs/Sheets/Slides используй экспорт, выбрав поддерживаемый MIME-тип:
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

`files download` возвращает длительную операцию, а не байты файла: если нужен именно этот метод, обработай статус операции и полученный URL скачивания. Перед записью проверь, что локальная папка существует и выбранный путь не перезапишет нужный файл.

**Создать папку:**
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

**Переместить файл в другую папку** (у Drive нет отдельного метода "move" — это patch по родителям):
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

**Расшарить файл/папку:**
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

`role`: `reader` / `writer` / `commenter` / `owner`. `type`: `user` / `group` / `domain` / `anyone`.

## Если нужного метода нет среди примеров

Не угадывай названия полей JSON — посмотри точную схему метода перед вызовом:
Команды для выбранной оболочки: [Bash](references/bash.md) / [PowerShell](references/powershell.md).

Без `--resolve-refs` схема короче, но вложенные `$ref` не раскрыты.

## Вывод

По умолчанию `--format json`. Для быстрого просмотра человеком — `--format table`. Для выгрузки в файл или дальнейшей обработки — `--format csv`.

## Осторожно — необратимые операции

- `gws drive files delete` удаляет файл **навсегда**, минуя корзину.
- `gws drive files emptyTrash` безвозвратно чистит всю корзину пользователя.

Для обычного удаления предпочитай корзину: `files update` с телом `{"trashed": true}`. Для безвозвратного удаления нужна явная авторизация на конкретные файлы или очистку корзины; если она уже получена, не спрашивай повторно. `--dry-run` проверяет запрос локально, но не права доступа и не фактический результат. После изменения проверь метаданные или права доступа.
