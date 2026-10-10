#!/usr/bin/env bash
# Demo for P0-I7 (ledger archive, restore, DuckLake copy): the ledger is sealed into signed,
# hash-chained segments; a tampered copy of the archive is caught at the first divergence; the
# ledger is rebuilt from the archive alone into a fresh database; the lake is synced from that
# database and answers queries that state the ledger seq they reflect.
# Run with `just demo P0-I7` from the repository root. Uses a temporary directory; nothing is left
# behind. Fails (exit 1) when an expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
export TL_DB="$workdir/tl.db"
unset TL_SCHEMA_DIR TL_LAKE_DIR
archive="$workdir/archive"
key="$workdir/archive.key"
pub="$workdir/archive.pub"

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
expect() { # expect <text> <pattern>: fail the demo if the pattern is missing
  if ! grep -Eq -- "$2" <<<"$1"; then
    echo "DEMO FAILED: expected /$2/ in:" >&2
    echo "$1" >&2
    exit 1
  fi
}

step "a small ledger: three records, valve data, a link"
tl init
tl record create --project P123 --key A-1 --title "Gate valve" >/dev/null
tl record create --project P123 --key B-1 --title "Valve data sheet" >/dev/null
tl record create --project P123 --key C-1 --title "Check valve" >/dev/null
tl pset set --project P123 A-1 valve_data size_in=4 manufacturer=Acme >/dev/null
tl link add --project P123 A-1 B-1 >/dev/null
tl pset set --project P123 C-1 valve_data size_in=6 manufacturer=Beta >/dev/null
tl events tail --project P123 -n 3

step "tl archive keygen ; tl archive seal   (signed, hash-chained segments, apart from the database)"
tl archive keygen --key "$key"
out="$(tl archive seal --archive "$archive" --key "$key" --max-events 4)"
echo "$out"
expect "$out" '^sealed 2 segments; archive is at seq [0-9]+$'
last_seq="$(sed -E -n 's/^sealed [0-9]+ segments; archive is at seq ([0-9]+)$/\1/p' <<<"$out")"

step "tl archive verify   (signatures, manifest chain, every event hash, every scope chain)"
out="$(tl archive verify --archive "$archive" --public-key "$pub")"
echo "$out"
expect "$out" "^verified 2 segments, seq 1\\.\\.$last_seq "

step "tamper with a COPY of the archive: change one byte of a payload in the second segment"
cp -R "$archive" "$workdir/tampered"
quiet uv run python - "$workdir/tampered" <<'PY'
import pathlib, sys

second = sorted(pathlib.Path(sys.argv[1], "segments").iterdir())[1]
path = second / "events.ndjson"
data = path.read_bytes()
assert b"Acme" in data or b"Beta" in data or b"valve" in data.lower()
path.chmod(0o644)
path.write_bytes(data.replace(b"valve", b"VALVE", 1) if b"valve" in data else data.replace(b"Acme", b"Acne", 1))
print("changed", path.parent.name + "/" + path.name)
PY
if tl archive verify --archive "$workdir/tampered" --public-key "$pub" >"$workdir/verify.out" 2>&1; then
  echo "DEMO FAILED: the tampered archive verified" >&2
  exit 1
fi
cat "$workdir/verify.out"
expect "$(cat "$workdir/verify.out")" 'divergence'
echo "(the untouched archive still verifies)"
tl archive verify --archive "$archive" --public-key "$pub" | head -1

step "tl restore --from-archive   (a fresh database from the archive alone)"
out="$(tl restore --from-archive "$archive" --db "$workdir/restored.db" --public-key "$pub")"
echo "$out"
expect "$out" "$last_seq"
quiet uv run python - "$TL_DB" "$workdir/restored.db" <<'PY'
import sqlite3, sys

cols = "seq, event_id, stream_id, event_type, payload, recorded_at, hash"
a = sqlite3.connect(sys.argv[1]).execute(f"SELECT {cols} FROM events ORDER BY seq").fetchall()
b = sqlite3.connect(sys.argv[2]).execute(f"SELECT {cols} FROM events ORDER BY seq").fetchall()
assert a == b, "restored events differ from the originals"
keys = "SELECT key, title, status FROM cur_core_record ORDER BY key"
assert sqlite3.connect(sys.argv[1]).execute(keys).fetchall() == sqlite3.connect(sys.argv[2]).execute(keys).fetchall()
print(f"restored {len(b)} events identical to the originals; current state equal")
PY

step "the lake section: sync the RESTORED database into DuckLake and query it (dev/demos/P0-I7-lake.sh)"
export TL_DB="$workdir/restored.db"
export TL_LAKE_DIR="$workdir/lake"
bash dev/demos/P0-I7-lake.sh

step "the lake reflects exactly the restored ledger: as of seq $last_seq"
out="$(tl lake query "SELECT max(last_seq) AS as_of_seq FROM _tl_sync")"
echo "$out"
expect "$out" "^$last_seq\$"
expect "$out" "^as of seq $last_seq "

echo
echo "P0-I7 demo ok"
