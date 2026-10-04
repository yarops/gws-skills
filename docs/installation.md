# Установка и обновление

[Главная](../README.md) · [Использование](usage.md)

## Зависимости и отсутствие gws

Установщик копирует скиллы, но не устанавливает `gws`, Python или оболочки.
Для работы нужен установленный и авторизованный `gws`; для помощника Sheets —
Python 3.9+ без сторонних пакетов. Помощнику не нужны Bash и `jq`;
`jq` нужен отдельным примерам Bash, использующим его.

До авторизации проверьте, доступен ли CLI в окружении инструмента агента:

```sh
command -v gws
```

В PowerShell:

```powershell
Get-Command gws -CommandType Application -ErrorAction SilentlyContinue
```

Если команда не найдена, установите CLI по
[официальной инструкции](https://github.com/googleworkspace/cli#installation)
или добавьте каталог уже установленного CLI в `PATH` инструмента агента.
На Windows нужен исполняемый `gws.exe`. Повторите проверку в новой сессии
после изменения окружения. `gws auth login` не поможет, пока CLI недоступен.

Пошаговая установка CLI и настройка доступа описаны ниже.

## Установка gws

Выберите инструкции для своей ОС. Устанавливайте CLI в том окружении, где
агент выполняет команды: например, для агента в WSL используйте раздел Linux.
После установки перезапустите терминал и приложение агента, чтобы они получили
обновлённый `PATH`.

Способы установки сверены с [документацией gws](https://github.com/googleworkspace/cli#installation).
Готовый бинарник не требует Node.js; вариант через npm требует Node.js 18+.

### Linux

Если Node.js и npm уже установлены:

```sh
node --version
npm --version
npm install -g @googleworkspace/cli
command -v gws
gws --version
```

Если npm сообщает об отсутствии прав на глобальную установку, настройте
пользовательский prefix вместо запуска с `sudo`:

```sh
npm config set prefix "$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
npm install -g @googleworkspace/cli
```

Добавьте строку `export PATH="$HOME/.local/bin:$PATH"` в `~/.bashrc` для Bash
или `~/.zshrc` для zsh, чтобы настройка сохранялась в новых терминалах.

Без Node.js скачайте архив Linux для своей архитектуры из
[GitHub Releases](https://github.com/googleworkspace/cli/releases).
Архитектуру можно узнать командой `uname -m`. Распакуйте архив и перейдите
в каталог с бинарником, затем выполните:

```sh
mkdir -p "$HOME/.local/bin"
install -m 755 ./gws "$HOME/.local/bin/gws"
export PATH="$HOME/.local/bin:$PATH"
gws --version
```

Сохраните настройку `PATH` в файле оболочки, как описано выше.

### macOS

Если установлен [Homebrew](https://brew.sh/):

```sh
brew install googleworkspace-cli
command -v gws
gws --version
```

Если `brew` не найден после установки Homebrew, выполните настройку `shellenv`
из завершающих подсказок его установщика и откройте новый терминал.

Альтернативы: `npm install -g @googleworkspace/cli` при установленном Node.js
18+ или готовый архив macOS из
[GitHub Releases](https://github.com/googleworkspace/cli/releases).
Для Apple Silicon выбирайте ARM64/aarch64, для Intel — x86_64.
Распакованный `gws` можно установить в `~/.local/bin` командами из раздела
Linux и добавить этот каталог в `PATH` в `~/.zshrc`.

### Windows

Для команд скиллов установите [PowerShell 7](https://github.com/PowerShell/PowerShell/releases)
версии 7.3 или новее и откройте `pwsh`. Встроенный Windows PowerShell 5.1
не подходит для этих примеров.

Скачайте архив Windows для своей архитектуры из
[GitHub Releases](https://github.com/googleworkspace/cli/releases), распакуйте
его и положите `gws.exe`, например, в `$HOME\Tools\gws`.
Добавьте эту папку в пользовательскую переменную `Path` через
«Изменение переменных среды для учётной записи». В текущем сеансе можно
проверить установку сразу:

```powershell
$env:Path = "$HOME\Tools\gws;$env:Path"
Get-Command gws.exe -CommandType Application -ErrorAction Stop
gws.exe --version
$PSVersionTable.PSVersion
$PSNativeCommandArgumentPassing = 'Standard'
```

Вариант через npm: установите Node.js 18+ и выполните
`npm install -g @googleworkspace/cli`. Затем проверьте наличие именно
`gws.exe` командой `Get-Command` выше: помощнику Sheets нужен исполняемый
файл, а не `.cmd`/`.bat`-обёртка. Если доступна только обёртка, используйте
готовый бинарник из архива и добавьте его папку в `Path`.

## Настройка доступа к Google

Настройка OAuth одинакова на всех трёх ОС. На Windows в приведённых командах
используйте `gws.exe`. Понадобятся аккаунт Google с доступом к нужным файлам
и проект Google Cloud. Подробности — в
[документации авторизации gws](https://github.com/googleworkspace/cli#authentication).

### Через gcloud

Установите [Google Cloud CLI](https://cloud.google.com/sdk/docs/install),
выбрав инструкции для своей ОС. Проверьте `gcloud --version`, затем выполните:

```sh
gcloud auth login
gws auth setup
gws auth login -s drive,sheets
gws auth status
```

Следуйте подсказкам мастера и завершите вход в браузере.
Для этих двух скиллов выбирайте сервисы Drive и Sheets.

### Вручную, без gcloud

1. Откройте [Google Cloud Console](https://console.cloud.google.com/),
   создайте или выберите проект.
2. В библиотеке API включите **Google Drive API** и **Google Sheets API**.
3. В **Google Auth Platform** настройте Branding и Audience. Для личного
   аккаунта выберите **External** и добавьте свой адрес в **Test users**,
   если приложение находится в режиме Testing.
4. В разделе **Clients** (или **APIs & Services → Credentials**) создайте
   OAuth client ID типа **Desktop app** и скачайте JSON.
5. Сохраните его под именем `client_secret.json` в каталоге конфигурации gws.

По умолчанию каталог — `~/.config/gws` на всех ОС, включая Windows
(`$HOME\.config\gws`). Если задана переменная
`GOOGLE_WORKSPACE_CLI_CONFIG_DIR`, используйте её значение вместо этого пути.
Для стандартного каталога в Bash/zsh:

```sh
mkdir -p "$HOME/.config/gws"
cp /path/to/downloaded-client.json "$HOME/.config/gws/client_secret.json"
chmod 600 "$HOME/.config/gws/client_secret.json"
```

В PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "$HOME\.config\gws" | Out-Null
Copy-Item -LiteralPath 'C:\path\to\downloaded-client.json' -Destination "$HOME\.config\gws\client_secret.json"
```

Замените путь к скачанному файлу своим, затем выполните
`gws auth login -s drive,sheets` и завершите вход в браузере.
OAuth JSON и файлы токенов храните вне репозитория.

### Проверка настройки

В Bash/zsh:

```sh
gws auth status
gws drive files list --params '{"pageSize": 5, "fields": "files(id,name)"}'
```

В PowerShell 7.3+:

```powershell
$PSNativeCommandArgumentPassing = 'Standard'
gws.exe auth status
$paramsJson = @{ pageSize = 5; fields = 'files(id,name)' } | ConvertTo-Json -Compress
gws.exe drive files list --params $paramsJson
if ($LASTEXITCODE -ne 0) { throw "gws: $LASTEXITCODE" }
```

Список файлов (в том числе пустой) без ошибки подтверждает доступ к Drive.
Проверьте доступ к Sheets чтением своей таблицы по примерам в
[документации использования](usage.md).
Если `token_valid: false`, но `has_refresh_token: true` и конфигурация
клиента доступна, CLI обновит токен при следующем запросе.

### Частые проблемы

- **Команда не найдена:** проверьте `PATH` именно в инструменте агента,
  затем перезапустите приложение. Установка в Windows не означает установку в WSL.
- **`gcloud` не найден:** установите Google Cloud CLI или используйте ручной OAuth.
- **Access blocked:** проверьте, что ваш аккаунт добавлен в Test users.
- **`redirect_uri_mismatch`:** нужен OAuth-клиент типа Desktop app.
- **Ошибка выбора scopes:** повторите `gws auth login -s drive,sheets`,
  выбирая доступ только к нужным сервисам.
- **403 / `accessNotConfigured`:** включите соответствующий API в том проекте,
  которому принадлежит OAuth-клиент, и повторите запрос.
- **Нет нужных прав / истёк refresh-токен:** повторите вход с Drive и Sheets.
  Разрешения OAuth не заменяют доступ аккаунта к конкретному файлу.

## Установка скиллов

Склонируйте репозиторий или распакуйте его архив. На macOS/Linux установщик требует Bash,
копирует оба скилла вместе со скриптами и ресурсами и не устанавливает зависимости.

```sh
# Для пользователя
./install.sh --dest "$HOME/.agents/skills"

# В конкретный проект
./install.sh --dest /path/to/project/.agents/skills
```

На Windows используйте PowerShell 7.3+:

```powershell
# Для пользователя
pwsh -NoProfile -File ./install.ps1 -Dest "$HOME/.agents/skills"

# В конкретный проект
pwsh -NoProfile -File ./install.ps1 -Dest 'C:\Projects\my-project\.agents\skills'
```

`--dest` (Bash) или `-Dest` (PowerShell) — родительский каталог скиллов: внутри появятся `gws-drive/` и
`gws-sheets/`. Можно указать другую папку, которую использует ваш агент.
Относительные пути считаются от текущего рабочего каталога; пути с пробелами
заключайте в кавычки. Установщик можно запускать из любого рабочего каталога.

## Повторная установка

Повторная установка идентичных папок завершается успешно (`Already installed`)
без изменения файлов. Сравниваются состав дерева, включая скрытые файлы и
пустые каталоги, и байты файлов; времена изменения и права доступа не учитываются.
Если один скилл отсутствует, а другой идентичен, установщик добавит отсутствующий.
При любых отличиях обычный запуск остановится до публикации обоих скиллов.

## Обновление и резервные копии

Для обновления используйте явный флаг:

```sh
./install.sh --dest "$HOME/.agents/skills" --upgrade
```

```powershell
pwsh -NoProfile -File ./install.ps1 -Dest "$HOME/.agents/skills" -Upgrade
```

Обновление заменяет отличающуюся папку целиком, включая ручные правки и
дополнительные файлы. Прежние папки сохраняются в
`DEST/.gws-skills-backups/<UTC-время>-<случайный-id>/`; установщик выводит
точный путь. Резервные копии автоматически не удаляются. Идентичные скиллы
не перезаписываются и не резервируются. Устанавливаются копии: последующие
правки в репозитории не меняют установленную версию.

## Ограничения путей и параллельных запусков

Файл, симлинк или junction вместо целевой папки отклоняется даже при обновлении.
Ссылки и специальные файлы внутри исходных и установленных деревьев также
отклоняются. Блокировка исключает параллельные запуски этого установщика;
чужая блокировка не удаляется.

## Восстановление после сбоя

При обрабатываемой ошибке публикации установщик удаляет новые папки своего
запуска и возвращает прежние. Если восстановление не удалось, он сообщает
пути сохранённых оригиналов и целевых папок. Для ручного восстановления
переместите текущую целевую папку, если она существует, в отдельное безопасное
место и перенесите соответствующую папку из резерва на её место.
Принудительное завершение или отключение питания могут оставить частично
опубликованную установку, временную папку и блокировку: автоматический откат
в этом случае не гарантируется. Перед ручным восстановлением и удалением
оставшейся блокировки убедитесь, что установщик больше не работает.

## Проверка установленной версии

После установки проверьте каталог скиллов в новой сессии агента:
оба скилла должны обнаруживаться, а скрипт и шаблон Sheets — быть доступны
относительно установленного `SKILL.md`. PowerShell-установщик отклоняет пути назначения,
проходящие через симлинки или junction, и каталоги внутри исходных скиллов.

Подробности оболочек и запуска помощника — в [использовании](usage.md).
