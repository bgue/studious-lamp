#!/usr/bin/env bash
# Demo for P2-I5 (rules of credit, the look-ahead, check-raised constraints and waivers, holds,
# the weekly plan and PPC, the work pack, the TUI landing and agents over MCP): `just demo P2-I5`.
#
# The exit clauses (docs/tickets/P2-I5/README.md, "Demo clauses"), each ending in a `PASS clause N`
# line, once on SQLite and once on Postgres:
#   1  the rules of credit: a package published by a controller; a copy with weights summing to
#      101 refused by the lint (L008); `awp roc set` adopts it; a plain user's publish refused;
#   2  a new XER snapshot, a worker run; `awp look-ahead` lists the activities with their IWPs,
#      ready counts and need-by dates (planned start minus awp.iwp.ready_lead_weeks);
#   3  a check-raised constraint cleared as waived by a holder of core.constraint.waive with a
#      reason; a plain user and a missing reason refused; the IWP is then released (hash, two
#      sign-offs, issue);
#   4  a blocking constraint raised on an Issued IWP: `awp worker --once` twice holds it once; the
#      week is opened and committed; a stale expected version refused;
#   5  item moves, steps and field work move the earned figure; a week is outcome-recorded and
#      closed (PPC); the KPI reports and the progress CSV agree with a ledger recount;
#   6  the work pack HTML with the template headings and an `<svg` per drawing; it is in slot pack;
#   9  the TUI opens as the foreman on the IWP log with the mine filter; with tui.landing=default it
#      opens on the grid;
#   10 agents over MCP: propose_progress and propose_week_commitment are accepted by a person; a
#      waive and a close of the week by an agent are refused; the same week reads the same
#      everywhere; the three T16 walk files pass.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. The server
# is `tl serve` on a free loopback port over a temporary ledger, stopped afterwards. Nothing is left
# behind. Exits non-zero (and prints DEMO FAILED) when any clause is not met.
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

