#!/usr/bin/env bash
# Restore drill (brief 24.3, 24.4): back up a ledger several ways, lose it, restore it each way,
# verify every restore, and write a report with the measured RPO and RTO.
#
#   dev/drills/restore.sh [--records N] [--tail N] [--report PATH] [--skip-pgbackrest]
#                         [--skip-litestream] [--skip-postgres]
#
# Everything happens under dev/data/drills/<timestamp>/ (git-ignored) and in scratch Postgres
# databases or a scratch cluster that the drill creates and drops. The shared test database
# `tl_test` is never touched. Exit status 0 when every exercised path passed.
set -uo pipefail
cd "$(dirname "$0")/../.."

RECORDS=120
TAIL=15
REPORT=""
SKIP_PGBACKREST=0
SKIP_LITESTREAM=0
SKIP_POSTGRES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --records) RECORDS=$2; shift 2 ;;
    --tail) TAIL=$2; shift 2 ;;
    --report) REPORT=$2; shift 2 ;;
    --skip-pgbackrest) SKIP_PGBACKREST=1; shift ;;
    --skip-litestream) SKIP_LITESTREAM=1; shift ;;
    --skip-postgres) SKIP_POSTGRES=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done

export TL_ENV=dev
export TL_SCHEMA_DIR=${TL_SCHEMA_DIR:-schema/fixtures}
STAMP=$(date +%Y%m%dT%H%M%S)
WORK=$(mkdir -p "dev/data/drills/$STAMP" && cd "dev/data/drills/$STAMP" && pwd)
MEAS=$WORK/measurements.tsv
FINDINGS=$WORK/findings.txt
: >"$MEAS"
: >"$FINDINGS"
TOOLS="uv run python dev/drills/drill_tools.py"
TL="uv run tl"
ARCHIVE=$WORK/archive
KEY=$WORK/keys/archive-signing.key
PUB=${KEY%.key}.pub
SOURCE=$WORK/source.db
LS_PID=""
# Only the server matters: the drill connects to the maintenance database `postgres` to create and
# drop its own scratch database, and never opens `tl_test`.
PG_SERVER_URL=${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}
PG_URL=$(uv run python -c "import sys; from tl_adapters.postgres import admin; print(admin.database_url(sys.argv[1], 'postgres'))" "$PG_SERVER_URL" 2>/dev/null)
PG_SCRATCH_NAME=$(tr 'A-Z' 'a-z' <<<"tl_drill_${STAMP}_$$" | tr -c 'a-z0-9_\n' '_')
FAILED=0

say() { echo "[drill] $*" >&2; }
m() { printf '%s\t%s\n' "$1" "$2" >>"$MEAS"; }
finding() { echo "- $*" >>"$FINDINGS"; }
now() { date +%s.%N; }
since() { awk -v a="$1" -v b="$(now)" 'BEGIN { printf "%.2f", b - a }'; }
sub() { awk -v a="$1" -v b="$2" 'BEGIN { printf "%.2f", a - b }'; }
word() { tr ' ' '\n' <<<"$1" | sed -n "s/^$2=//p" | head -1; }

cleanup() {
  [ -n "$LS_PID" ] && kill -9 "$LS_PID" 2>/dev/null
  if [ -n "$PG_SCRATCH_NAME" ]; then
    uv run python - "$PG_URL" "$PG_SCRATCH_NAME" >/dev/null 2>&1 <<'PY'
import sys
from tl_adapters.postgres import admin
admin.drop_database(sys.argv[1], sys.argv[2])
PY
  fi
}
trap cleanup EXIT

# met <rpo limit s> <rpo s> <rto s> -> yes / no
met() { awk -v l="$1" -v r="$2" -v t="$3" 'BEGIN { print (r <= l && t <= 3600) ? "yes" : "no" }'; }

# Checks every restored database gets: hashes recomputed, and every field equal to the archive.
verify_restored() { # <name> <db>
  $TL ledger verify --db "$2" >/dev/null || { finding "$1: tl ledger verify failed"; return 1; }
  $TL archive verify --archive "$ARCHIVE" --public-key "$PUB" --db "$2" --deep >/dev/null \
    || { finding "$1: tl archive verify --deep failed"; return 1; }
}

