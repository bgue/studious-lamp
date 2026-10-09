#!/usr/bin/env bash
# Demo for P0-I2 (layered psets, effective schema, TUI shell): the schema hash, pset writes with
# conformance, and the TUI client against the real services.
# Run with `just demo P0-I2` from the repository root. Uses a temporary ledger and a temporary copy
# of the fixture packages; nothing is left behind. Fails (exit 1) when an expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
export TL_DB="$workdir/tl.db"
unset TL_SCHEMA_DIR

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

step "packages: co.acme.engineering@3.2.0, x.P123@1.4.0, prj.P123@1.0.0 in schema/fixtures"
ls schema/fixtures

step "tl schema hash P123   (stable content hash of the effective schema)"
hash1="$(tl schema hash P123)"
hash2="$(tl schema hash P123)"
echo "$hash1"
expect "$hash1" '^[0-9a-f]{64}$'
[ "$hash1" = "$hash2" ] || { echo "DEMO FAILED: hash is not stable" >&2; exit 1; }

step "changing a fixture package changes the hash (copy with size_in.maximum widened 144 -> 200)"
cp -r schema/fixtures "$workdir/fixtures"
sed -i 's/^        maximum: 144$/        maximum: 200/' "$workdir/fixtures/"co.acme.engineering@3.2.0.yaml
grep -q 'maximum: 200' "$workdir/fixtures/"co.acme.engineering@3.2.0.yaml
hash3="$(TL_SCHEMA_DIR="$workdir/fixtures" tl schema hash P123)"
echo "$hash3"
[ "$hash1" != "$hash3" ] || { echo "DEMO FAILED: an edited package kept the same hash" >&2; exit 1; }

step "tl schema lint / validate"
tl schema lint
validate="$(tl schema validate)"
echo "$validate"
expect "$validate" '^ok project:P123 '

step "tl init ; tl record create --project P123 --key V-0001 --title \"Valve 1\""
tl init
tl record create --project P123 --key V-0001 --title "Valve 1" >/dev/null

step "set valve_data.size_in only: a missing advisory property is a warning"
out="$(tl pset set --project P123 V-0001 valve_data size_in=4)"
echo "$out"
expect "$out" '^conformance warning$'

step "fill the advisory property: conformance ok"
out="$(tl pset set --project P123 V-0001 valve_data manufacturer=Acme)"
echo "$out"
expect "$out" '^conformance ok$'

step "set the project custom section: valve_data.x.fat_witness_by"
out="$(tl pset set --project P123 V-0001 valve_data --layer custom x.fat_witness_by=client)"
echo "$out"
expect "$out" '^version 4$'

step "tl pset get   (values, and the schema hash they were validated against)"
got="$(tl pset get --project P123 V-0001)"
echo "$got"
expect "$got" "^effective_schema_hash: $hash1\$"
expect "$got" '"size_in":4'
expect "$got" '"x":\{"fat_witness_by":"client"\}'

step "a property the effective schema does not define is refused (exit 1)"
if tl pset set --project P123 V-0001 valve_data nonsense=1; then
  echo "DEMO FAILED: an undefined property was accepted" >&2
  exit 1
fi

step "unset a property with NAME=null: the advisory warning returns"
out="$(tl pset set --project P123 V-0001 valve_data manufacturer=null)"
echo "$out"
expect "$out" '^conformance warning$'

step "every Pset.ValuesSet event carries the effective schema hash"
quiet uv run python - "$TL_DB" "$hash1" <<'PY'
import json, sqlite3, sys

db, expected = sys.argv[1], sys.argv[2]
rows = sqlite3.connect(db).execute(
    "SELECT payload FROM events WHERE event_type = 'Pset.ValuesSet' ORDER BY seq"
).fetchall()
hashes = {json.loads(payload)["effective_schema_hash"] for (payload,) in rows}
print(f"{len(rows)} Pset.ValuesSet events, hashes: {sorted(h[:12] for h in hashes)}")
assert len(rows) == 4, rows
assert hashes == {expected}, hashes
PY

step "the TUI client over the same real services (EmbeddedClient, form metadata, conformance, save)"
tui="$(quiet uv run pytest packages/tl-tui/tests/test_embedded_real_services.py -q 2>&1 | tail -1)" || true
echo "$tui"
expect "$tui" '^5 passed'

step "TUI snapshots: shell, grid, record view, psets tab, forms, narrow mode (120x40 and 80x24)"
snaps="$(quiet uv run pytest packages/tl-tui/tests/test_snapshots.py -q 2>&1 | tail -1)" || true
echo "$snaps"
expect "$snaps" '^15 passed'

printf '\nP0-I2 demo ok\n'
