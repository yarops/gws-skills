# gws skills

Скиллы для Claude/других агентов поверх личной CLI-утилиты `gws` (Google Workspace CLI, `gws drive ...`, `gws sheets ...`). Разработка и проверка ведётся здесь; в `~/.agents/skills/` скиллы устанавливаются отдельным осознанным шагом, когда версия готова — не автоматически при каждой правке.

## Структура

- `gws-drive/` — скилл для работы с Google Drive через `gws`.
- `gws-sheets/` — скилл для Google Sheets через `gws`; включает `assets/header_style.json` (шаблон оформления заголовка таблицы) и `scripts/create_tracker.sh` (создаёт таблицу с уже применённым единым стилем; заголовки принимает JSON-массивом, `--resume` завершает настройку созданного файла после сбоя).
- `plans/` — локальные рабочие планы по доработке скиллов (не коммитится, см. `.gitignore`).

## Проверка

Локальные тесты без моделей, сети и доступа к Google:

```sh
python3 -B -m unittest discover -s tests -v
```

Требуются Python 3.9+, Bash и jq. Покрытие и ограничения — в [tests/README.md](tests/README.md).

Интеграционная проверка с настоящим `gws` и Google API (создаёт временные
объекты и после проверки переносит их в корзину):

```sh
python3 -B tests/integration_gws.py --live
```

## Установка в `~/.agents/skills/`

Способ не зафиксирован окончательно, обсуждается симлинк — так правки в этом репозитории сразу видны агентам без переустановки:

```
ln -s /projects/skills/gws-drive /home/yarops/.agents/skills/gws-drive
ln -s /projects/skills/gws-sheets /home/yarops/.agents/skills/gws-sheets
```

Выполнять по явному запросу, не автоматически.
