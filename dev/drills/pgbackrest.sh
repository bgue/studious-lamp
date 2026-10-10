#!/usr/bin/env bash
# Postgres backup drill with pgBackRest, against a scratch cluster this script creates and drops
# (fanout decision D5). The shared cluster on port 5432 and its tl_test database are never touched.
#
#   dev/drills/pgbackrest.sh [--records N] [--tail N] [--work DIR]
#
# Steps: create cluster 16/drill on port 5440 with WAL archiving into a pgBackRest repository,
# populate a ledger, seal a ledger archive from it, take a full backup, write more events (one batch
# switched into the archive, one not), destroy the data directory, restore with pgBackRest, then
# verify the restored database against the ledger archive and measure RPO and RTO.
#
# Output: key<TAB>value lines on stdout (prefix pgbackrest_), human progress on stderr. Needs sudo,
# the apt package pgbackrest (MIT) and the postgres 16 server packages.
set -euo pipefail
cd "$(dirname "$0")/../.."

RECORDS=60
TAIL=10
WORK=""
while [ $# -gt 0 ]; do
  case "$1" in
    --records) RECORDS=$2; shift 2 ;;
    --tail) TAIL=$2; shift 2 ;;
    --work) WORK=$2; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[ -n "$WORK" ] || WORK="dev/data/drills/pgbackrest-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$WORK"
WORK=$(cd "$WORK" && pwd)

VER=16
CLUSTER=drill
PORT=5440
PGDATA=/var/lib/postgresql/$VER/$CLUSTER
ROOT=/var/lib/postgresql/tl-drill
CONF=$ROOT/pgbackrest.conf
URL="postgresql://postgres:drill@localhost:$PORT/tl_drill"
TOOLS="uv run python dev/drills/drill_tools.py"
TL="uv run tl"
ARCHIVE=$WORK/pg-archive
KEY=$WORK/keys/archive-signing.key
export TL_SCHEMA_DIR=${TL_SCHEMA_DIR:-schema/fixtures}
export TL_ENV=dev

say() { echo "[pgbackrest drill] $*" >&2; }
out() { printf '%s\t%s\n' "$1" "$2"; }
now() { date +%s.%N; }
since() { awk -v a="$1" -v b="$(now)" 'BEGIN { printf "%.2f", b - a }'; }
word() { tr ' ' '\n' <<<"$1" | sed -n "s/^$2=//p" | head -1; }
as_pg() { (cd /tmp && sudo -u postgres "$@"); }
pgbr() { as_pg pgbackrest --config="$CONF" --stanza=$CLUSTER "$@"; }
psql_drill() { as_pg psql -X -q -p $PORT -d "${DB:-postgres}" -At -c "$1"; }

cleanup() {
  set +e
  sudo pg_ctlcluster $VER $CLUSTER stop -m immediate >/dev/null 2>&1
  sudo pg_dropcluster $VER $CLUSTER --stop >/dev/null 2>&1
  sudo rm -rf "$ROOT"
}
trap cleanup EXIT

command -v pgbackrest >/dev/null || { say "pgbackrest is not installed: sudo apt-get install -y pgbackrest"; exit 3; }
if pg_lsclusters -h | awk '{print $2}' | grep -qx $CLUSTER; then
  say "removing a leftover scratch cluster $VER/$CLUSTER from an earlier run"
  sudo pg_dropcluster $VER $CLUSTER --stop || true
fi
sudo rm -rf "$ROOT"
sudo install -d -o postgres -g postgres -m 0750 "$ROOT" "$ROOT/repo" "$ROOT/log" "$ROOT/lock" "$ROOT/spool"

say "creating scratch cluster $VER/$CLUSTER on port $PORT"
sudo pg_createcluster $VER $CLUSTER --port $PORT >&2
sed -e "s|@ROOT@|$ROOT|g" -e "s|@PGDATA@|$PGDATA|g" -e "s|@PORT@|$PORT|g" dev/backup/pgbackrest.conf.tmpl \
  | sudo -u postgres tee "$CONF" >/dev/null
