#!/usr/bin/env bash
# Demo for P2-QR (QR codes at the workface: labels, the scan page, status cards): `just demo P2-QR`.
#
# The eight clauses of docs/tickets/P2-QR/README.md "Demo", each ending in a `PASS clause N: ...` line
# that is printed only after its check returned success (a command's exit code and output, or a
# driver assertion in dev/demos/p2_qr_demo.py):
#   1  the label is refused while api.public_base_url is unset (the shipped file); with it set, a
#      label file whose QR text is <base>/web/q/<16 chars> and that holds no key, id or project;
#   2  signed out, the code and a nonsense path give the same sign-in bounce; signed in as uma, the
#      card shows its banner, key, "as of" and lines;
#   3  4 of 6 miss kinds (malformed, unknown, revoked, hidden) give byte-identical 404 pages for uma;
#      expired and no-view-word are in test_scan_page.py (not makeable by commands);
#   4  rotate: the old code is a miss, the new one resolves; `tl qr ls` shows both rows and no code;
#      eleven lookups in one session give one 429 on the eleventh;
#   5  scaffold card: deferred (tl_mod_scaffold has no scan_card; the driver checks it);
#   6  an agent token is refused on the scan path (401) and the API routes (403) before any lookup; a
#      signed-in person gets the 404 miss; `tl qr export --format jsonl` rows equal `tl qr ls` rows;
#   7  `tl qr resolve` (code on standard input) prints the same banner and lines the page shows;
#   8  a label for an inspection and one for a permit resolve to their status cards.
#
# The api.public_base_url setting is platform-only: `tl config set` refuses it at every layer. The
# shipped schema/settings/platform.yaml is never changed. The label calls read a scratch copy of it,
# written under this demo's own temporary directory, through TL_SETTINGS_PLATFORM_FILE; only those
# calls export the variable. The base address is the demo's own loopback server.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Clauses 1-8 run on
# both backends. Postgres is a throw-away database on TL_PG_URL (default
# postgresql://postgres:postgres@localhost:5432/tl_test, `just dev up`), dropped afterwards; an
# unreachable server is a failure, not a skip. The API is `tl serve` on a free loopback port over a
# temporary ledger, stopped afterwards. Nothing is left behind. Exits non-zero (and prints DEMO FAILED)
# when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
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
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'stop_server; drop_pg; rm -rf "$workdir"' EXIT

PROJECT=P123
export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_LAKE_DIR="$workdir/lake"
export TL_WEB=on
export P2_QR_WORKDIR="$workdir"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN
unset TL_SETTINGS_PLATFORM_FILE

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2"; }
driver() { # driver MODE [ARG...]: the web and label-file checks; their output is shown, stderr is kept
  local began=$SECONDS
  quiet uv run python dev/demos/p2_qr_demo.py "$@" 2>"$workdir/driver.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/driver.err" >&2; fail "a check was not met: $*"; }
  echo "(driver $1: $((SECONDS - began)) s)"
}
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
labelling() { # labelling NAME cmd...: as NAME, with the scratch platform settings (the base address set)
  ( export TL_SETTINGS_PLATFORM_FILE="$workdir/platform.yaml"; as "$@" )
}
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}
refuse() { # refuse TEXT cmd...: the command must fail and say TEXT
  local text="$1" out; shift
  if out="$("$@" 2>&1)"; then echo "$out"; fail "this was accepted: $*"; fi
  echo "$out"; expect "$text" "$out"
}
code_of() { # code_of LABEL: the plain code, for standard input only (never printed or put in argv)
  sed -n 's/.*<div class="code">\([A-Z0-9-]*\)<\/div>.*/\1/p' "$1" | tr -d '-'
}
reg_of() { awk '{print $2}' <<<"$1"; } # reg_of OUTPUT: the register id of a one-line verb output
ls_rows() { awk 'NR>1' "$1" | wc -l | tr -d ' '; }

