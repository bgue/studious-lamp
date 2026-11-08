#!/usr/bin/env bash
# Demo for P2-I2 (IWPs, constraints, readiness, release sign-off): `just demo P2-I2`.
#
# The exit clauses (docs/tickets/P2-I2/README.md, "Demo clauses"), each ending in a `PASS clause N`
# line, once on SQLite and once on Postgres:
#   1  one IWP, P123-IWP-PIP-0001, from 24 + 8 scope items and 3 tags: 35 `contains` links;
#   2  two drawings pinned at revision A; a new IFC revision of ISO-1234 makes documents_current
#      blocked, the stale pin named as resolve_via;
#   3  a constraint raised by hand, and one raised by the materials check (MTO lines assigned to
#      the IWP, then short); need-by = planned start minus awp.iwp.ready_lead_weeks; the review
#      groups by owner and category; the reservation clears the check's constraint;
#   4  readiness 7/9 with documents_current and constraints_cleared blocked; re-pin and clear give
#      9/9; IWP.Ready reaches the loopback receiver, verified;
#   5  sign-off: a plain user refused, two distinct signers (dora, sue) accepted, the same signer
#      again refused, a wrong record hash refused;
#   6  issue to the foreman (user:frank): Issued; the permit to work is reported missing, not
#      blocking;
#   7  an oversize IWP (hours over awp.iwp.size_hours) warns; the split makes two IWPs;
#   8  an agent proposes adding scope over MCP (propose_iwp_scope); a person accepts; the scope
#      item is on the IWP;
#   9  the same state over the API, the TUI (palette and the IWP screen), the web (/web/p/...) and
#      MCP; readiness history in the ledger; the backlog tile shows weeks per foreman;
#   10 (the simulator) a sim project with its awp roles set by hand; `tl sim` runs a short scenario
#      naming iwp_planner; `tl sim assert` holds.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. The server
# is `tl serve` on a free loopback port over a temporary ledger; the webhook receiver is a
# process on a free loopback port. Both are stopped afterwards. Nothing is left behind. Exits
# non-zero (and prints DEMO FAILED) when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
receiver_pid=""
pg_url=""
stop_group() { # stop a process group started with setsid
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || true
  sleep 0.2
  kill -KILL -- "-$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
stop_server() {
  stop_group "$server_pid"
  server_pid=""
}
stop_receiver() {
  stop_group "$receiver_pid"
  receiver_pid=""
}
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'stop_receiver; stop_server; drop_pg; rm -rf "$workdir"' EXIT

STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
AWP_STANDARDS=schema/fixtures/standards/co.acme.awp@1.0.0.yaml
DOC_STANDARDS=schema/fixtures/standards/co.acme.documents@1.0.0.yaml
MATERIALS=schema/fixtures/standards/co.acme.materials@1.0.0.yaml
MAT_SAMPLES=packages/tl-modules/materials/src/tl_mod_materials/samples
PROJECT=P123
IWP=P123-IWP-PIP-0001

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
driver() { quiet uv run python dev/demos/p2_i2_demo.py "$@" || fail "an exit clause was not met: $*"; }
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
last_word() { awk '{print $NF}' <<<"$1"; } # the key a `created ...` line ends with
state_of() { # state_of NUMBER: the workflow state of an IWP
  as alice tl awp iwp show "$1" --project "$PROJECT" | awk '/^state /{ $1=""; sub(/^ /,""); print }'
}
readiness_of() { as alice tl awp readiness show "$1" --project "$PROJECT"; }
# One `worker --once` polls 100 outbox events, then runs the readiness jobs they queued. The first
# run after the setup reads a backlog of several hundred events, so it runs the worker 8 times.
catch_up() { local i; for i in $(seq 1 8); do as alice tl awp worker --once >/dev/null; done; }
evaluate() { local i; for i in 1 2; do as alice tl awp worker --once >/dev/null; done; }

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, the people, the agent, the API on a free loopback port, a receiver"
  stop_receiver
  stop_server
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake-$backend" "$workdir"/session-* "$workdir"/receiver.*
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
  setsid uv run python dev/demos/p2_i2_demo.py receiver "$workdir" >"$workdir/receiver-$backend.log" 2>&1 &
  receiver_pid=$!
  for _ in $(seq 1 100); do [ -s "$workdir/receiver.port" ] && break; sleep 0.1; done
  [ -s "$workdir/receiver.port" ] || fail "the receiver did not start"
  printf 'demo\n' | as demo tl login demo --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for ada" | as demo tl admin user add ada --display-name "Ada" --role admin --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for alice" | as demo tl admin user add alice --display-name "Alice" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for dora" | as demo tl admin user add dora --display-name "Dora" --role document_controller --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for sue" | as demo tl admin user add sue --display-name "Sue" --role document_controller --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for frank" | as demo tl admin user add frank --display-name "Frank" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for plain" | as demo tl admin user add plain --display-name "Plain" --password-stdin >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  TL_DEMO_AGENT_TOKEN="$(as demo tl admin token issue triage --label demo 2>/dev/null)"
  export TL_DEMO_AGENT_TOKEN
  case "$TL_DEMO_AGENT_TOKEN" in tla_*) ;; *) fail "no agent token was issued" ;; esac
  for who in ada alice dora sue frank plain; do
    printf '%s\n' "a long passphrase for $who" | as "$who" tl login "$who" --password-stdin >/dev/null
  done
  as ada tl admin roles grant dora --project "$PROJECT" --module awp --role superuser --reason demo >/dev/null
  as ada tl admin roles grant sue --project "$PROJECT" --module awp --role superuser --reason demo >/dev/null
  as ada tl admin roles grant alice --project "$PROJECT" --module awp --role user --reason demo >/dev/null
  as ada tl admin roles grant alice --project "$PROJECT" --module documents --role user --reason demo >/dev/null
  as ada tl admin roles grant alice --project "$PROJECT" --module materials --role user --reason demo >/dev/null
  as ada tl admin roles grant dora --project "$PROJECT" --module documents --role superuser --reason demo >/dev/null
  as ada tl admin roles grant sue --project "$PROJECT" --module documents --role superuser --reason demo >/dev/null
  as ada tl admin roles grant sue --project "$PROJECT" --module materials --role superuser --reason demo >/dev/null
  as ada tl admin roles grant triage --project "$PROJECT" --module awp --role user --reason demo >/dev/null
  as ada tl admin roles grant triage --project "$PROJECT" --module materials --role user --reason demo >/dev/null
  as demo tl config set webhooks.egress.allowlist 127.0.0.1 --company --reason "the demo receiver" --accept-risk >/dev/null
  as alice tl awp worker --once >/dev/null # the readiness follower starts at the head of the outbox

  step "[$backend] clause 1: the standards, 32 scope items, 3 tags, one IWP; all scope is contains links"
  for std in "$STANDARDS" "$AWP_STANDARDS" "$DOC_STANDARDS" "$MATERIALS"; do
    out="$(as ada tl standards load "$std")"; echo "$out" | tail -1
  done
  out="$(as ada tl load open "$MAT_SAMPLES/items.csv" --company --loader mat-items)"; echo "$out"
  as ada tl load extract "mat/items#1" --company >/dev/null
  as ada tl load profile "mat/items#1" --company >/dev/null
  as ada tl load plan "mat/items#1" --company >/dev/null
  out="$(as ada tl load load "mat/items#1" --company --expect-new 50)"; echo "$out"
  expect "created 50" "$out"
  keys24=()
  for n in $(seq 1 24); do
    out="$(as alice tl awp iwp item-create --project "$PROJECT" --commodity piping --description "Spool $n, line 47-P-$n" --qty 10 --uom m --hours 4)"
    keys24+=("$(last_word "$out")")
  done
  keys8=()
  for n in $(seq 25 32); do
    out="$(as alice tl awp iwp item-create --project "$PROJECT" --commodity structural-steel --description "Support $n" --qty 40 --uom kg --hours 3)"
    keys8+=("$(last_word "$out")")
  done
  for n in 1 2 3; do
    as alice tl tag create "47-FV-100$n" --class ControlValve --service "Feed gas" --project "$PROJECT" >/dev/null
  done
  out="$(as alice tl awp iwp create --project "$PROJECT" --discipline PIP --title "Pipe rack spools, level 1" \
    --planned-start 2026-11-09 --planned-finish 2027-01-29 --foreman user:frank --hours 120)"; echo "$out"
  expect "created IWP $IWP" "$out"
  out="$(as alice tl awp iwp add-scope "$IWP" "${keys24[@]}" --project "$PROJECT")"; echo "$out"
  expect "add-scope $IWP  24 items" "$out"
  out="$(as alice tl awp iwp add-scope "$IWP" "${keys8[@]}" 47-FV-1001 47-FV-1002 47-FV-1003 --project "$PROJECT")"; echo "$out"
  expect "add-scope $IWP  11 items" "$out"
  out="$(as alice tl awp iwp show "$IWP" --project "$PROJECT")"; echo "$out"
  expect "scope 35" "$out"
  links="$(as alice tl link list "$IWP" --project "$PROJECT" | grep -c ' contains ' || true)"
  [ "$links" = 35 ] || fail "the IWP has $links contains links, not 35"
  catch_up
  clause 1 "$IWP from 24 + 8 scope items and 3 tags: 35 contains links"

  step "[$backend] clause 2: two drawings pinned at A; a new IFC revision of ISO-1234 blocks documents_current"
  for doc in ISO-1234 ISO-1235; do
    as alice tl doc register "$doc" --project "$PROJECT" --title "Piping isometric $doc" --type ISO --discipline PIP --originator "Acme Piping" >/dev/null
    as alice tl doc rev create "$doc" --project "$PROJECT" --purpose "For review" >/dev/null
    printf '%%PDF-1.7 %s rev A\n' "$doc" >"$workdir/$doc-A.pdf"
    as alice tl doc rendition add "$doc" A "$workdir/$doc-A.pdf" --project "$PROJECT" --kind pdf --pages 1 >/dev/null
    out="$(as dora tl doc rev issue "$doc" A --project "$PROJECT" --status IFR)"; echo "$out"
    expect "issued $doc@A as IFR" "$out"
    out="$(as alice tl awp iwp pin "$IWP" "$doc" --pin A --project "$PROJECT")"; echo "$out"
    expect "pin $IWP  version" "$out"
  done
  as alice tl awp iwp move "$IWP" start-development --project "$PROJECT" >/dev/null
  as alice tl awp iwp move "$IWP" constraint-check --project "$PROJECT" >/dev/null
  evaluate
  out="$(readiness_of "$IWP")"; echo "$out"
  expect "documents_current  ok" "$out"
  as alice tl doc rev create ISO-1234 --project "$PROJECT" --purpose "Issued for construction" >/dev/null
  printf '%%PDF-1.7 ISO-1234 rev B\n' >"$workdir/ISO-1234-B.pdf"
  as alice tl doc rendition add ISO-1234 B "$workdir/ISO-1234-B.pdf" --project "$PROJECT" --kind pdf --pages 1 >/dev/null
  out="$(as dora tl doc rev issue ISO-1234 B --project "$PROJECT" --status IFC)"; echo "$out"
  expect "issued ISO-1234@B as IFC" "$out"
  evaluate
  out="$(readiness_of "$IWP")"; echo "$out"
  expect "documents_current  blocked" "$out"
  expect "resolve  " "$out"
  expect "ISO-1234" "$out"
  clause 2 "ISO-1234 and ISO-1235 pinned at A; the IFC revision B makes documents_current blocked, ISO-1234 the stale pin"

  step "[$backend] clause 3: a constraint by hand; the materials check raises one; need-by; the review groups"
  out="$(as alice tl constraint raise --project "$PROJECT" --subject "$IWP" --phase ready --severity blocking \
    --category labour --owner user:alice --description "Scaffold crew not confirmed" --due 2026-10-12)"; echo "$out"
  expect "raised " "$out"
  manual="$(awk '/^raised /{print $2}' <<<"$out")"
  [ -n "$manual" ] || fail "the manual constraint has no key"
  # the materials take-off: a derived document of ISO-1234 rev A, published, assigned to the IWP
  driver locations
  rcpt_out="$(as alice tl mat receipt receive --project "$PROJECT" --location L2 --received-on 2026-11-07 \
    --line FLG-WN-6-150-A105:6:H-7781)"; echo "$rcpt_out"
  rcpt="$(awk '/^received /{print $2}' <<<"$rcpt_out")"
  [ -n "$rcpt" ] || fail "the receipt has no key"
  as alice tl mat receipt inspect "$rcpt" --project "$PROJECT" >/dev/null
  out="$(as alice tl mat receipt accept "$rcpt" --project "$PROJECT")"; echo "$out"
  expect "$rcpt is Accepted" "$out"
  cat >"$workdir/takeoff.yaml" <<'YAML'