sudo pg_conftool $VER $CLUSTER set archive_mode on
sudo pg_conftool $VER $CLUSTER set archive_timeout 15s
sudo pg_conftool $VER $CLUSTER set archive_command "pgbackrest --config=$CONF --stanza=$CLUSTER archive-push %p"
sudo pg_ctlcluster $VER $CLUSTER start
for _ in $(seq 1 30); do pg_isready -q -h localhost -p $PORT && break; sleep 1; done
DB=postgres psql_drill "ALTER USER postgres PASSWORD 'drill'" >/dev/null
DB=postgres psql_drill "CREATE DATABASE tl_drill" >/dev/null

say "populating $RECORDS records and sealing a ledger archive from the cluster"
HEAD0=$(word "$($TOOLS populate --db "$URL" --records "$RECORDS" 2>/dev/null)" head)
$TL archive keygen --key "$KEY" >/dev/null
$TL archive seal --db "$URL" --archive "$ARCHIVE" --key "$KEY" >/dev/null
DIGEST0=$($TOOLS digest --db "$URL" 2>/dev/null)

say "stanza-create, check, full backup"
pgbr stanza-create >&2
pgbr check >&2
T=$(now)
pgbr backup --type=full >&2
out pgbackrest_backup_seconds "$(since "$T")"

say "writing $TAIL events, switching the WAL segment into the archive, then $TAIL more that are not switched"
sleep 2
ARCHIVED_BEFORE=$(DB=postgres psql_drill "SELECT coalesce(last_archived_wal, '') FROM pg_stat_archiver")
$TOOLS append --db "$URL" --count "$TAIL" --prefix A >/dev/null 2>&1
DB=tl_drill psql_drill "SELECT pg_switch_wal()" >/dev/null
for _ in $(seq 1 30); do
  ARCHIVED_NOW=$(DB=postgres psql_drill "SELECT coalesce(last_archived_wal, '') FROM pg_stat_archiver")
  [ "$ARCHIVED_NOW" != "$ARCHIVED_BEFORE" ] && break
  sleep 1
done
[ "$ARCHIVED_NOW" != "$ARCHIVED_BEFORE" ] || { say "the switched WAL segment was not archived within 30 s"; exit 1; }
$TOOLS append --db "$URL" --count "$TAIL" --prefix B >/dev/null 2>&1
LOSS=$($TOOLS head --db "$URL" 2>/dev/null)
HEADLOSS=$(word "$LOSS" head)
ATLOSS=$(word "$LOSS" at)

say "damage: immediate stop, then the data directory is erased"
sudo pg_ctlcluster $VER $CLUSTER stop -m immediate
sudo find "$PGDATA" -mindepth 1 -delete
LOSS_AT=$(now)

say "restore with pgBackRest"
T=$(now)
pgbr restore >&2
out pgbackrest_restore_seconds "$(since "$T")"
sudo pg_ctlcluster $VER $CLUSTER start
for _ in $(seq 1 120); do
  if pg_isready -q -h localhost -p $PORT && [ "$(DB=tl_drill psql_drill "SELECT pg_is_in_recovery()" 2>/dev/null || echo t)" = f ]; then break; fi
  sleep 1
done
$TL ledger verify --db "$URL" >&2
$TL archive verify --archive "$ARCHIVE" --public-key "${KEY%.key}.pub" --db "$URL" --deep >&2
$TOOLS probe --db "$URL" >/dev/null 2>&1
out pgbackrest_rto_seconds "$(since "$LOSS_AT")"

RECOVERED=$(word "$($TOOLS head --db "$URL" 2>/dev/null)" head)
RECOVERED=$((RECOVERED - 1))   # the probe event
RECOVERED_AT=$(word "$($TOOLS head --db "$URL" --seq "$RECOVERED" 2>/dev/null)" at)
out pgbackrest_head_before_loss "$HEADLOSS"
out pgbackrest_head_recovered "$RECOVERED"
out pgbackrest_rpo_events "$((HEADLOSS - RECOVERED))"
out pgbackrest_loss_at "$ATLOSS"
out pgbackrest_recovered_at "$RECOVERED_AT"
out pgbackrest_archive_timeout_seconds 15
out pgbackrest_archive_seq "$HEAD0"
out pgbackrest_status pass
say "done: recovered seq $RECOVERED of $HEADLOSS"
