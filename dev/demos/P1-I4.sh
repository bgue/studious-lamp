#!/usr/bin/env bash
# Demo for P1-I4 (M11 cost snapshots and P6 XER schedule snapshots): `just demo P1-I4`.
#
# The exit clauses, each ending in a PASS line, once on SQLite and once on Postgres:
#   1  a controller defines a schedule (a user cannot); two synthetic XER files a week apart are
#      uploaded by a user and built by the worker (admin); the same file twice is refused;
#   2  the comparison shows the date shifts, the float erosion (A1230: 9 days to 4), the activity
#      that came (A2500) and the one that went (A1990), the logic that changed and the activities
#      that became critical;
#   3  a record linked to A1230 resolves to the current snapshot and, as of the earlier one, to
#      snapshot 1 (by number and by date); publishing is the controller's; the link to the
#      removed A1990 is flagged by the worker (until then the schedule says its links are being
#      checked) and shows in the link health view;
#   4  the look-ahead lists what is under way and what starts in the next four weeks; the float
#      trend of A1230 follows it through both snapshots;
#   5  a file that is not a schedule gives an Invalid snapshot with a report and the worker goes on
#      to the next file;
#   6  two cost periods are previewed (a user may), applied (admin only), compared with the
#      budget (three codes forecast over it); the records with no cost code and no activity are listed;
#   7  the API, the TUI screens (F12, the comparison, the activities) and an agent's MCP read
#      tools agree on the schedule;
#   8  the lake holds the snapshots, the tables of the XER files and the float trend;
#   9  an agent proposes publishing snapshot 4: nothing is published until a controller accepts,
#      and a user cannot accept;
#  10  after a restore (the typed rows and the queue lost) the reads say so instead of answering
#      with nothing, and `tl xer reconcile` writes the rows again from the files: the comparison
#      is the same.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. Starts
# `tl serve` on a free loopback port over a temporary ledger; nothing is left behind.
# Exits non-zero (and prints DEMO FAILED) when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
pg_url=""
stop_server() { # the server has its own process group (setsid): stop the whole group
  [ -n "$server_pid" ] || return 0
  kill -TERM -- "-$server_pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    curl -fs "${TL_DEMO_URL:-http://127.0.0.1:1}/health" >/dev/null 2>&1 || break
    sleep 0.1
  done
  kill -KILL -- "-$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  server_pid=""
}
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'stop_server; drop_pg; rm -rf "$workdir"' EXIT

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_DEMO_STATE="$workdir/state"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i4_demo.py "$@" || fail "an exit clause was not met"; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}
refuse() { # refuse TEXT cmd...: the command must fail and say TEXT
  local text="$1" out; shift
  if out="$("$@" 2>&1)"; then echo "$out"; fail "this was accepted: $*"; fi
  echo "$out"; expect "$text" "$out"
}

