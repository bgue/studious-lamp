#!/usr/bin/env bash
# Demo for P2-FORMS (general forms: publish, fill, submit, review): `just demo P2-FORMS`.
#
# The V3-F1a clauses of docs/tickets/P2-FORMS/README.md "Demo", each ending in a `PASS clause N: ...`
# line that is printed only after its check returned success (a command's exit code and output, or
# a driver comparison in dev/demos/p2_forms_demo.py). Each clause prints its wall time; the forms
# list reads of the API are timed in the `budget` check and fail the demo over one second.
#   1  a controller publishes a template from a file (CLI); the API reads it back as JSON Schema and as
#      SurveyJS, both equal to the projection of its fields; the ETag answers 304;
#   2  a user saves a draft and submits it (CLI): the number is allocated at submit, not at the save;
#   3  a user fills a template through the runner model (one field at a time) and submits it;
#   5  a controller other than the submitter accepts it; the submitter's own review is refused with the
#      exact text; a second controller accepts a controller's own form;
#   7  a submission only its author may read answers as a missing one on every forms read (CLI and
#      API), byte for byte, for five readers;
#   8  a draft is invisible to every reader but its author (CLI and API).
# Clauses 4 and 6 (draft resume, the inspection form) belong to later units and are not run here.
#
# The ledger is the whole demo project P200 (its `forms` section included). On SQLite it is the full
# ledger tests/perf caches under .gate/demo-full (built once, about four minutes, then copied); on
# Postgres it is built into a throw-away database on TL_PG_URL (default
# postgresql://postgres:postgres@localhost:5432/tl_test, `just dev up`), dropped afterwards.
# `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". The API is `tl serve` on a
# free loopback port, stopped afterwards. Exits non-zero (and prints DEMO FAILED) when a clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
ROOT="$PWD"
workdir="$(mktemp -d)"
server_pid=""
pg_url=""
stop_group() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || true
  sleep 0.2
  kill -KILL -- "-$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
stop_server() { stop_group "$server_pid"; server_pid=""; }
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'stop_server; drop_pg; rm -rf "${workdir:?}"' EXIT

PROJECT=P200
PASS_WORD="p200-demo-pass" # demo data only (dev/seed/demo_project/core.py)
export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_LAKE_DIR="$workdir/lake"
export TL_SCHEMA_DIR="$ROOT/dev/data/demo-project-schema"
unset TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2 (${3} s)"; }
driver() {
  quiet uv run python dev/demos/p2_forms_demo.py "$@" 2>"$workdir/driver.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/driver.err" >&2; fail "a check was not met: $*"; }
}
as() { local who="$1"; shift; TL_SESSION_FILE="$workdir/session-$who.json" "$@"; }
expect() { case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac; }
refuse() { # refuse TEXT cmd...: the command must fail and say TEXT
  local text="$1" out; shift
  if out="$("$@" 2>&1)"; then echo "$out"; fail "this was accepted: $*"; fi
  echo "$out"; expect "$text" "$out"
}
last_word() { awk '{print $NF}' <<<"$1"; }