record_rpo() { # <name> <recovered head> <rpo limit seconds> <rto seconds>
  local name=$1 recovered=$2 limit=$3 rto=$4 at gap
  at=$(word "$($TOOLS head --db "$SOURCE_REF" --seq "$recovered" 2>/dev/null)" at)
  gap=$(word "$($TOOLS gap --from "$at" --to "$AT_LOSS" 2>/dev/null)" gap)
  m "${name}_rpo_events" "$((HEAD_LOSS - recovered))"
  m "${name}_rpo_seconds" "$gap"
  m "${name}_rto_seconds" "$rto"
  m "${name}_met" "$(met "$limit" "$gap" "$rto")"
}

# --- prepare -------------------------------------------------------------------------------------
say "work directory $WORK"
T0=$(now)
$TL archive keygen --key "$KEY" >/dev/null || exit 1
HEAD0=$(word "$($TOOLS populate --db "$SOURCE" --records "$RECORDS" 2>/dev/null)" head)
DIGEST0=$($TOOLS digest --db "$SOURCE" 2>/dev/null)
SEAL_OUT=$($TL --db "$SOURCE" archive seal --archive "$ARCHIVE" --key "$KEY" --max-events 60) || exit 1
ARCHIVE_LAST_SEQ=$(sed -n 's/.*last_seq \([0-9]*\) manifest_sha256.*/\1/p' <<<"$SEAL_OUT")
MANIFEST_SHA=$(sed -n 's/.*manifest_sha256 \([0-9a-f]*\)$/\1/p' <<<"$SEAL_OUT")
SEGMENTS=$(find "$ARCHIVE/segments" -mindepth 1 -maxdepth 1 -type d | wc -l)
$TL --db "$SOURCE" backup sqlite --to "$WORK/snapshot.db" >/dev/null || exit 1
SNAPSHOT_HEAD=$(word "$($TOOLS head --db "$WORK/snapshot.db" 2>/dev/null)" head)

LITESTREAM_READY=0
if [ "$SKIP_LITESTREAM" = 0 ]; then
  if bash dev/drills/fetch_litestream.sh 2>"$WORK/fetch-litestream.log"; then
    export TL_DB=$SOURCE LITESTREAM_REPLICA=$WORK/litestream
    dev/data/tools/litestream replicate -config dev/backup/litestream.yml >"$WORK/litestream.log" 2>&1 &
    LS_PID=$!
    sleep 3
    LITESTREAM_READY=1
  else
    finding "Litestream was skipped: the pinned release could not be fetched ($(tail -1 "$WORK/fetch-litestream.log")). The snapshot path covers the SQLite database layer."
  fi
fi
m t_prepare "$(since "$T0")"

# --- writes after the backups, then the loss ---------------------------------------------------------
$TOOLS append --db "$SOURCE" --count "$TAIL" --prefix L >/dev/null 2>&1
LOSS=$($TOOLS head --db "$SOURCE" 2>/dev/null)
HEAD_LOSS=$(word "$LOSS" head)
AT_LOSS=$(word "$LOSS" at)
[ -n "$LS_PID" ] && { kill -9 "$LS_PID" 2>/dev/null; wait "$LS_PID" 2>/dev/null; LS_PID=""; }
# The loss: the live ledger is gone. Its files are only moved aside so that recorded times of lost
# events can be looked up for the RPO.
for suffix in "" -wal -shm; do [ -e "$SOURCE$suffix" ] && mv "$SOURCE$suffix" "$WORK/source-lost.db$suffix"; done
SOURCE_REF=$WORK/source-lost.db
m head_at_backup "$HEAD0"
m tail_events "$TAIL"
m head_at_loss "$HEAD_LOSS"
m at_loss "$AT_LOSS"
m archive_segments "$SEGMENTS"
m archive_last_seq "$ARCHIVE_LAST_SEQ"
m schema_dir "$TL_SCHEMA_DIR"

run_path() { # <label> <function>
  local label=$1 fn=$2 t
  t=$(now)
  if ( set -e; "$fn" ); then
    m "${label}_status" pass
  else
    m "${label}_status" FAIL
    FAILED=1
    finding "$label failed; see the output above."
  fi
  m "t_${label}" "$(since "$t")"
}

