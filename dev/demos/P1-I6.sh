#!/usr/bin/env bash
# Demo for P1-I6 (M10 Technical / RFI and Commercial domains, escalation, evidence trail, export to
# the cost system): `just demo P1-I6`.
#
# The exit clauses, each ending in a PASS line, once on SQLite and once on Postgres:
#   1  an RFI is raised and sent to review by a person; issuing it is a controller's act (a user is
#      refused): a PDF is stored, the send is a stub, and a clock counts to the date an answer is
#      needed;
#   2  the client's answer says yes to cost impact: the RFI log shows the response time and the flag;
#   3  a controller escalates it into an early warning, a restricted draft linked to the RFI whose
#      time bar counts from the day of the answer; a user does not see it, nor that it exists;
#   4  the notice is priced, reviewed and issued, which meets its time bar; a second one, issued
#      after its bar ran out, is issued all the same and shows as LATE;
#   5  the other party agrees one notice and disputes the other: the register totals each currency
#      on its own line; a dispute goes to the legal route and cancels its clocks;
#   6  the cost-system export holds the pending and approved changes, names the class it carries,
#      is a private file and quotes a cell a spreadsheet would run;
#   7  the evidence trail of the notice leads to its RFI for a controller and to nothing for a user,
#      and a day before the item existed is refused;
#   8  the TUI (Ctrl+G) and an agent's MCP tools read the same RFIs, and show no notice to a person
#      or an agent who may not read it;
#   9  a simulated site engineer and client representative play two days of RFIs and `tl sim assert`
#      holds the run to its ground truth.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. Starts
# `tl serve` on a free loopback port over a temporary ledger; nothing is left behind. Nothing is
# sent anywhere: issuing a letter is a stub. Exits non-zero (and prints DEMO FAILED) when any
# clause is not met.
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
# The schema directory of this demo: the fixture packages and the working calendar of the project
# the simulator plays in (clause 9: `sim-wk1`; the clocks of an issued RFI count on it).
mkdir -p "$workdir"
cp -r schema/fixtures "$workdir/schema"
sed -e 's/P123-default/sim-wk1-default/' -e 's/project:P123/project:sim-wk1/' \
  schema/fixtures/calendars/P123-default@1.yaml >"$workdir/schema/calendars/sim-wk1-default@1.yaml"
export TL_SCHEMA_DIR="$workdir/schema"
unset TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i6_demo.py "$@" || fail "an exit clause was not met"; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}


