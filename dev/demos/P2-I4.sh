#!/usr/bin/env bash
# Demo for P2-I4-A (requisitions and work orders, CLI, API, TUI and MCP agreeing): `just demo P2-I4`.
#
# The exit clauses of the trimmed increment (docs/tickets/P2-I4A/README.md), each ending in a
# `PASS clause N` line, once on SQLite and once on Postgres:
#   1  raise to close: uma raises a material requisition for the IWP; her approve is refused and
#      sue's is accepted, which opens P123-WO-0001; the work order is scheduled, assigned, started,
#      completed and closed; a labour requisition is rejected by sue and another cancelled by uma;
#      the final states are read back with req show and wo show;
#   2  a general requisition of type crane_lift takes the crane_lift pset (load_t, radius_m) and
#      pset get prints both values back (P123 adopts crane_lift in the demo world only: the copy of
#      schema/fixtures in the workdir, see TL_SCHEMA_DIR below; no shared fixture changes);
#   3  numbering under two writers: two background loops of ten labour raises and two of ten
#      general raises; each kind's keys are exactly -0001 .. -<n> once, n counted by this script;
#   4  one state over API, TUI palette and MCP (driver: dev/demos/p2_i4_demo.py); an agent's
#      propose_requisition waits for uma, then uma accepts it. (No refusal check: no account on this
#      ledger lacks requisitions.view, decision D-r3h.)
# Deferred and not claimed here: stock fulfilment, FIFO lots, the shortage constraint, the labour
# forecast, reports, thread dispatch and web pages.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. Nothing is
# left behind. Exits non-zero (and prints DEMO FAILED) when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
pg_url=""
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
finished=0
trap 'status=$?; [ "$finished" = 1 ] || [ "$status" = 0 ] || echo "DEMO FAILED: stopped with exit $status; the last command shown above did not succeed" >&2; drop_pg; rm -rf "$workdir"' EXIT
STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
AWP_STANDARDS=schema/fixtures/standards/co.acme.awp@1.0.0.yaml
MATERIALS=schema/fixtures/standards/co.acme.materials@1.0.0.yaml
SAMPLES=packages/tl-modules/materials/src/tl_mod_materials/samples
IWP=P123-IWP-PIP-0001
MAT=P123-REQ-MAT-0001
WO=P123-WO-0001

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_LAKE_DIR="$workdir/lake"
export P2_I4_WORKDIR="$workdir"
unset TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2"; }
driver() { # driver MODE [ARG...]: the API, TUI and MCP checks; their output is shown, stderr is kept
  uv run python dev/demos/p2_i4_demo.py "$@" 2>"$workdir/driver.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/driver.err" >&2; fail "an exit clause was not met: $*"; }
}
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
state_of() { # state_of KEY PERSON: the state line of tl req show (or wo show) for KEY
  as "$2" tl req show "$1" --project P123 | awk '/^state /{print $2}'
}
raise_loop() { # raise_loop KIND COUNT TAG: COUNT raises of KIND by uma; each must succeed
  local kind="$1" count="$2" tag="$3" i
  for i in $(seq 1 "$count"); do
    if [ "$kind" = labor ]; then
      as uma tl req raise-labor --project P123 --subject "$tag $i" --craft Pipefitter \
        --headcount 6 --start 2026-11-02 --end 2026-11-13 >/dev/null || exit 1
    else
      as uma tl req raise-general --project P123 --subject "$tag $i" --type crane_lift \
        >/dev/null || exit 1
    fi
  done
}
keys_are() { # keys_are KIND PREFIX COUNT: the listed keys are PREFIX0001 .. PREFIX<COUNT>, once each
  local out got want
  out="$(as uma tl req ls --project P123 --kind "$1" --limit 100)"
  got="$(printf '%s\n' "$out" | awk -v p="$2" 'index($1, p) == 1 { print $1 }' | sort)"
  want="$(for i in $(seq 1 "$3"); do printf '%s%04d\n' "$2" "$i"; done | sort)"
  [ -z "$(printf '%s\n' "$got" | uniq -d)" ] || { echo "$out"; fail "a $1 key is listed twice"; }
  [ "$got" = "$want" ] || { echo "$out"; fail "the $1 keys are not $2 0001 to $2 $3 once each"; }
  echo "$1: $(printf '%s\n' "$got" | wc -l | tr -d ' ') keys, each once, $2 0001 to $2$(printf '%04d' "$3")"
}

# Clause 2: the demo copies schema/fixtures, adds the crane_lift ref to the copy of x.P123@1.4.0.yaml
# and points TL_SCHEMA_DIR at the copy for the whole run (pattern: dev/demos/P0-I2.sh). No shared
# fixture changes; P123 adopts crane_lift in the demo world only.
cp -r schema/fixtures "$workdir/fixtures"
sed -i '/^extends:$/a\  - ref: co.acme.engineering@3.2.0#crane_lift' "$workdir/fixtures/x.P123@1.4.0.yaml"
grep -q 'ref: co.acme.engineering@3.2.0#crane_lift' "$workdir/fixtures/x.P123@1.4.0.yaml" \
  || fail "could not add crane_lift to the demo copy of x.P123@1.4.0"