run_backend() {
  local backend="$1" port url out iwp insp permit hidden_permit num reg_old reg_new reg_rev token
  local iwp_label="$workdir/iwp-label.html" iwp_new="$workdir/iwp-label-new.html"
  local rev_label="$workdir/iwp-label-revoked.html" hidden_label="$workdir/permit-hidden-label.html"
  local insp_label="$workdir/insp-label.html" permit_label="$workdir/permit-label.html"
  step "[$backend] a new ledger, the people, and the grants the clauses need"
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake" "$workdir"/session-* "$workdir"/*.html "$workdir"/*.out "$workdir"/*.err
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
  printf '%s\n' "a long passphrase for uma" | as demo tl admin user add uma --display-name "Uma" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for sue" | as demo tl admin user add sue --display-name "Sue" --role document_controller --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for rob" | as demo tl admin user add rob --display-name "Rob" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for dora" | as demo tl admin user add dora --display-name "Dora" --role document_controller --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for frank" | as demo tl admin user add frank --display-name "Frank" --password-stdin >/dev/null
  for who in uma sue rob dora frank; do
    printf '%s\n' "a long passphrase for $who" | as "$who" tl login "$who" --password-stdin >/dev/null
  done
  for std in schema/fixtures/standards/co.acme.standards@1.0.0.yaml schema/fixtures/standards/co.acme.awp@1.0.0.yaml \
    schema/fixtures/standards/co.acme.documents@1.0.0.yaml; do
    as demo tl standards load "$std" >/dev/null
  done
  as demo tl admin roles grant sue --project "$PROJECT" --module awp --role superuser --reason demo >/dev/null
  as demo tl admin roles grant sue --project "$PROJECT" --module quality --role superuser --reason demo >/dev/null
  as demo tl admin roles grant sue --project "$PROJECT" --module permits --role superuser --reason demo >/dev/null
  as demo tl admin roles grant sue --project "$PROJECT" --module qr --role superuser --reason demo >/dev/null
  as demo tl admin roles grant dora --project "$PROJECT" --module documents --role superuser --reason demo >/dev/null
  # an agent with an explicit module grant, made by the admin CLI as P2-PUNCH.sh does (agent_grant.py
  # fails on Postgres: PostgresUowFactory has no close), and a token for it
  as demo tl admin user add triage --kind agent >/dev/null
  as demo tl admin roles grant triage --project "$PROJECT" --module '*' --role user --reason "the demo agent may file proposals" >/dev/null
  token="$(as demo tl admin token issue triage --label demo 2>/dev/null)"
  [ -n "$token" ] || fail "the agent token was not issued"

  step "[$backend] the setup: one IWP, an inspection and a permit on it; a permit on a correspondence item"
  out="$(as sue tl awp iwp create --project "$PROJECT" --discipline PIP --title "Pipe rack spools, level 1" \
    --planned-start 2026-11-09 --planned-finish 2027-01-29 --foreman user:frank --hours 120)"; echo "$out"
  expect "created IWP" "$out"
  iwp="$(as sue tl awp iwp ls --project "$PROJECT" | awk 'NR==2{print $1}')"
  [ -n "$iwp" ] || fail "the IWP list shows no IWP"
  out="$(as uma tl insp plan --project "$PROJECT" --subject "$iwp" --title "Flange make-up" --point hold)"; echo "$out"
  insp="$(reg_of "$out")"
  [ -n "$insp" ] || fail "the inspection has no key"
  out="$(as rob tl permit request --project "$PROJECT" --type general --area A1 --location "Pump room" \
    --description "Weld repair, rack 12" --holder Rob --from 2026-12-01 --until 2026-12-31 --for "$iwp")"; echo "$out"
  permit="$(reg_of "$out")"
  [ -n "$permit" ] || fail "the permit has no key"
  out="$(as dora tl corr receive --project "$PROJECT" --subject "Permit query" --body "Is the pump room open?")"; echo "$out"
  num="$(awk '/^received /{print $2}' <<<"$out")"
  [ -n "$num" ] || fail "the correspondence item has no number"
  out="$(as rob tl permit request --project "$PROJECT" --type general --area A1 --location "Pump room" \
    --description "Hot work near the query" --holder Rob --from 2026-12-01 --until 2026-12-31 --for "$num")"; echo "$out"
  hidden_permit="$(reg_of "$out")"
  [ -n "$hidden_permit" ] || fail "the permit on the correspondence item has no key"

  step "[$backend] the server on a free loopback port; the scratch platform settings with its base address"
  port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  url="http://127.0.0.1:$port"
  driver platform schema/settings/platform.yaml "$workdir/platform.yaml" "$url"
  export TL_API_URL="$url" P2_QR_BASE="$url" P2_QR_AGENT_TOKEN="$token"
  setsid uv run tl serve --port "$port" >"$workdir/server-$backend.log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 150); do
    curl -fs "$url/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  curl -fs "$url/health" | grep -q '"status":"ok"' || { cat "$workdir/server-$backend.log" >&2; fail "the server did not start"; }
  echo "(serving $backend at $url)"

  step "[$backend] clause 1: refused without the base address; with it, a label file with no key, id or project"
  refuse "error: set api.public_base_url first" as uma tl qr label "$iwp" --project "$PROJECT" --output "$iwp_label"
  [ ! -e "$iwp_label" ] || fail "a refused label wrote a file"
  out="$(labelling uma tl qr label "$iwp" --project "$PROJECT" --output "$iwp_label" 2>/dev/null)"; echo "$out"
  expect "label " "$out"
  reg_old="$(reg_of "$out")"
  printf '%s\n' "$out" >"$workdir/iwp-label.out"
  driver label-check "$iwp_label" "$workdir/iwp-label.out" "$iwp" "$PROJECT"
  clause 1 "unset: refused with the fixed text and no file; set: $reg_old writes a label that holds no key, id or project"

  step "[$backend] clause 2: signed out, the same bounce for a code and a nonsense path; signed in, the card"
  driver clause2 "$iwp_label" "$iwp"
  clause 2 "signed out, the code and a nonsense path both bounce to sign-in (303, same body); uma's card for $iwp has its banner, key, as-of and lines"

  step "[$backend] clause 3: four misses for uma give one 404 page (malformed, unknown, revoked, hidden)"
  out="$(labelling uma tl qr label "$iwp" --project "$PROJECT" --output "$rev_label" 2>/dev/null)"; echo "$out"
  reg_rev="$(reg_of "$out")"
  as sue tl qr revoke "$reg_rev" --project "$PROJECT" --reason "printed in error" >/dev/null
  out="$(labelling sue tl qr label "$hidden_permit" --project "$PROJECT" --output "$hidden_label" 2>/dev/null)"; echo "$out"
  driver visible "$hidden_label"
  as dora tl corr class set "$num" --project "$PROJECT" --to restricted --reason Legal >/dev/null
  driver clause3 "$rev_label" "$hidden_label"
  clause 3 "uma: malformed, unknown, revoked and a code restricted after its label was made give byte-identical 404 pages (4 of 6 miss kinds; expired and no-view-word are in test_scan_page.py)"

  step "[$backend] clause 4: rotate; the old code misses, the new one resolves; ls shows both rows and no code"
  out="$(labelling uma tl qr rotate "$reg_old" --project "$PROJECT" --reason lost --output "$iwp_new")"; echo "$out"
  reg_new="$(reg_of "$out")"
  driver clause4-hit "$iwp_new" "$iwp"
  driver clause4-misses "$iwp_label"
  out="$(as uma tl qr ls "$iwp" --project "$PROJECT")"; echo "$out" >"$workdir/ls4.out"; echo "$out"
  expect "scan codes: 3" "$out"
  expect "$reg_old" "$out"
  expect "$reg_new" "$out"
  driver no-code "$workdir/ls4.out" "$iwp_label" "$iwp_new" "$rev_label"
  clause 4 "rotated $reg_old to $reg_new: the old code misses, the new one resolves; ls lists both (and the revoked one) and no code; eleven lookups in one session give the 429 on the eleventh"

  step "[$backend] clause 5: the scaffold card"
  driver clause5
  clause 5 "deferred (scaffold card not built)"

  step "[$backend] clause 6: an agent token is refused before any lookup; a person gets the 404; export equals ls"
  driver clause6-agent "$iwp_new" "$iwp"
  out="$(as uma tl qr export "$iwp" --project "$PROJECT" --format jsonl)"; echo "$out" >"$workdir/export6.jsonl"
  out="$(as uma tl qr ls "$iwp" --project "$PROJECT")"; echo "$out" >"$workdir/ls6.out"
  driver export-eq "$workdir/ls6.out" "$workdir/export6.jsonl"
  clause 6 "an agent token: 401 on the scan path, 403 on /qr/codes and /qr/resolve, no card; uma gets the 404 miss; export rows equal ls rows"

  step "[$backend] clause 7: tl qr resolve (code on standard input) prints the card the page shows"
  printf '%s\n' "$(code_of "$iwp_new")" | as uma tl qr resolve --project "$PROJECT" >"$workdir/resolve7.out"
  cat "$workdir/resolve7.out"
  driver card-compare "$iwp_new" "$workdir/resolve7.out"
  clause 7 "tl qr resolve prints the banner, key, title and lines that uma's page shows for $iwp"

  step "[$backend] clause 8: a label for the inspection and one for the permit each resolve to their card"
  out="$(labelling uma tl qr label "$insp" --project "$PROJECT" --output "$insp_label" 2>/dev/null)"; echo "$out"
  printf '%s\n' "$(code_of "$insp_label")" | as uma tl qr resolve --project "$PROJECT" >"$workdir/insp8.out"
  driver card-compare "$insp_label" "$workdir/insp8.out" "HOLD POINT - not released"
  out="$(labelling uma tl qr label "$permit" --project "$PROJECT" --output "$permit_label" 2>/dev/null)"; echo "$out"
  printf '%s\n' "$(code_of "$permit_label")" | as uma tl qr resolve --project "$PROJECT" >"$workdir/permit8.out"
  driver card-compare "$permit_label" "$workdir/permit8.out" "REQUESTED - not approved"
  clause 8 "the inspection label shows its hold-point banner and the permit label REQUESTED - not approved; both match tl qr resolve"

  stop_server
  drop_pg
  echo "[$backend] clauses 1-8 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-QR demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