run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, two people, a controller and an agent, and the API on a free loopback port"
  stop_server
  case "$backend" in
    sqlite) export TL_DB="$workdir/$backend.db" ;;
    postgres)
      pg_url="$(quiet uv run python dev/demos/p1_i0_demo.py pg-create)" || fail "Postgres is not reachable at TL_PG_URL (try: just dev up)"
      export TL_DB="$pg_url"
      ;;
    *) fail "unknown backend $backend" ;;
  esac
  local port
  port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  export TL_DEMO_URL="http://127.0.0.1:$port" TL_API_URL="http://127.0.0.1:$port"
  export TL_TOKENS="$workdir/tokens-$backend.json" TL_SIM_DIR="$workdir/sim-$backend"
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
  export TL_DEMO_DORA_PASSWORD="a long passphrase for dora"
  printf '%s\n' "$TL_DEMO_DORA_PASSWORD" | as demo tl admin user add dora --display-name "Dora C" --password-stdin >/dev/null
  as demo tl admin user roles dora --add document_controller >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  TL_DEMO_AGENT_TOKEN="$(as demo tl admin token issue triage --label demo 2>/dev/null)"
  export TL_DEMO_AGENT_TOKEN
  case "$TL_DEMO_AGENT_TOKEN" in tla_*) ;; *) fail "no agent token was issued" ;; esac
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as amy tl login amy --password-stdin >/dev/null
  printf '%s\n' "$TL_DEMO_DORA_PASSWORD" | as dora tl login dora --password-stdin >/dev/null

  local today needed late_aware yesterday
  today="$(python3 -c 'import datetime as d; print(d.date.today())')"
  needed="$(python3 -c 'import datetime as d; print(d.date.today() + d.timedelta(days=10))')"
  late_aware="$(python3 -c 'import datetime as d; print(d.date.today() - d.timedelta(days=20))')"
  yesterday="$(python3 -c 'import datetime as d; print(d.date.today() - d.timedelta(days=1))')"

  step "[$backend] clause 1: an RFI is raised by a person; issuing it is a controller's act"
  out="$(as amy tl rfi raise --project P123 --subject "Beam B12 clashes with line 47" --question "The isometric clashes with beam B12; confirm the routing." --discipline structural --required-by "$needed" --to "Meridian:pm@meridian.example")"; echo "$out"
  rfi="$(echo "$out" | awk '/^raised/ {print $2}')"
  [ "$rfi" = "P123-RFI-0001" ] || fail "no RFI number ($rfi)"
  out="$(as amy tl rfi submit "$rfi" --project P123)"; echo "$out"
  expect "is in internal review" "$out"
  if out="$(as amy tl rfi issue "$rfi" --project P123 2>&1)"; then fail "a user issued an RFI"; fi
  echo "$out"
  expect "needs the document_controller or admin role" "$out"
  out="$(as dora tl rfi issue "$rfi" --project P123)"; echo "$out"
  expect "delivery stub: nothing was sent" "$out"
  expect "clock $rfi-C01 Answer required due $needed" "$out"
  out="$(as amy tl rfi show "$rfi" --project P123)"; echo "$out"
  expect "Awaiting response" "$out"
  expect "clock $rfi-C01 Answer required running due $needed left 10" "$out"
  echo "PASS 1: $rfi was raised and sent to review by a person; a user was refused the issue; its clock is due $needed"
  export TL_DEMO_RFI="$rfi"

  step "[$backend] clause 2: the answer says yes to cost impact; the log shows the response time and the flag"
  out="$(as amy tl rfi answer "$rfi" --project P123 --answer "Re-route above the beam; revision C follows." --cost-impact yes --schedule-impact no)"; echo "$out"
  expect "answered $rfi: cost yes schedule no" "$out"
  expect "tl rfi escalate $rfi" "$out"
  out="$(as amy tl rfi ls --project P123 --impact)"; echo "$out"
  expect "$rfi Answered rfi structural needed $needed answered $today took 0d cost yes schedule no" "$out"
  expect "1 answered, 0 open, 0 overdue, 1 with an impact; average response 0.0d" "$out"
  out="$(as amy tl rfi show "$rfi" --project P123)"; echo "$out"
  expect "clock $rfi-C01 Answer required met" "$out"
  echo "PASS 2: $rfi was answered on the day it was issued; the log shows 0 days, cost yes, and the clock is met"

  step "[$backend] clause 3: a controller escalates it into a restricted early warning; a user cannot see it"
  if out="$(as amy tl rfi escalate "$rfi" --project P123 2>&1)"; then fail "a user escalated an RFI"; fi
  echo "$out"
  expect "needs the document_controller or admin role" "$out"
  out="$(as dora tl rfi escalate "$rfi" --project P123)"; echo "$out"
  expect "escalated $rfi to P123-EW-0001" "$out"
  bar_due="$(python3 -c 'import datetime as d; print(d.date.today() + d.timedelta(days=14))')"
  expect "time bar P123-EW-0001-C01 Early warning time bar due $bar_due" "$out"
  expect "P123-EW-0001 is a draft, class restricted" "$out"
  out="$(as dora tl rfi show "$rfi" --project P123)"
  expect "escalated to P123-EW-0001 (early_warning, Draft)" "$out"
  out="$(as amy tl rfi show "$rfi" --project P123)"
  case "$out" in *"P123-EW-0001"*) fail "a user was told of the early warning" ;; esac
  if out="$(as amy tl comm ls --project P123 2>&1)"; then fail "a user listed the notices"; fi
  expect "needs the document_controller or admin role" "$out"
  export TL_DEMO_NOTICE="P123-EW-0001"
  driver hidden
  echo "PASS 3: $rfi became P123-EW-0001, restricted, its time bar due $bar_due (14 days from the answer); a user cannot see it or tell that it exists"

  step "[$backend] clause 4: the notice is priced, reviewed and issued, which meets its time bar; a late one shows LATE"
  as dora tl comm update P123-EW-0001 --project P123 --currency USD --value 12500 --hours 240 --cost-code "2.3.1=10000" --cost-code "2.3.2=2500:100" --schedule-days 3 --basis "Answer to $rfi" --to "Meridian:pm@meridian.example" >/dev/null
  as dora tl comm submit P123-EW-0001 --project P123 >/dev/null
  out="$(as dora tl comm review P123-EW-0001 --project P123 --note "figures checked")"; echo "$out"
  expect "P123-EW-0001 is PM approval" "$out"
  out="$(as dora tl comm issue P123-EW-0001 --project P123)"; echo "$out"
  expect "clock P123-EW-0001-C01 Early warning time bar met due $bar_due" "$out"
  expect "clock P123-EW-0001-C02 Assessment expected running" "$out"
  out="$(as dora tl comm raise --project P123 --subject "=SUM(1+1) late warning" --subtype early_warning --aware-on "$late_aware" --currency EUR --value 4000 --to "Meridian:pm@meridian.example")"; echo "$out"
  late_due="$(python3 -c "import datetime as d; print(d.date.fromisoformat('$late_aware') + d.timedelta(days=14))")"
  expect "time bar P123-EW-0002-C01 Early warning time bar due $late_due" "$out"
  as dora tl comm submit P123-EW-0002 --project P123 >/dev/null
  as dora tl comm review P123-EW-0002 --project P123 >/dev/null
  out="$(as dora tl comm issue P123-EW-0002 --project P123)"; echo "$out"
  expect "clock P123-EW-0002-C01 Early warning time bar met due $late_due LATE" "$out"
  out="$(as dora tl comm ls --project P123 --time-bars)"; echo "$out"
  expect "P123-EW-0002 Awaiting assessment early_warning bar met due $late_due left 0 LATE" "$out"
  expect "0 time bars running, 1 late" "$out"
  echo "PASS 4: P123-EW-0001 met its bar by being issued; P123-EW-0002 was issued after its bar ($late_due) and is marked LATE"

  step "[$backend] clause 5: one notice is agreed, one disputed; each currency has its own total; a dispute goes to the legal route"
  as dora tl comm assess P123-EW-0001 --project P123 --status agreed --value 9000 --note "as stated" >/dev/null
  as dora tl comm assess P123-EW-0002 --project P123 --status disputed --note "no entitlement" >/dev/null
  out="$(as dora tl comm ls --project P123)"; echo "$out"
  expect "total EUR: 1 items, estimated 4000.00, assessed 0.00" "$out"
  expect "total USD: 1 items, estimated 12500.00, assessed 9000.00" "$out"
  out="$(as dora tl comm legal P123-EW-0002 --project P123 --reason "formal dispute")"; echo "$out"
  expect "P123-EW-0002 is Escalated" "$out"
  out="$(as dora tl comm show P123-EW-0002 --project P123)"; echo "$out"
  case "$out" in *"running"*) fail "a clock of the escalated item is still running" ;; esac
  as dora tl comm close P123-EW-0001 --project P123 >/dev/null
  echo "PASS 5: the register totals EUR and USD on their own lines (never added); the dispute is Escalated and its clocks are not running"

  step "[$backend] clause 6: the cost-system export names its class, is a private file, and quotes a formula"
  out="$(as dora tl comm export --project P123 2>&1)"; echo "$out" | sed -n 1,3p
  expect "2 restricted items were left out: name the class with --class restricted" "$out"
  if out="$(as dora tl comm export --project P123 --class privileged 2>&1)"; then fail "a privileged export was written"; fi
  expect "never exported" "$out"
  as dora tl comm export --project P123 --class restricted --out "$workdir/changes-$backend.csv"
  driver csv "$workdir/changes-$backend.csv"
  if out="$(as dora tl comm export --project P123 --class restricted --out "$workdir/changes-$backend.csv" 2>&1)"; then fail "an existing file was replaced without --force"; fi
  expect "exists already" "$out"

  step "[$backend] clause 7: the evidence trail leads to the RFI for a controller; a user sees nothing of the notice"
  out="$(as dora tl evidence P123-EW-0001 --project P123)"; echo "$out" | cut -c1-160
  expect "P123-RFI-0001 [correspondence.TechnicalItem] Answered" "$out"
  expect "<- derived from (active, since $today)" "$out"
  if out="$(as amy tl evidence P123-EW-0001 --project P123 2>&1)"; then fail "a user read the trail of a restricted notice"; fi
  expect "no correspondence item" "$out"
  out="$(as amy tl evidence "$rfi" --project P123)"
  case "$out" in *"P123-EW-0001"*) fail "the trail of the RFI shows the restricted notice to a user" ;; esac
  if out="$(as dora tl evidence P123-EW-0001 --project P123 --as-of "$yesterday" 2>&1)"; then fail "a trail was made for a day before the item existed"; fi
  expect "did not exist on $yesterday" "$out"
  echo "PASS 7: a controller's trail runs from the notice to its RFI; a user's trail of the RFI stops at the RFI; yesterday, before either existed, is refused"

  step "[$backend] clause 8: the TUI and an agent read the same RFIs and no notice they may not read"
  driver screen
  driver agent

  step "[$backend] clause 9: a simulated site engineer and client representative play two days of RFIs"
  sed 's/operators: \[user:dev\]/operators: [user:dora]/' dev/seed/scenarios/rfi-weeks.yaml >"$workdir/rfi-weeks.yaml"
  out="$(tl sim create "$workdir/rfi-weeks.yaml" --run-id wk1)"; echo "$out"
  tl sim advance --run wk1 --days 1 >/dev/null
  issued=0
  for number in $(as dora tl rfi ls --project sim-wk1 --state "Internal review" | awk '$1 ~ /-RFI-/ {print $1}'); do
    as dora tl rfi issue "$number" --project sim-wk1 >/dev/null
    issued=$((issued + 1))
  done
  [ "$issued" -ge 1 ] || fail "the author raised no RFI on day one"
  tl sim advance --run wk1 --days 2 >/dev/null
  out="$(as dora tl rfi ls --project sim-wk1)"; echo "$out"
  expect "answered 2026-" "$out"
  out="$(tl sim assert --run wk1)"; echo "$out"
  expect "ok: " "$out"
  echo "PASS 9: $issued RFIs the author raised were issued by a controller; the client answered at least one; sim assert holds the run to its ground truth"

  stop_server
  drop_pg
  echo "[$backend] all clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I6 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
