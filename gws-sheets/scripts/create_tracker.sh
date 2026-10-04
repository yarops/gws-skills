#!/usr/bin/env bash
# create_tracker.sh [--resume SPREADSHEET_ID] --config FILE
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
  [[ $# -ge 3 ]] || { echo 'Использование: --resume ID HEADERS_JSON [TAB_NAME] или --resume ID --config FILE' >&2; exit 1; }
  RESUME_ID="${2:?Укажите ID таблицы}"
  shift 2
fi
if [[ ${1:-} == --config ]]; then
  [[ $# == 2 ]] || { echo 'Использование: [--resume ID] --config FILE' >&2; exit 1; }
  CONFIG=$(jq -cs 'if length == 1 then .[0] else error("Нужен один JSON-объект") end' "$2")
else
  if [[ -n "$RESUME_ID" ]]; then
    [[ $# -ge 1 && $# -le 2 ]] || exit 1
    TITLE="resume"
  else
    [[ $# -ge 2 && $# -le 3 ]] || { echo 'Использование: TITLE HEADERS_JSON [TAB_NAME] или --config FILE' >&2; exit 1; }
    TITLE="${1:?Укажите название таблицы}"
    shift
  fi
  CONFIG=$(jq -cn --arg title "$TITLE" --arg tab "${2:-Sheet1}" --argjson headers "$1"     '{title: $title, sheets: [{title: $tab, headers: $headers}]}')
fi
CONFIG=$(jq -ce '
  if type == "object" and (.title | type == "string" and length > 0)
    and (.sheets | type == "array" and length > 0)
  then . else error("Нужны title и непустой массив sheets") end
  | if all(.sheets[]; type == "object" and (.title | type == "string" and length > 0)
      and (.headers | type == "array" and length > 0 and length <= 18278
        and all(.[]; type == "string" and length > 0)))
    then . else error("Для каждого листа нужны title и непустые строковые headers (до 18278 колонок)") end
  | if (.sheets | map(.title | ascii_downcase) | unique | length) == (.sheets | length)
    then . else error("Названия листов должны быть уникальны") end
  | if all(.sheets[].headers[]; ({userEnteredValue: {stringValue: .}} | tojson | utf8bytelength) <= 60000)
    then . else error("Заголовок слишком длинный: JSON одной ячейки должен быть не больше 60000 байт") end
' <<< "$CONFIG")
jq -e '.requests | type == "array" and length > 0' "$STYLE_TEMPLATE" >/dev/null
SPREADSHEET_ID="$RESUME_ID"
SPREADSHEET_URL=""
on_error() {
  local status=$?
  if [[ -n "$SPREADSHEET_ID" ]]; then
    echo "Не удалось завершить настройку. ID: $SPREADSHEET_ID" >&2
    echo "URL: ${SPREADSHEET_URL:-https://docs.google.com/spreadsheets/d/$SPREADSHEET_ID/edit}" >&2
    echo 'Продолжите через --resume с той же конфигурацией или заголовками и вкладкой; новая таблица не нужна.' >&2
  else
    echo 'Создание не подтверждено. Перед повтором проверьте Drive: при сетевом сбое файл мог быть создан.' >&2
  fi
  exit "$status"
}
trap on_error ERR
if [[ -n "$RESUME_ID" ]]; then
  RESPONSE=$(gws sheets spreadsheets get --params "$(jq -n --arg id "$RESUME_ID" '{spreadsheetId: $id, fields: "spreadsheetId,spreadsheetUrl,sheets(properties)"}')")
else
  RESPONSE=$(gws sheets spreadsheets create --json "$(jq -c '{properties: {title: .title}, sheets: [.sheets[] | {properties: {title: .title, gridProperties: {columnCount: (.headers | length)}}}]}' <<< "$CONFIG")")
fi
SPREADSHEET_ID=$(jq -er '.spreadsheetId | select(type == "string" and length > 0)' <<< "$RESPONSE")
SPREADSHEET_URL="https://docs.google.com/spreadsheets/d/$SPREADSHEET_ID/edit"
SPREADSHEET_URL=$(jq -er '.spreadsheetUrl | select(type == "string" and length > 0)' <<< "$RESPONSE")
echo "Таблица: $SPREADSHEET_URL (ID: $SPREADSHEET_ID)" >&2
# Validate every target before writing any headers, including in resume mode.
TARGETS=$(jq -ce --argjson response "$RESPONSE" '
  [.sheets[] | . as $sheet
    | [$response.sheets[].properties | select(.title == $sheet.title)]
    | if length == 1 then .[0] else error("Вкладка не найдена или неоднозначна") end
    | if (.sheetId | type == "number" and . >= 0 and floor == .)
        and (.gridProperties.columnCount | type == "number" and floor == .)
        and .gridProperties.columnCount >= ($sheet.headers | length)
      then {id: .sheetId, headers: $sheet.headers}
      else error("Некорректный sheetId или недостаточно колонок") end]
' <<< "$CONFIG")
PARAMS=$(jq -cn --arg id "$SPREADSHEET_ID" '{spreadsheetId: $id}')
while IFS= read -r TARGET; do
SHEET_ID=$(jq '.id' <<< "$TARGET")
HEADERS_JSON=$(jq -c '.headers' <<< "$TARGET")
COLUMN_COUNT=$(jq 'length' <<< "$HEADERS_JSON")
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
while IFS= read -r REQUEST; do
  gws sheets spreadsheets batchUpdate --params "$PARAMS" --json "$REQUEST" >/dev/null
done <<< "$REQUESTS"
done <<< "$(jq -c '.[]' <<< "$TARGETS")"
printf '%s\n' "$SPREADSHEET_URL"