code: takeoff
semver: "1.0.0"
title: Material take-off
json_schema:
  type: object
  required: [line, item, qty, uom]
  properties:
    line: {type: string}
    item: {type: string}
    qty: {type: string}
    uom: {type: string}
key_column: line
target_kind: mto
mapping:
  target: mto
  key_column: line
  columns:
    - {column: line, to: number}
    - {column: item, to: item_code}
    - {column: qty, to: qty}
    - {column: uom, to: uom}
YAML
  printf 'line,item,qty,uom\n1,FLG-WN-6-150-A105,4,EA\n' >"$workdir/takeoff.csv"
  out="$(as ada tl derive schema register "$workdir/takeoff.yaml" --company)"; echo "$out"
  expect "registered takeoff@1.0.0 company" "$out"
  out="$(as alice tl derive open ISO-1234 A --schema takeoff --project "$PROJECT")"; echo "$out"
  tkey="ISO-1234@A/takeoff"
  expect "opened $tkey" "$out"
  as alice tl derive content "$tkey" "$workdir/takeoff.csv" --project "$PROJECT" >/dev/null
  as alice tl derive start "$tkey" --project "$PROJECT" >/dev/null
  as alice tl derive worker --once >/dev/null
  out="$(as alice tl derive show "$tkey" --project "$PROJECT")"; echo "$out"
  expect "state Valid" "$out"
  driver publish "$tkey"
  line="$(as alice tl mat mto list --project "$PROJECT" | awk 'NR==1{print $1}')"
  [ -n "$line" ] || fail "the take-off published no MTO line"
  out="$(as alice tl mat mto assign "$line" --work-package "$IWP" --project "$PROJECT")"; echo "$out"
  expect "assign" "$out"
  evaluate
  out="$(readiness_of "$IWP")"; echo "$out"
  expect "materials_reserved  blocked" "$out"
  out="$(as alice tl constraint ls --project "$PROJECT")"; echo "$out"
  expect "materials" "$out"
  out="$(as alice tl constraint groups --project "$PROJECT" --by owner)"; echo "$out"
  expect "user:alice" "$out"
  out="$(as alice tl constraint groups --project "$PROJECT" --by category)"; echo "$out"
  expect "materials" "$out"
  out="$(as alice tl constraint show "$manual" --project "$PROJECT")"; echo "$out"
  expect "due 2026-10-12" "$out"
  # the reservation covers the line: the check passes and its constraint clears
  lid="$(as alice tl record show "$line" --project "$PROJECT" | awk '/^id:/{print $2}')"
  out="$(as alice tl mat move reserve --project "$PROJECT" --lot "$rcpt@1" --qty 4 --uom EA --from L2 --for-line "$lid")"; echo "$out"
  expect "reserve 4 EA lot $rcpt@1" "$out"
  evaluate
  out="$(readiness_of "$IWP")"; echo "$out"
  expect "materials_reserved  ok" "$out"
  clause 3 "a constraint raised by hand and one by the materials check; need-by 2026-10-12 (4 weeks before 2026-11-09); the review groups by owner and category"

  step "[$backend] clause 4: readiness 7/9; re-pin and clear give 9/9; IWP.Ready reaches the receiver"
  rport="$(cat "$workdir/receiver.port")"
  out="$(as demo tl webhook add --name iwp-ready --url "http://127.0.0.1:$rport/iwp" --project "$PROJECT" --event-type IWP.Ready)"; echo "$out" | sed 's/secret .*/secret (hidden)/'
  awk '$1 == "secret" {print $2}' <<<"$out" >"$workdir/receiver.secret"
  [ -s "$workdir/receiver.secret" ] || fail "the webhook subscription printed no signing secret"
  out="$(readiness_of "$IWP")"; echo "$out"
  expect "checks  7/9" "$out"
  expect "documents_current  blocked" "$out"
  expect "constraints_cleared  blocked" "$out"
  link="$(as alice tl doc stale --project "$PROJECT" | awk '$3 == "ISO-1234" {print $NF; exit}')"
  [ -n "$link" ] || fail "doc stale names no link for ISO-1234"
  out="$(as alice tl doc repin "$link" --project "$PROJECT" --apply)"; echo "$out"
  as alice tl constraint clear "$manual" --project "$PROJECT" --reason "scaffold crew confirmed" >/dev/null
  evaluate
  out="$(readiness_of "$IWP")"; echo "$out"
  expect "checks  9/9" "$out"
  out="$(as demo tl webhook run --once --allow-host 127.0.0.1)"; echo "$out"
  sleep 0.5
  driver received "$workdir" "$IWP"
  clause 4 "readiness 7/9 with documents_current and constraints_cleared blocked; re-pin and clear give 9/9; IWP.Ready verified at the receiver"

  step "[$backend] clause 5: a plain user refused; two distinct signers; the same signer twice refused; a wrong hash refused"
  out="$(as alice tl awp iwp hash "$IWP" --project "$PROJECT")"; echo "$out"
  hash="$(awk '/^record hash /{print $3}' <<<"$out")"
  [ -n "$hash" ] || fail "no record hash for $IWP"
  refuse "forbidden" as plain tl awp iwp sign-off "$IWP" --project "$PROJECT" --hash "$hash"
  out="$(as dora tl awp iwp sign-off "$IWP" --project "$PROJECT" --hash "$hash")"; echo "$out"
  expect "sign-off $IWP  version" "$out"
  refuse "already signed" as dora tl awp iwp sign-off "$IWP" --project "$PROJECT" --hash "$hash"
  refuse "changed since the hash was read" as sue tl awp iwp sign-off "$IWP" --project "$PROJECT" \
    --hash "0000000000000000000000000000000000000000000000000000000000000000"
  out="$(as sue tl awp iwp sign-off "$IWP" --project "$PROJECT" --hash "$hash")"; echo "$out"
  expect "sign-off $IWP  version" "$out"
  out="$(as alice tl awp iwp show "$IWP" --project "$PROJECT")"; echo "$out"
  expect "signoffs 2" "$out"
  clause 5 "plain user refused; dora and sue signed the record hash; a second dora signature and a wrong hash refused"

  step "[$backend] clause 6: issue to the foreman; the permit to work is reported missing, not blocking"
  out="$(as dora tl awp iwp issue "$IWP" --project "$PROJECT" --hash "$hash" --foreman user:frank)"; echo "$out"
  expect "issue $IWP  version" "$out"
  out="$(as alice tl awp iwp show "$IWP" --project "$PROJECT")"; echo "$out"
  expect "state Issued" "$out"
  expect "foreman user:frank" "$out"
  out="$(as alice tl link list "$IWP" --project "$PROJECT")"; echo "$out"
  expect "missing permit to work (rule: requires@Issued)" "$out"
  expect "state Issued" "$(as alice tl awp iwp show "$IWP" --project "$PROJECT")"
  clause 6 "issued to user:frank; the permit to work is reported missing and nothing is blocked"

  step "[$backend] clause 7: an oversize IWP warns; the split makes two"
  out="$(as alice tl awp iwp create --project "$PROJECT" --discipline PIP --title "Oversize spool set" \
    --planned-start 2026-12-01 --planned-finish 2027-02-26 --foreman user:frank --hours 900)"; echo "$out"
  big="$(awk '/^created IWP /{print $3}' <<<"$out")"
  [ -n "$big" ] || fail "the oversize IWP has no number"
  bigkeys=()
  for n in 1 2 3 4; do
    out="$(as alice tl awp iwp item-create --project "$PROJECT" --commodity piping --description "Oversize spool $n" --qty 5 --uom m --hours 200)"
    bigkeys+=("$(last_word "$out")")
  done
  as alice tl awp iwp add-scope "$big" "${bigkeys[@]}" --project "$PROJECT" >/dev/null
  driver oversize "$big"
  out="$(as alice tl awp iwp split "$big" --project "$PROJECT" --reason "oversize: split by scope" \
    --group "${bigkeys[0]},${bigkeys[1]}" --group "${bigkeys[2]},${bigkeys[3]}")"; echo "$out"
  expect "split $big" "$out"
  out="$(as alice tl awp iwp ls --project "$PROJECT" --state Draft)"; echo "$out"
  [ "$(grep -c "IWP-PIP-" <<<"$out" || true)" -ge 2 ] || fail "the split made no two IWPs"
  clause 7 "$big (900 hours) warns; the split makes two IWPs"

  step "[$backend] clause 8: an agent proposes scope over MCP; a person accepts it"
  out="$(as alice tl awp iwp create --project "$PROJECT" --discipline PIP --title "Support steel set" \
    --planned-start 2026-12-14 --planned-finish 2027-01-22 --foreman user:frank --hours 90)"; echo "$out"
  small="$(awk '/^created IWP /{print $3}' <<<"$out")"
  out="$(as alice tl awp iwp item-create --project "$PROJECT" --commodity structural-steel --description "Support, proposed" --qty 40 --uom kg --hours 3)"
  proposed="$(last_word "$out")"
  driver propose "$small" "$proposed"
  pid="$(cat "$TL_DEMO_STATE")"
  out="$(as alice tl proposal ls --project "$PROJECT")"; echo "$out"
  expect "$pid" "$out"
  out="$(as alice tl awp iwp scope "$small" --project "$PROJECT")"
  case "$out" in *"$proposed"*) fail "a proposal put scope on $small before a person accepted it" ;; esac
  out="$(as alice tl proposal accept "$pid")"; echo "$out"
  expect "accepted $pid" "$out"
  out="$(as alice tl awp iwp scope "$small" --project "$PROJECT")"; echo "$out"
  expect "$proposed" "$out"
  clause 8 "the agent's propose_iwp_scope waited; alice accepted it; $proposed is on $small"

  step "[$backend] clause 9: the same state over the API, the TUI, the web and MCP; readiness history; the backlog"
  driver screens "$IWP"
  history="$(as demo tl events tail --project "$PROJECT" -n 2000 2>/dev/null | grep -c 'IWP.ReadinessEvaluated' || true)"
  [ "$history" -ge 3 ] || fail "the ledger holds $history readiness evaluations, not three"
  echo "readiness evaluations in the ledger: $history"
  driver backlog
  clause 9 "the API, the TUI, the web and MCP show $IWP as the CLI does; readiness history in the ledger; the backlog tile shows weeks per foreman"

  step "[$backend] clause 10: the simulator; a sim project with its awp roles by hand; a short run with iwp_planner"
  as ada tl admin roles grant dora --project sim-iwp1 --module awp --role superuser --reason demo >/dev/null
  cat >"$workdir/iwp-planner.yaml" <<'YAML'
