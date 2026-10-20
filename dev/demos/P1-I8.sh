#!/usr/bin/env bash
# Demo for P1-I8 (the schema workbench on the command line: packages, governance, adoption,
# waivers, crosswalk, git export and import; the legacy register; the lake marts; the exit chain):
# `just demo P1-I8`.
#
# The exit clauses (brief 27.8 and 6.3), each ending in a PASS line, once on SQLite and once on
# Postgres:
#   1  a person drafts an additive co.acme.engineering 3.3.0; it analyses as worst additive; the
#      author submits it and cannot approve it; the admin approves it and publishes it; a draft
#      that retypes a property (4.0.0) analyses as breaking and its submit is refused;
#   2  the impact report of 3.3.0 for P999 prints a digest; the admin pins 3.3.0 with that digest;
#      adoptions lists the pin;
#   3  a person asks for a 30-day waiver of psets.valve_data.size_in on P999; the admin approves
#      it; waiver ls shows it Approved until that day; the admin revokes it and the list shows
#      Revoked;
#   4  the crosswalk of P123 maps valve_data.body_material; export-git writes the published
#      versions and a second run says unchanged; import-git --dry-run drafts nothing; a file
#      edited by hand makes import-git print a problem and exit 1;
#   5  an admin loads a CSV register of three documents (P123) through the dms-register loader:
#      extract, profile, bronze, plan (3 new), load --expect-new 3, reconcile (no problems); a
#      restricted file is loaded too; later `compensate` ends the three documents (gone from
#      `tl doc ls`), and a new plan of the same file says `new 0 existing 3` (the compensated keys
#      stay in the ledger, voided);
#   6  after `tl lake sync` the lake lists the document marts and the schedule-history mart (two
#      XER uploads, as in P1-I4). The lake is built for the LOWEST reader (ADR-0016, @D10), so the
#      restricted document is absent from the mart for the admin and for a plain user alike;
#      `mart_document_status` for P123 counts 3 more documents after the load and falls back after
#      the compensate (the order is: load, sync, mart checks, compensate, sync, mart checks);
#   7  the exit chain, PDF -> derived -> published -> feed -> receiver: a rule on the publication
#      posts to the feed and an action sends a signed webhook that the loopback receiver verifies
#      (the PDF and publication steps of P1-I3, and the receiver, allow-list, action and rule
#      steps of P1-I7, copied here).
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. No server is
# needed: the `tl` commands work on the ledger, and clause 7 starts a receiver on a loopback
# port and stops it again. Nothing is left behind.
# Exits non-zero (and prints DEMO FAILED) when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
pg_url=""
receiver_pid=""
stop_receiver() { # the receiver has its own process group (setsid): stop the whole group
  local pid="$receiver_pid"
  [ -n "$pid" ] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || true
  for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
  kill -KILL -- "-$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  receiver_pid=""
}
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'stop_receiver; drop_pg; rm -rf "$workdir"' EXIT

STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
SAMPLES=schema/fixtures/document-schemas

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_LAKE_DIR="$workdir/lake"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i8_demo.py "$@" || fail "an exit clause was not met"; }
i3() { quiet uv run python dev/demos/p1_i3_demo.py "$@" || fail "the P1-I3 driver failed: $*"; }
i7() { quiet uv run python dev/demos/p1_i7_demo.py "$@" || fail "the P1-I7 driver failed: $*"; }
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

