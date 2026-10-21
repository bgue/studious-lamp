#!/usr/bin/env bash
# Demo for P1-UX (the full record screen from every register, plain language by default, and the
# technical-details toggle): `just demo P1-UX`.
#
# The four clauses (SCOPE.md), each ending in a PASS line, once on SQLite and once on Postgres:
#   1  from each register (documents, tags, correspondence register, triage inbox, clocks, RFI log,
#      commercial, schedule list, review queue) Enter opens the record screen; its Properties tab
#      lists the set for that type with labels (Document data, RFI data, Correspondence data), and
#      Esc returns to the same row. The ledger holds values for the three new example sets;
#   2  as a plain user no screen shows a ULID, hash, schema version, internal key, or clock or
#      calendar id (the T11 walking test, and every register and record screen of this ledger read
#      through the same leak finder), and the toggle key answers with a one-line refusal;
#   3  as an admin Ctrl+D shows those details on the document register and Ctrl+D hides them again;
#   4  a restricted notice (an early warning the rule proposed and a controller accepted, as in
#      P1-I6) opened by a plain user from a stale row reads exactly like a record that never existed.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. No server is
# needed: the `tl` commands and the TUI work on the ledger. Nothing is sent anywhere and nothing is
# left behind. Exits non-zero (and prints DEMO FAILED) when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
pg_url=""
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'drop_pg; rm -rf "$workdir"' EXIT

STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
DOC_STANDARDS=schema/fixtures/standards/co.acme.documents@1.0.0.yaml

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_ux_demo.py "$@" || fail "an exit clause was not met"; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}
setvalues() { # setvalues WHO KEY PSET NAME=VALUE...: set a pset and expect a conformance verdict
  local who="$1" key="$2" pset="$3" out; shift 3
  out="$(as "$who" tl pset set --project P123 "$key" "$pset" "$@")" || { echo "$out"; fail "pset set $key $pset"; }
  echo "$out" | sed -n 1,2p
  expect "conformance" "$out"
}

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger: an admin, a plain user, a controller"
  drop_pg
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
  printf '%s\n' "a long passphrase for dora" | as demo tl admin user add dora --display-name "Dora C" --password-stdin >/dev/null
  as demo tl admin user roles dora --add document_controller >/dev/null
  printf '%s\n' "a long passphrase for amy" | as amy tl login amy --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for dora" | as dora tl login dora --password-stdin >/dev/null

  step "[$backend] seed: a document, a tag, letters, an RFI, a restricted early warning, a schedule"
  as demo tl standards load "$STANDARDS" >/dev/null
  as demo tl standards load "$DOC_STANDARDS" >/dev/null
  as dora tl corr party add ACME --project P123 --name "Acme Construction" --role contractor \
    --email-domain acme.example --contact "Ann:ann@acme.example" >/dev/null
  as amy tl doc register ISO-1234 --project P123 --title "Isometric, line 47-P-101" --type ISO --discipline PIP --originator "Acme Piping" >/dev/null
  as demo tl tag create 47-FV-1001 --class ControlValve --service "Feed gas" --project P123 >/dev/null
  printf '%s\n' "Please find our revised programme. We would be grateful for your comments." >"$workdir/letter.txt"
  out="$(as amy tl corr receive --project P123 --subject "Revised programme" --from "Acme Construction" --file "$workdir/letter.txt" --body-file "$workdir/letter.txt")"
  letter="$(echo "$out" | awk '/^received/ {print $2}')"
  [ -n "$letter" ] || fail "no item number for the letter"
  as amy tl corr suggest "$letter" --project P123 >/dev/null
  as amy tl corr triage "$letter" --project P123 --accept >/dev/null
  out="$(as amy tl corr receive --project P123 --subject "Site access arrangements" --from "Acme Construction")"
  inbox="$(echo "$out" | awk '/^received/ {print $2}')"
  [ -n "$inbox" ] || fail "no item number for the letter in the inbox"
  local needed
  needed="$(python3 -c 'import datetime as d; print(d.date.today() + d.timedelta(days=10))')"
  out="$(as amy tl rfi raise --project P123 --subject "Beam B12 clashes with line 47" --question "The isometric clashes with beam B12; confirm the routing." --discipline structural --required-by "$needed" --to "Meridian:pm@meridian.example")"
  rfi="$(echo "$out" | awk '/^raised/ {print $2}')"
  [ -n "$rfi" ] || fail "no RFI number"
  as amy tl rfi submit "$rfi" --project P123 >/dev/null
  as dora tl rfi issue "$rfi" --project P123 >/dev/null
  as demo tl rule create --file dev/seed/rules/rfi-escalation.json --project P123 >/dev/null
  as demo tl rule enable rfi-escalation --project P123 >/dev/null
  as amy tl rfi answer "$rfi" --project P123 --answer "Re-route above the beam; revision C follows." --cost-impact yes --schedule-impact no >/dev/null
  as demo tl integration serve --once >/dev/null
  proposal="$(as dora tl proposal ls --project P123 | awk '/svc:rule-rfi-escalation/ {print $1; exit}')"
  [ -n "$proposal" ] || fail "the rule made no proposal"
  as dora tl proposal accept "$proposal" >/dev/null
  notice="P123-EW-0001"
  expect "class restricted" "$(as dora tl comm show "$notice" --project P123)"
  driver prepare "$workdir"
  as demo tl xer define MAIN --project P123 --name "Pipe rack schedule" --type current >/dev/null
  as amy tl xer upload "$workdir/update-1.xer" --project P123 --schedule MAIN >/dev/null
  as demo tl xer worker --once >/dev/null
  echo "seeded: $letter (triaged), $inbox (inbox), $rfi, $notice (restricted), schedule MAIN"

  step "[$backend] the three new sets get values on those records (each set prints a conformance line)"
  setvalues amy ISO-1234 document_data originator="Acme Piping" area="Unit 47" system="Fuel gas" \
    confidentiality_note="Vendor data, share with the owner only" native_format=DWG review_due=2027-01-15
  setvalues dora "$rfi" rfi_data location="Grid C-4" drawing_ref=DWG-4711 trade=structural \
    cost_estimate=12500 cost_currency=USD schedule_impact_days=3
  for item in "$letter" "$inbox" "$notice"; do
    setvalues dora "$item" correspondence_data contract_clause='"14.2"' other_party_ref=ACME-LTR-0042 \
      response_required_by=2027-02-01 delivery_method=email
  done
  setvalues demo 47-FV-1001 valve_data size_in=4 body_material=SS316L

  step "[$backend] clause 1: Enter opens the record screen from each register; Properties lists the set"
  driver registers

  step "[$backend] clause 2: a plain user sees no technical text; the toggle key is refused"
  if [ -z "${walk_done:-}" ]; then
    out="$(quiet uv run pytest packages/tl-tui/tests/test_plain_walk.py -q -p no:cacheprovider 2>&1)" || { echo "$out"; fail "the plain-user walk failed"; }
    echo "$out" | tail -n 3
    expect " passed" "$out"
    walk_done=1
  fi
  driver plain

  step "[$backend] clause 3: an admin turns technical details on and off"
  driver admin

  step "[$backend] clause 4: a restricted record opened from a stale row reads like a missing one"
  export TL_DEMO_NOTICE="$notice"
  driver hidden

  drop_pg
  echo "[$backend] clauses 1-4 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-UX demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