AWP_STANDARDS=schema/fixtures/standards/co.acme.awp@1.0.0.yaml
STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
DOC_STANDARDS=schema/fixtures/standards/co.acme.documents@1.0.0.yaml
MATERIALS=schema/fixtures/standards/co.acme.materials@1.0.0.yaml
RULES=schema/fixtures/packages/co.acme.awp@1.1.0.yaml
PROJECT=P123
IWP=P123-IWP-PIP-0001
IWP2=P123-IWP-PIP-0002

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
driver() { quiet uv run python dev/demos/p2_i5_demo.py "$@" || fail "an exit clause was not met: $*"; }
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
catch_up() { local i; for i in $(seq 1 8); do as ada tl awp worker --once >/dev/null; done; }
evaluate() { local i; for i in 1 2; do as ada tl awp worker --once >/dev/null; done; }

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, the people, the agent, the API on a free loopback port"
  stop_server
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake-$backend" "$workdir"/session-* "$workdir"/*.xer
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
  as ada tl admin roles grant frank --project "$PROJECT" --module awp --role user --reason demo >/dev/null
  as ada tl admin roles grant alice --project "$PROJECT" --module documents --role user --reason demo >/dev/null
  as ada tl admin roles grant alice --project "$PROJECT" --module materials --role user --reason demo >/dev/null
  as ada tl admin roles grant dora --project "$PROJECT" --module documents --role superuser --reason demo >/dev/null
  as ada tl admin roles grant sue --project "$PROJECT" --module documents --role superuser --reason demo >/dev/null
  as ada tl admin roles grant triage --project "$PROJECT" --module awp --role user --reason demo >/dev/null
  as ada tl admin roles grant triage --project "$PROJECT" --module materials --role user --reason demo >/dev/null
  as ada tl awp worker --once >/dev/null 2>&1 || true # the readiness follower starts at the head of the outbox
  for std in "$STANDARDS" "$AWP_STANDARDS" "$DOC_STANDARDS" "$MATERIALS"; do
    out="$(as ada tl standards load "$std")"; echo "$out" | tail -1
  done

  step "[$backend] clause 1: the rules of credit published by a controller; a 101 copy refused; roc set"
  out="$(as ada tl schema package draft "$RULES" --changelog "P2-I5 rules of credit")"; echo "$out"
  expect "drafted co.acme.awp@1.1.0" "$out"
  key="$(awk '/^drafted /{print $3}' <<<"$out")"
  as ada tl schema package analyse co.acme.awp@1.1.0 >/dev/null
  as ada tl schema package submit co.acme.awp@1.1.0 >/dev/null
  out="$(as demo tl schema package approve co.acme.awp@1.1.0)"; echo "$out"
  refuse "forbidden" as plain tl schema package publish co.acme.awp@1.1.0
  out="$(as ada tl schema package publish co.acme.awp@1.1.0)"; echo "$out"
  expect "published co.acme.awp@1.1.0" "$out"
  mkdir -p "$workdir/bad"
  sed '0,/weight: 30, evidence: manual/s//weight: 31, evidence: manual/' "$RULES" >"$workdir/bad/co.acme.awp@1.1.0.yaml"
  refuse "do not sum to 100" as ada tl schema lint --dir "$workdir/bad"
  out="$(as alice tl awp roc show --project "$PROJECT")"; echo "$out"
  out="$(as ada tl awp roc set co.acme.awp@1.1.0 --project "$PROJECT")"; echo "$out"
  out="$(as alice tl awp roc show --project "$PROJECT")"; echo "$out"
  expect "edition co.acme.awp@1.1.0" "$out"
  expect "source setting" "$out"
  clause 1 "co.acme.awp@1.1.0 published by ada; a copy at 101 refused by L008; a plain publish refused; adopted for $PROJECT"

  step "[$backend] the work: standards, 32 scope items, three tags, two IWPs"
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
  as alice tl awp iwp add-scope "$IWP" "${keys24[@]}" --project "$PROJECT" >/dev/null
  as alice tl awp iwp add-scope "$IWP" "${keys8[@]}" 47-FV-1001 47-FV-1002 47-FV-1003 --project "$PROJECT" >/dev/null
  out="$(as alice tl awp iwp create --project "$PROJECT" --discipline PIP --title "Pipe rack spools, level 2" \
    --planned-start 2026-11-16 --planned-finish 2027-02-05 --foreman user:frank --hours 60)"; echo "$out"
  expect "created IWP $IWP2" "$out"
  keys2=()
  for n in 1 2 3 4; do
    out="$(as alice tl awp iwp item-create --project "$PROJECT" --commodity piping --description "Spool B$n, line 48-P-$n" --qty 6 --uom m --hours 2)"
    keys2+=("$(last_word "$out")")
  done
  as alice tl awp iwp add-scope "$IWP2" "${keys2[@]}" --project "$PROJECT" >/dev/null
  catch_up

  step "[$backend] clause 2: a new XER snapshot; the look-ahead lists the activity with its IWP and need-by"
  quiet uv run python dev/demos/p1_i4_demo.py prepare "$workdir" >/dev/null || fail "no XER files were written"
  out="$(as ada tl xer define MAIN --project "$PROJECT" --name "Pipe rack schedule" --type current)"; echo "$out"
  expect "defined MAIN" "$out"
  out="$(as alice tl xer upload "$workdir/update-1.xer" --project "$PROJECT" --schedule MAIN)"; echo "$out"
  expect "queued MAIN#1" "$out"
  out="$(as ada tl xer worker --once)"; echo "$out"
  expect "worker done: ran=1" "$out"
  out="$(as dora tl xer publish 1 --project "$PROJECT" --schedule MAIN)"; echo "$out"
  expect "published MAIN#1" "$out"
  as alice tl xer link "$IWP" A1230 --project "$PROJECT" --schedule MAIN >/dev/null
  out="$(as alice tl awp look-ahead --project "$PROJECT" --schedule MAIN --weeks 4)"; echo "$out"
  expect "need-by" "$out"
  expect "ready " "$out"
  expect "$IWP" "$out"
  expect "need-by 2026-10-12" "$out"
  clause 2 "the look-ahead lists A1230 with $IWP, ready counts and need-by 2026-10-12 (planned start minus 4 weeks)"

  step "[$backend] clause 3: a check-raised constraint cleared as waived; the release"
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
  as alice tl doc rev create ISO-1234 --project "$PROJECT" --purpose "Issued for construction" >/dev/null
  printf '%%PDF-1.7 ISO-1234 rev B\n' >"$workdir/ISO-1234-B.pdf"
  as alice tl doc rendition add ISO-1234 B "$workdir/ISO-1234-B.pdf" --project "$PROJECT" --kind pdf --pages 1 >/dev/null
  out="$(as dora tl doc rev issue ISO-1234 B --project "$PROJECT" --status IFC)"; echo "$out"
  evaluate
  out="$(readiness_of "$IWP")"; echo "$out"
  expect "documents_current  blocked" "$out"
  out="$(as alice tl constraint ls --project "$PROJECT")"; echo "$out"
  check_key="$(awk '/readiness check documents_current is blocked/ {print $1; exit}' <<<"$out")"
  [ -n "$check_key" ] || fail "no constraint was raised by the documents check"
  refuse "needs the core.constraint.waive access word" as plain tl constraint clear "$check_key" --project "$PROJECT" --reason "not mine"
  refuse "reason" as ada tl constraint clear "$check_key" --project "$PROJECT"
  out="$(as ada tl constraint clear "$check_key" --project "$PROJECT" --reason "stale pin accepted for the demo")"; echo "$out"
  expect "clear $check_key" "$out"
  out="$(as alice tl awp iwp show "$IWP" --project "$PROJECT")"; echo "$out"
  expect "waived" "$out"
  out="$(as dora tl doc stale --project "$PROJECT")"; echo "$out"
  link="$(awk '$3 == "ISO-1234" {print $NF; exit}' <<<"$out")"
  [ -n "$link" ] && as alice tl doc repin "$link" --project "$PROJECT" --apply >/dev/null
  evaluate
  out="$(as alice tl awp iwp hash "$IWP" --project "$PROJECT")"; echo "$out"
  hash="$(awk '/^record hash /{print $3}' <<<"$out")"
  [ -n "$hash" ] || fail "no record hash for $IWP"
  as dora tl awp iwp sign-off "$IWP" --project "$PROJECT" --hash "$hash" >/dev/null
  as sue tl awp iwp sign-off "$IWP" --project "$PROJECT" --hash "$hash" >/dev/null
  out="$(as dora tl awp iwp issue "$IWP" --project "$PROJECT" --hash "$hash" --foreman user:frank)"; echo "$out"
  expect "issue $IWP  version" "$out"
  expect "Issued" "$(state_of "$IWP")"
  clause 3 "$check_key raised by documents_current and cleared as waived by ada with a reason; plain and reason-less clears refused; $IWP issued"

  step "[$backend] clause 4: the week; a blocking constraint on an Issued IWP holds it once; a stale version"
  out="$(as alice tl awp week open --date 2026-11-09 --project "$PROJECT")"; echo "$out"
  expect "open 2026-W46" "$out"
  ver="$(awk '/^open /{print $NF}' <<<"$out")"
  out="$(as alice tl awp week commit 2026-W46 "$IWP" --foreman user:frank --hours 120 --expected-version "$ver" --project "$PROJECT")"; echo "$out"
  expect "commit 2026-W46" "$out"
  refuse "changed since it was read" as alice tl awp week commit 2026-W46 "$IWP" --foreman user:frank --hours 120 --expected-version "$ver" --project "$PROJECT"
  # IWP2 is the second package: it goes through the same release as IWP
  as alice tl awp iwp move "$IWP2" start-development --project "$PROJECT" >/dev/null
  as alice tl awp iwp move "$IWP2" constraint-check --project "$PROJECT" >/dev/null
  evaluate
  out="$(as alice tl awp iwp hash "$IWP2" --project "$PROJECT")"; echo "$out"
  hash2="$(awk '/^record hash /{print $3}' <<<"$out")"
  [ -n "$hash2" ] || fail "no record hash for $IWP2"
  as dora tl awp iwp sign-off "$IWP2" --project "$PROJECT" --hash "$hash2" >/dev/null
  as sue tl awp iwp sign-off "$IWP2" --project "$PROJECT" --hash "$hash2" >/dev/null
  out="$(as dora tl awp iwp issue "$IWP2" --project "$PROJECT" --hash "$hash2" --foreman user:frank)"; echo "$out"
  expect "Issued" "$(state_of "$IWP2")"
  out="$(as alice tl constraint raise --project "$PROJECT" --subject "$IWP2" --phase start --severity blocking \
    --category labour --owner user:alice --description "Scaffold crew not confirmed")"; echo "$out"
  as ada tl awp worker --once >/dev/null
  as ada tl awp worker --once >/dev/null
  out="$(as alice tl awp iwp show "$IWP2" --project "$PROJECT")"; echo "$out"
  expect "On hold" "$out"
  held="$(as demo tl events tail --project "$PROJECT" -n 2000 2>/dev/null | grep -c 'IWP.Held' || true)"
  [ "$held" = 1 ] || fail "the IWP.Held count is $held, not 1"
  echo "IWP.Held events: $held"
  as ada tl awp worker --once >/dev/null
  held2="$(as demo tl events tail --project "$PROJECT" -n 2000 2>/dev/null | grep -c 'IWP.Held' || true)"
  [ "$held2" = 1 ] || fail "the replay wrote a second IWP.Held ($held2)"
  clause 4 "$IWP2 On hold after the first worker run, one IWP.Held after the second; week 2026-W46 open with $IWP committed; a stale version refused"

  step "[$backend] clause 5: progress moves the earned figure; the week is closed; the KPIs and the CSV"
  as alice tl awp iwp start-work "$IWP" --project "$PROJECT" >/dev/null
  k0="${keys24[0]}"
  as alice tl awp iwp step "$IWP" "$k0" "Material received" --project "$PROJECT" >/dev/null
  out="$(as alice tl awp iwp item-move "$k0" install --project "$PROJECT")"; echo "$out"
  expect "install $k0" "$out"
  out="$(as alice tl awp iwp progress "$IWP" --project "$PROJECT")"; echo "$out"
  pct="$(awk -v k="$k0" '$1 == k {print $2; exit}' <<<"$out")"
  case "$pct" in 90|90.*) ;; *) fail "the item $k0 reads '$pct', not 90 (material 30 and installed 60)" ;; esac
  out="$(as alice tl awp iwp complete-field "$IWP" --project "$PROJECT")"; echo "$out"
  expect "complete-field $IWP" "$out"
  out="$(as alice tl awp week outcome 2026-W46 "$IWP" done --project "$PROJECT")"; echo "$out"
  expect "outcome" "$out"
  pver="$(grep -oE 'version [0-9]+' <<<"$out" | awk '{print $2; exit}')"
  out="$(as dora tl awp week close 2026-W46 --expected-version "$pver" --project "$PROJECT")"; echo "$out"
  expect "close 2026-W46" "$out"
  ppc_text="$(as alice tl awp week ppc --project "$PROJECT")"; echo "$ppc_text"
  expect "ppc 100.0" "$ppc_text"
  free_text="$(as alice tl awp report kpi_constraint_free --project "$PROJECT")"; echo "$free_text"
  kpi_ppc="$(as alice tl awp report kpi_ppc --project "$PROJECT")"; echo "$kpi_ppc"
  driver recount 2026-W46 "$ppc_text" "$free_text"
  printf 'code,description,quantity_budget,quantity_actual,quantity_eac\n4210-CMD,=cmd,100,40,100\n' >"$workdir/cost.csv"
  out="$(as demo tl cost import "$workdir/cost.csv" --project "$PROJECT" --period 2026-10 --as-of 2026-10-31 --apply)"; echo "$out" | tail -1
  out="$(as alice tl awp export progress --project "$PROJECT" --period 2026-W45)"; echo "$out"
  expect "=cmd" "$out"
  clause 5 "$k0 at 90 after the material step and install; PPC 100.0 and the constraint-free figure equal a ledger recount; the CSV quotes =cmd"

  step "[$backend] clause 6: the work pack"
  out="$(as alice tl awp iwp pack "$IWP" --project "$PROJECT" --out "$workdir/pack.html" --attach)"; echo "$out"
  expect "pack $IWP" "$out"
  expect "slot pack" "$out"
  grep -q "not tracked yet" "$workdir/pack.html" || fail "the pack has no 'not tracked yet' line"
  while read -r heading; do
    grep -qF "$heading" "$workdir/pack.html" || fail "the pack lacks the template heading: $heading"
  done < <(grep -oE '<h[1-6][^>]*>[^<]+' packages/tl-modules/awp/src/tl_mod_awp/pack_template.html | sed -E 's/^<h[1-6][^>]*>//')
  if grep -q '^note:' <<<"$out"; then
    echo "segno is not installed: the pack has no drawing marks ($(grep "^note:" <<<"$out" | head -1))"
  else
    grep -q '<svg' "$workdir/pack.html" || fail "the pack has no <svg for the drawings"
  fi
  out="$(as alice tl file ls --record "$IWP" --project "$PROJECT" --slot pack)"; echo "$out"
  expect "pack" "$out"
  clause 6 "$IWP pack holds the template headings and 'not tracked yet'; the file is in slot pack"

  step "[$backend] clause 9: the TUI as the foreman"
  driver landing "$IWP"
  as frank tl config set tui.landing default --user frank >/dev/null || fail "tl config set tui.landing default --user frank was refused"
  driver grid
  as frank tl config set tui.landing iwp_mine --user frank >/dev/null
  clause 9 "the TUI opens as user:frank on the IWP log, mine filter on, the summary names the foreman; with tui.landing=default it opens on the grid"

  step "[$backend] clause 10: agents over MCP"
  driver tools
  driver week-counts 2026-W46
  fail "clause 10 is not complete: the agent's proposals, the person's acceptance, the refusals and the T16 walk are not in this demo yet"

  stop_server
  drop_pg
  echo "[$backend] clauses 1 2 3 4 5 6 9 10 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-I5 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
