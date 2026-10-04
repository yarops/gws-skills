# gws skills

Скиллы для Claude/других агентов поверх личной CLI-утилиты `gws` (Google Workspace CLI, `gws drive ...`, `gws sheets ...`). Разработка и проверка ведётся здесь; в `~/.agents/skills/` скиллы устанавливаются отдельным осознанным шагом, когда версия готова — не автоматически при каждой правке.

## Структура

- `gws-drive/` — скилл для работы с Google Drive через `gws`.
- `gws-sheets/` — скилл для Google Sheets через `gws`; включает `assets/header_style.json` (шаблон оформления заголовка таблицы) и `scripts/create_tracker.sh` (создаёт таблицу с уже применённым единым стилем).
- `plans/` — локальные рабочие планы по доработке скиллов (не коммитится, см. `.gitignore`).

## Установка в `~/.agents/skills/`

Способ не зафиксирован окончательно, обсуждается симлинк — так правки в этом репозитории сразу видны агентам без переустановки:

```
ln -s /projects/skills/gws-drive /home/yarops/.agents/skills/gws-drive
ln -s /projects/skills/gws-sheets /home/yarops/.agents/skills/gws-sheets
```

Выполнять по явному запросу, не автоматически.
