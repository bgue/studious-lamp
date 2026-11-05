#!/usr/bin/env bash
# Demo for P2-I1 (work packaging: the awp loaders, the WBS, the path of construction, CWPs, the
# budget rollup, the external packages, the screens, and the simulator): `just demo P2-I1`.
#
# The exit clauses (spec m3-wbs-cwp section 11), each ending in a `PASS clause N` line, once on
# SQLite and once on Postgres:
#   1  an admin loads co.acme.standards@1.0.0 and co.acme.awp@1.0.0; loading the awp edition twice
#      changes nothing; Commodity holds the nine starter values;
#   2  `tl load` of wbs-sample.csv plans 12 new and 1 invalid (`allocation sums to 101.00`), loads
#      12; each leaf references its cost codes; compensate then reload gives the same tree; a
#      superuser who is not an admin is refused `tl load`;
#   3  the CWA loader makes 4 CWAs and path v1; `path move` makes v2; both versions read back; a
#      stale expected version is refused (driver);
#   4  the P1-I4 demo schedule is seeded (its prepare step); a user creates 6 CWPs, allocates them,
#      links two EWP references (one constraint source) and activities of that schedule; release is
#      refused without an allocation, accepted for a superuser, refused for a user;
#   5  the rollup runs; `wbs_vs_cost_code` shows budget hours per cost code and the Unallocated row;
#      a revised budget moves the figures and both runs are in the ledger; rebuild gives the same rows;
#   6  a user cannot map cost codes or move the path; an agent's `propose_cwp` waits until a person
#      accepts it;
#   7  API, TUI (CWP register, WBS tree, path screen at 170 columns) and MCP show the same CWP (driver);
#   8  the CWA register lists the 4 CWAs with path position, CWP count and budget hours (driver);
#   9  the external packages log lists both EWP references, Constraint source Yes on one, with the
#      CWPs that require them (driver);
#   10 (the simulator, D43/D45) a sim project gets its awp data by hand; `tl sim` runs a short
#      scenario naming workface_planner; the approver accepts its proposal and it shows as a CWP row;
#      `tl sim assert` holds.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. The server
# is `tl serve` on a free loopback port over a temporary ledger; it is stopped afterwards. Nothing
# is left behind. Exits non-zero (and prints DEMO FAILED) when any clause is not met.
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

STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
AWP_STANDARDS=schema/fixtures/standards/co.acme.awp@1.0.0.yaml
SAMPLES=packages/tl-modules/awp/src/tl_mod_awp/samples
PROJECT=P123

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2"; }
driver() { quiet uv run python dev/demos/p2_i1_demo.py "$@" || fail "an exit clause was not met: $*"; }
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
run_key() { # the run key a `tl load open` printed: `opened <key> <id>`
  awk '/^opened /{print $2}' <<<"$1"
}
cwp_count() { # cwp_count WHO PROJECT: how many CWPs the project lists
  as "$1" tl awp cwp ls --project "$2" | grep -c "^$2-CWP-" || true
}

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, the demo account, the people, and the API on a free loopback port"
  stop_server
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake-$backend"
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
  export TL_DEMO_URL="http://127.0.0.1:$port" TL_API_URL="http://127.0.0.1:$port"
  export TL_TOKENS="$workdir/tokens-$backend.json" TL_SIM_DIR="$workdir/sim-$backend"
  export TL_DEMO_STATE="$workdir/proposal-$backend.txt"
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
  printf '%s\n' "a long passphrase for ada" | as demo tl admin user add ada --display-name "Ada" --role admin --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for alice" | as demo tl admin user add alice --display-name "Alice" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for dora" | as demo tl admin user add dora --display-name "Dora" --role document_controller --password-stdin >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  TL_DEMO_AGENT_TOKEN="$(as demo tl admin token issue triage --label demo 2>/dev/null)"
  export TL_DEMO_AGENT_TOKEN
  case "$TL_DEMO_AGENT_TOKEN" in tla_*) ;; *) fail "no agent token was issued" ;; esac
  for who in ada alice dora; do
    printf '%s\n' "a long passphrase for $who" | as "$who" tl login "$who" --password-stdin >/dev/null
  done

  step "[$backend] clause 1: the standards load, twice; Commodity holds the nine starter values"
  out="$(as ada tl standards load "$STANDARDS")"; echo "$out"
  expect "loaded co.acme.standards@1.0.0" "$out"
  out="$(as ada tl standards load "$AWP_STANDARDS")"; echo "$out"
  expect "loaded co.acme.awp@1.0.0" "$out"
  again="$(as ada tl standards load "$AWP_STANDARDS")"; echo "$again"
  if grep -q 'create=[1-9]' <<<"$again"; then fail "the second load created values"; fi
  values="$(as ada tl standards values Commodity --project "$PROJECT")"; echo "$values"
  [ "$(grep -c ' company ' <<<"$values")" = 9 ] || fail "Commodity does not hold the nine starter values"
  clause 1 "co.acme.awp@1.0.0 loaded; the second load changed nothing; Commodity holds 9 values"

  step "[$backend] clause 2: the WBS load: plan, refuse a superuser who is not an admin, load, compensate, reload"
  printf 'code,title,quantity_budget,hours_budget\nWLD,Welding,100,1000\nERC,Erection,100,800\nTST,Testing,100,300\n' >"$workdir/cost.csv"
  out="$(as ada tl cost import "$workdir/cost.csv" --project "$PROJECT" --period 2026-10 --as-of 2026-10-31 --apply)"; echo "$out" | tail -1
  expect "applied 2026-10@1" "$out"
  as ada tl admin roles grant dora --project "$PROJECT" --module awp --role superuser --reason demo >/dev/null
  out="$(as ada tl load open "$SAMPLES/wbs-sample.csv" --project "$PROJECT" --loader awp-wbs)"; echo "$out"
  wbs="$(run_key "$out")"
  as ada tl load extract "$wbs" --project "$PROJECT" >/dev/null
  as ada tl load profile "$wbs" --project "$PROJECT" >/dev/null
  out="$(as ada tl load plan "$wbs" --project "$PROJECT")"; echo "$out"
  expect "new 12 existing 0 invalid 1" "$out"
  expect "allocation sums to 101.00, not 100.00" "$out"
  refuse "needs the admin role" as dora tl load load "$wbs" --project "$PROJECT" --expect-new 12
  out="$(as ada tl load load "$wbs" --project "$PROJECT" --expect-new 12)"; echo "$out"
  expect "created 12 existing 0 invalid 1" "$out"
  out="$(as ada tl load reconcile "$wbs" --project "$PROJECT")"; echo "$out"
  expect "mismatches 0" "$out"
  for code in 1.1.1 1.1.2 1.2.1 1.2.2 2.1.1 2.1.2; do
    out="$(as ada tl link list "awp.wbs@$code" --project "$PROJECT")"
    expect "references" "$out"
  done
  echo "each of the six cost-coded leaves references its cost codes"
  before="$(as ada tl awp wbs tree --project "$PROJECT")"; echo "$before"
  out="$(as ada tl load compensate "$wbs" --project "$PROJECT" --reason "demo: take the batch back")"; echo "$out"
  out="$(as ada tl load open "$SAMPLES/wbs-sample.csv" --project "$PROJECT" --loader awp-wbs)"; echo "$out"
  wbs2="$(run_key "$out")"
  as ada tl load extract "$wbs2" --project "$PROJECT" >/dev/null
  as ada tl load profile "$wbs2" --project "$PROJECT" >/dev/null
  as ada tl load plan "$wbs2" --project "$PROJECT" >/dev/null
  out="$(as ada tl load load "$wbs2" --project "$PROJECT" --expect-new 12)"; echo "$out"
  expect "created 12" "$out"
  after="$(as ada tl awp wbs tree --project "$PROJECT")"
  [ "$before" = "$after" ] || { diff <(echo "$before") <(echo "$after") || true; fail "the reloaded tree differs"; }
  clause 2 "plan 12 new and 1 invalid; 12 loaded; leaves reference cost codes; reload gives the same tree; a superuser is refused tl load"

  step "[$backend] clause 3: the CWA loader, the path of construction, a second version, a stale version"
  out="$(as ada tl load open "$SAMPLES/cwa-sample.csv" --project "$PROJECT" --loader awp-cwa)"; echo "$out"
  cwa="$(run_key "$out")"
  as ada tl load extract "$cwa" --project "$PROJECT" >/dev/null
  as ada tl load profile "$cwa" --project "$PROJECT" >/dev/null
  out="$(as ada tl load plan "$cwa" --project "$PROJECT")"; echo "$out"
  expect "new 5 existing 0 invalid 0" "$out"
  out="$(as ada tl load load "$cwa" --project "$PROJECT" --expect-new 5)"; echo "$out"
  expect "created 5 existing 0 invalid 0" "$out"
  out="$(as ada tl awp cwa ls --project "$PROJECT")"; echo "$out"
  [ "$(grep -c '^CWA-' <<<"$out")" = 4 ] || fail "the CWA register does not list 4 areas"
  out="$(as ada tl awp path versions --project "$PROJECT")"; echo "$out"
  expect "steps 4" "$out"
  out="$(as ada tl awp path move CWA-C --to 1 --reason Access --project "$PROJECT")"; echo "$out"
  expect "move CWA-C  version" "$out"
  out="$(as ada tl awp path versions --project "$PROJECT")"; echo "$out"
  [ "$(grep -c 'steps 4' <<<"$out")" = 2 ] || fail "both path versions should read back"
  out="$(as ada tl awp path show --project "$PROJECT" --version 2)"; echo "$out"
  expect "CWA-C" "$out"
  driver stale
  clause 3 "4 CWAs and path v1; move makes v2; both versions read back; a stale expected version is refused"

  step "[$backend] clause 4: the P1-I4 schedule; a user builds six CWPs; release needs an allocation and a superuser"
  quiet uv run python dev/demos/p1_i4_demo.py prepare "$workdir" >/dev/null || fail "no XER files were written"
  out="$(as ada tl xer define MAIN --project "$PROJECT" --name "Pipe rack schedule" --type current)"; echo "$out"
  expect "defined MAIN" "$out"
  out="$(as alice tl xer upload "$workdir/update-1.xer" --project "$PROJECT" --schedule MAIN)"; echo "$out"
  expect "queued MAIN#1" "$out"
  out="$(as ada tl xer worker --once)"; echo "$out"
  expect "worker done: ran=1" "$out"
  out="$(as dora tl xer publish 1 --project "$PROJECT" --schedule MAIN)"; echo "$out"
  expect "published MAIN#1" "$out"
  for n in 1 2 3 4 5 6; do
    cwa_code=CWA-A; [ "$n" -gt 3 ] && cwa_code=CWA-B
    out="$(as alice tl awp cwp create --project "$PROJECT" --discipline PIP --title "Piping run $n" --cwa "$cwa_code" \
      --planned-start 2026-11-09 --planned-finish 2027-01-29 --budget-hours 120 --contractor "Acme Fab" --qty piping:100:m)"
    expect "created CWP $PROJECT-CWP-PIP-000$n" "$out"
    as alice tl awp cwp move "$PROJECT-CWP-PIP-000$n" start-development --project "$PROJECT" >/dev/null
  done
  for n in 1 2 3 4 5; do
    as alice tl awp cwp allocate "$PROJECT-CWP-PIP-000$n" --wbs 1.1.1:60 --wbs 1.2.1:40 --project "$PROJECT" >/dev/null
  done
  refuse "allocation" as dora tl awp cwp move "$PROJECT-CWP-PIP-0006" release --project "$PROJECT"
  refuse "forbidden" as alice tl awp cwp move "$PROJECT-CWP-PIP-0001" release --project "$PROJECT"
  out="$(as dora tl awp cwp move "$PROJECT-CWP-PIP-0001" release --project "$PROJECT")"; echo "$out"
  expect "move $PROJECT-CWP-PIP-0001  version" "$out"
  out="$(as dora tl awp cwp show "$PROJECT-CWP-PIP-0001" --project "$PROJECT")"; echo "$out"
  expect "state Released" "$out"
  out="$(as alice tl awp package record --project "$PROJECT" --type ewp --number EWP-0001 --title "Pipe rack EWP" \
    --constraint-source --status Issued --forecast 2027-01-15)"; echo "$out"
  out="$(as alice tl awp package record --project "$PROJECT" --type ewp --number EWP-0002 --title "Support EWP" \
    --no-constraint-source --status Issued --forecast 2027-01-20)"; echo "$out"
  as alice tl link add "$PROJECT-CWP-PIP-0001" awp.ewp@EWP-0001 --project "$PROJECT" --relation requires >/dev/null
  as alice tl link add "$PROJECT-CWP-PIP-0002" awp.ewp@EWP-0001 --project "$PROJECT" --relation requires >/dev/null
  as alice tl link add "$PROJECT-CWP-PIP-0003" awp.ewp@EWP-0002 --project "$PROJECT" --relation requires >/dev/null
  out="$(as alice tl xer link "$PROJECT-CWP-PIP-0001" A1230 --project "$PROJECT" --schedule MAIN)"; echo "$out"
  expect "linked $PROJECT-CWP-PIP-0001 -> MAIN/A1230" "$out"
  [ "$(cwp_count alice "$PROJECT")" = 6 ] || fail "alice does not see six CWPs"
  out="$(as alice tl awp package ls --project "$PROJECT")"; echo "$out"
  expect "EWP-0001" "$out"
  clause 4 "six CWPs built and allocated; EWP-0001 (constraint source) and EWP-0002 linked; activity linked; release refused, accepted, refused"

  step "[$backend] clause 5: the rollup, a revised budget, a rebuild"
  out="$(as ada tl awp rollup --project "$PROJECT")"; echo "$out"
  as ada tl awp worker --once >/dev/null
  report1="$(as ada tl awp report wbs_vs_cost_code --project "$PROJECT")"; echo "$report1"
  expect "Unallocated" "$report1"
  expect "WLD  Welding" "$report1"
  printf 'code,title,quantity_budget,hours_budget\nWLD,Welding,100,1300\nERC,Erection,100,800\nTST,Testing,100,300\n' >"$workdir/cost-revised.csv"
  as ada tl cost import "$workdir/cost-revised.csv" --project "$PROJECT" --period 2026-11 --as-of 2026-11-04 --apply >/dev/null
  out="$(as ada tl awp rollup --project "$PROJECT")"; echo "$out"
  expect "rollup requested" "$out"
  out="$(as ada tl awp worker --once)"; echo "$out"
  expect "worker done: ran=1" "$out"
  report2="$(as ada tl awp report wbs_vs_cost_code --project "$PROJECT")"; echo "$report2"
  [ "$report1" != "$report2" ] || fail "the revised budget did not move the figures"
  snaps="$(as ada tl cost snapshots --project "$PROJECT")"; echo "$snaps"
  expect "2026-10@1" "$snaps"
  expect "2026-11@1" "$snaps"
  as ada tl projections rebuild >/dev/null
  report3="$(as ada tl awp report wbs_vs_cost_code --project "$PROJECT")"
  [ "$report2" = "$report3" ] || fail "the rebuild changed the rows"
  clause 5 "the rollup shows budget hours per cost code and Unallocated; the revision moves it; both runs are in the ledger; rebuild gives the same rows"

  step "[$backend] clause 6: a user cannot map or move; an agent's proposal waits until a person accepts it"
  refuse "forbidden" as alice tl awp wbs map 1.1.1 --cost-code WLD:100 --project "$PROJECT"
  refuse "forbidden" as alice tl awp path move CWA-A --to 2 --reason Access --project "$PROJECT"
  before="$(cwp_count alice "$PROJECT")"
  driver propose
  pid="$(cat "$TL_DEMO_STATE")"
  out="$(as alice tl proposal ls --project "$PROJECT")"; echo "$out"
  expect "$pid" "$out"
  [ "$(cwp_count alice "$PROJECT")" = "$before" ] || fail "a proposal made a CWP before a person accepted it"
  out="$(as alice tl proposal accept "$pid")"; echo "$out"
  expect "accepted $pid" "$out"
  [ "$(cwp_count alice "$PROJECT")" = "$((before + 1))" ] || fail "the accepted proposal did not make a CWP"
  clause 6 "alice is refused the cost-code map and the path move; propose_cwp waited and a user's accept made the CWP"

  step "[$backend] clause 7: the API, the TUI and an agent show the same CWP"
  driver screens "$PROJECT-CWP-PIP-0001"
  step "[$backend] clause 8: the CWA register"
  driver cwas
  step "[$backend] clause 9: the external packages log"
  driver packages

  step "[$backend] clause 10: a sim project with its awp data by hand; a short run with workface_planner; the approver's accept shows"
  as ada tl admin roles grant dora --project sim-wk1 --module awp --role superuser --reason demo >/dev/null
  as dora tl awp cwa define CWA-A --title "Area A" --project sim-wk1 >/dev/null
  as dora tl awp cwa define CWA-B --title "Area B" --project sim-wk1 >/dev/null
  as dora tl awp path define --step CWA-A --step CWA-B --project sim-wk1 >/dev/null
  cat >"$workdir/workface-weeks.yaml" <<'YAML'
scenario: workface-weeks
seed: 31
start: 2026-11-02
duration_days: 2
template: small-piping
operators: [user:dora]
actors:
  document_controller: null
  crew: null
  planner: null
  workface_planner: {cwps_per_day: 1}
  approver: {accept_rate: 1.0}
YAML
  out="$(as demo tl sim create "$workdir/workface-weeks.yaml" --run-id wk1)"; echo "$out"
  out="$(as demo tl sim advance --run wk1 --days 2)"; echo "$out"
  out="$(as dora tl awp cwp ls --project sim-wk1)"; echo "$out"
  [ "$(grep -c 'CWP-' <<<"$out" || true)" -ge 1 ] || fail "the approver's accept made no CWP in sim-wk1"
  if ! out="$(as demo tl sim assert --run wk1 2>&1)"; then echo "$out"; fail "tl sim assert found a difference"; fi
  echo "$out"
  clause 10 "workface_planner proposed, the approver accepted, a CWP row shows in sim-wk1, sim assert holds"

  stop_server
  drop_pg
  echo "[$backend] clauses 1-10 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-I1 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
