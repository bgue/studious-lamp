#!/usr/bin/env bash
# Demo for P1-I5 (M10 correspondence core, the clock engine, the General and Document-control
# domains): `just demo P1-I5`.
#
# The exit clauses, each ending in a PASS line, once on SQLite and once on Postgres:
#   1  a letter is received by upload; triage proposes the General domain; a person confirms it;
#   2  a reply is drafted and issued (a controller's act; a user is refused): a PDF is stored, the
#      send is a stub, and a 14-calendar-day clock starts on the project calendar;
#   3  the clocks screen (TUI F12) shows that clock with its days left;
#   4  a document-control transmittal of I2 appears in the master register next to the letters;
#   5  an email (an .eml with a PDF attached) is read in: party matched by its domain, threaded to
#      the letter by its subject, the original and the attachment kept;
#   6  a restricted item does not exist for a user or an agent, and the register export leaves it out;
#   7  the API, the TUI and an agent's MCP tools read the same register; an agent's triage is a
#      proposal that leaves the item as it was;
#   8  a working-day clock skips the weekend, and rebuilding every projection from the ledger gives
#      the same clocks.
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
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i5_demo.py "$@" || fail "an exit clause was not met"; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}


STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
DOC_STANDARDS=schema/fixtures/standards/co.acme.documents@1.0.0.yaml

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, three people and an agent, and the API on a free loopback port"
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
  as demo tl admin user roles dora --add document_controller >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  TL_DEMO_AGENT_TOKEN="$(as demo tl admin token issue triage --label demo 2>/dev/null)"
  export TL_DEMO_AGENT_TOKEN
  case "$TL_DEMO_AGENT_TOKEN" in tla_*) ;; *) fail "no agent token was issued" ;; esac
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as amy tl login amy --password-stdin >/dev/null
  printf '%s\n' "$TL_DEMO_DORA_PASSWORD" | as dora tl login dora --password-stdin >/dev/null
  as dora tl corr party add ACME --project P123 --name "Acme Construction" --role contractor \
    --email-domain acme.example --contact "Ann:ann@acme.example" >/dev/null
  expect "ACME" "$(as amy tl corr party ls --project P123)"

  step "[$backend] clause 1: a letter is received by upload; triage proposes General"
  printf '%s\n' "Please find our revised programme. We would be grateful for your comments." >"$workdir/letter.txt"
  out="$(as amy tl corr receive --project P123 --subject "Revised programme" --from "Acme Construction" --file "$workdir/letter.txt" --body-file "$workdir/letter.txt")"; echo "$out"
  expect "file original letter.txt" "$out"
  letter="$(echo "$out" | awk '/^received/ {print $2}')"
  [ -n "$letter" ] || fail "no item number for the letter"
  out="$(as amy tl corr suggest "$letter" --project P123)"; echo "$out"
  expect "suggested general/letter" "$out"
  out="$(as amy tl corr triage "$letter" --project P123 --accept)"; echo "$out"
  expect "triaged $letter as general/letter" "$out"
  out="$(as amy tl corr show "$letter" --project P123)"; echo "$out"
  expect "Triaged" "$out"
  expect "response required" "$out"
  echo "PASS 1: $letter arrived by upload; the engine proposed general/letter; a person confirmed it"

  step "[$backend] clause 2: the reply is issued by a controller; a 14-calendar-day clock starts"
  out="$(as amy tl corr draft --project P123 --subject "Re: Revised programme" --to "Acme Construction:ann@acme.example" --reply-to "$letter" --domain general --subtype letter --body "We have received the programme and will reply by the due date.")"; echo "$out"
  reply="$(echo "$out" | awk '/^drafted/ {print $2}')"
  [ -n "$reply" ] || fail "no item number for the reply"
  if out="$(as amy tl corr issue "$reply" --project P123 2>&1)"; then fail "a user issued a letter"; fi
  echo "$out"
  expect "needs the document_controller or admin role" "$out"
  out="$(as dora tl corr issue "$reply" --project P123)"; echo "$out"
  expect "nothing was sent" "$out"
  due="$(python3 -c 'import datetime as d; print(d.date.today() + d.timedelta(days=14))')"
  expect "clock $reply-C01 Reply expected due $due" "$out"
  out="$(as amy tl corr clock ls --project P123)"; echo "$out"
  expect "$reply-C01 running due $due left 14 14 calendar" "$out"
  echo "PASS 2: $reply was issued by a controller (a user was refused); its clock is due $due on P123-default@1"
  export TL_DEMO_REPLY="$reply"

  step "[$backend] clause 3: the clocks screen shows it"
  driver clocks

  step "[$backend] clause 4: an I2 transmittal appears in the master register"
  as demo tl standards load "$STANDARDS" >/dev/null
  as demo tl standards load "$DOC_STANDARDS" >/dev/null
  as amy tl doc register ISO-1234 --project P123 --title "Isometric, line 47-P-101" --type ISO --discipline PIP >/dev/null
  as amy tl doc rev create ISO-1234 --project P123 --purpose "For construction" >/dev/null
  printf '%s\n' '%PDF-1.7 sheet A' >"$workdir/sheet-A.pdf"
  as amy tl doc rendition add ISO-1234 A "$workdir/sheet-A.pdf" --project P123 --kind pdf --pages 3 >/dev/null
  as dora tl doc rev issue ISO-1234 A --project P123 --status IFC >/dev/null
  out="$(as amy tl transmittal create --project P123 --subject "Isometrics for construction" --purpose for_construction --to "Site Office:Acme Construction:site@acme.example" --revision ISO-1234@A)"; echo "$out"
  trn="$(echo "$out" | grep -oE '[A-Z0-9]+-TRN-[0-9]+' | sed -n 1p)"
  [ -n "$trn" ] || fail "no transmittal number in the output"
  as dora tl transmittal issue "$trn" --project P123 >/dev/null
  out="$(as amy tl corr ls --project P123)"; echo "$out"
  expect "$trn" "$out"
  expect "[transmittal]" "$out"
  expect "$letter" "$out"
  echo "PASS 4: the master register lists $trn (document control) next to the letters"

  step "[$backend] clause 5: an email is read in; its party, thread and attachment"
  driver make-eml "$workdir/reply.eml"
  out="$(as amy tl corr mail ingest "$workdir/reply.eml" --project P123)"; echo "$out"
  expect "ingested" "$out"
  expect "attachments 1" "$out"
  mail="$(echo "$out" | awk '/^ingested/ {print $2}')"
  out="$(as amy tl corr show "$mail" --project P123)"; echo "$out"
  expect "email" "$out"
  expect "file attachment programme-markup.pdf" "$out"
  expect "file message " "$out"
  letter_thread="$(as amy tl corr show "$letter" --project P123 | awk '/^thread/ {print $2}')"
  mail_thread="$(echo "$out" | awk '/^thread/ {print $2}')"
  [ "$letter_thread" = "$mail_thread" ] && [ "$letter_thread" != "-" ] || fail "the email did not join the thread of the letter ($letter_thread vs $mail_thread)"
  if out="$(as amy tl corr mail ingest "$workdir/reply.eml" --project P123 2>&1)"; then fail "the same message was read in twice"; fi
  echo "$out"
  expect "already" "$out"
  echo "PASS 5: $mail joined thread $mail_thread by its subject, kept the original and the PDF; reading it again is refused"

  step "[$backend] clause 6: a restricted item does not exist for a user or an agent"
  as dora tl corr class set "$mail" --project P123 --to restricted --reason "commercial terms"
  if out="$(as amy tl corr show "$mail" --project P123 2>&1)"; then fail "a user read a restricted item"; fi
  echo "$out"
  expect "no item" "$out"
  out="$(as dora tl corr report register --project P123)"; echo "$out" | sed -n 1,3p
  case "$out" in *"$mail"*) fail "the export carries a restricted item" ;; esac
  expect "$letter" "$out"
  out="$(as dora tl corr report register --project P123 --include-class restricted)"
  expect "$mail" "$out"
  if out="$(as amy tl corr report register --project P123 --include-class restricted 2>&1)"; then fail "a user named a class in an export"; fi
  expect "needs the document_controller or admin role" "$out"
  export TL_DEMO_SECRET="$mail"
  driver hidden

  step "[$backend] clause 7: the API, the TUI and an agent read the same register"
  out="$(as amy tl corr receive --project P123 --subject "Site access arrangements" --from "Acme Construction")"; echo "$out"
  export TL_DEMO_RECEIVED="$(echo "$out" | awk '/^received/ {print $2}')"
  driver reads

  step "[$backend] clause 8: a working-day clock skips the weekend; the clocks come back from the ledger"
  out="$(as amy tl corr clock start "$letter" --project P123 --label "Comments due" --days 5 --type working --warn 1)"; echo "$out"
  expect "started $letter-C" "$out"
  key="$(echo "$out" | awk '/^started/ {print $2}')"
  before="$(as amy tl corr clock ls --project P123 --all)"; echo "$before"
  expect "$key running" "$before"
  working_due="$(echo "$before" | awk -v k="$key" '$1 == k {print $4}')"
  driver working "$working_due"
  out="$(tl projections rebuild)"; echo "$out"
  expect "replayed" "$out"
  after="$(as amy tl corr clock ls --project P123 --all)"
  [ "$before" = "$after" ] || { echo "$after"; fail "the clocks changed when the projections were rebuilt"; }
  echo "PASS 8: $key (5 working days) is due $working_due, not on a weekend; the clocks are the same after a full rebuild"

  stop_server
  drop_pg
  echo "[$backend] all clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I5 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