# --- the archive, into SQLite ----------------------------------------------------------------------
archive_sqlite() {
  local target=$WORK/restored-archive.db t d rto
  t=$(now)
  $TL restore --from-archive "$ARCHIVE" --db "$target" --public-key "$PUB" >&2
  verify_restored archive_sqlite "$target"
  d=$(now)
  [ "$($TOOLS digest --db "$target" 2>/dev/null)" = "$DIGEST0" ] || { finding "archive_sqlite: restored tables differ from the original"; return 1; }
  d=$(since "$d")
  $TOOLS probe --db "$target" >/dev/null 2>&1
  rto=$(sub "$(since "$t")" "$d")
  record_rpo archive_sqlite "$ARCHIVE_LAST_SEQ" 900 "$rto"
}
run_path archive_sqlite archive_sqlite

# --- the archive, into a scratch Postgres database --------------------------------------------------
archive_postgres() {
  local PG_SCRATCH=$PG_SCRATCH_NAME
  uv run python - "$PG_URL" "$PG_SCRATCH" >&2 <<'PY'
import sys
from tl_adapters.postgres import admin
admin.create_database(sys.argv[1], sys.argv[2])
print("created scratch database", sys.argv[2], file=sys.stderr)
PY
  local url t d rto
  url=$(uv run python -c "import sys; from tl_adapters.postgres import admin; print(admin.database_url(sys.argv[1], sys.argv[2]))" "$PG_SERVER_URL" "$PG_SCRATCH" 2>/dev/null)
  t=$(now)
  $TL restore --from-archive "$ARCHIVE" --db "$url" --public-key "$PUB" >&2
  verify_restored archive_postgres "$url"
  d=$(now)
  [ "$($TOOLS digest --db "$url" 2>/dev/null)" = "$DIGEST0" ] || { finding "archive_postgres: restored tables differ from the SQLite original"; return 1; }
  d=$(since "$d")
  $TOOLS probe --db "$url" >/dev/null 2>&1
  rto=$(sub "$(since "$t")" "$d")
  record_rpo archive_postgres "$ARCHIVE_LAST_SEQ" 900 "$rto"
  m pg_scratch_database "$PG_SCRATCH"
}
if [ "$SKIP_POSTGRES" = 0 ] && uv run python -c "import sys; from tl_adapters.postgres import admin; sys.exit(0 if admin.reachable(sys.argv[1]) else 1)" "$PG_URL" 2>/dev/null; then
  run_path archive_postgres archive_postgres
else
  m archive_postgres_status skipped
  m pg_scratch_database "(none)"
  finding "The Postgres archive restore was skipped: Postgres is not reachable at TL_PG_URL, or --skip-postgres was given."
fi

# --- the SQLite online snapshot ----------------------------------------------------------------------
snapshot() {
  local target=$WORK/restored-snapshot.db t d rto
  t=$(now)
  cp "$WORK/snapshot.db" "$target"; chmod 644 "$target"
  verify_restored snapshot "$target"
  d=$(now)
  [ "$($TOOLS digest --db "$target" 2>/dev/null)" = "$DIGEST0" ] || { finding "snapshot: restored tables differ from the original"; return 1; }
  d=$(since "$d")
  $TOOLS probe --db "$target" >/dev/null 2>&1
  rto=$(sub "$(since "$t")" "$d")
  record_rpo snapshot "$SNAPSHOT_HEAD" 300 "$rto"
}
run_path snapshot snapshot

# --- Litestream ------------------------------------------------------------------------------------------
litestream() {
  local target=$WORK/restored-litestream.db t rto head
  t=$(now)
  TL_DB=$SOURCE LITESTREAM_REPLICA=$WORK/litestream dev/data/tools/litestream restore \
    -config dev/backup/litestream.yml -o "$target" "$SOURCE" >"$WORK/litestream-restore.log" 2>&1
  verify_restored litestream "$target"
  head=$(word "$($TOOLS head --db "$target" 2>/dev/null)" head)
  $TOOLS probe --db "$target" >/dev/null 2>&1
  rto=$(since "$t")
  record_rpo litestream "$head" 300 "$rto"
}
if [ "$LITESTREAM_READY" = 1 ]; then
  run_path litestream litestream
else
  m litestream_status skipped
fi

