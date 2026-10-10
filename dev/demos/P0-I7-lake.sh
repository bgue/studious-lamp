#!/usr/bin/env bash
# Lake section of the P0-I7 demo (DuckLake copy of the ledger; brief 28): an incremental sync by
# seq, the demo queries over bronze and silver, time travel to an earlier snapshot, and the
# lake_query guard refusing writes and file reads. Every result ends with "as of seq N".
#
#   just demo P0-I7-lake        standalone: builds a small temporary ledger and lake
#   TL_DB=... TL_LAKE_DIR=... bash dev/demos/P0-I7-lake.sh
#                               included by the P0-I7 demo: uses the ledger it was given (for
#                               example the one just restored from the archive), skips seeding and
#                               the checks that depend on the seeded rows
#
# Nothing is left behind in standalone mode. Fails (exit 1) when an expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
seeded=0
if [ -z "${TL_DB:-}" ]; then
  seeded=1
  export TL_DB="$workdir/tl.db"
fi
export TL_LAKE_DIR="${TL_LAKE_DIR:-$workdir/lake}"
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
refuse() { # refuse <description> <sql>: lake_query must refuse it; the reason is printed
  local what="$1" sql="$2"
  if tl lake query -- "$sql" >"$workdir/refused.out" 2>"$workdir/refused.err"; then
    echo "DEMO FAILED: $what was accepted" >&2
    exit 1
  fi
  expect "$(cat "$workdir/refused.err")" '^error: refused: '
  printf '%s -> ' "$what"
  cat "$workdir/refused.err"
}

if [ "$seeded" = 1 ]; then
  step "a small ledger: two records, valve data on one, and a link between them"
  tl init
  tl record create --project P123 --key A-1 --title "Gate valve" >/dev/null
  tl record create --project P123 --key B-1 --title "Valve data sheet" >/dev/null
  tl pset set --project P123 A-1 valve_data size_in=4 manufacturer=Acme >/dev/null
  tl link add --project P123 A-1 B-1 >/dev/null
fi

step "tl lake status   (before the first sync)"
before="$(tl lake status)"
echo "$before"

step "tl lake sync   (one DuckLake snapshot; bronze events + silver records, links, pset values)"
out="$(tl lake sync)"
echo "$out"
expect "$out" '^synced seq 1\.\.[0-9]+ \([0-9]+ events\) in snapshot [0-9]+$'
first_snapshot="$(sed -E -n '1s/.* in snapshot ([0-9]+)$/\1/p' <<<"$out")"

step "tl lake status   (the as-of seq is the ledger seq the lake reflects)"
out="$(tl lake status)"
echo "$out"
expect "$out" '^as of seq [0-9]+ \(snapshot '"$first_snapshot"','
expect "$out" '^syncs 1$'

step "tl lake tables"
out="$(tl lake tables)"
head -n 12 <<<"$out"
echo "..."

for file in events_by_type records_overview links_by_relation valve_sizes pset_coverage as_of; do
  step "dev/lake/queries/$file.sql"
  sql="$(cat "dev/lake/queries/$file.sql")"
  out="$(tl lake query --limit 20 -- "$sql")"
  echo "$out"
  expect "$out" '^as of seq [0-9]+ \(snapshot [0-9]+\)$'
done

if [ "$seeded" = 1 ]; then
  step "more work in the ledger, then an incremental sync (only the changed record is replaced)"
  tl record create --project P123 --key C-1 --title "Check valve" >/dev/null
  tl pset set --project P123 C-1 valve_data size_in=6 manufacturer=Beta >/dev/null
  out="$(tl lake sync)"
  echo "$out"
  expect "$out" '^synced seq [0-9]+\.\.[0-9]+ \([0-9]+ events\) in snapshot [0-9]+$'
  expect "$out" 'silver rows: cur_core_record 1, links 0, pset_values 2$'

  step "time travel: the records now, and as of the first snapshot"
  now="$(tl lake query "SELECT count(*) AS records FROM cur_core_record")"
  echo "$now"
  expect "$now" '^3$'
  then="$(tl lake query "SELECT count(*) AS records FROM cur_core_record AT (VERSION => $first_snapshot)")"
  echo "$then"
  expect "$then" '^2$'
fi

step "a second sync with nothing new makes no snapshot"
out="$(tl lake sync)"
echo "$out"
expect "$out" '^lake is up to date as of seq [0-9]+$'

step "lake_query refuses everything but one SELECT over lake tables"
refuse "DROP TABLE" "DROP TABLE events"
refuse "stacked statements" "SELECT 1; DROP TABLE events"
refuse "INSERT" "INSERT INTO events SELECT * FROM events"
refuse "ATTACH" "ATTACH ':memory:' AS other"
refuse "COPY" "COPY events TO '/tmp/leak.csv'"
refuse "PRAGMA" "PRAGMA database_list"
refuse "read_csv on an arbitrary path" "SELECT * FROM read_csv('/etc/passwd')"
refuse "read_text on an arbitrary path" "SELECT * FROM read_text('/etc/hostname')"
refuse "a file as a table" "SELECT * FROM '/etc/passwd.csv'"
out="$(tl lake query "SELECT count(*) AS events FROM events")"
expect "$out" '^as of seq [0-9]+ '
echo "the lake is unchanged: $(sed -n 2p <<<"$out")"

step "every lake_query call is logged (last 3 lines of lake_query.log.jsonl)"
log_tail="$(tail -n 3 "$TL_LAKE_DIR/lake_query.log.jsonl")"
cut -c1-200 <<<"$log_tail"
refused_lines="$(grep -c '"outcome": "refused"' "$TL_LAKE_DIR/lake_query.log.jsonl")"
[ "$refused_lines" -ge 9 ] || { echo "DEMO FAILED: expected 9 refused calls in the log" >&2; exit 1; }

if [ "$seeded" = 1 ]; then
  step "tl lake rebuild --yes   (the lake is rebuildable: same rows from one load)"
  out="$(tl lake rebuild --yes)"
  echo "$out"
  expect "$out" '^synced seq 1\.\.'
  expect "$(tl lake status)" '^syncs 1$'
  expect "$(tl lake query "SELECT count(*) AS records FROM cur_core_record")" '^3$'
fi

echo
echo "P0-I7 lake demo ok"
