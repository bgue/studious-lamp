#!/usr/bin/env bash
# Demo for P1-UX2 (the log standard, actions from the server, the RFI record and document preview):
# `just demo P1-UX2`.
#
# The four clauses (SCOPE.md section 5), each ending in a PASS line, once on SQLite and once on
# Postgres. This demo drives only the four clauses; the leak check of every screen runs inside the
# tour generator (`just tour-all`), not here (skill rule 12).
#   1  the breadcrumb of the RFI log follows the highlighted row and changes when the cursor moves;
#   2  the actions bar of an RFI shows Answer where an answer is due and Issue only to a controller
#      (a plain reader is offered neither Issue nor, once it is answered, Answer), and Answer from
#      the bar answers it;
#   3  the RFI record shows the narrative (the question whole), the timeline of the answer round in
#      order, and the Files tab lists both attached files;
#   4  `v` on the document row hands a copy of the PDF to the viewer (a recorder script): the copy
#      is in a private folder (mode 0700) and its sha256 equals the stored file's; with images off
#      the panel reads the page-count fallback ("PDF document ... 3 pages").
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
driver() { quiet uv run python dev/demos/p1_ux2_demo.py "$@" || fail "an exit clause was not met"; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger: an admin, an answerer, a controller"
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
  driver prepare "$workdir"

  step "[$backend] seed: an RFI after an answer round, a second RFI, a document with a 3-page PDF"
  as demo tl standards load "$STANDARDS" >/dev/null
  as demo tl standards load "$DOC_STANDARDS" >/dev/null
  local needed out first second third
  needed="$(python3 -c 'import datetime as d; print(d.date.today() + d.timedelta(days=10))')"
  out="$(as amy tl rfi raise --project P123 --subject "$(cat "$workdir/subject-1")" --question "$(cat "$workdir/question")" --discipline structural --required-by "$needed" --to "Meridian:pm@meridian.example")"
  first="$(echo "$out" | awk '/^raised/ {print $2}')"
  [ -n "$first" ] || fail "no number for the first RFI"
  as amy tl file put "$workdir/beam-b12-sketch.pdf" --project P123 --record "$first" --slot attachment --actor user:amy >/dev/null
  as amy tl file put "$workdir/survey-notes.txt" --project P123 --record "$first" --slot attachment --actor user:amy >/dev/null
  as amy tl rfi submit "$first" --project P123 >/dev/null
  as dora tl rfi issue "$first" --project P123 >/dev/null
  as amy tl rfi answer "$first" --project P123 --answer "Use the original routing." --cost-impact no --schedule-impact no >/dev/null
  as dora tl rfi review "$first" --project P123 --reject --note "The beam moved in revision C; please check again." >/dev/null
  as amy tl rfi reissue "$first" --project P123 --reason "Revision C attached" >/dev/null
  as dora tl rfi issue "$first" --project P123 >/dev/null
  out="$(as amy tl rfi raise --project P123 --subject "$(cat "$workdir/subject-2")" --question "Which gasket class applies to the new flange at line 47-P-102?" --discipline piping --required-by "$needed" --to "Meridian:pm@meridian.example")"
  second="$(echo "$out" | awk '/^raised/ {print $2}')"
  [ -n "$second" ] || fail "no number for the second RFI"
  as amy tl rfi submit "$second" --project P123 >/dev/null
  as dora tl rfi issue "$second" --project P123 >/dev/null
  out="$(as amy tl rfi raise --project P123 --subject "$(cat "$workdir/subject-3")" --question "Confirm 1.5 m support spacing for the cable trays on rack R-2." --discipline structural --required-by "$needed" --to "Meridian:pm@meridian.example")"
  third="$(echo "$out" | awk '/^raised/ {print $2}')"
  [ -n "$third" ] || fail "no number for the third RFI"
  as amy tl rfi submit "$third" --project P123 >/dev/null
  as amy tl doc register ISO-1234 --project P123 --title "Isometric, line 47-P-101" --type ISO --discipline PIP --originator "Acme Piping" >/dev/null
  as amy tl doc rev create ISO-1234 --project P123 --purpose "For review" >/dev/null
  as amy tl doc rendition add ISO-1234 A "$workdir/iso-1234.pdf" --project P123 --kind pdf >/dev/null
  as demo tl doc rev issue ISO-1234 A --project P123 --status IFR >/dev/null
  echo "seeded: $first (answer round, two files), $second (awaiting an answer), $third (waiting to be issued), ISO-1234 (3-page PDF)"
  export TL_DEMO_RFI_1="$first" TL_DEMO_RFI_2="$second" TL_DEMO_RFI_3="$third"

  step "[$backend] clause 1: the breadcrumb follows the highlighted row"
  driver crumb

  step "[$backend] clause 2: the bar offers Answer where an answer is due and Issue to a controller only; Answer answers"
  driver bar

  step "[$backend] clause 3: the RFI record shows narrative, timeline and files"
  driver record

  step "[$backend] clause 4: v opens the PDF in the viewer; the panel falls back to the page count"
  export TL_IMAGES=off TL_VIEWER_CMD="python3 $workdir/viewer.py" TL_DEMO_VIEWER_OUT="$workdir/viewer.json"
  rm -f "$workdir/viewer.json"
  driver preview
  unset TL_IMAGES TL_VIEWER_CMD TL_DEMO_VIEWER_OUT

  drop_pg
  echo "[$backend] clauses 1-4 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-UX2 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
