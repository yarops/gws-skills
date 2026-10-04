# Команды Bash/zsh

Выполняй примеры в Bash/zsh. Перед API проверь `gws auth status` и следуй правилам
авторизации из SKILL.md. После ошибки прекращай зависимые действия; при запуске
нескольких команд в Bash используй `set -e`, а для цепочек — `&&`.

Пользовательские строки сериализуй через Python или `jq --arg`;
не вставляй их конкатенацией в текст shell-команды. `jq` нужен только
для динамических данных; статические примеры ниже его не требуют.

## Поиск по имени

```bash
gws drive files list --params '{"q": "name contains '\''report'\'' and trashed = false", "pageSize": 20, "fields": "nextPageToken,files(id,name,mimeType,webViewLink)"}'
```

## Файлы внутри папки

```bash
gws drive files list --params '{"q": "'\''FOLDER_ID'\'' in parents and trashed = false", "pageSize": 100, "fields": "nextPageToken,files(id,name,mimeType)"}'
```

## Метаданные файла

```bash
gws drive files get --params '{"fileId": "FILE_ID", "fields": "id,name,mimeType,parents,owners,modifiedTime,size,webViewLink"}'
```

## Загрузка файла

```bash
gws drive +upload ./report.csv --parent FOLDER_ID --name "Отчёт.csv"
```

## Скачивание файла

```bash
gws drive files get --params '{"fileId": "FILE_ID", "alt": "media"}' --output ./local/report.pdf
```

## Экспорт Google-файла

```bash
gws drive files export --params '{"fileId": "FILE_ID", "mimeType": "application/pdf"}' --output ./local/report.pdf
```

## Создание папки

```bash
gws drive files create --json '{"name": "Новая папка", "mimeType": "application/vnd.google-apps.folder", "parents": ["PARENT_ID"]}'
```

## Перемещение файла

```bash
gws drive files update --params '{"fileId": "FILE_ID", "addParents": "NEW_FOLDER_ID", "removeParents": "OLD_FOLDER_ID"}'
```

## Доступ к файлу

```bash
gws drive permissions create --params '{"fileId": "FILE_ID"}' --json '{"role": "writer", "type": "user", "emailAddress": "someone@example.com"}'
```

## Схемы методов

```bash
gws schema drive.files.list --resolve-refs
gws schema drive.permissions.create --resolve-refs
```
