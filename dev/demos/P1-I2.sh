#!/usr/bin/env bash
# Demo for P1-I2 (M1 Document control core: documents, revisions, renditions, pinned links,
# transmittals, review cycles): `just demo P1-I2`.
#
# The exit clauses, each ending in a PASS line, once on SQLite and once on Postgres:
#   1  the company standards and the document number pattern load; ISO-1234 is registered and
#      ISO-12 is refused with every problem;
#   2  a draft revision takes a PDF; issuing it is the admin's act (a user is refused);
#   3  a tag pinned to revision A goes stale when revision B is issued; the re-pin shows what
#      changed and only a yes moves the pin;
#   4  the stale rule is class-aware (ADR-0012): an IFR issued after an IFC leaves the IFC pins
#      alone, an IFC issued after an IFC flags them;
#   5  a transmittal lists the current revisions; issuing it is the admin's act;
#   6  a review cycle with an unanswered reviewer shows up in the overdue report;
#   7  a legacy DMS register is previewed (7 of 16 rows cannot be imported) and applied (admin only);
#   8  a user cannot void, issue or claim a system link; no one changes a document generically;
#   9  the API, the TUI document register (F7) and an agent's MCP tools read the same documents.
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
driver() { quiet uv run python dev/demos/p1_i2_demo.py "$@" || fail "an exit clause was not met"; }
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
  export TL_DEMO_ANA_PASSWORD="a long passphrase for ana"
  printf '%s\n' "$TL_DEMO_ANA_PASSWORD" | as demo tl admin user add ana --display-name "Ana B" --password-stdin >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  TL_DEMO_AGENT_TOKEN="$(as demo tl admin token issue triage --label demo 2>/dev/null)"
  export TL_DEMO_AGENT_TOKEN
  case "$TL_DEMO_AGENT_TOKEN" in tla_*) ;; *) fail "no agent token was issued" ;; esac
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as amy tl login amy --password-stdin >/dev/null

  step "[$backend] clause 1: the standards and the number pattern load; a wrong number is refused"
  as demo tl standards load "$STANDARDS" >/dev/null
  out="$(as demo tl standards load "$DOC_STANDARDS")"; echo "$out"
  expect "loaded co.acme.documents@1.0.0" "$out"
  if out="$(as amy tl doc register ISO-12 --project P123 --title "Too short" --type ISO --discipline PIP 2>&1)"; then fail "ISO-12 was accepted"; fi
  echo "$out"
  expect "error:" "$out"
  out="$(as amy tl doc register ISO-1234 --project P123 --title "Isometric, line 47-P-101" --type ISO --discipline PIP --originator "Acme Piping")"; echo "$out"
  expect "state Registered" "$out"
  expect "scheme alpha" "$out"
  as amy tl doc register ISO-2000 --project P123 --title "Isometric, line 47-P-102" --type ISO --discipline PIP >/dev/null
  as demo tl tag create 47-FV-1001 --class ControlValve --service "Feed gas" --project P123 >/dev/null
  as demo tl tag create 47-FV-1002 --class ControlValve --service "Fuel gas" --project P123 >/dev/null
  out="$(as amy tl doc ls --project P123)"; echo "$out"
  expect "ISO-1234" "$out"
  echo "PASS 1: ISO-1234 is registered under the company number pattern; ISO-12 is refused"

  step "[$backend] clause 2: a draft takes a PDF; issuing is the admin's act"
  as amy tl doc rev create ISO-1234 --project P123 --purpose "For review" >/dev/null
  printf '%s\n' '%PDF-1.7 sheet A' >"$workdir/sheet-A.pdf"
  printf '%s\n' '%PDF-1.7 sheet B, with the new tie-in' >"$workdir/sheet-B.pdf"
  as amy tl doc rendition add ISO-1234 A "$workdir/sheet-A.pdf" --project P123 --kind pdf --pages 3
  if out="$(as amy tl doc rev issue ISO-1234 A --project P123 --status IFR 2>&1)"; then fail "a user issued a revision"; fi
  echo "$out"
  expect "needs the admin role" "$out"
  out="$(as demo tl doc rev issue ISO-1234 A --project P123 --status IFR)"; echo "$out"
  expect "IFR" "$out"
  out="$(as amy tl doc show ISO-1234 --project P123)"; echo "$out"
  expect "current: A" "$out"
  echo "PASS 2: revision A holds a PDF and was issued as IFR by an admin; a user was refused"

  step "[$backend] clause 3: a pinned link goes stale; the re-pin shows the diff first"
  as amy tl doc link 47-FV-1001 ISO-1234 --project P123 --pin A
  as amy tl doc rev create ISO-1234 --project P123 --purpose "Issued for construction" >/dev/null
  as amy tl doc rendition add ISO-1234 B "$workdir/sheet-B.pdf" --project P123 --kind pdf --pages 5
  as demo tl doc rev issue ISO-1234 B --project P123 --status IFC
  out="$(as amy tl doc stale --project P123)"; echo "$out"
  expect "47-FV-1001" "$out"
  link="$(echo "$out" | awk 'NR==1 {print $NF}')"
  out="$(as amy tl doc repin "$link" --project P123)"; echo "$out"
  expect "ISO-1234" "$out"
  out="$(as amy tl doc stale --project P123)"
  expect "47-FV-1001" "$out"
  as amy tl doc repin "$link" --project P123 --apply
  out="$(as amy tl doc stale --project P123)"; echo "(stale after the re-pin: ${out:-none})"
  [ -z "$out" ] || fail "the link is still stale after the re-pin"
  echo "PASS 3: 47-FV-1001 went stale when B (IFC) was issued; the re-pin showed the diff and moved it to B"

  step "[$backend] clause 4: the stale rule is class-aware (ADR-0012)"
  as amy tl doc link 47-FV-1002 ISO-1234 --project P123 --pin B
  as amy tl doc rev create ISO-1234 --project P123 --purpose "Review comments incorporated" >/dev/null
  printf '%s\n' '%PDF-1.7 sheet C' >"$workdir/sheet-C.pdf"
  as amy tl doc rendition add ISO-1234 C "$workdir/sheet-C.pdf" --project P123 --kind pdf
  as demo tl doc rev issue ISO-1234 C --project P123 --status IFR
  out="$(as amy tl doc stale --project P123)"; echo "(stale after IFR C: ${out:-none})"
  [ -z "$out" ] || fail "an IFR issued after an IFC flagged the IFC pin"
  as amy tl doc rev create ISO-1234 --project P123 --purpose "Final for construction" >/dev/null
  printf '%s\n' '%PDF-1.7 sheet D' >"$workdir/sheet-D.pdf"
  as amy tl doc rendition add ISO-1234 D "$workdir/sheet-D.pdf" --project P123 --kind pdf
  as demo tl doc rev issue ISO-1234 D --project P123 --status IFC
  out="$(as amy tl doc stale --project P123)"; echo "$out"
  expect "47-FV-1002" "$out"
  echo "PASS 4: IFR C left the IFC pin on B alone; IFC D flagged it"

  step "[$backend] clause 5: a transmittal lists the current revision; issuing it is the admin's act"
  out="$(as amy tl transmittal create --project P123 --subject "Isometrics for construction" --purpose for_construction --to "Site Office:Acme Construction:site@example.com" --revision ISO-1234@D)"; echo "$out"
  number="$(echo "$out" | awk '/^(created|drafted)/ {print $NF; exit}')"
  [ -n "$number" ] || number="$(echo "$out" | grep -oE '[A-Z0-9]+-TRN-[0-9]+' | sed -n 1p)"
  [ -n "$number" ] || fail "no transmittal number in the output"
  if out="$(as amy tl transmittal issue "$number" --project P123 2>&1)"; then fail "a user issued a transmittal"; fi
  echo "$out"
  expect "needs the admin role" "$out"
  as demo tl transmittal issue "$number" --project P123
  out="$(as amy tl transmittal show "$number" --project P123)"; echo "$out"
  expect "ISO-1234" "$out"
  expect "Issued" "$out"
  echo "PASS 5: transmittal $number lists ISO-1234@D and was issued by an admin"

  step "[$backend] clause 6: a review with an unanswered reviewer is overdue"
  as amy tl doc rev create ISO-2000 --project P123 --purpose "First draft" >/dev/null
  as demo tl review open ISO-2000 A --project P123 --reviewer user:ana --reviewer user:amy --due 2026-10-01
  as demo tl review ls ISO-2000 A --project P123
  out="$(as demo tl doc report overdue --project P123 --on 2026-10-13)"; echo "$out"
  expect "ISO-2000" "$out"
  expect "ana" "$out"
  printf '%s\n' "$TL_DEMO_ANA_PASSWORD" | as ana tl login ana --password-stdin >/dev/null
  as ana tl review answer ISO-2000@A/RC1 --project P123 --outcome approved_with_comments --comment "check the weld map" --actor user:ana
  out="$(as demo tl doc report overdue --project P123 --on 2026-10-13)"; echo "$out"
  case "$out" in *"ana"*) fail "ana answered and is still overdue" ;; esac
  expect "amy" "$out"
  echo "PASS 6: the overdue report names the reviewers who have not answered, and drops ana after her answer"

  step "[$backend] clause 7: a legacy DMS register is previewed and applied (admin only)"
  out="$(as amy tl doc import "$DMS_FILE" --mapping "$DMS_MAPPING" --project P123)"; echo "$out" | grep -E '^(import|new=|!)' | sed -n 1,6p
  expect "dry run: nothing written" "$out"
  expect "invalid=7" "$out"
  if out="$(as amy tl doc import "$DMS_FILE" --mapping "$DMS_MAPPING" --project P123 --apply --skip-invalid 2>&1)"; then fail "a user applied an import"; fi
  echo "$out"
  expect "needs the admin role" "$out"
  out="$(as demo tl doc import "$DMS_FILE" --mapping "$DMS_MAPPING" --project P123 --apply --skip-invalid --job dms-2024)"; echo "$out" | tail -n 2
  expect "applied dms-2024: registered=" "$out"
  out="$(as amy tl doc show ISO-0101 --project P123)"; echo "$out" | sed -n 1,4p
  expect "title: Isometric, line 47-P-101" "$out"
  echo "PASS 7: the old register was previewed, 7 rows refused with reasons, the valid ones imported by an admin"

  step "[$backend] clause 8: what a user cannot do"
  driver refused

  step "[$backend] clause 9: the API, the TUI register and an agent read the same documents"
  driver reads

  stop_server
  drop_pg
  echo "[$backend] all clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I2 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
