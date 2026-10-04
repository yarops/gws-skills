#!/usr/bin/env bash
set -euo pipefail
usage() {
  cat <<'HELP'
Usage: ./install.sh --dest DIRECTORY [--upgrade]

Copy gws-drive and gws-sheets into DIRECTORY (macOS and Linux).
Identical installations are left unchanged. --upgrade replaces differing
folders, including local edits, and preserves their originals in
DIRECTORY/.gws-skills-backups/. Links and special files are rejected.
HELP
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
dest=''
upgrade=false
while (($#)); do
  case "$1" in
    --dest)
      (($# >= 2)) || fail '--dest requires a directory'
      [[ -z "$dest" && -n "$2" ]] || fail '--dest requires one nonempty directory'
      dest=$2; shift 2 ;;
    --upgrade) upgrade=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown argument: $1" ;;
  esac
done
[[ -n "$dest" ]] || { usage >&2; exit 1; }
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
skills=(gws-drive gws-sheets)
validate_tree() {
  [[ -d "$1" && ! -L "$1" ]] || fail "Expected an ordinary directory: $1"
  local invalid
  invalid=$(find "$1" ! -type d ! -type f -print) || fail "Cannot inspect: $1"
  [[ -z "$invalid" ]] || fail "Links or special files in: $1"
}
for skill in "${skills[@]}"; do
  validate_tree "$source_dir/$skill"
  [[ -f "$source_dir/$skill/SKILL.md" ]] || fail "Missing source: $skill/SKILL.md"
done
[[ -f "$source_dir/gws-sheets/assets/header_style.json" ]] || fail 'Missing Sheets style'
[[ -f "$source_dir/gws-sheets/scripts/create_tracker.py" ]] || fail 'Missing Python Sheets helper'
[[ "$dest" = /* ]] || dest="$PWD/$dest"
# Resolve the existing ancestor before creating directories to avoid writing
# inside a source skill through a redirected destination.
ancestor=$dest
while [[ ! -e "$ancestor" ]]; do
  [[ ! -L "$ancestor" ]] || fail "Dangling destination link: $ancestor"
  ancestor=$(dirname -- "$ancestor")
done
resolved=$(cd -- "$ancestor" && pwd -P) || fail "Invalid destination: $dest"
for skill in "${skills[@]}"; do
  case "$resolved/" in "$source_dir/$skill/"*) fail "Destination is inside source skill: $skill" ;; esac
done
mkdir -p -- "$dest"
dest=$(cd -- "$dest" && pwd -P)
lock="$dest/.gws-skills-install.lock"
mkdir -- "$lock" 2>/dev/null || fail "Installation lock exists: $lock"
stage=''
backup=''
published=()
saved=()
actions=()
committed=false
cleanup() {
  local status=$? skill
  trap - EXIT
  if ! $committed; then
    for skill in ${published[@]+"${published[@]}"}; do
      rm -rf -- "$dest/$skill" || { printf 'Rollback failed removing: %s\n' "$dest/$skill" >&2; status=1; }
    done
    for skill in ${saved[@]+"${saved[@]}"}; do
      if [[ -e "$dest/$skill" || -L "$dest/$skill" ]] || ! mv -- "$backup/$skill" "$dest/$skill"; then
        printf 'Rollback failed; restore %s to %s manually\n' "$backup/$skill" "$dest/$skill" >&2
        status=1
      fi
    done
  fi
  [[ -z "$stage" ]] || rm -rf -- "$stage" || status=1
  rmdir -- "$lock" || status=1
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
stage=$(mktemp -d "$dest/.gws-skills-install.XXXXXXXX")
for skill in "${skills[@]}"; do
  cp -R -- "$source_dir/$skill" "$stage/$skill"
  if [[ -e "$dest/$skill" || -L "$dest/$skill" ]]; then
    validate_tree "$dest/$skill"
    if diff -r -- "$stage/$skill" "$dest/$skill" > /dev/null; then
      actions+=(unchanged)
    else
      result=$?
      [[ "$result" = 1 ]] || fail "Cannot compare: $dest/$skill"
      $upgrade || fail "Different installation: $dest/$skill; rerun with --upgrade"
      actions+=(updated)
    fi
  else
    actions+=(installed)
  fi
done
for ((i=0; i<${#skills[@]}; i++)); do
  skill=${skills[$i]}
  [[ ${actions[$i]} != unchanged ]] || continue
  if [[ ${actions[$i]} = updated ]]; then
    if [[ -z "$backup" ]]; then
      backup_root="$dest/.gws-skills-backups"
      [[ ! -L "$backup_root" ]] || fail "Backup directory is a link: $backup_root"
      mkdir -p -- "$backup_root"
      backup=$(mktemp -d "$backup_root/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXXXX")
    fi
    mv -- "$dest/$skill" "$backup/$skill"
    saved+=("$skill")
  fi
  [[ ! -e "$dest/$skill" && ! -L "$dest/$skill" ]] || fail "Destination appeared: $dest/$skill"
  mv -- "$stage/$skill" "$dest/$skill"
  published+=("$skill")
done
committed=true
for ((i=0; i<${#skills[@]}; i++)); do
  case ${actions[$i]} in
    unchanged) printf 'Already installed: %s\n' "$dest/${skills[$i]}" ;;
    installed) printf 'Installed: %s\n' "$dest/${skills[$i]}" ;;
    updated) printf 'Updated: %s\n' "$dest/${skills[$i]}" ;;
  esac
done
[[ -z "$backup" ]] || printf 'Backup: %s\n' "$backup"
