#!/usr/bin/env bash
# Copy the released skill directories; do not overwrite existing installations.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install.sh --dest DIRECTORY

Copy gws-drive and gws-sheets into DIRECTORY (macOS and Linux).
Existing paths, including symbolic links, are never overwritten.
Examples:
  ./install.sh --dest "$HOME/.agents/skills"
  ./install.sh --dest /path/to/project/.agents/skills
EOF
}

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

dest=''
while (($#)); do
  case "$1" in
    --dest)
      (($# >= 2)) || fail '--dest requires a directory'
      [[ -z "$dest" ]] || fail '--dest may only be specified once'
      [[ -n "$2" ]] || fail '--dest requires a nonempty directory'
      dest=$2
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown argument: $1" ;;
  esac
done
[[ -n "$dest" ]] || { usage >&2; exit 1; }

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
skills=(gws-drive gws-sheets)
for skill in "${skills[@]}"; do
  [[ -f "$source_dir/$skill/SKILL.md" ]] || fail "Missing source: $skill/SKILL.md"
done
[[ -f "$source_dir/gws-sheets/assets/header_style.json" ]] || fail 'Missing Sheets style'
[[ -x "$source_dir/gws-sheets/scripts/create_tracker.sh" ]] || fail 'Missing executable Sheets helper'

# Resolve the destination before checking containment and conflicts.
[[ "$dest" = /* ]] || dest="$PWD/$dest"
mkdir -p -- "$dest"
dest=$(cd -- "$dest" && pwd -P)
for skill in "${skills[@]}"; do
  case "$dest/" in
    "$source_dir/$skill/"*) fail "Destination is inside source skill: $skill" ;;
  esac
  [[ ! -e "$dest/$skill" && ! -L "$dest/$skill" ]] || fail "Destination already exists: $dest/$skill"
done

# Stage both copies before publishing either one. A lock prevents simultaneous
# runs of this installer from merging directories or racing conflict checks.
lock="$dest/.gws-skills-install.lock"
mkdir -- "$lock" 2>/dev/null || fail "Installation lock exists: $lock"
stage=''
cleanup() {
  [[ -z "$stage" ]] || rm -rf -- "$stage"
  rmdir -- "$lock"
}
trap cleanup EXIT
stage=$(mktemp -d "$dest/.gws-skills-install.XXXXXXXX")
for skill in "${skills[@]}"; do
  cp -R -- "$source_dir/$skill" "$stage/$skill"
done
for skill in "${skills[@]}"; do
  [[ ! -e "$dest/$skill" && ! -L "$dest/$skill" ]] || fail "Destination already exists: $dest/$skill"
done
for skill in "${skills[@]}"; do
  mv -- "$stage/$skill" "$dest/$skill"
  printf 'Installed: %s\n' "$dest/$skill"
done
