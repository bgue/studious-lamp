#!/usr/bin/env bash
# Demo for P2-INSP (inspections, module quality, slice 1): `just demo P2-INSP`.
#
# The seven clauses (docs/build-spec/module-designs/inspections.md section 10), each ending in a
# `PASS clause N: ...` line that is printed only after its check returned success:
#   1  a checklist: create, publish; an edit of the published one refused; revise gives version 2
#      and the first is Retired;
#   2  a hold point for an IWP: plan, schedule, record with one required failure: reject, one
#      punch item category A linked to it; verify by the recorder refused; by sue it passes;
#   3  reinspect: the new inspection names the first; all answers pass: accept;
#   4  readiness check inspections_planned on the IWP: n_a, blocked, ok, blocked, ok;
#   5  hidden subject: an inspection on a record restricted from uma answers as a missing key
#      (CLI, API, MCP); uma's list and total do not count it; sue and dora see it;
#   6  one state over the API, the TUI (palette entry inspections, 170x44) and MCP; an agent's
#      propose_inspection waits for uma; no record or verify tool is an agent action;
#   7  the export: csv and jsonl have the rows of `tl insp ls`, field by field.
#   7b the generator's quality section (SQLite only): `just demo-project` prints a quality line
#      without `skipped`, and `tl insp ls` on that ledger is not empty.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Clauses 1-7 run
# on both backends; clause 7b runs on SQLite only. Postgres is a throw-away database on TL_PG_URL
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
MISSING=P123-INS-9999

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export P2_INSP_WORKDIR="$workdir"
export TL_LAKE_DIR="$workdir/lake"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2"; }
driver() { # driver MODE [ARG...]: the API, TUI, MCP and export checks; their output is shown
  uv run python dev/demos/p2_insp_demo.py "$@" 2>"$workdir/driver.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/driver.err" >&2; tail -n 20 "$workdir"/server-*.log >&2; fail "a driver check was not met: $*"; }
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
list_total() { as uma tl insp ls --project "$PROJECT" --limit 500 | tail -n 1 | awk '{print $3}'; }
# readiness_is STATE: the check inspections_planned on the IWP is STATE now (the worker first)
readiness_is() {
  local out line
  local i
  for i in 1 2; do as ada tl awp worker --once >/dev/null || fail "the worker did not run"; done
  out="$(as uma tl awp readiness show "$IWP" --project "$PROJECT")" || { echo "$out"; fail "no readiness for $IWP"; }
  line="$(awk '$1 == "inspections_planned" {print; exit}' <<<"$out")"
  echo "readiness $line"
  case "$line" in "inspections_planned  $1  "*) ;; *) echo "$out"; fail "inspections_planned is not $1: $line" ;; esac
}

