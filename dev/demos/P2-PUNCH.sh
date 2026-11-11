#!/usr/bin/env bash
# Demo for P2-PUNCH (the punch list, module quality, minimal slice): `just demo P2-PUNCH`.
#
# The seven clauses (docs/tickets/P2-PUNCH/README.md, "Demo clauses"), each ending in a
# `PASS clause N: ...` line that is printed only after its check returned success:
#   1  raise to verify (uma raises, rob clears, rob and uma refused, sue verifies, show);
#   2  reopen with a reason, a reason-less reopen refused, void is terminal, a stale version refused;
#   3  three items raised from an IWP, a tag and a document; ls --from; an unknown source writes
#      nothing; the raised_against link;
#   4  two background loops of ten raises give every key from -0001 to -<n> exactly once;
#   5  hidden source: an item raised from a restricted correspondence item is absent for uma and
#      answers like a key that never existed (CLI, API, MCP); sue and dora see it;
#   6  one state over the API, the TUI (palette entry punch, 170x44) and MCP; the agent's
#      propose_punch_item waits for uma; no clear or verify tool is an agent action;
#   7  the generator's quality section. SQLite only: `just demo-project` builds a SQLite ledger
#      here, so the Postgres run does not repeat it.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Clauses 1-6 run
# on both backends; clause 7 runs on SQLite only. Postgres is a throw-away database on TL_PG_URL
# (default postgresql://postgres:postgres@localhost:5432/tl_test, `just dev up`), dropped afterwards;
# an unreachable server is a failure, not a skip. The API is `tl serve` on a free loopback port over
# a temporary ledger, stopped afterwards. Nothing is left behind. Exits non-zero (and prints
# DEMO FAILED) when any clause is not met.
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
MISSING=P123-PUN-9999

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export P2_PUNCH_WORKDIR="$workdir"
export TL_LAKE_DIR="$workdir/lake"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2"; }
driver() { # driver MODE [ARG...]: the API, TUI and MCP checks; their output is shown, stderr is kept
  uv run python dev/demos/p2_punch_demo.py "$@" 2>"$workdir/driver.err" \
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
exits() { # exits CODE TEXT cmd...: the command must exit with CODE and say TEXT
  local code="$1" text="$2" out rc=0; shift 2
  out="$("$@" 2>&1)" || rc=$?
  echo "$out"
  [ "$rc" = "$code" ] || fail "exit $rc, not $code: $*"
  expect "$text" "$out"
}
key_after() { awk -v w="$1" '$1 == w {print $2; exit}' <<<"$2"; } # key_after WORD OUTPUT: the key on a `WORD KEY ...` line
item_keys() { as sue tl punch ls --project "$PROJECT" --limit 500 | awk '/^P123-PUN-/{print $1}' | sort; }
item_count() { item_keys | wc -l | tr -d ' '; } # every item, as sue sees them (she reads the hidden one too)
list_total() { as uma tl punch ls --project "$PROJECT" --limit 500 | awk '/^punch items:/{print $3}'; }

run_backend() {
  local backend="$1" api_port api_url out IWP TAG DOC key_iwp key_tag key_doc before after n
  local num hidden uma_before uma_after rows total
  step "[$backend] a new ledger, the people, the API on a free loopback port"
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake" "$workdir"/session-* "$workdir"/*.db "$workdir"/loop-*.out
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
  printf '%s\n' "a long passphrase for sue" | as demo tl admin user add sue --display-name "Sue" --role document_controller --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for rob" | as demo tl admin user add rob --display-name "Rob" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for uma" | as demo tl admin user add uma --display-name "Uma" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for dora" | as demo tl admin user add dora --display-name "Dora" --role document_controller --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for frank" | as demo tl admin user add frank --display-name "Frank" --password-stdin >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  for who in ada sue rob uma dora frank; do
    printf '%s\n' "a long passphrase for $who" | as "$who" tl login "$who" --password-stdin >/dev/null
  done
  for std in schema/fixtures/standards/co.acme.standards@1.0.0.yaml schema/fixtures/standards/co.acme.awp@1.0.0.yaml \
    schema/fixtures/standards/co.acme.documents@1.0.0.yaml; do
    as ada tl standards load "$std" >/dev/null
  done
  as ada tl admin roles grant sue --project "$PROJECT" --module quality --role superuser --reason demo >/dev/null
  as ada tl admin roles grant rob --project "$PROJECT" --module quality --role superuser --reason demo >/dev/null
  as ada tl admin roles grant sue --project "$PROJECT" --module awp --role superuser --reason demo >/dev/null
  as ada tl admin roles grant sue --project "$PROJECT" --module documents --role superuser --reason demo >/dev/null
  as ada tl admin roles grant dora --project "$PROJECT" --module documents --role superuser --reason demo >/dev/null
  api_port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  api_url="http://127.0.0.1:$api_port"
  export TL_API_URL="$api_url" TL_DEMO_STATE="$workdir/proposal-$backend.txt"
  setsid uv run tl serve --port "$api_port" >"$workdir/server-$backend.log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 150); do
    curl -fs "$api_url/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  curl -fs "$api_url/health" | grep -q '"status":"ok"' || { cat "$workdir/server-$backend.log" >&2; fail "the server did not start"; }
  echo "(serving $backend at $api_url)"

  step "[$backend] the setup: one IWP (sue), one tag and one document"
  out="$(as sue tl awp iwp create --project "$PROJECT" --discipline PIP --title "Pipe rack spools, level 1" \
    --planned-start 2026-11-09 --planned-finish 2027-01-29 --foreman user:frank --hours 120)"; echo "$out"
  IWP="$(awk '/^created IWP /{print $3}' <<<"$out")"
  [ -n "$IWP" ] || fail "the IWP has no number"
  as sue tl tag create 47-FV-1001 --class ControlValve --service "Feed gas" --project "$PROJECT" >/dev/null
  as dora tl doc register ISO-1234 --project "$PROJECT" --title "Piping isometric ISO-1234" \
    --type ISO --discipline PIP --originator "Acme Piping" >/dev/null
  TAG=47-FV-1001
  DOC=ISO-1234

  step "[$backend] clause 1: raise to verify; rob clears; rob and uma refused; sue verifies; show"
  out="$(as uma tl punch raise --project "$PROJECT" --subject "Gasket missing on F12" --area A1 --system 47-01 \
    --due 2026-11-20 --category A --assignee user:rob --from "$IWP")"; echo "$out"
  expect "raised P123-PUN-0001  version" "$out"
  out="$(as uma tl punch ls --project "$PROJECT" --state Open)"; echo "$out"
  expect "P123-PUN-0001" "$out"
  out="$(as rob tl punch clear P123-PUN-0001 --project "$PROJECT" --note "Gasket fitted")"; echo "$out"
  expect "cleared P123-PUN-0001  version" "$out"
  refuse "the person who cleared a punch item may not verify it" as rob tl punch verify P123-PUN-0001 --project "$PROJECT"
  refuse "error: forbidden" as uma tl punch verify P123-PUN-0001 --project "$PROJECT"
  out="$(as sue tl punch verify P123-PUN-0001 --project "$PROJECT")"; echo "$out"
  expect "verified P123-PUN-0001  version" "$out"
  out="$(as uma tl punch show P123-PUN-0001 --project "$PROJECT")"; echo "$out"
  expect "state  Verified" "$out"
  expect "cleared  user:rob" "$out"
  expect "verified  user:sue" "$out"
  clause 1 "P123-PUN-0001 raised by uma, cleared by rob, refused for rob and uma, verified by sue"

  step "[$backend] clause 2: reopen with a reason; a reason-less reopen exits 2; void is terminal; a stale version"
  out="$(as uma tl punch raise --project "$PROJECT" --subject "Wrong size flange on F14" --assignee user:rob --from "$IWP")"; echo "$out"
  expect "raised P123-PUN-0002  version" "$out"
  out="$(as rob tl punch clear P123-PUN-0002 --project "$PROJECT" --note "Fitted")"; echo "$out"
  out="$(as sue tl punch reopen P123-PUN-0002 --project "$PROJECT" --reason "Wrong size")"; echo "$out"
  expect "reopened P123-PUN-0002  version" "$out"
  out="$(as uma tl punch show P123-PUN-0002 --project "$PROJECT")"; echo "$out"
  expect "state  Open" "$out"
  expect "reopened  1  Wrong size" "$out"
  exits 2 "--reason" as sue tl punch reopen P123-PUN-0002 --project "$PROJECT"
  out="$(as uma tl punch raise --project "$PROJECT" --subject "Duplicate line on F15" --assignee user:rob --from "$IWP")"; echo "$out"
  expect "raised P123-PUN-0003  version" "$out"
  out="$(as sue tl punch void P123-PUN-0003 --project "$PROJECT" --reason Duplicate)"; echo "$out"
  expect "voided P123-PUN-0003  version" "$out"
  refuse "a void punch item accepts no further change" as rob tl punch clear P123-PUN-0003 --project "$PROJECT" --note x
  refuse "the record changed since it was read" as rob tl punch clear P123-PUN-0002 --project "$PROJECT" --note x --expected-version 1
  clause 2 "P123-PUN-0002 reopened (reopened 1, Wrong size); no --reason exits 2; P123-PUN-0003 void and final; a stale version refused"

  step "[$backend] clause 3: raised from an IWP, a tag and a document; ls --from; an unknown source; the link"
  out="$(as uma tl punch raise --project "$PROJECT" --subject "Tag 47-FV-1001 stem leaks" --from "$TAG")"; echo "$out"
  key_tag="$(key_after raised "$out")"
  out="$(as uma tl punch raise --project "$PROJECT" --subject "ISO-1234 weld note missing" --from "$DOC")"; echo "$out"
  key_doc="$(key_after raised "$out")"
  out="$(as uma tl punch raise --project "$PROJECT" --subject "IWP check, F16" --assignee user:rob --from "$IWP")"; echo "$out"
  key_iwp="$(key_after raised "$out")"
  [ -n "$key_tag" ] && [ -n "$key_doc" ] && [ -n "$key_iwp" ] || fail "a raise printed no key"
  for pair in "$key_iwp:$IWP" "$key_tag:$TAG" "$key_doc:$DOC"; do
    out="$(as uma tl punch show "${pair%%:*}" --project "$PROJECT")"; echo "$out"
    expect "raised from  ${pair#*:}" "$out"
  done
  out="$(as uma tl punch ls --project "$PROJECT" --from "$IWP" --limit 500)"; echo "$out"
  expect "$key_iwp" "$out"
  case "$out" in *"$key_tag"*|*"$key_doc"*) fail "ls --from $IWP lists another source" ;; esac
  out="$(as uma tl punch ls --project "$PROJECT" --from "$TAG")"; echo "$out"
  expect "punch items: 1" "$out"
  expect "$key_tag" "$out"
  before="$(list_total)"
  refuse "error: no record NOPE-1" as uma tl punch raise --project "$PROJECT" --subject x --from NOPE-1
  after="$(list_total)"
  [ "$before" = "$after" ] || fail "a raise from NOPE-1 changed the count: $before then $after"
  out="$(as uma tl link list "$key_iwp" --project "$PROJECT")"; echo "$out"
  expect "raised against  $IWP" "$out"
  expect "$IWP" "$out"
  clause 3 "$key_iwp, $key_tag and $key_doc show raised from their source; ls --from lists only its items; NOPE-1 writes nothing; raised_against links the IWP"

  step "[$backend] clause 4: two background loops of ten raises; every key once"
  before="$(item_count)"
  raise_loop() { # raise_loop TAG: ten raises by uma, in order
    local i
    for i in $(seq 1 10); do
      as uma tl punch raise --project "$PROJECT" --subject "Loop $1 item $i" >>"$workdir/loop-$1.out"
    done
  }
  raise_loop a & loop_a=$!
  raise_loop b & loop_b=$!
  wait "$loop_a" || fail "loop a failed"
  wait "$loop_b" || fail "loop b failed"
  [ "$(grep -c '^raised P123-PUN-' "$workdir/loop-a.out" "$workdir/loop-b.out" | awk -F: '{s+=$2} END{print s}')" = 20 ] \
    || fail "the loops did not print 20 raised lines"
  n=$((before + 20))
  [ "$(item_keys | uniq -d | wc -l | tr -d ' ')" = 0 ] || fail "a key is listed twice"
  [ "$(item_keys)" = "$(seq -f 'P123-PUN-%04g' 1 "$n")" ] || fail "the keys are not -0001 to -$n with no gap"
  echo "keys: P123-PUN-0001 to P123-PUN-$(printf %04d "$n"), each once; n = $n counted by the script"
  clause 4 "two loops of ten raises: keys -0001 to -$(printf %04d "$n") (n = $n), each once"

  step "[$backend] clause 5: a restricted source hides its item from uma; the same text as a missing key; sue and dora see it"
  out="$(as dora tl corr receive --project "$PROJECT" --subject "Legal letter" --body "Counsel's letter, restricted")"; echo "$out"
  num="$(awk '/^received /{print $2}' <<<"$out")"
  [ -n "$num" ] || fail "the correspondence item has no number"
  out="$(as dora tl corr class set "$num" --project "$PROJECT" --to restricted --reason Legal)"; echo "$out"
  expect "is now restricted" "$out"
  uma_before="$(list_total)"
  out="$(as dora tl punch raise --project "$PROJECT" --subject "Letter follow-up" --from "$num")"; echo "$out"
  hidden="$(key_after raised "$out")"
  [ -n "$hidden" ] || fail "the follow-up has no key"
  exits 1 "error: no punch item $hidden" as uma tl punch show "$hidden" --project "$PROJECT"
  hidden_text="$(as uma tl punch show "$hidden" --project "$PROJECT" 2>&1 || true)"
  missing_text="$(as uma tl punch show "$MISSING" --project "$PROJECT" 2>&1 || true)"
  [ "${hidden_text//$hidden/KEY}" = "${missing_text//$MISSING/KEY}" ] \
    || fail "the hidden and the missing key answer differently: $hidden_text | $missing_text"
  out="$(as uma tl punch ls --project "$PROJECT" --limit 500)"; echo "$out"
  case "$out" in *"$hidden"*) fail "uma's list holds $hidden" ;; esac
  rows="$(awk 'NR>1' <<<"$out" | wc -l | tr -d ' ')"
  total="$(awk '/^punch items:/{print $3}' <<<"$out")"
  [ "$total" = "$uma_before" ] && [ "$total" = "$rows" ] || fail "uma's total is $total, rows $rows, before $uma_before"
  driver clause5 "$hidden"
  expect "$hidden" "$(as sue tl punch ls --project "$PROJECT" --limit 500)"
  expect "$hidden" "$(as dora tl punch ls --project "$PROJECT" --limit 500)"
  clause 5 "$hidden from $num is absent for uma (CLI list, total $total, API 404, MCP as uma and as the agent) and answers as a missing key; sue and dora list it"

  step "[$backend] clause 6: the API, the TUI and MCP agree; the agent's proposal waits for uma"
  as uma tl punch show P123-PUN-0001 --project "$PROJECT" >"$workdir/show-0001.txt"
  driver clause6 P123-PUN-0001 "$IWP" "$workdir/show-0001.txt"
  pre="$(item_count)"
  driver clause6-propose "$IWP" "$TL_DEMO_STATE"
  pid="$(cat "$TL_DEMO_STATE")"
  [ -n "$pid" ] || fail "the agent's proposal has no id"
  out="$(as uma tl proposal ls --project "$PROJECT")"; echo "$out"
  expect "$pid" "$out"
  [ "$(item_count)" = "$pre" ] || fail "a proposal raised an item before a person accepted it"
  out="$(as uma tl proposal accept "$pid")"; echo "$out"
  expect "accepted $pid" "$out"
  total="$(item_count)"
  [ "$total" = "$((pre + 1))" ] || fail "accepting the proposal did not add one item"
  next="$(printf 'P123-PUN-%04d' "$total")"
  out="$(as uma tl punch show "$next" --project "$PROJECT")"; echo "$out"
  expect "raised by  user:uma" "$out"
  clause 6 "API, TUI (punch) and MCP agree on P123-PUN-0001 (Verified); the agent's proposal waits; uma's accept raises $next; no clear or verify tool"

  if [ "$backend" = sqlite ]; then
    step "[sqlite] clause 7: the generator's quality section; the states and overdue"
    gen_db="$workdir/generated.db"
    out="$(just demo-project "$gen_db" --sections core,engineering,awp,constraints,quality 2>&1)" || { echo "$out"; fail "just demo-project failed"; }
    echo "$out" | grep -E '^(quality|core|engineering|awp|constraints)' || true
    quality_line="$(grep -E '^quality: [0-9]+ records' <<<"$out" || true)"
    [ -n "$quality_line" ] || { echo "$out"; fail "the generator printed no quality line"; }
    case "$quality_line" in *skipped*) fail "the quality section was skipped: $quality_line" ;; esac
    (
      export TL_DB="$gen_db" TL_SCHEMA_DIR=dev/data/demo-project-schema
      printf 'p200-demo-pass\n' | as hsato tl login hsato --password-stdin >/dev/null
      for st in Open Cleared Verified Void; do
        out="$(as hsato tl punch ls --project P200 --state "$st")"; echo "$out" | head -n 2
        [ "$(awk '/^punch items:/{print $3}' <<<"$out")" -ge 1 ] || fail "no $st item on the generated ledger"
      done
      out="$(as hsato tl punch ls --project P200 --overdue)"; echo "$out" | head -n 2
      [ "$(awk '/^punch items:/{print $3}' <<<"$out")" -ge 1 ] || fail "no overdue item on the generated ledger"
    )
    clause 7 "$quality_line; P200 has items in Open, Cleared, Verified and Void, and an overdue one (SQLite only)"
  fi

  stop_server
  drop_pg
  echo "[$backend] clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-PUNCH demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