P=(--project P123)
S=(--schedule MAIN)

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, the demo account, and the API on a free loopback port"
  stop_server
  case "$backend" in
    sqlite) export TL_DB="$workdir/$backend.db" ;;
    postgres)
      pg_url="$(quiet uv run python dev/demos/p1_i0_demo.py pg-create)" || fail "Postgres is not reachable at TL_PG_URL (try: just dev up)"
      export TL_DB="$pg_url"
      ;;
    *) fail "unknown backend $backend" ;;
  esac
  export TL_LAKE_DIR="$workdir/lake-$backend"
  local port
  port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  export TL_DEMO_URL="http://127.0.0.1:$port"
  export TL_TOKENS="$workdir/tokens-$backend.json"
  tl init --dev 2>"$workdir/init.err" >/dev/null || { cat "$workdir/init.err" >&2; fail "tl init --dev"; }
  setsid uv run tl serve --port "$port" >"$workdir/server-$backend.log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 150); do
    curl -fs "$TL_DEMO_URL/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  curl -fs "$TL_DEMO_URL/health" | grep -q '"status":"ok"' || {
    cat "$workdir/server-$backend.log" >&2
    fail "the server did not start"
  }
  echo "(serving $backend at $TL_DEMO_URL)"
  printf 'demo\n' | as demo tl login demo --password-stdin >/dev/null
  export TL_DEMO_AMY_PASSWORD="a long passphrase for amy"
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as demo tl admin user add amy --display-name "Amy A" --password-stdin >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  TL_DEMO_AGENT_TOKEN="$(as demo tl admin token issue triage --label demo 2>/dev/null)"
  export TL_DEMO_AGENT_TOKEN
  case "$TL_DEMO_AGENT_TOKEN" in tla_*) ;; *) fail "no agent token was issued" ;; esac
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as amy tl login amy --password-stdin >/dev/null
  driver prepare "$workdir"

  step "[$backend] clause 1: a controller defines the schedule; a user uploads two updates; the worker builds them"
  refuse "needs the document_controller or admin role" as amy tl xer define MAIN "${P[@]}" --name "Pipe rack schedule"
  out="$(as demo tl xer define MAIN "${P[@]}" --name "Pipe rack schedule" --type current)"; echo "$out"
  expect "defined MAIN" "$out"
  out="$(as amy tl xer upload "$workdir/update-1.xer" "${P[@]}" "${S[@]}")"; echo "$out"
  expect "queued MAIN#1" "$out"
  as amy tl xer upload "$workdir/update-2.xer" "${P[@]}" "${S[@]}" >/dev/null
  refuse "same SHA-256" as amy tl xer upload "$workdir/update-2.xer" "${P[@]}" "${S[@]}"
  refuse "needs the admin role" as amy tl xer worker --once
  out="$(as demo tl xer worker --once)"; echo "$out"
  expect "worker done: ran=2" "$out"
  out="$(as amy tl xer show "${P[@]}" "${S[@]}")"; echo "$out"
  expect "snapshot 2  Valid" "$out"
  expect "snapshot 1  Valid" "$out"
  expect "activities 21" "$out"
  echo "PASS 1: MAIN was defined by the controller; both updates were built by the worker (Valid, 21 activities)"

  step "[$backend] clause 2: the comparison shows date shifts and float erosion"
  out="$(as amy tl xer compare "${P[@]}" "${S[@]}" --new 2 --old 1 --limit 30)"; echo "$out"
  expect "data date shift +7d" "$out"
  expect "float A1230  9d -> 4d  eroded" "$out"
  expect "shift A1110  start -  finish +7d" "$out"
  expect "added A2500  Weld inspection hold point" "$out"
  expect "removed A1990  Temporary fencing" "$out"
  expect "logic added A1230 -> A2500" "$out"
  expect "critical A1110  entered" "$out"
  echo "PASS 2: A1230's float eroded from 9 to 4 days; dates shifted; A2500 came, A1990 went; the critical path moved"

  step "[$backend] clause 3: links by activity id resolve now and as of an earlier snapshot; orphans are flagged"
  refuse "needs the document_controller or admin role" as amy tl xer publish 1 "${P[@]}" "${S[@]}"
  as demo tl xer publish 1 "${P[@]}" "${S[@]}" >/dev/null
  as amy tl record create "${P[@]}" --key REC-A --title "Pipe rack supports work package" >/dev/null
  as amy tl record create "${P[@]}" --key REC-B --title "Temporary fencing permit" >/dev/null
  as amy tl record create "${P[@]}" --key REC-C --title "Unplanned site visit" >/dev/null
  out="$(as amy tl xer link REC-A A1230 "${P[@]}" "${S[@]}")"; echo "$out"
  expect "linked REC-A -> MAIN/A1230" "$out"
  as amy tl xer link REC-B A1990 "${P[@]}" "${S[@]}" >/dev/null
  refuse "A9999" as amy tl xer link REC-A A9999 "${P[@]}" "${S[@]}"
  out="$(as demo tl xer publish 2 "${P[@]}" "${S[@]}")"; echo "$out"
  expect "published MAIN#2" "$out"
  expect "will be checked by the worker" "$out"
  out="$(as amy tl xer show "${P[@]}" "${S[@]}")"
  expect "links being checked" "$out"
  as demo tl xer worker --once >/dev/null
  out="$(as amy tl xer show "${P[@]}" "${S[@]}")"
  case "$out" in *"links being checked"*) echo "$out"; fail "the links are still being checked" ;; esac
  out="$(as amy tl xer resolve A1230 "${P[@]}" "${S[@]}")"; echo "$out"
  expect "A1230  current  MAIN#2" "$out"
  out="$(as amy tl xer resolve A1230 "${P[@]}" "${S[@]}" --as-of 1)"; echo "$out"
  expect "A1230  as_of  MAIN#1" "$out"
  expect "float 72h" "$out"
  out="$(as amy tl xer resolve A1230 "${P[@]}" "${S[@]}" --as-of 2026-10-08)"; echo "$out"
  expect "A1230  as_of  MAIN#1" "$out"
  out="$(as amy tl xer resolve A1990 "${P[@]}" "${S[@]}")"; echo "$out"
  expect "A1990  orphaned" "$out"
  out="$(as amy tl xer health "${P[@]}" "${S[@]}")"; echo "$out"
  expect "orphaned links: 1" "$out"
  expect "activity A1990  last seen 1" "$out"
  echo "PASS 3: REC-A resolves to MAIN#2 now and MAIN#1 as of snapshot 1 or 2026-10-08; REC-B's link to A1990 is flagged"

  step "[$backend] clause 4: the look-ahead and the float trend"
  out="$(as amy tl xer look-ahead "${P[@]}" "${S[@]}")"; echo "$out"
  expect "look-ahead MAIN#2  2026-10-12 to 2026-11-09  4 weeks" "$out"
  expect "in progress 3  late start 0  starting 3" "$out"
  expect "A2500  starting" "$out"
  out="$(as amy tl xer trend A1230 "${P[@]}" "${S[@]}")"; echo "$out"
  expect "MAIN#1  Superseded  data date 2026-10-05T08:00  float 9d" "$out"
  expect "MAIN#2  Published  data date 2026-10-12T08:00  float 4d" "$out"
  echo "PASS 4: the look-ahead lists six activities (3 under way, 3 starting); A1230's float went 9d to 4d"

  step "[$backend] clause 5: a file that is not a schedule is an Invalid snapshot; the worker goes on"
  as amy tl xer upload "$workdir/not-a-schedule.xer" "${P[@]}" "${S[@]}" >/dev/null
  as amy tl xer upload "$workdir/update-3.xer" "${P[@]}" "${S[@]}" >/dev/null
  out="$(as demo tl xer worker --once)"; echo "$out"
  expect "worker done: ran=2" "$out"
  out="$(as amy tl xer show "${P[@]}" "${S[@]}")"; echo "$out"
  expect "snapshot 4  Valid" "$out"
  expect "snapshot 3  Invalid" "$out"
  refuse "only a Valid snapshot can be published" as demo tl xer publish 3 "${P[@]}" "${S[@]}"
  echo "PASS 5: snapshot 3 (not a schedule) is Invalid and cannot be published; snapshot 4 was built after it"

  step "[$backend] clause 6: cost periods, the budget report, and the records nobody coded or scheduled"
  out="$(as amy tl cost import "$workdir/cost-2026-07.csv" "${P[@]}" --period 2026-07 --as-of 2026-07-31)"; echo "$out" | sed -n 1,3p
  expect "new=4" "$out"
  expect "dry run: nothing written" "$out"
  refuse "needs the admin role" as amy tl cost import "$workdir/cost-2026-07.csv" "${P[@]}" --period 2026-07 --as-of 2026-07-31 --apply
  out="$(as demo tl cost import "$workdir/cost-2026-07.csv" "${P[@]}" --period 2026-07 --as-of 2026-07-31 --apply)"; echo "$out" | tail -1
  expect "applied 2026-07@1" "$out"
  as demo tl cost import "$workdir/cost-2026-08.csv" "${P[@]}" --period 2026-08 --as-of 2026-08-31 --apply >/dev/null
  out="$(as amy tl cost snapshots "${P[@]}")"; echo "$out"
  expect "2026-08@1" "$out"
  expect "2026-07@1" "$out"
  out="$(as amy tl cost show 4210-PIP "${P[@]}")"; echo "$out"
  expect "history 2" "$out"
  as demo tl link add REC-A 4210-PIP "${P[@]}" --relation references >/dev/null
  out="$(as amy tl cost report budget "${P[@]}" --unit quantity)"; echo "$out"
  expect "budget report (quantity): 4 codes, 3 over budget" "$out"
  expect "4210-WLD  level 2" "$out"
  expect "linked 1" "$out"
  out="$(as amy tl cost report uncoded "${P[@]}" --type core.Record)"; echo "$out"
  expect "records without a cost code (core.Record): 2" "$out"
  out="$(as amy tl xer unscheduled "${P[@]}" --type core.Record)"; echo "$out"
  expect "records without an activity (core.Record): 2" "$out"
  expect "REC-C" "$out"
  echo "PASS 6: two periods imported (apply is the admin's); three codes forecast over budget; REC-B and REC-C have no cost code and no live activity link"

  step "[$backend] clause 7: the API, the TUI and an agent show the same schedule"
  driver reads

  step "[$backend] clause 8: the lake holds the snapshots, the XER tables and the float trend"
  out="$(tl lake sync)"; echo "$out"
  expect "schedule snapshots: loaded 3" "$out"
  driver lake

  step "[$backend] clause 9: an agent proposes to publish; only a controller accepts"
  driver propose
  proposal="$(cat "$TL_DEMO_STATE")"
  out="$(as demo tl proposal ls "${P[@]}")"; echo "$out"
  expect "$proposal" "$out"
  refuse "needs the controller role" as amy tl proposal accept "$proposal"
  out="$(as amy tl xer show "${P[@]}" "${S[@]}")"
  expect "current 2" "$out"
  out="$(as demo tl proposal accept "$proposal")"; echo "$out"
  expect "accepted" "$out"
  out="$(as amy tl xer show "${P[@]}" "${S[@]}")"; echo "$out"
  expect "current 4" "$out"
  echo "PASS 9: the agent's proposal changed nothing until the controller accepted it; a user could not"

  step "[$backend] clause 10: after a restore, reconcile writes the typed rows again from the files"
  before="$(as amy tl xer compare "${P[@]}" "${S[@]}" --new 2 --old 1 --limit 30)"
  driver lose
  refuse "tl xer reconcile" as amy tl xer compare "${P[@]}" "${S[@]}" --new 2 --old 1
  out="$(as demo tl xer reconcile)"; echo "$out"
  expect "problems=0" "$out"
  after="$(as amy tl xer compare "${P[@]}" "${S[@]}" --new 2 --old 1 --limit 30)"
  [ "$before" = "$after" ] || { echo "$after"; fail "the comparison changed after the reconcile"; }
  echo "PASS 10: reconcile rebuilt the typed rows of every built snapshot; the comparison is the same"

  stop_server
  drop_pg
  echo "[$backend] all clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I4 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
