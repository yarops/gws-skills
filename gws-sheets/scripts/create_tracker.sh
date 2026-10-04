#!/usr/bin/env bash
# Создаёт Google Sheet, пишет строку заголовков и применяет единый стиль
# из assets/header_style.json (жирный белый текст на тёмном фоне, закреплённая первая строка).
#
# Использование: create_tracker.sh "<title>" "<col1,col2,...>" [sheet_tab_name]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STYLE_TEMPLATE="$SCRIPT_DIR/../assets/header_style.json"

TITLE="${1:?Укажите название таблицы}"
HEADERS_CSV="${2:?Укажите заголовки колонок через запятую}"
TAB_NAME="${3:-Sheet1}"

IFS=',' read -ra HEADERS <<< "$HEADERS_CSV"
HEADERS_JSON=$(printf '%s\n' "${HEADERS[@]}" | jq -R . | jq -s .)

CREATE_RESPONSE=$(gws sheets spreadsheets create --json "$(jq -n \
  --arg title "$TITLE" --arg tab "$TAB_NAME" \
  '{properties: {title: $title}, sheets: [{properties: {title: $tab}}]}')")

SPREADSHEET_ID=$(echo "$CREATE_RESPONSE" | jq -r '.spreadsheetId')
SHEET_ID=$(echo "$CREATE_RESPONSE" | jq -r '.sheets[0].properties.sheetId')
SPREADSHEET_URL=$(echo "$CREATE_RESPONSE" | jq -r '.spreadsheetUrl')

gws sheets spreadsheets values update \
  --params "$(jq -n --arg id "$SPREADSHEET_ID" --arg range "${TAB_NAME}!A1" \
    '{spreadsheetId: $id, range: $range, valueInputOption: "USER_ENTERED"}')" \
  --json "$(jq -n --argjson row "$HEADERS_JSON" '{values: [$row]}')" > /dev/null

STYLE_REQUEST=$(sed "s/__SHEET_ID__/$SHEET_ID/g" "$STYLE_TEMPLATE")

gws sheets spreadsheets batchUpdate \
  --params "$(jq -n --arg id "$SPREADSHEET_ID" '{spreadsheetId: $id}')" \
  --json "$STYLE_REQUEST" > /dev/null

echo "$SPREADSHEET_URL"
