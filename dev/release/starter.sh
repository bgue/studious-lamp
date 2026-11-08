#!/usr/bin/env bash
# Build the P200 starter bundle (P2-REL-T04): a SQLite ledger of the demo project P200, the overlay schema
# directory the clients need, and START.txt. The bundle is the "try it" path; it is never a deployment.
#
# Usage: dev/release/starter.sh [--sections LIST] [--out DIR]
#   --sections LIST  passed to `just demo-project` (default: every section, the full P200 build)
#   --out DIR        output directory (default: dist/release-<version>); it is kept, not emptied
# Output: DIR/starter-p200-<version>.tar.gz with the members ledger/p200.db, schema/ and START.txt (nothing
#   else), and a line for that archive in DIR/SHA256SUMS (other lines are kept; an old line for this archive
#   is replaced). Run dev/release/build.sh first if you want the wheels too: it empties its output directory.
# Determinism: with GNU tar the archive uses --sort=name, owner 0, group 0 and --mtime=@$SOURCE_DATE_EPOCH
#   (default 0), and gzip -n drops the gzip timestamp. macOS ships bsdtar, which has no --sort=name: there the
#   archive keeps the same members and contents but is not byte-identical across runs.
# The ledger's object store is built with TL_OBJECT_SECRET set to the try-it value written into START.txt.
# Exit: 0 on success; 1 when the version cannot be read, the build fails or the overlay is missing; 2 on bad arguments.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cli_pyproject="$root/packages/tl-cli/pyproject.toml"

sections=""
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --sections)
      [ $# -ge 2 ] || { echo "starter: --sections needs a value" >&2; exit 2; }
      sections="$2"; shift 2 ;;
    --sections=*) sections="${1#--sections=}"; shift ;;
    --out)
      [ $# -ge 2 ] || { echo "starter: --out needs a value" >&2; exit 2; }
      out="$2"; shift 2 ;;
    --out=*) out="${1#--out=}"; shift ;;
    *) echo "starter: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$cli_pyproject" ]; then
  echo "starter: no $cli_pyproject" >&2
  exit 1
fi
version="$(awk '/^\[/ { section = $0 } section == "[project]" && /^version *=/ { sub(/^version *= *"/, ""); sub(/".*$/, ""); print; exit }' "$cli_pyproject")"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "starter: no X.Y.Z version in [project] of $cli_pyproject (got '$version')" >&2
  exit 1
fi

# The try-it object secret. Public on purpose: the bundle is for a loopback try-out on one machine only.
try_it_secret="throughline-try-it-p200-not-a-secret"

if [ -z "$out" ]; then
  out="$root/dist/release-$version"
fi
mkdir -p "$out"
out="$(cd "$out" && pwd)"

work="$(mktemp -d "${TMPDIR:-/tmp}/tl-starter.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/ledger"

# 1. The ledger. The recipe sets TL_ENV=dev for the object store and builds the overlay schema directory.
build_args=("$work/ledger/p200.db" --objects "$work/ledger/files")
if [ -n "$sections" ]; then
  build_args+=(--sections "$sections")
fi
echo "starter: building P200 into a temporary ledger (sections: ${sections:-all})"
if ! (cd "$root" && TL_OBJECT_SECRET="$try_it_secret" just demo-project "${build_args[@]}"); then
  echo "starter: the demo-project build failed" >&2
  exit 1
fi
if [ ! -f "$work/ledger/p200.db" ]; then
  echo "starter: no ledger written to $work/ledger/p200.db" >&2
  exit 1
fi

# 2. The overlay schema directory, copied with its symlinks resolved so the bundle is self-contained.
overlay="$root/dev/data/demo-project-schema"
if [ ! -d "$overlay" ]; then
  echo "starter: no overlay schema directory at $overlay" >&2
  exit 1
fi
cp -RL "$overlay" "$work/schema"
if find "$work/schema" -type l | grep -q .; then
  echo "starter: the copied schema directory still holds symlinks" >&2
  exit 1
fi

# 3. START.txt: plain English, 25 lines at most.
cat > "$work/START.txt" <<EOF
Throughline starter bundle, version $version: the demo project P200 (North Refinery, Hydrotreater Unit 2).
This is a try-it copy on your own machine. It is not a deployment.

1. Install: in a Python 3.12 virtual environment, run
   pip install --find-links <the folder of this release's wheels> tl-cli tl-api tl-tui
2. Open a terminal in this folder and set the variables for this ledger:
   export TL_ENV=demo TL_DB=./ledger/p200.db TL_SCHEMA_DIR=./schema TL_OBJECT_ROOT=./ledger/files TL_OBJECT_SECRET=$try_it_secret
3. Start the API on this machine:   tl serve
4. In a second terminal, in this folder with the same variables:   tl-tui --remote http://127.0.0.1:8765
5. Sign in as the project administrator: user mokafor, password p200-demo-pass
   The other demo accounts (ipetrov, lhartmann, treyes, cbrooks, pnair, hsato, odoyle, gwhitfield)
   use the same password.

Warnings:
- The server listens on 127.0.0.1 only. Keep it that way.
- Never run this on a shared host, or on any host other people can reach.
- Never import this ledger into a real ledger. The password is demo data.
EOF
if [ "$(wc -l < "$work/START.txt")" -gt 25 ]; then
  echo "starter: START.txt is longer than 25 lines" >&2
  exit 1
fi

# 4. The archive: exactly ledger/p200.db, schema/ and START.txt. ledger/files and any -wal or -shm
#    sidecar of the ledger stay out.
name="starter-p200-$version.tar.gz"
tarball="$out/$name"
members=(ledger/p200.db schema START.txt)
if tar --version 2>/dev/null | grep -q GNU; then
  tar -C "$work" --sort=name --owner=0 --group=0 --numeric-owner --mtime="@${SOURCE_DATE_EPOCH:-0}" \
    -cf - "${members[@]}" | gzip -n > "$tarball"
else
  echo "starter: this tar has no --sort=name (not GNU tar); the archive is not byte-identical across runs" >&2
  tar -C "$work" -cf - "${members[@]}" | gzip -n > "$tarball"
fi

# 5. SHA256SUMS: replace any old line for this archive, keep the other lines (the wheels from build.sh).
if command -v sha256sum >/dev/null 2>&1; then
  sha_cmd=(sha256sum)
else
  sha_cmd=(shasum -a 256)
fi
line="$(cd "$out" && "${sha_cmd[@]}" -- "$name")"
sums="$out/SHA256SUMS"
tmp_sums="$work/SHA256SUMS"
if [ -f "$sums" ]; then
  awk -v n="$name" '$NF != n' "$sums" > "$tmp_sums"
else
  : > "$tmp_sums"
fi
printf '%s\n' "$line" >> "$tmp_sums"
mv "$tmp_sums" "$sums"

echo "starter: $tarball ($(wc -c < "$tarball") bytes)"