export TL_SCHEMA_DIR="$workdir/fixtures"

run_backend() {
  local backend="$1" labour general cli_state
  step "[$backend] a new ledger: ada (admin), sue (requisitions superuser), uma and rob (users)"
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake"
  case "$backend" in
    sqlite) export TL_DB="$workdir/$backend.db" ;;
    postgres)
      pg_url="$(quiet uv run python dev/demos/p1_i0_demo.py pg-create)" || fail "Postgres is not reachable at TL_PG_URL (try: just dev up)"
      export TL_DB="$pg_url"
      ;;
    *) fail "unknown backend $backend" ;;
  esac
  tl init --dev 2>"$workdir/init.err" >/dev/null || { cat "$workdir/init.err" >&2; fail "tl init --dev"; }
  printf 'demo\n' | as demo tl login demo --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for ada" | as demo tl admin user add ada --display-name "Ada" --role admin --password-stdin >/dev/null
  for who in sue uma rob; do
    printf '%s\n' "a long passphrase for $who" | as demo tl admin user add "$who" --display-name "$who" --password-stdin >/dev/null
  done
  for who in ada sue uma rob; do
    printf '%s\n' "a long passphrase for $who" | as "$who" tl login "$who" --password-stdin >/dev/null
  done
  out="$(as ada tl admin roles grant sue --project P123 --module requisitions --role superuser --reason demo)"; echo "$out"
  expect "granted superuser on requisitions for project:P123 to sue" "$out"
  out="$(as ada tl admin roles grant uma --project P123 --module requisitions --role user --reason demo)"; echo "$out"
  expect "granted user on requisitions for project:P123 to uma" "$out"
  out="$(as ada tl admin roles grant rob --project P123 --module requisitions --role user --reason demo)"; echo "$out"
  expect "granted user on requisitions for project:P123 to rob" "$out"

  step "[$backend] setup: the standards, the item library, one IWP, and the PO lines that make the item a project item"
  for std in "$STANDARDS" "$AWP_STANDARDS" "$MATERIALS"; do
    as ada tl standards load "$std" >/dev/null
  done
  out="$(as ada tl load open "$SAMPLES/items.csv" --company --loader mat-items)"; echo "$out"
  as ada tl load extract "mat/items#1" --company >/dev/null
  as ada tl load profile "mat/items#1" --company >/dev/null
  as ada tl load plan "mat/items#1" --company >/dev/null
  out="$(as ada tl load load "mat/items#1" --company --expect-new 50)"; echo "$out"
  expect "created 50" "$out"
  out="$(as ada tl load open "$SAMPLES/po_lines.csv" --project P123 --loader mat-po-lines)"; echo "$out"
  as ada tl load extract "mat/po_lines#1" --project P123 >/dev/null
  as ada tl load profile "mat/po_lines#1" --project P123 >/dev/null
  as ada tl load plan "mat/po_lines#1" --project P123 >/dev/null
  out="$(as ada tl load load "mat/po_lines#1" --project P123 --expect-new 15)"; echo "$out"
  expect "created 15" "$out"
  out="$(as ada tl awp iwp create --project P123 --discipline PIP --title "Pipe rack spools, level 1")"; echo "$out"
  expect "created IWP $IWP" "$out"

  step "[$backend] clause 1: raise to close; approve by the superuser only; the work order; labour rejected and cancelled"
  out="$(as uma tl req raise-material --project P123 --subject "Flanges" --line FLG-WN-6-150-A105:10:ea --for "$IWP")"; echo "$out"
  expect "raised $MAT" "$out"
  out="$(as uma tl req ls --project P123 --for "$IWP")"; echo "$out"
  expect "$MAT  material  Requested" "$out"
  refuse "error: forbidden" as uma tl req approve "$MAT" --project P123
  out="$(as sue tl req approve "$MAT" --project P123)"; echo "$out"
  expect "approve $MAT  version" "$out"
  out="$(as uma tl wo show "$WO" --project P123)"; echo "$out"
  expect "requisition $MAT" "$out"
  expect "state Open" "$out"
  out="$(as sue tl wo schedule "$WO" --start 2026-11-16 --finish 2026-11-20 --project P123)"; echo "$out"
  expect "schedule $WO  version" "$out"
  out="$(as sue tl wo assign "$WO" --to user:rob --project P123)"; echo "$out"
  expect "assign $WO  version" "$out"
  out="$(as rob tl wo start "$WO" --project P123)"; echo "$out"
  expect "start $WO  version" "$out"
  out="$(as rob tl wo complete "$WO" --hours 40.0 --project P123)"; echo "$out"
  expect "complete $WO  version" "$out"
  out="$(as sue tl wo close "$WO" --project P123)"; echo "$out"
  expect "close $WO  version" "$out"
  out="$(as uma tl wo ls --state Closed --project P123)"; echo "$out"
  expect "$WO  issue  Closed" "$out"
  out="$(as uma tl req raise-labor --project P123 --subject Pipefitters --craft Pipefitter --headcount 6 --start 2026-11-02 --end 2026-11-13)"; echo "$out"
  expect "raised P123-REQ-LAB-0001" "$out"
  out="$(as uma tl req raise-labor --project P123 --subject Pipefitters --craft Pipefitter --headcount 6 --start 2026-11-02 --end 2026-11-13)"; echo "$out"
  expect "raised P123-REQ-LAB-0002" "$out"
  out="$(as sue tl req reject P123-REQ-LAB-0001 --reason "No budget" --project P123)"; echo "$out"
  expect "reject P123-REQ-LAB-0001  version" "$out"
  out="$(as uma tl req cancel P123-REQ-LAB-0002 --reason "Not needed" --project P123)"; echo "$out"
  expect "cancel P123-REQ-LAB-0002  version" "$out"
  out="$(as uma tl req ls --project P123)"; echo "$out"
  expect "P123-REQ-LAB-0001  labor  Rejected" "$out"
  expect "P123-REQ-LAB-0002  labor  Cancelled" "$out"
  [ "$(state_of "$MAT" uma)" = Closed ] || fail "$MAT is not Closed"
  [ "$(state_of P123-REQ-LAB-0001 uma)" = Rejected ] || fail "P123-REQ-LAB-0001 is not Rejected"
  [ "$(state_of P123-REQ-LAB-0002 uma)" = Cancelled ] || fail "P123-REQ-LAB-0002 is not Cancelled"
  out="$(as uma tl wo show "$WO" --project P123)"; expect "state Closed" "$out"
  labour=2
  clause 1 "$MAT raised, refused for uma, approved by sue, closed through its work order; two labour requisitions rejected and cancelled"

  step "[$backend] clause 2: a general requisition of type crane_lift takes the crane_lift pset"
  out="$(as uma tl req raise-general --project P123 --subject "Rack 12 lift" --type crane_lift)"; echo "$out"
  expect "raised P123-REQ-GEN-0001" "$out"
  out="$(as uma tl pset set --project P123 P123-REQ-GEN-0001 crane_lift load_t=40 radius_m=18)"; echo "$out"
  expect "conformance ok" "$out"
  out="$(as uma tl pset get --project P123 P123-REQ-GEN-0001 crane_lift)"; echo "$out"
  expect 'psets: {"load_t":40,"radius_m":18}' "$out"
  general=1
  clause 2 "crane_lift on P123-REQ-GEN-0001 reads back load_t 40 and radius_m 18 (P123 adopts crane_lift in the demo world only)"

  step "[$backend] clause 3: numbering under two writers; 20 labour and 20 general raised by two loops each"
  raise_loop labor 10 "Pipefit A" & p1=$!
  raise_loop labor 10 "Pipefit B" & p2=$!
  wait "$p1" || fail "a labour raise failed (loop A)"
  wait "$p2" || fail "a labour raise failed (loop B)"
  labour=$((labour + 20))
  raise_loop general 10 "Lift A" & p3=$!
  raise_loop general 10 "Lift B" & p4=$!
  wait "$p3" || fail "a general raise failed (loop A)"
  wait "$p4" || fail "a general raise failed (loop B)"
  general=$((general + 20))
  out="$(keys_are labor P123-REQ-LAB- "$labour")"; echo "$out"
  out2="$(keys_are general P123-REQ-GEN- "$general")"; echo "$out2"
  clause 3 "labour keys P123-REQ-LAB-0001..$(printf '%04d' "$labour") and general keys P123-REQ-GEN-0001..$(printf '%04d' "$general"), each once"

  step "[$backend] clause 4: one state over the API, the TUI palette and MCP; the agent's proposal waits for uma"
  cli_state="$(state_of "$MAT" uma)"
  [ "$cli_state" = Closed ] || fail "tl req show says $cli_state for $MAT"
  driver clause4 "$cli_state" "$labour"
  out="$(as uma tl req ls --project P123 --kind labor --limit 100)"; echo "$out"
  expect "P123-REQ-LAB-$(printf '%04d' $((labour + 1)))  labor  Requested  normal  -  user:uma" "$out"
  clause 4 "API, palette screens (170x44) and MCP agree with tl req show; an agent's proposal waits for uma, who accepts it"

  drop_pg
  echo "[$backend] clauses 1-4 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

finished=1
echo
echo "P2-I4 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