run_backend() {
  local backend="$1" api_port api_url out IWP CHK1 CHK2 INS1 INS2 PUN HIDDEN NUM PID NEW
  local uma_before questions
  step "[$backend] a new ledger, the people, the API on a free loopback port"
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake" "$workdir"/session-* "$workdir"/*.db "$workdir"/*.txt
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
  as demo tl admin roles grant triage --project P123 --module '*' --role user --reason "the demo agent may file proposals" >/dev/null
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

  step "[$backend] the setup: one IWP (sue), and the questions of the checklist"
  out="$(as sue tl awp iwp create --project "$PROJECT" --discipline PIP --title "Pipe rack spools, level 1" \
    --planned-start 2026-11-09 --planned-finish 2027-01-29 --foreman user:frank --hours 120)"; echo "$out"
  IWP="$(awk '/^created IWP /{print $3}' <<<"$out")"
  [ -n "$IWP" ] || fail "the IWP has no number"
  as sue tl awp iwp move "$IWP" start-development --project "$PROJECT" >/dev/null
  as sue tl awp iwp move "$IWP" constraint-check --project "$PROJECT" >/dev/null
  questions="$workdir/questions.json"
  cat >"$questions" <<'JSON'
[
  {"id": "q1", "text": "Gauge fitted?", "kind": "yes_no_na", "required": true, "unit": null,
   "min": null, "max": null, "choices": null, "fails_when": "no"},
  {"id": "q2", "text": "Label legible?", "kind": "yes_no_na", "required": false, "unit": null,
   "min": null, "max": null, "choices": null, "fails_when": "no"},
  {"id": "q3", "text": "Test pressure", "kind": "number", "required": false, "unit": "bar",
   "min": 1, "max": 10, "choices": null, "fails_when": "out_of_range"}
]
JSON

  step "[$backend] clause 1: a checklist; publish; edit refused; revise gives version 2; the first Retired"
  out="$(as uma tl checklist create --project "$PROJECT" --title "Hold check, flange make-up" --discipline piping \
    --questions-file "$questions")"; echo "$out"
  CHK1="$(awk '{print $2}' <<<"$out")"
  expect "created $CHK1  version" "$out"
  out="$(as sue tl checklist publish "$CHK1" --project "$PROJECT")"; echo "$out"
  expect "published $CHK1  version" "$out"
  refuse "a checklist that is Published does not take EditChecklist" \
    as uma tl checklist edit "$CHK1" --project "$PROJECT" --title "Changed after publish"
  out="$(as sue tl checklist revise "$CHK1" --project "$PROJECT")"; echo "$out"
  CHK2="$(awk '{print $2}' <<<"$out")"
  expect "revised $CHK2  version" "$out"
  out="$(as sue tl checklist publish "$CHK2" --project "$PROJECT")"; echo "$out"
  out="$(as uma tl checklist ls --project "$PROJECT")"; echo "$out"
  expect "$CHK2  Hold check, flange make-up  piping  version 2  Published" "$out"
  expect "$CHK1  Hold check, flange make-up  piping  version 1  Retired" "$out"
  clause 1 "$CHK1 published, its edit refused; $CHK2 is version 2 and Published; $CHK1 is Retired"

  step "[$backend] clause 4 (first half): n_a before any plan"
  readiness_is n_a

  step "[$backend] clause 2: plan, schedule, record a reject; the punch item; verify refused, then passes"
  out="$(as uma tl insp plan --project "$PROJECT" --subject "$IWP" --for "$IWP" --title "Flange make-up, F16" \
    --point hold)"; echo "$out"
  INS1="$(awk '{print $2}' <<<"$out")"
  expect "planned $INS1  version" "$out"
  readiness_is blocked
  out="$(as uma tl insp schedule "$INS1" --project "$PROJECT" --checklist "$CHK2" --on 2026-12-01 \
    --inspector user:uma)"; echo "$out"
  expect "scheduled $INS1  version" "$out"
  readiness_is ok
  out="$(as rob tl insp record "$INS1" --project "$PROJECT" --answer q1=no --answer q2=yes --answer q3=5 \
    --note "Gauge missing")"; echo "$out"
  expect "result reject" "$out"
  expect "punch 1" "$out"
  readiness_is blocked
  PUN="$(as uma tl insp show "$INS1" --project "$PROJECT" | awk '/^Punch items/{print $3; exit}')"
  [ -n "$PUN" ] || fail "the reject raised no punch item on $INS1"
  out="$(as uma tl punch ls --project "$PROJECT" --limit 500)"; echo "$out"
  expect "$PUN" "$out"
  [ "$(awk -v k="$PUN" '$1 == k && $3 == "A"' <<<"$out" | wc -l | tr -d ' ')" = 1 ] \
    || fail "$PUN is not a category A punch item"
  expect "$INS1 q1: Gauge fitted?" "$out"
  out="$(as uma tl link list "$PUN" --project "$PROJECT")"; echo "$out"
  expect "raised against  $INS1" "$out"
  refuse "the person who recorded an inspection may not verify it" as rob tl insp verify "$INS1" --project "$PROJECT"
  out="$(as sue tl insp verify "$INS1" --project "$PROJECT")"; echo "$out"
  expect "verified $INS1  version" "$out"
  clause 2 "$INS1 rejected with one category A punch item $PUN linked; rob's verify refused; sue verifies"

  step "[$backend] clause 3: reinspect; schedule; record all pass: accept; show names the first"
  out="$(as uma tl insp reinspect "$INS1" --project "$PROJECT")"; echo "$out"
  INS2="$(awk '{print $2}' <<<"$out")"
  expect "reinspected $INS2  version" "$out"
  out="$(as uma tl insp schedule "$INS2" --project "$PROJECT" --checklist "$CHK2" --on 2026-12-05 \
    --inspector user:uma)"; echo "$out"
  expect "scheduled $INS2  version" "$out"
  readiness_is ok
  out="$(as rob tl insp record "$INS2" --project "$PROJECT" --answer q1=yes --answer q2=yes --answer q3=5)"; echo "$out"
  expect "result accept" "$out"
  expect "punch 0" "$out"
  out="$(as uma tl insp show "$INS2" --project "$PROJECT")"; echo "$out"
  grep -qE "^Reinspection of +$INS1\$" <<<"$out" || fail "$INS2 does not name $INS1 as its first"
  clause 3 "$INS2 names $INS1 as the first; all answers pass; result accept"

  step "[$backend] clause 4: the readiness states in order, from the lines above"
  clause 4 "inspections_planned on $IWP: n_a, blocked (Planned), ok (Scheduled), blocked (reject), ok (reinspection Scheduled)"

  step "[$backend] clause 5: an inspection on a restricted record answers uma as a missing key"
  out="$(as dora tl corr receive --project "$PROJECT" --subject "Legal letter" --body "Counsel's letter, restricted")"; echo "$out"
  NUM="$(awk '/^received /{print $2}' <<<"$out")"
  [ -n "$NUM" ] || fail "the correspondence item has no number"
  out="$(as dora tl corr class set "$NUM" --project "$PROJECT" --to restricted --reason Legal)"; echo "$out"
  expect "is now restricted" "$out"
  uma_before="$(list_total)"
  out="$(as dora tl insp plan --project "$PROJECT" --subject "$NUM" --title "Letter walk" --point review)"; echo "$out"
  HIDDEN="$(awk '{print $2}' <<<"$out")"
  expect "planned $HIDDEN  version" "$out"
  exits 1 "error: no inspection $HIDDEN" as uma tl insp show "$HIDDEN" --project "$PROJECT"
  hidden_text="$(as uma tl insp show "$HIDDEN" --project "$PROJECT" 2>&1 || true)"
  missing_text="$(as uma tl insp show "$MISSING" --project "$PROJECT" 2>&1 || true)"
  [ "${hidden_text//$HIDDEN/KEY}" = "${missing_text//$MISSING/KEY}" ] \
    || fail "the hidden and the missing key answer differently: $hidden_text | $missing_text"
  out="$(as uma tl insp ls --project "$PROJECT" --limit 500)"; echo "$out"
  case "$out" in *"$HIDDEN"*) fail "uma's list holds $HIDDEN" ;; esac
  rows="$(awk -F'  ' 'NF == 9' <<<"$out" | wc -l | tr -d ' ')"
  total="$(tail -n 1 <<<"$out" | awk '{print $3}')"
  [ "$total" = "$uma_before" ] && [ "$total" = "$rows" ] || fail "uma's total is $total, rows $rows, before $uma_before"
  driver clause5 "$HIDDEN"
  expect "$HIDDEN" "$(as sue tl insp ls --project "$PROJECT" --limit 500)"
  expect "$HIDDEN" "$(as dora tl insp ls --project "$PROJECT" --limit 500)"
  clause 5 "$HIDDEN from $NUM is absent for uma (CLI list, total $total, API 404, MCP as uma and as the agent) and answers as a missing key; sue and dora list it"

  step "[$backend] clause 6: the API, the TUI and MCP agree; the agent's proposal waits for uma"
  as uma tl insp show "$INS1" --project "$PROJECT" >"$workdir/show-1.txt"
  driver clause6 "$INS1" "$workdir/show-1.txt"
  as uma tl insp ls --project "$PROJECT" --limit 500 >"$workdir/ls-before.txt"
  driver clause6-propose "$IWP" "$TL_DEMO_STATE"
  PID="$(cat "$TL_DEMO_STATE")"
  [ -n "$PID" ] || fail "the agent's proposal has no id"
  out="$(as uma tl proposal ls --project "$PROJECT")"; echo "$out"
  expect "$PID" "$out"
  as uma tl insp ls --project "$PROJECT" --limit 500 >"$workdir/ls-pending.txt"
  cmp -s "$workdir/ls-before.txt" "$workdir/ls-pending.txt" || fail "a proposal changed the inspection list before uma accepted it"
  out="$(as uma tl proposal accept "$PID")"; echo "$out"
  expect "accepted $PID" "$out"
  as uma tl insp ls --project "$PROJECT" --limit 500 >"$workdir/ls-after.txt"
  NEW="$(comm -13 <(awk -F'  ' 'NF == 9 {print $1}' "$workdir/ls-before.txt" | sort) \
    <(awk -F'  ' 'NF == 9 {print $1}' "$workdir/ls-after.txt" | sort))"
  [ "$(wc -l <<<"$NEW" | tr -d ' ')" = 1 ] && [ -n "$NEW" ] || fail "accepting the proposal did not add one inspection row"
  out="$(as uma tl insp show "$NEW" --project "$PROJECT")"; echo "$out"
  expect "Witness point proposed by the agent" "$out"
  clause 6 "API, TUI (inspections) and MCP agree on $INS1; the agent's proposal waits for uma; accepting it adds $NEW"

  step "[$backend] clause 7: the export has the rows of ls, csv and jsonl, field by field"
  as uma tl insp ls --project "$PROJECT" --limit 500 >"$workdir/ls.txt"
  as uma tl insp export --project "$PROJECT" --format csv >"$workdir/export.csv"
  as uma tl insp export --project "$PROJECT" --format jsonl >"$workdir/export.jsonl"
  driver export "$workdir/ls.txt" "$workdir/export.csv" "$workdir/export.jsonl"
  clause 7 "csv and jsonl have the same rows as tl insp ls (key, state, point, subject, for, inspector, scheduled, result)"

  if [ "$backend" = sqlite ]; then
    step "[sqlite] clause 7b: the generator's quality section; tl insp ls is not empty"
    gen_db="$workdir/generated.db"
    out="$(just demo-project "$gen_db" --sections core,engineering,awp,constraints,quality 2>&1)" || { echo "$out"; fail "just demo-project failed"; }
    echo "$out" | grep -E '^(quality|core|engineering|awp|constraints)' || true
    quality_line="$(grep -E '^quality: [0-9]+ records' <<<"$out" || true)"
    [ -n "$quality_line" ] || { echo "$out"; fail "the generator printed no quality line"; }
    case "$quality_line" in *skipped*) fail "the quality section was skipped: $quality_line" ;; esac
    (
      export TL_DB="$gen_db" TL_SCHEMA_DIR=dev/data/demo-project-schema
      printf 'p200-demo-pass\n' | as hsato tl login hsato --password-stdin >/dev/null
      out="$(as hsato tl insp ls --project P200 --limit 500)"; echo "$out" | head -n 3
      [ "$(tail -n 1 <<<"$out" | awk '{print $3}')" -ge 1 ] || fail "tl insp ls is empty on the generated ledger"
    )
    echo "PASS clause 7b: $quality_line; tl insp ls on the generated ledger is not empty (SQLite only)"
  fi

  stop_server
  drop_pg
  echo "[$backend] clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-INSP demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