# --- pgBackRest -------------------------------------------------------------------------------------------
if [ "$SKIP_PGBACKREST" = 0 ] && command -v pgbackrest >/dev/null && sudo -n true 2>/dev/null; then
  T=$(now)
  if bash dev/drills/pgbackrest.sh --records "$RECORDS" --tail "$TAIL" --work "$WORK/pgbackrest" >"$WORK/pgbackrest.tsv" 2>"$WORK/pgbackrest.log"; then
    cat "$WORK/pgbackrest.tsv" >>"$MEAS"
    GAP=$(word "$($TOOLS gap --from "$(awk -F'\t' '$1=="pgbackrest_recovered_at"{print $2}' "$WORK/pgbackrest.tsv")" --to "$(awk -F'\t' '$1=="pgbackrest_loss_at"{print $2}' "$WORK/pgbackrest.tsv")" 2>/dev/null)" gap)
    RTO=$(awk -F'\t' '$1=="pgbackrest_rto_seconds"{print $2}' "$WORK/pgbackrest.tsv")
    m pgbackrest_rpo_seconds "$GAP"
    m pgbackrest_met "$(met 300 "$GAP" "$RTO")"
  else
    m pgbackrest_status FAIL
    FAILED=1
    finding "pgBackRest failed; see $WORK/pgbackrest.log."
  fi
  m t_pgbackrest "$(since "$T")"
else
  m pgbackrest_status skipped
  finding "pgBackRest was skipped (--skip-pgbackrest, pgbackrest not installed, or no passwordless sudo)."
fi

# --- a tampered copy of the archive is refused -------------------------------------------------------------
TAMPER=$WORK/archive-tampered
cp -r "$ARCHIVE" "$TAMPER"
FIRST_NDJSON=$(find "$TAMPER/segments" -name events.ndjson | sort | sed -n 2p)
[ -n "$FIRST_NDJSON" ] || FIRST_NDJSON=$(find "$TAMPER/segments" -name events.ndjson | sort | head -1)
chmod 644 "$FIRST_NDJSON"
sed -i '0,/"actor":"user:drill"/s//"actor":"user:evil"/' "$FIRST_NDJSON"
TAMPER_OUT=$($TL archive verify --archive "$TAMPER" --public-key "$PUB" 2>/dev/null)
if [ $? -ne 0 ] && grep -q '^divergence: file_hash' <<<"$TAMPER_OUT"; then
  m check_tamper "pass: $(head -1 <<<"$TAMPER_OUT")"
else
  m check_tamper FAIL
  FAILED=1
  finding "The tampered archive was not refused as expected: $TAMPER_OUT"
fi

# --- the archive itself, with the recorded last seq and manifest ---------------------------------------------
if $TL archive verify --archive "$ARCHIVE" --public-key "$PUB" --expect-last-seq "$ARCHIVE_LAST_SEQ" --expect-manifest "$MANIFEST_SHA" >/dev/null; then
  m check_archive_verify "pass (seq 1..$ARCHIVE_LAST_SEQ, recorded last seq and manifest present)"
else
  m check_archive_verify FAIL; FAILED=1
fi

# --- report ------------------------------------------------------------------------------------------------------
all_pass() { # every exercised path passed its checks
  local status
  for p in archive_sqlite archive_postgres snapshot litestream pgbackrest; do
    status=$(awk -F'\t' -v k="${p}_status" '$1==k{print $2}' "$MEAS")
    [ "$status" = FAIL ] && return 1
  done
  return 0
}
status_of() { awk -F'\t' -v k="$1" '$1==k{print $2}' "$MEAS"; }
if all_pass && [ "$FAILED" = 0 ]; then
  m status passed
  m check_deep_verify "pass on every restored database"
  m check_ledger_verify "pass on every restored database"
  m check_digest "pass (archive and snapshot paths)"
  m check_probe "pass"
else
  m status FAILED
  m check_deep_verify "see findings"; m check_ledger_verify "see findings"; m check_digest "see findings"; m check_probe "see findings"
fi
m digest_original "$DIGEST0"
m environment "${TL_DRILL_ENV:-dev container}"
m date "$(date +%Y-%m-%d)"
m commit "$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
m operator "${TL_DRILL_OPERATOR:-$(id -un)}"
[ -s "$FINDINGS" ] || finding "none"
m findings "$(cat "$FINDINGS")"
$TOOLS render --measurements "$MEAS" --template docs/templates/restore-drill.md --out "$WORK/report.md" >&2
[ -n "$REPORT" ] && { mkdir -p "$(dirname "$REPORT")"; cp "$WORK/report.md" "$REPORT"; say "report copied to $REPORT"; }
say "report: $WORK/report.md"
[ "$FAILED" = 0 ]
