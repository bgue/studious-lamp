#!/usr/bin/env bash
# Demo for P1-I2b (the document controller role, ADR-0013): `just demo P1-I2b`.
#
# The exit clauses, each ending in a PASS line, once on SQLite and once on Postgres:
#   1  a plain user prepares a revision (register, draft, PDF) and is refused the controlling acts
#      (issue a revision, issue a transmittal, import with --apply);
#   2  an admin grants `document_controller` to that person with `tl admin user roles --add`; the
#      account events record who and why;
#   3  the controller issues the revision and the transmittal, with no admin session, and the
#      ledger names the controller as the actor;
#   4  the controller is not an admin: she cannot create an account, change a role (her own
#      included), issue a token or recover a link, and an agent account cannot hold the role;
#   5  the HTTP matrix: user, document controller, admin and agent over the controlling commands;
#   6  the TUI: the accounts screen offers the role (key c) and the transmittal composer issues for
#      a controller (Ctrl+T) and says what is missing to anyone else;
#   7  the admin takes the role away and the same person is refused again; demo/demo still works.
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
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i2b_demo.py "$@" || fail "an exit clause was not met"; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}

STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
DOC_STANDARDS=schema/fixtures/standards/co.acme.documents@1.0.0.yaml
DMS_MAPPING=dev/seed/templates/document-register-dms-export.yaml
DMS_FILE=dev/seed/legacy/dms-document-register.csv
NEEDS="needs the document_controller or admin role"

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
  export TL_DEMO_DORA_PASSWORD="a long passphrase for dora"
  printf '%s\n' "$TL_DEMO_DORA_PASSWORD" | as demo tl admin user add dora --display-name "Dora C" --password-stdin >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  TL_DEMO_AGENT_TOKEN="$(as demo tl admin token issue triage --label demo 2>/dev/null)"
  export TL_DEMO_AGENT_TOKEN
  case "$TL_DEMO_AGENT_TOKEN" in tla_*) ;; *) fail "no agent token was issued" ;; esac
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as amy tl login amy --password-stdin >/dev/null
  printf '%s\n' "$TL_DEMO_DORA_PASSWORD" | as dora tl login dora --password-stdin >/dev/null
  as demo tl standards load "$STANDARDS" >/dev/null
  as demo tl standards load "$DOC_STANDARDS" >/dev/null

  step "[$backend] clause 1: a plain user prepares work and is refused the controlling acts"
  as amy tl doc register ISO-1234 --project P123 --title "Isometric, line 47-P-101" --type ISO --discipline PIP --originator "Acme Piping" >/dev/null
  as amy tl doc rev create ISO-1234 --project P123 --purpose "For construction" >/dev/null
  printf '%s\n' '%PDF-1.7 sheet A' >"$workdir/sheet-A.pdf"
  as amy tl doc rendition add ISO-1234 A "$workdir/sheet-A.pdf" --project P123 --kind pdf --pages 3
  out="$(as demo tl admin user show dora)"; echo "$out" | grep -E '^(username|roles)'
  expect "roles user" "$out"
  if out="$(as dora tl doc rev issue ISO-1234 A --project P123 --status IFC 2>&1)"; then fail "a plain user issued a revision"; fi
  echo "$out"
  expect "$NEEDS" "$out"
  if out="$(as amy tl doc import "$DMS_FILE" --mapping "$DMS_MAPPING" --project P123 --apply --skip-invalid 2>&1)"; then fail "a plain user applied an import"; fi
  echo "$out"
  expect "$NEEDS" "$out"
  echo "PASS 1: amy registered a document, drafted revision A and attached its PDF; issuing and importing were refused"

  step "[$backend] clause 2: an admin grants the role; the history says who and why"
  out="$(as demo tl admin user roles dora --add document_controller --reason "takes over document control")"; echo "$out"
  expect "dora  person  document_controller,user  active" "$out"
  out="$(as demo tl admin user show dora)"
  expect "roles document_controller,user" "$out"
  driver granted

  step "[$backend] clause 3: the controller issues a revision and a transmittal, no admin involved"
  out="$(as dora tl doc rev issue ISO-1234 A --project P123 --status IFC)"; echo "$out"
  expect "issued ISO-1234@A as IFC" "$out"
  out="$(as amy tl transmittal create --project P123 --subject "Isometrics for construction" --purpose for_construction --to "Site Office:Acme Construction:site@example.com" --revision ISO-1234@A)"; echo "$out"
  number="$(echo "$out" | grep -oE '[A-Z0-9]+-TRN-[0-9]+' | sed -n 1p)"
  [ -n "$number" ] || fail "no transmittal number in the output"
  if out="$(as amy tl transmittal issue "$number" --project P123 2>&1)"; then fail "a plain user issued a transmittal"; fi
  echo "$out"
  expect "$NEEDS" "$out"
  as dora tl transmittal issue "$number" --project P123
  out="$(as amy tl transmittal show "$number" --project P123)"; echo "$out"
  expect "Issued" "$out"
  out="$(as dora tl doc import "$DMS_FILE" --mapping "$DMS_MAPPING" --project P123 --apply --skip-invalid --job dms-2024)"; echo "$out" | tail -n 2
  expect "applied dms-2024: registered=" "$out"
  driver actors

  step "[$backend] clause 4: the controller is not an admin"
  for args in "admin user ls" "admin token ls" "admin user roles dora --add admin" "admin user roles amy --add document_controller"; do
    # shellcheck disable=SC2086
    if out="$(as dora tl $args 2>&1)"; then fail "dora ran: tl $args"; fi
    echo "tl $args -> $out"
    expect "forbidden" "$out"
  done
  if out="$(printf '%s\n' "a long passphrase for eve" | as dora tl admin user add eve --password-stdin 2>&1)"; then fail "dora created an account"; fi
  echo "tl admin user add eve -> $out"
  expect "forbidden" "$out"
  if out="$(as demo tl admin user add bot --kind agent --role document_controller 2>&1)"; then fail "an agent account got the role"; fi
  echo "$out"
  expect "agent account cannot hold the document_controller role" "$out"
  echo "PASS 4: dora cannot list or create accounts, change roles (hers included) or list tokens; an agent cannot hold the role"

  step "[$backend] clause 5: the HTTP matrix over the controlling commands"
  driver matrix

  step "[$backend] clause 6: the TUI offers the role to the admin and the issue key to the controller"
  driver tui

  step "[$backend] clause 7: taking the role away refuses her again; demo/demo still works"
  out="$(as demo tl admin user roles dora --remove document_controller --reason "moved to site")"; echo "$out"
  expect "dora  person  user  active" "$out"
  as amy tl doc rev create ISO-1234 --project P123 --purpose "Issued for review" >/dev/null
  printf '%s\n' '%PDF-1.7 sheet B' >"$workdir/sheet-B.pdf"
  as amy tl doc rendition add ISO-1234 B "$workdir/sheet-B.pdf" --project P123 --kind pdf --pages 4
  if out="$(as dora tl doc rev issue ISO-1234 B --project P123 --status IFR 2>&1)"; then fail "dora issued after losing the role"; fi
  echo "$out"
  expect "$NEEDS" "$out"
  out="$(as demo tl doc rev issue ISO-1234 B --project P123 --status IFR)"; echo "$out"
  expect "issued ISO-1234@B as IFR" "$out"
  out="$(printf 'demo\n' | as demo2 tl login demo --password-stdin)"; echo "$out"
  expect "demo" "$out"
  echo "PASS 7: after the role was taken away dora was refused; the admin demo still issues and signs in"

  stop_server
  drop_pg
  echo "[$backend] all clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I2b demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
