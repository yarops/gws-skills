#!/usr/bin/env bash
# create_tracker.sh TITLE HEADERS_JSON [TAB_NAME]
# create_tracker.sh --resume SPREADSHEET_ID HEADERS_JSON [TAB_NAME]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STYLE_TEMPLATE="$SCRIPT_DIR/../assets/header_style.json"
for dependency in gws jq; do
  command -v "$dependency" >/dev/null || { echo "Не найден $dependency" >&2; exit 1; }
done
RESUME_ID=""
if [[ ${1:-} == --resume ]]; then
  [[ $# -ge 3 && $# -le 4 ]] || { echo 'Использование: --resume ID HEADERS_JSON [TAB_NAME]' >&2; exit 1; }
  RESUME_ID="${2:?Укажите ID таблицы}"
  shift 2
  HEADERS_INPUT="$1"
  TAB_NAME="${2:-Sheet1}"
else
  [[ $# -ge 2 && $# -le 3 ]] || { echo 'Использование: TITLE HEADERS_JSON [TAB_NAME]' >&2; exit 1; }
  TITLE="${1:?Укажите название таблицы}"
  HEADERS_INPUT="$2"
  TAB_NAME="${3:-Sheet1}"
fi
HEADERS_JSON=$(jq -ce 'if type == "array" and length > 0 and length <= 18278 and all(.[]; type == "string" and length > 0) then . else error("Нужен непустой JSON-массив непустых строк (до 18278 колонок)") end | if all(.[]; ({userEnteredValue: {stringValue: .}} | tojson | utf8bytelength) <= 60000) then . else error("Заголовок слишком длинный: JSON одной ячейки должен быть не больше 60000 байт") end' <<< "$HEADERS_INPUT")
COLUMN_COUNT=$(jq 'length' <<< "$HEADERS_JSON")
jq -e '.requests | type == "array" and length > 0' "$STYLE_TEMPLATE" >/dev/null
SPREADSHEET_ID="$RESUME_ID"
SPREADSHEET_URL=""
on_error() {
  local status=$?
  if [[ -n "$SPREADSHEET_ID" ]]; then
    echo "Не удалось завершить настройку. ID: $SPREADSHEET_ID" >&2
    echo "URL: ${SPREADSHEET_URL:-https://docs.google.com/spreadsheets/d/$SPREADSHEET_ID/edit}" >&2
    echo 'Продолжите через --resume с теми же заголовками и вкладкой; новая таблица не нужна.' >&2
  else
    echo 'Создание не подтверждено. Перед повтором проверьте Drive: при сетевом сбое файл мог быть создан.' >&2
  fi
  exit "$status"
}
trap on_error ERR
if [[ -n "$RESUME_ID" ]]; then
  RESPONSE=$(gws sheets spreadsheets get --params "$(jq -n --arg id "$RESUME_ID" '{spreadsheetId: $id, fields: "spreadsheetId,spreadsheetUrl,sheets(properties)"}')")
else
  RESPONSE=$(gws sheets spreadsheets create --json "$(jq -n --arg title "$TITLE" --arg tab "$TAB_NAME" --argjson count "$COLUMN_COUNT" '{properties: {title: $title}, sheets: [{properties: {title: $tab, gridProperties: {columnCount: $count}}}]}')")
fi
SPREADSHEET_ID=$(jq -er '.spreadsheetId | select(type == "string" and length > 0)' <<< "$RESPONSE")
SPREADSHEET_URL="https://docs.google.com/spreadsheets/d/$SPREADSHEET_ID/edit"
SPREADSHEET_URL=$(jq -er '.spreadsheetUrl | select(type == "string" and length > 0)' <<< "$RESPONSE")
echo "Таблица: $SPREADSHEET_URL (ID: $SPREADSHEET_ID)" >&2
SHEET_ID=$(jq -er --arg tab "$TAB_NAME" '[.sheets[].properties | select(.title == $tab)] | if length == 1 then .[0].sheetId | select(type == "number" and . >= 0 and floor == .) else error("Вкладка не найдена или неоднозначна") end' <<< "$RESPONSE")
GRID_COLUMNS=$(jq -er --argjson id "$SHEET_ID" '.sheets[].properties | select(.sheetId == $id) | .gridProperties.columnCount | select(type == "number")' <<< "$RESPONSE")
[[ "$GRID_COLUMNS" -ge "$COLUMN_COUNT" ]] || { echo 'Недостаточно колонок в существующей вкладке' >&2; false; }
REQUESTS=$(jq -c --argjson id "$SHEET_ID" --argjson count "$COLUMN_COUNT" --slurpfile style "$STYLE_TEMPLATE" '
  . as $headers | $style[0]
  | .requests |= map(
    if has("repeatCell") then .repeatCell.range.sheetId = $id | .repeatCell.range.startColumnIndex = 0 | .repeatCell.range.endColumnIndex = $count
    elif has("updateSheetProperties") then .updateSheetProperties.properties.sheetId = $id
    elif has("autoResizeDimensions") then .autoResizeDimensions.dimensions.sheetId = $id | .autoResizeDimensions.dimensions.endIndex = $count
    else error("Неизвестный запрос в шаблоне") end)
  | .requests as $formatting
  | ($headers | map({userEnteredValue: {stringValue: .}})) as $cells
  # Bound serialized UTF-8 size, not column count: Cyrillic and escapes vary.
  | reduce $cells[] as $cell
      ({chunks: [], current: [], bytes: 0};
       ($cell | tojson | utf8bytelength) as $size
       | if (.bytes + $size + 1 > 60000) and (.current | length > 0)
         then .chunks += [.current] | .current = [] | .bytes = 0 else . end
       | .current += [$cell] | .bytes += ($size + 1))
  | (.chunks + [.current]) as $chunks
  | reduce range(0; $chunks | length) as $i
      ({batches: [], offset: 0};
       .batches += [{requests: ([{updateCells: {
         start: {sheetId: $id, rowIndex: 0, columnIndex: .offset},
         rows: [{values: $chunks[$i]}], fields: "userEnteredValue"
       }}] + (if $i == (($chunks | length) - 1) then $formatting else [] end))}]
       | .offset += ($chunks[$i] | length))
  | .batches[]
' <<< "$HEADERS_JSON")
PARAMS=$(jq -cn --arg id "$SPREADSHEET_ID" '{spreadsheetId: $id}')
while IFS= read -r REQUEST; do
  gws sheets spreadsheets batchUpdate --params "$PARAMS" --json "$REQUEST" >/dev/null
done <<< "$REQUESTS"
printf '%s\n' "$SPREADSHEET_URL"
