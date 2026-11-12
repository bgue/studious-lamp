#!/usr/bin/env bash
# Set one release version on every workspace package (P2-REL-T01).
#
# Usage: dev/release/set_version.sh <X.Y.Z>
#   Rewrites the `version = "..."` line in the [project] table of every packages/*/pyproject.toml and
#   packages/tl-modules/*/pyproject.toml, one output line per file. Nothing is written unless every
#   file has a version line in [project].
# Exit: 0 on success, 2 on bad usage or a version not matching ^[0-9]+\.[0-9]+\.[0-9]+$,
#       1 when a pyproject has no version line in [project] (or no pyproject is found).
# The repository root is the grandparent of this script (dev/release/ -> repo root).
set -euo pipefail

usage() {
  echo "usage: dev/release/set_version.sh <X.Y.Z>" >&2
  exit 2
}

[ $# -eq 1 ] || usage
version="$1"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "set_version: bad version '$version' (want X.Y.Z)" >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
shopt -s nullglob
files=("$root"/packages/*/pyproject.toml "$root"/packages/tl-modules/*/pyproject.toml)
if [ "${#files[@]}" -eq 0 ]; then
  echo "set_version: no packages/*/pyproject.toml under $root" >&2
  exit 1
fi

# count_versions FILE: number of version lines inside the [project] table.
count_versions() {
  awk '
    /^\[/ { intable = ($0 ~ /^\[project\][ \t]*$/); next }
    intable && /^version[ \t]*=[ \t]*"/ { n++ }
    END { print n + 0 }
  ' "$1"
}

# Check every file first, so a missing line leaves the tree untouched.
for f in "${files[@]}"; do
  if [ "$(count_versions "$f")" -eq 0 ]; then
    echo "set_version: no version line in [project] of ${f#"$root"/}" >&2
    exit 1
  fi
done

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
for f in "${files[@]}"; do
  awk -v ver="$version" '
    /^\[/ { intable = ($0 ~ /^\[project\][ \t]*$/); print; next }
    intable && /^version[ \t]*=[ \t]*"/ { print "version = \"" ver "\""; next }
    { print }
  ' "$f" > "$tmp"
  cat "$tmp" > "$f"  # keeps the file's own mode
  echo "set_version: ${f#"$root"/} -> $version"
done
