#!/usr/bin/env bash
# Demo for P1-I7 workstream A (the integration layer: inbound endpoints, rules, enrichment,
# actions): `just demo P1-I7`.
#
# The exit clauses (FANOUT D20), each ending in a PASS line, once on SQLite and once on Postgres:
#   1  an admin creates the inbound endpoint acme-nde/results (HMAC); its dry run shows the plan;
#      enabled and live, a signed POST is 202 and the records change with source
#      inbound:acme-nde/results; the same POST again, an unsigned one and a wrong endpoint give 401,
#      401 and 404; a delivery the mapping cannot apply lands in the error queue and is retried with
#      a corrected payload;
#   2  rule hse-notify: a post with #safety makes the feed post "HSE notified" (act mode); its dry
#      run over recent events lists what it would have done; two rules that answer each other stop
#      at depth 3;
#   3  doc_classifier proposes a doc_type for a registered document; a person accepts it from the
#      review queue and it reads back from psets.enrich.doc_classifier.doc_type;
#   4  the same action runs from a record thread: `/dispatch send_to_nde method=UT` on V-1001, as
#      a person, previewed and confirmed (workstream B's /dispatch); the receiver verifies a
#      second signed POST and the invocation is by the person who dispatched it. (It runs after
#      clause 5 in this script because it needs the action that clause defines.)
#   5  action send_to_nde (a signed webhook to the loopback receiver, allow-listed) is invoked and
#      the receiver verifies it;
#   6  a user cannot author anything here; no signing secret is in the ledger; the kill switch stops
#      the layer at once.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. Starts
# `tl serve` on a free loopback port and a receiver over a temporary ledger; nothing is left behind.
# Exits non-zero (and prints DEMO FAILED) when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
receiver_pid=""
pg_url=""
stop_group() { # the process has its own process group (setsid): stop the whole group
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || true
  for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
  kill -KILL -- "-$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
stop_all() {
  stop_group "$server_pid"; server_pid=""
  stop_group "$receiver_pid"; receiver_pid=""
}
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'stop_all; drop_pg; rm -rf "$workdir"' EXIT

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i7_demo.py "$@" || fail "an exit clause was not met"; }
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
status_of() { # status_of PATH MODE MESSAGE_ID PAYLOAD: the HTTP status of a POST to the API
  driver post "$workdir" "$1" "$2" "$3" "$4"
}

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, two people, the API on a free loopback port, a receiver"
  stop_all
  rm -f "$workdir"/receiver.* "$workdir"/endpoint.secret
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
  printf '%s\n' "a long passphrase for amy" | as demo tl admin user add amy --display-name "Amy A" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for amy" | as amy tl login amy --password-stdin >/dev/null
  driver prepare "$workdir"
  setsid uv run python dev/demos/p1_i7_demo.py receiver "$workdir" >"$workdir/receiver-$backend.log" 2>&1 &
  receiver_pid=$!
  for _ in $(seq 1 100); do [ -s "$workdir/receiver.port" ] && break; sleep 0.1; done
  [ -s "$workdir/receiver.port" ] || fail "the receiver did not start"
  as demo tl config set webhooks.egress.allowlist 127.0.0.1 --company --reason "the demo receiver" --accept-risk >/dev/null
  as demo tl record create --project P123 --title "Valve 1" --key V-1001 >/dev/null
  as demo tl record create --project P123 --title "Valve 2" --key V-1002 >/dev/null

  step "[$backend] clause 1: an inbound endpoint, from dry run to a signed delivery"
  refuse "forbidden" as amy tl integration app add acme-nde --label "Acme NDE" --project P123
  out="$(as demo tl integration app add acme-nde --label "Acme NDE" --project P123)"; echo "$out"
  expect "app acme-nde" "$out"
  out="$(as demo tl endpoint create acme-nde/results --project P123 --mapping-file "$workdir/map.jsonata" --allow SetPsetValues)"
  echo "$out" | sed 's/^secret .*/secret ***/'
  expect "endpoint acme-nde/results" "$out"
  echo "$out" | sed -n 's/^secret //p' >"$workdir/endpoint.secret"
  [ -s "$workdir/endpoint.secret" ] || fail "no signing secret was printed"
  out="$(as demo tl endpoint show acme-nde/results --project P123)"; echo "$out"
  expect "dry-run" "$out"
  case "$out" in *"$(cat "$workdir/endpoint.secret")"*) fail "show printed the secret" ;; esac
  out="$(as demo tl delivery dry-run acme-nde/results --project P123 --sample "$workdir/payload.json")"; echo "$out"
  expect "SetPsetValues" "$out"
  [ "$(status_of /in/acme-nde/results signed m1 "$workdir/payload.json")" = 404 ] || fail "a disabled endpoint must answer 404"
  as demo tl endpoint mode acme-nde/results live --reason "the dry run looked right" --project P123 >/dev/null
  as demo tl endpoint enable acme-nde/results --project P123 >/dev/null
  [ "$(status_of /in/acme-nde/results signed m1 "$workdir/payload.json")" = 202 ] || fail "a signed POST must be 202"
  out="$(as demo tl integration serve --once)"; echo "$out"
  expect "jobs 1" "$out"
  [ "$(status_of /in/acme-nde/results signed m1 "$workdir/payload.json")" = 401 ] || fail "the same POST again must be 401"
  [ "$(status_of /in/acme-nde/results unsigned m2 "$workdir/payload.json")" = 401 ] || fail "an unsigned POST must be 401"
  [ "$(status_of /in/acme-nde/nothing signed m3 "$workdir/payload.json")" = 404 ] || fail "a wrong endpoint must be 404"
  [ "$(status_of /in/acme-nde/results signed m4 "$workdir/bad-payload.json")" = 202 ] || fail "a signed POST must be 202"
  as demo tl integration serve --once >/dev/null
  out="$(as demo tl delivery ls --state failed)"; echo "$out"
  expect "key_not_found" "$out"
  bad="$(echo "$out" | awk 'NR==1{print $1}')"
  out="$(as demo tl delivery show "$bad" --project P123)"; echo "$out"
  case "$out" in *V-9999*) fail "the error queue printed the payload" ;; esac
  as demo tl delivery retry "$bad" --project P123 --file "$workdir/fixed-payload.json" >/dev/null
  as demo tl integration serve --once >/dev/null
  driver inbound
  passed_1="the signed POST changed the records; the replay, the unsigned POST and the wrong endpoint were refused; the failed delivery was retried with a corrected payload"
  echo "PASS 1: $passed_1"

  step "[$backend] clause 2: rules, a dry run, and a loop that stops"
  refuse "forbidden" as amy tl rule create --file "$workdir/hse.json" --project P123
  as demo tl feed post "Earlier: gas alarm in unit 47 #safety" --project P123 >/dev/null
  as demo tl rule create --file "$workdir/hse.json" --project P123 >/dev/null
  out="$(as demo tl rule dry-run hse-notify --project P123)"; echo "$out"
  expect "firings 1" "$out"
  expect "PostToFeed" "$out"
  as demo tl rule mode hse-notify act --reason "the dry run looked right" --project P123 >/dev/null
  as demo tl rule enable hse-notify --project P123 >/dev/null
  as demo tl feed post "Gas alarm in unit 47 #safety" --project P123 >/dev/null
  as demo tl integration serve --once >/dev/null
  out="$(as demo tl feed ls --project P123)"
  expect "svc:rule-hse-notify" "$out"
  expect "HSE notified" "$out"
  for key in ping pong; do
    as demo tl rule create --file "$workdir/$key.json" --project P123 >/dev/null
    as demo tl rule mode "$key" act --reason "the demo loop" --project P123 >/dev/null
    as demo tl rule enable "$key" --project P123 >/dev/null
  done
  as demo tl feed post "start #ping" --project P123 >/dev/null
  as demo tl integration serve --once >/dev/null
  driver rules

  step "[$backend] clause 3: doc_classifier proposes, a person decides"
  as demo tl enricher register doc_classifier --file "$workdir/enricher.json" --project P123 >/dev/null
  as demo tl enricher enable doc_classifier --project P123 >/dev/null
  as amy tl doc register ISD-001 --project P123 --title "Piping isometric drawing, unit 47" >/dev/null
  as demo tl integration serve --once >/dev/null
  out="$(as amy tl enrich ls --project P123)"; echo "$out"
  expect "enrich.doc_classifier.doc_type" "$out"
  expect '"ISO"' "$out"
  type_id="$(echo "$out" | awk '/doc_classifier.doc_type/{print $1}')"
  other_id="$(echo "$out" | awk '/doc_classifier.discipline/{print $1}')"
  as amy tl enrich accept "$type_id" --project P123 >/dev/null
  as amy tl enrich reject "$other_id" --reason "not what this team calls it" --project P123 >/dev/null
  out="$(as amy tl pset get ISD-001 --project P123)"; echo "$out"
  expect '"doc_type":"ISO"' "$out"
  driver enrichment

  step "[$backend] clause 5: an action, a signed webhook, a verified receipt"
  driver action-file "$workdir"
  refuse "forbidden" as amy tl action define --file "$workdir/action.json" --project P123
  out="$(as demo tl action define --file "$workdir/action.json" --project P123)"
  echo "$out" | sed 's/^secret .*/secret ***/'
  echo "$out" | sed -n 's/^secret //p' >"$workdir/receiver.secret"
  [ -s "$workdir/receiver.secret" ] || fail "no action secret was printed"
  sleep 0.5 # the receiver picks the secret up
  out="$(as amy tl action invoke send_to_nde --project P123 --target V-1001 --param method=RT)"; echo "$out"
  as demo tl integration serve --once >/dev/null
  for _ in $(seq 1 50); do [ -s "$workdir/receiver.log" ] && break; sleep 0.1; done
  out="$(as amy tl action invocations)"; echo "$out"
  expect "completed" "$out"
  driver action "$workdir"

  step "[$backend] clause 4: the same action, run from a record thread's /dispatch"
  refuse "threads are not switched on" as amy tl thread post --project P123 V-1001 "too early"
  as demo tl config set threads.enabled true --company --reason "the demo" >/dev/null
  as demo tl config set threads.enabled_types core.Record --company --reason "the demo" >/dev/null
  out="$(as amy tl thread preview --project P123 V-1001 "/dispatch send_to_nde method=UT")"; echo "$out"
  expect "send_to_nde" "$out"
  out="$(as amy tl thread dispatch --project P123 V-1001 "/dispatch send_to_nde method=UT" --yes)"; echo "$out"
  expect "dispatched" "$out"
  as demo tl integration serve --once >/dev/null
  for _ in $(seq 1 50); do [ "$(wc -l <"$workdir/receiver.log")" -ge 2 ] && break; sleep 0.1; done
  driver thread-action "$workdir"
  echo "PASS 4: an action ran from a thread's /dispatch and the receiver verified it"

  step "[$backend] clause 6: no secret in the ledger; the kill switch stops the layer"
  driver secrets "$workdir"
  as demo tl config set integration.kill_switch true --company --reason "the demo" --accept-risk >/dev/null
  out="$(as demo tl integration status)"; echo "$out" | sed -n 1p
  expect "kill_switch on" "$out"
  [ "$(status_of /in/acme-nde/results signed m9 "$workdir/payload.json")" = 404 ] || fail "the kill switch must answer 404"
  as demo tl config set integration.kill_switch false --company --reason "the demo is over" --accept-risk >/dev/null
  echo "PASS 6b: with the kill switch on, inbound answered the fixed 404"

  stop_all
  drop_pg
  echo "[$backend] all clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I7 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