scenario: iwp-planner
seed: 31
start: 2026-11-02
duration_days: 2
template: small-piping
operators: [user:dora]
actors:
  iwp_planner: {iwps_per_day: 1, scope_items: 3, constraint_rate: 1.0, clears_per_day: 1}
YAML
  out="$(as demo tl sim create "$workdir/iwp-planner.yaml" --run-id iwp1)"; echo "$out"
  out="$(as demo tl sim advance --run iwp1 --days 2)"; echo "$out"
  out="$(as dora tl awp iwp ls --project sim-iwp1)"; echo "$out"
  [ "$(grep -c -- '-IWP-' <<<"$out" || true)" -ge 1 ] || fail "the planner made no IWP in sim-iwp1"
  out="$(as dora tl constraint ls --project sim-iwp1)"; echo "$out"
  [ "$(grep -c -- '-CON-' <<<"$out" || true)" -ge 1 ] || fail "the planner raised no constraint in sim-iwp1"
  if ! out="$(as demo tl sim assert --run iwp1 2>&1)"; then echo "$out"; fail "tl sim assert found a difference"; fi
  echo "$out"
  clause 10 "iwp_planner built IWPs in sim-iwp1 and raised constraints; tl sim assert holds"

  stop_receiver
  stop_server
  drop_pg
  echo "[$backend] clauses 1-10 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-I2 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