run_backend() {
  local backend="$1" port url out began tpl draft key own hsato_draft h m who
  step "[$backend] the demo project P200"
  drop_pg
  rm -rf "${workdir:?}/objects" "${workdir:?}/lake"
  rm -f "${workdir:?}"/session-* "${workdir:?}"/*.out "${workdir:?}"/*.yaml
  began=$SECONDS
  case "$backend" in
    sqlite)
      export TL_DB="$workdir/$backend.db"
      driver ledger "$TL_DB"
      ;;
    postgres)
      pg_url="$(quiet uv run python dev/demos/p1_i0_demo.py pg-create)" || fail "Postgres is not reachable at TL_PG_URL (try: just dev up)"
      export TL_DB="$pg_url"
      quiet uv run python -m dev.seed.demo_project --db "$pg_url" --objects "$workdir/objects" >"$workdir/build.out" \
        || { tail -20 "$workdir/build.out" >&2; fail "the demo project did not build on Postgres"; }
      tail -3 "$workdir/build.out"
      ;;
    *) fail "unknown backend $backend" ;;
  esac
  echo "(ledger ready: $((SECONDS - began)) s)"
  for who in mokafor ipetrov cbrooks pnair hsato treyes; do
    printf '%s\n' "$PASS_WORD" | as "$who" tl login "$who" --password-stdin >/dev/null
  done
  as mokafor tl admin roles grant ipetrov --project "$PROJECT" --module forms --role superuser \
    --reason "demo: reviews forms" >/dev/null

  port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  url="http://127.0.0.1:$port"
  export TL_API_URL="$url"
  setsid uv run tl serve --port "$port" >"$workdir/server-$backend.log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 150); do
    curl -fs "$url/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  curl -fs "$url/health" | grep -q '"status":"ok"' || { cat "$workdir/server-$backend.log" >&2; fail "the server did not start"; }
  echo "(serving $backend at $url)"

  step "[$backend] clause 1: publish a template (CLI); read it back as JSON Schema and SurveyJS (API)"
  began=$SECONDS
  driver template-file "$workdir/induction.yaml" >/dev/null
  out="$(as mokafor tl form publish "$workdir/induction.yaml")"; echo "$out"
  expect "published TPL-" "$out"
  tpl="$(awk '{print $2}' <<<"$out")"
  out="$(as cbrooks tl form ls)"; echo "$out"
  expect "$tpl" "$out"
  driver clause1 "$tpl"
  clause 1 "$tpl published; JSON Schema and SurveyJS equal the projections; the ETag answers 304" "$((SECONDS - began))"

  step "[$backend] clause 2: save a draft and submit it from the CLI; the number is taken at submit"
  began=$SECONDS
  out="$(as cbrooks tl form fill "$tpl" --project "$PROJECT" --answer topic="Scaffold tag check" --answer talk_date=2026-11-05)"; echo "$out"
  expect "saved " "$out"
  draft="$(last_word "$out")"
  out="$(as cbrooks tl form drafts --project "$PROJECT")"; echo "$out"
  expect "$draft" "$out"
  out="$(as cbrooks tl form submit "$draft" --project "$PROJECT" --answer led_by=Callum \
    --answer 'hazards_covered=Falls,Lifting' --answer ppe_checked=yes --answer attendees=9)"; echo "$out"
  expect "submitted P200-FRM-" "$out"
  key="$(last_word "$out")"
  as cbrooks tl form show "$key" --submission --project "$PROJECT"
  driver clause2 "$key" "$draft"
  clause 2 "$draft saved with no number, submitted as $key" "$((SECONDS - began))"

  step "[$backend] clause 3: fill through the runner model and submit"
  began=$SECONDS
  out="$(driver clause3 "$tpl")"; echo "$out"
  clause 3 "the runner walked $tpl one field at a time; the submission holds the confirmed answers" "$((SECONDS - began))"

  step "[$backend] clause 5: a controller who did not fill it accepts; the submitter's own review is refused"
  began=$SECONDS
  out="$(as ipetrov tl form review "$key" accept --note "Checked and filed." --project "$PROJECT")"; echo "$out"
  expect "accepted $key" "$out"
  out="$(as ipetrov tl form submit "$tpl" --project "$PROJECT" --answer topic="Controller's own talk" --answer talk_date=2026-11-05 \
    --answer led_by=Ivan --answer 'hazards_covered=Electrical' --answer ppe_checked=yes --answer attendees=4)"; echo "$out"
  own="$(last_word "$out")"
  refuse "error: the person who filled a form may not review it" \
    as ipetrov tl form review "$own" accept --project "$PROJECT"
  out="$(as mokafor tl form review "$own" accept --project "$PROJECT")"; echo "$out"
  expect "accepted $own" "$out"
  driver clause5 "$key" "$own"
  clause 5 "$key accepted by ipetrov (not its author); ipetrov's own review of $own refused with the exact text; mokafor accepted it" "$((SECONDS - began))"

  step "[$backend] clause 7: a hidden submission answers as a missing one on every forms read"
  began=$SECONDS
  for who in mokafor ipetrov treyes cbrooks pnair; do
    h="$(as "$who" tl form show P200-FRM-0012 --submission --project "$PROJECT" 2>&1 || true)"
    m="$(as "$who" tl form show P200-FRM-9999 --submission --project "$PROJECT" 2>&1 || true)"
    [ "${h//P200-FRM-0012/<ref>}" = "${m//P200-FRM-9999/<ref>}" ] || { echo "$h"; echo "$m"; fail "$who: hidden differs from missing (CLI show)"; }
    expect "no submission" "$h"
    h="$(as "$who" tl form review P200-FRM-0012 accept --project "$PROJECT" 2>&1 || true)"
    m="$(as "$who" tl form review P200-FRM-9999 accept --project "$PROJECT" 2>&1 || true)"
    [ "${h//P200-FRM-0012/<ref>}" = "${m//P200-FRM-9999/<ref>}" ] || { echo "$h"; echo "$m"; fail "$who: hidden differs from missing (CLI review)"; }
    expect "no submission" "$h"
    out="$(as "$who" tl form ls --submissions --project "$PROJECT")"
    case "$out" in *P200-FRM-0012*) fail "$who: the list shows the hidden submission" ;; esac
    echo "$who: CLI show, review and list: the same as a missing key"
  done
  driver clause7 P200-FRM-0012
  clause 7 "P200-FRM-0012 (a privileged form) is a missing key for mokafor, ipetrov, treyes, cbrooks and pnair on CLI show, review, list and the API, byte for byte" "$((SECONDS - began))"

  step "[$backend] clause 8: a draft is invisible to every reader but its author"
  began=$SECONDS
  hsato_draft="$(as hsato tl form drafts --project "$PROJECT" | awk 'NR==2{print $1}')"
  [ -n "$hsato_draft" ] || fail "hsato has no draft"
  for who in mokafor ipetrov treyes cbrooks pnair; do
    h="$(as "$who" tl form show "$hsato_draft" --submission --project "$PROJECT" 2>&1 || true)"
    m="$(as "$who" tl form show 01J000000000000000000000 --submission --project "$PROJECT" 2>&1 || true)"
    [ "${h//$hsato_draft/<ref>}" = "${m//01J000000000000000000000/<ref>}" ] || { echo "$h"; fail "$who: the draft differs from a missing id"; }
    out="$(as "$who" tl form ls --submissions --state Draft --project "$PROJECT")"
    case "$out" in *"$hsato_draft"*) fail "$who: the list shows the draft" ;; esac
  done
  out="$(as hsato tl form show "$hsato_draft" --submission --project "$PROJECT")"; echo "$out"
  expect "Draft" "$out"
  driver clause8 "$hsato_draft" hsato
  clause 8 "hsato's draft is a missing id for five other readers (CLI show and list, API); hsato reads it" "$((SECONDS - began))"

  step "[$backend] clause 11: the terminal app: open the forms log, fill a template through the runner screen"
  began=$SECONDS
  out="$(driver clause11 "$tpl")"; echo "$out"
  expect "submitted P200-FRM-" "$out"
  clause 11 "the forms log opened in the terminal app; $tpl filled through the runner screen and sent; the new number is in the log" "$((SECONDS - began))"

  step "[$backend] the forms list reads are under one second"
  driver budget

  stop_server
  drop_pg
  echo "[$backend] clauses 1, 2, 3, 5, 7, 8 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-FORMS demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
