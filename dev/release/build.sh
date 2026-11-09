#!/usr/bin/env bash
# Build one wheel per workspace package into dist/release-<version>/ and write SHA256SUMS (P2-REL-T03).
#
# Usage: dev/release/build.sh
#   The version is the [project] version of packages/tl-cli/pyproject.toml (set by dev/release/set_version.sh).
#   Wheels come from `uv build --all-packages --wheel --out-dir`; the output directory is removed first, so it
#   holds only this build. SHA256SUMS lists the wheels by bare file name (`sha256sum -c` runs inside the directory).
# Exit: 0 on success; 1 when the version cannot be read or no wheel was built.
# The repository root is the grandparent of this script (dev/release/ -> repo root).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cli_pyproject="$root/packages/tl-cli/pyproject.toml"

if [ ! -f "$cli_pyproject" ]; then
  echo "build: no $cli_pyproject" >&2
  exit 1
fi
version="$(awk '/^\[/ { section = $0 } section == "[project]" && /^version *=/ { sub(/^version *= *"/, ""); sub(/".*$/, ""); print; exit }' "$cli_pyproject")"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "build: no X.Y.Z version in [project] of $cli_pyproject (got '$version')" >&2
  exit 1
fi

out="$root/dist/release-$version"
rm -rf "$out"
mkdir -p "$out"

cd "$root"
uv build --all-packages --wheel --out-dir "$out"

shopt -s nullglob
wheels=("$out"/*.whl)
shopt -u nullglob
if [ "${#wheels[@]}" -eq 0 ]; then
  echo "build: no wheel written to $out" >&2
  exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha_cmd=(sha256sum)
else
  sha_cmd=(shasum -a 256)
fi
(cd "$out" && "${sha_cmd[@]}" -- *.whl > SHA256SUMS)

echo "build: ${#wheels[@]} wheels in dist/release-$version (version $version)"