mart_json() { # mart_json WHO MART: the mart as the person sees it (a missing mart is no rows)
  as "$1" tl lake mart show "$2" --json 2>/dev/null || echo '{"columns": [], "rows": []}'
}
mart_docs() { # mart_docs JSON: documents counted for P123 in mart_document_status
  python3 -c '
import json, sys
d = json.loads(sys.argv[1])
i = d["columns"].index("documents") if d["columns"] else 0
print(sum(r[i] for r in d["rows"] if r[0] == "project:P123"))' "$1"
}
mart_has_restricted() { # mart_has_restricted JSON: any row of the restricted document (PRC, CIV)?
  python3 -c '
import json, sys
d = json.loads(sys.argv[1])
print("yes" if [r for r in d["rows"] if "PRC" in r or "CIV" in r] else "no")' "$1"
}

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, two people"
  drop_pg
  rm -rf "$workdir/git" "$workdir/lake"
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
  printf '%s\n' "a long passphrase for amy" | as demo tl admin user add amy --display-name "Amy A" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for amy" | as amy tl login amy --password-stdin >/dev/null

  step "[$backend] clause 1: an additive draft is reviewed and published; a breaking draft is refused"
  out="$(as amy tl schema package draft "$workdir/pkg-3.3.0.yaml" --changelog "Adds the actuator make.")"; echo "$out"
  expect "drafted co.acme.engineering@3.3.0" "$out"
  out="$(as amy tl schema package analyse co.acme.engineering@3.3.0)"; echo "$out"
  expect "analysed co.acme.engineering@3.3.0 additive" "$out"
  out="$(as amy tl schema package classify co.acme.engineering@3.3.0)"; echo "$out"
  expect "worst additive" "$out"
  as amy tl schema package submit co.acme.engineering@3.3.0 >/dev/null
  out="$(as amy tl schema package approve co.acme.engineering@3.3.0 2>&1)" && {
    echo "$out"; fail "the author approved their own draft"
  }
  echo "$out"
  case "$out" in *forbidden* | *"cannot approve"*) ;; *) fail "the author's approval was refused without saying why" ;; esac
  out="$(as demo tl schema package approve co.acme.engineering@3.3.0 --comment "additive, reviewed")"; echo "$out"
  expect "co.acme.engineering@3.3.0" "$out"
  out="$(as demo tl schema package publish co.acme.engineering@3.3.0)"; echo "$out"
  expect "published co.acme.engineering@3.3.0" "$out"
  out="$(as amy tl schema package draft "$workdir/pkg-4.0.0.yaml")"; echo "$out"
  expect "drafted co.acme.engineering@4.0.0" "$out"
  out="$(as amy tl schema package analyse co.acme.engineering@4.0.0)"; echo "$out"
  expect "analysed co.acme.engineering@4.0.0 breaking" "$out"
  out="$(as amy tl schema package classify co.acme.engineering@4.0.0)"; echo "$out"
  expect "worst breaking" "$out"
  refuse "not allowed in place" as amy tl schema package submit co.acme.engineering@4.0.0
  echo "PASS 1: an additive draft was analysed, submitted, approved by the admin and published; its author could not approve it; a draft that retypes size_in was analysed as breaking and its submit was refused"

  step "[$backend] clause 2: the impact digest of 3.3.0 for P999, and the pin"
  out="$(as demo tl schema package impact co.acme.engineering@3.3.0 --project P999)"; echo "$out"
  expect "digest" "$out"
  digest="$(echo "$out" | awk '$1 == "digest" {print $2}')"
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || fail "the impact report printed no sha256 digest"
  out="$(as demo tl schema adopt P999 co.acme.engineering 3.3.0 --impact-sha256 "$digest")"; echo "$out"
  expect "adopted P999 co.acme.engineering@3.3.0" "$out"
  out="$(as demo tl schema adoptions)"; echo "$out"
  expect "P999  co.acme.engineering@3.3.0  from 3.2.0  additive  by user:" "$out"
  echo "PASS 2: the impact of 3.3.0 for P999 has a digest; the admin pinned 3.3.0 with it; adoptions lists the pin"

  step "[$backend] clause 3: a waiver asked for by amy, approved by the admin, revoked"
  until="$(python3 -c 'import datetime; print(datetime.date.today() + datetime.timedelta(days=30))')"
  out="$(as amy tl schema waiver request P999 psets.valve_data.size_in --reason "Legacy valves keep the old nominal size." --expires "$until")"; echo "$out"
  expect "requested P999/psets.valve_data.size_in@1" "$out"
  out="$(as demo tl schema waiver approve P999/psets.valve_data.size_in@1 --comment "for 30 days")"; echo "$out"
  expect "approved P999/psets.valve_data.size_in@1" "$out"
  out="$(as amy tl schema waiver ls --project P999)"; echo "$out"
  expect "P999/psets.valve_data.size_in@1  Approved  until $until" "$out"
  out="$(as demo tl schema waiver revoke P999/psets.valve_data.size_in@1 --reason "Fixed at the source.")"; echo "$out"
  expect "revoked P999/psets.valve_data.size_in@1" "$out"
  out="$(as amy tl schema waiver ls --project P999)"; echo "$out"
  expect "P999/psets.valve_data.size_in@1  Revoked  until $until" "$out"
  echo "PASS 3: amy asked for a 30-day waiver of psets.valve_data.size_in on P999; the admin approved it, then revoked it; the list shows Revoked"

  step "[$backend] clause 4: the crosswalk, export-git, import-git"
  out="$(as demo tl schema crosswalk --project P123)"; echo "$out"
  expect "valve_data.body_material  MaterialCode  SS316L-NACE  SS316L  mapped" "$out"
  out="$(as demo tl schema export-git "$workdir/git")"; echo "$out"
  expect "exported" "$out"
  out="$(as demo tl schema export-git "$workdir/git")"; echo "$out"
  expect "exported 0 written" "$out"
  expect "unchanged" "$out"
  out="$(as demo tl schema import-git "$workdir/git" --dry-run)"; echo "$out"
  expect "dry run 0 to draft" "$out"
  printf '# edited by hand\n' >>"$workdir/git/co.acme.engineering@3.3.0.yaml"
  code=0; out="$(as demo tl schema import-git "$workdir/git" 2>&1)" || code=$?
  echo "$out"
  [ "$code" = 1 ] || fail "import-git must exit 1 on a problem, not $code"
  expect "problem co.acme.engineering@3.3.0.yaml exists with other text" "$out"
  echo "PASS 4: the crosswalk maps valve_data.body_material; export-git wrote the published versions and a second run was unchanged; import-git --dry-run drafted nothing; a file edited by hand was refused with a problem and exit 1"

  step "[$backend] clause 5: a legacy register is extracted, profiled, loaded and reconciled"
  driver registers "$workdir"
  out="$(as demo tl load open "$workdir/register.csv" --project P123 --loader dms-register)"; echo "$out"
  expect "opened dms/register#1" "$out"
  out="$(as demo tl load extract dms/register#1 --project P123)"; echo "$out"
  expect "rows 3" "$out"
  as demo tl load profile dms/register#1 --project P123 >/dev/null
  out="$(as demo tl load bronze dms/register#1 --project P123 --include-confidential)"; echo "$out"
  expect "bronze dms/register#1 rows 3" "$out"
  out="$(as demo tl load plan dms/register#1 --project P123)"; echo "$out"
  expect "new 3 existing 0 invalid 0" "$out"
  docs_before="$(mart_docs "$(mart_json demo mart_document_status)")"
  [ "$docs_before" = 0 ] || fail "the document mart counted $docs_before documents before the load"
  out="$(as demo tl load load dms/register#1 --project P123 --expect-new 3)"; echo "$out"
  expect "created 3 existing 0 invalid 0" "$out"
  out="$(as demo tl load reconcile dms/register#1 --project P123)"; echo "$out"
  expect "mismatches 0" "$out"
  # a restricted file (one document), loaded as a restricted run: its rows are not copied to the lake
  as demo tl load open "$workdir/restricted.csv" --project P123 --loader dms-register \
    --confidentiality restricted >/dev/null
  as demo tl load extract dms/register#2 --project P123 >/dev/null
  as demo tl load profile dms/register#2 --project P123 >/dev/null
  as demo tl load plan dms/register#2 --project P123 >/dev/null
  out="$(as demo tl load load dms/register#2 --project P123 --expect-new 1)"; echo "$out"
  expect "created 1" "$out"
  out="$(as demo tl doc ls --project P123)"; echo "$out"
  for key in ISO-0101 ISO-0102 PID-0201 SEC-0001; do expect "$key" "$out"; done

  step "[$backend] clause 6: the lake marts (built for the lowest reader) and schedule history, before the compensate"
  # The lake is built for the lowest reader by design (ADR-0016, @D10): the restricted document
  # SEC-0001 (type PRC, discipline CIV) is in the mart for nobody, the admin included.
  as demo tl lake sync >/dev/null
  out="$(as demo tl lake mart ls)"; echo "$out"
  expect "mart_document_status" "$out"
  expect "mart_document_issues" "$out"
  expect "mart_document_turnaround" "$out"
  for who in demo amy; do
    json="$(mart_json "$who" mart_document_status)"
    docs="$(mart_docs "$json")"
    echo "[$who] mart_document_status counts $docs documents of P123"
    [ "$docs" = "$((docs_before + 3))" ] || fail "$who: the mart counts $docs documents, not $((docs_before + 3))"
    [ "$(mart_has_restricted "$json")" = no ] || fail "$who: the restricted document is in the mart"
  done
  # schedule history: the XER define, two uploads and the worker, as in P1-I4 clause 1, then publish
  quiet uv run python dev/demos/p1_i4_demo.py prepare "$workdir" >/dev/null || fail "no XER files were written"
  out="$(as demo tl xer define MAIN --project P123 --name "Pipe rack schedule" --type current)"; echo "$out"
  expect "defined MAIN" "$out"
  out="$(as amy tl xer upload "$workdir/update-1.xer" --project P123 --schedule MAIN)"; echo "$out"
  expect "queued MAIN#1" "$out"
  as amy tl xer upload "$workdir/update-2.xer" --project P123 --schedule MAIN >/dev/null
  out="$(as demo tl xer worker --once)"; echo "$out"
  expect "worker done: ran=2" "$out"
  # the mart holds one row per published snapshot: the controller publishes both
  as demo tl xer publish 1 --project P123 --schedule MAIN >/dev/null
  out="$(as demo tl xer publish 2 --project P123 --schedule MAIN)"; echo "$out"
  expect "published MAIN#2" "$out"
  as demo tl lake sync >/dev/null
  out="$(as demo tl lake mart ls)"; echo "$out"
  expect "mart_schedule_history" "$out"
  json="$(mart_json demo mart_schedule_history)"
  python3 -c 'import json, sys; sys.exit(0 if json.loads(sys.argv[1])["rows"] else 1)' "$json" \
    || fail "mart_schedule_history has no rows"
  echo "mart_schedule_history has rows"

  step "[$backend] clause 5 (continued): compensate takes the register back; a new plan counts the keys as existing"
  out="$(as demo tl load compensate dms/register#1 --project P123 --reason "demo: the load is taken back")"; echo "$out"
  expect "compensated dms/register#1 reversed 3" "$out"
  out="$(as demo tl doc ls --project P123)"; echo "$out"
  for key in ISO-0101 ISO-0102 PID-0201; do
    case "$out" in *"$key"*) fail "$key is still in the register after the compensate" ;; esac
  done
  as demo tl load open "$workdir/register.csv" --project P123 --loader dms-register >/dev/null
  as demo tl load extract dms/register#3 --project P123 >/dev/null
  as demo tl load profile dms/register#3 --project P123 >/dev/null
  out="$(as demo tl load plan dms/register#3 --project P123)"; echo "$out"
  expect "new 0 existing 3 invalid 0" "$out"
  as demo tl load void dms/register#3 --project P123 --reason "demo: the plan was only a check" >/dev/null
  echo "PASS 5: the register of 3 documents (P123) was extracted, profiled, bronzed, planned (3 new), loaded with --expect-new 3 and reconciled (0 mismatches); compensate ended the 3 documents (gone from doc ls) and a new plan says new 0 existing 3 (the keys stay in the ledger, voided)"

  step "[$backend] clause 6 (continued): after the compensate the marts no longer count the documents"
  as demo tl lake sync >/dev/null
  for who in demo amy; do
    docs="$(mart_docs "$(mart_json "$who" mart_document_status)")"
    echo "[$who] mart_document_status counts $docs documents of P123"
    [ "$docs" = "$docs_before" ] || fail "$who: the mart still counts $docs documents after the compensate"
  done
  echo "PASS 6: after tl lake sync the document marts and mart_schedule_history are listed; mart_document_status for P123 rose by 3 after the load and fell back after the compensate; the restricted document was in no mart, for the admin or for a plain user (the lake is built for the lowest reader)"

  step "[$backend] clause 7: PDF -> derived -> published -> feed -> receiver"
  # The PDF and publication steps are copied from dev/demos/P1-I3.sh (clauses 2 and 5); the
  # receiver, allow-list, action and rule steps from dev/demos/P1-I7.sh (clauses 2 and 5).
  rm -f "$workdir"/receiver.* "$workdir"/action.json
  mkdir -p "$workdir/exit"
  i3 prepare "$workdir/exit"
  as demo tl standards load "$STANDARDS" >/dev/null
  as demo tl derive schema register "$workdir/exit/instrument-index.yaml" --company >/dev/null
  as amy tl doc register ISD-001 --project P123 --title "Instrument index, unit 47" >/dev/null
  as amy tl doc rev create ISD-001 --project P123 --purpose "First issue" >/dev/null
  as amy tl doc rendition add ISD-001 A "$workdir/exit/isd-001-A.pdf" --project P123 --kind pdf \
    --pages 3 >/dev/null
  out="$(as amy tl derive open ISD-001 A --schema instrument-index --project P123)"; echo "$out"
  expect "opened ISD-001@A/instrument-index" "$out"
  as amy tl derive content "ISD-001@A/instrument-index" "$SAMPLES/instrument-index@1.0.0.sample.csv" \
    --project P123 >/dev/null
  as amy tl derive start "ISD-001@A/instrument-index" --project P123 >/dev/null
  as amy tl derive worker --once >/dev/null
  out="$(as amy tl derive show "ISD-001@A/instrument-index" --project P123)"; echo "$out"
  expect "state Valid" "$out"

  setsid uv run python dev/demos/p1_i7_demo.py receiver "$workdir" \
    >"$workdir/receiver-$backend.log" 2>&1 &
  receiver_pid=$!
  for _ in $(seq 1 100); do [ -s "$workdir/receiver.port" ] && break; sleep 0.1; done
  [ -s "$workdir/receiver.port" ] || fail "the receiver did not start"
  i7 action-file "$workdir"
  as demo tl config set webhooks.egress.allowlist 127.0.0.1 --company --reason "the demo receiver" \
    --accept-risk >/dev/null
  as demo tl record create --project P123 --title "Valve 1" --key V-1001 >/dev/null
  valve="$(as demo tl record show V-1001 --project P123 | awk '/^id:/{print $2}')"
  [ -n "$valve" ] || fail "the valve record has no id"
  out="$(as demo tl action define --file "$workdir/action.json" --project P123)"
  echo "$out" | sed 's/^secret .*/secret ***/'
  echo "$out" | sed -n 's/^secret //p' >"$workdir/receiver.secret"
  [ -s "$workdir/receiver.secret" ] || fail "no action secret was printed"
  sleep 0.5 # the receiver picks the secret up
  cat >"$workdir/publish-notify.json" <<JSON
{
  "key": "publish-notify",
  "title": "A publication posts to the feed and sends the webhook",
  "when": {"event_types": ["DerivedDocument.Published"]},
  "then": [
    {"command": "PostToFeed", "args": {"body": "Published: derived document to the feed #published"}},
    {"command": "InvokeAction", "args": {"action": "send_to_nde", "targets": ["$valve"], "parameters": {"method": "RT"}}}
  ]
}
JSON
  as demo tl rule create --file "$workdir/publish-notify.json" --project P123 >/dev/null
  as demo tl rule mode publish-notify act --reason "the demo" --project P123 >/dev/null
  as demo tl rule enable publish-notify --project P123 >/dev/null
  out="$(as demo tl derive publish "ISD-001@A/instrument-index" --project P123 --apply)"
  echo "$out" | tail -n 2
  expect "published 40 records" "$out"
  as demo tl integration serve --once >/dev/null
  out="$(as demo tl feed ls --project P123)"; echo "$out"
  expect "svc:rule-publish-notify" "$out"
  expect "Published: derived document to the feed" "$out"
  out="$(as demo tl action invocations)"; echo "$out"
  expect "completed" "$out"
  for _ in $(seq 1 50); do [ -s "$workdir/receiver.log" ] && break; sleep 0.1; done
  [ -s "$workdir/receiver.log" ] || fail "the receiver logged nothing"
  grep -q '"verified": true' "$workdir/receiver.log" || fail "the receiver did not verify the webhook"
  grep -q '"invoked_by": "svc:rule-publish-notify"' "$workdir/receiver.log" \
    || fail "the webhook was not invoked by the rule"
  stop_receiver
  echo "PASS 7: the publication of ISD-001@A/instrument-index posted to the feed; the rule's action sent a signed webhook that the receiver verified"

  drop_pg
  echo "[$backend] clauses 1-7 passed"
}

driver prepare "$workdir"
for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I8 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
