#!/usr/bin/env bash
# Demo for P2-W0 (module roles, the offline class, the record-type route, readiness words, load
# and publish targets, the tour's module roles log): `just demo P2-W0`.
#
# The exit clauses (wave0.md section 8), each ending in a `PASS clause N` line, once on SQLite and
# once on Postgres:
#   1  a seeded ledger: alice (user), dora (document_controller), ada (admin). With no grant alice
#      registers a document in P1 and cannot issue it (forbidden); dora issues it, and also runs
#      one correspondence controller act (a party) and one schedule controller act (a publish);
#   2  `tl admin roles grant alice --project P1 --module documents --role superuser`: alice issues
#      in P1, is refused in P2, and still cannot read a restricted P1 document;
#   3  dora, granted viewer of documents on P2, is refused RegisterDocument there (driver), is
#      offered no action on a P2 document (driver), and still issues in P1;
#   4  `tl admin roles effective alice --project P1` lists every module with its source; alice
#      cannot grant; GET /events as alice shows no grant event, as ada it does (driver);
#   5  an agent's propose_import_documents proposal of a valid derived register: bob and alice
#      are 403 (the accept reads the account role) and the proposal stays pending; dora, a
#      document controller, accepts it and the register's documents are created (driver);
#   6  a company grant for a stand-in module with company_roles (awp.cwp.release) is accepted and
#      the same grant on documents is refused no_company_roles (driver);
#   7  OFFLINE_CLASSES, the capture rules on the device and authority nodes (driver), and
#      `TL_NODE_KIND=device tl serve` stops with exit 2;
#   8  GET /record-types lists engineering.Tag as full, and the Offline class line shows in
#      technical mode only (driver);
#   9  load_checks() is empty, the contract passes on a sample check, a reserved identifier is
#      422 and awp.iwp.ready_lead_weeks reads 4 (driver);
#   10 `tl load targets` lists tags and documents; the tag seed loads through the tags target
#      (11 created, the 3 invalid rows refused) and reconciles; a derived document publishes
#      through the documents publish target;
#   11 `just state P2-W0` prints at most 40 lines; `just relay-lint` passes on relay-ok.txt and
#      fails on relay-bad.txt.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. The API
# clauses run in dev/demos/p2_w0_demo.py. Nothing is left behind.
# Exits non-zero (and prints DEMO FAILED) when any clause is not met.
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
clause() { echo "PASS clause $1"; }
driver() { quiet uv run python dev/demos/p2_w0_demo.py "$@" || fail "an exit clause was not met: $*"; }
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
pdf() { # pdf NAME: a rendition file for a revision (the rendition step checks the kind, not the bytes)
  printf '%%PDF-1.7 %s\n' "$1" >"$workdir/$1.pdf"
  echo "$workdir/$1.pdf"
}

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger: ada (admin), alice, bob, dora (document controller)"
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake"
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
  printf '%s\n' "a long passphrase for alice" | as demo tl admin user add alice --display-name "Alice" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for bob" | as demo tl admin user add bob --display-name "Bob" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for dora" | as demo tl admin user add dora --display-name "Dora" --role document_controller --password-stdin >/dev/null
  for who in ada alice bob dora; do
    printf '%s\n' "a long passphrase for $who" | as "$who" tl login "$who" --password-stdin >/dev/null
  done

  step "[$backend] clause 1: alice registers and cannot issue; dora issues, and runs a correspondence and a schedule act"
  out="$(as alice tl doc register ISO-1001 --project P1 --title "Isometric drawing unit 47")"; echo "$out"
  expect "document ISO-1001" "$out"
  out="$(as alice tl doc rev create ISO-1001 --project P1 --purpose "First issue")"; echo "$out"
  expect "created revision A Draft" "$out"
  out="$(as alice tl doc rendition add ISO-1001 A "$(pdf ISO-1001-A)" --project P1 --kind pdf --pages 1)"; echo "$out"
  expect "attached pdf" "$out"
  refuse "forbidden" as alice tl doc rev issue ISO-1001 A --project P1 --status IFR
  out="$(as dora tl doc rev issue ISO-1001 A --project P1 --status IFR)"; echo "$out"
  expect "issued ISO-1001@A as IFR" "$out"
  refuse "forbidden" as alice tl corr party add ACME --project P1 --name "Acme Construction" --role contractor \
    --email-domain acme.example --contact "Ann:ann@acme.example"
  out="$(as dora tl corr party add ACME --project P1 --name "Acme Construction" --role contractor \
    --email-domain acme.example --contact "Ann:ann@acme.example")"; echo "$out"
  expect "ACME" "$out"
  quiet uv run python dev/demos/p1_i4_demo.py prepare "$workdir" >/dev/null || fail "no XER files were written"
  out="$(as ada tl xer define MAIN --project P1 --name "Pipe rack schedule" --type current)"; echo "$out"
  expect "defined MAIN" "$out"
  out="$(as alice tl xer upload "$workdir/update-1.xer" --project P1 --schedule MAIN)"; echo "$out"
  expect "queued MAIN#1" "$out"
  out="$(as ada tl xer worker --once)"; echo "$out"
  expect "worker done: ran=1" "$out"
  out="$(as dora tl xer publish 1 --project P1 --schedule MAIN)"; echo "$out"
  expect "published MAIN#1" "$out"
  clause 1

  step "[$backend] clause 2: alice is superuser on documents in P1, refused in P2, and cannot read a restricted document"
  out="$(as ada tl admin roles grant alice --project P1 --module documents --role superuser --reason demo)"; echo "$out"
  expect "granted superuser on documents for project:P1 to alice" "$out"
  out="$(as alice tl doc rev create ISO-1001 --project P1 --purpose "Second issue")"; echo "$out"
  expect "created revision B Draft" "$out"
  as alice tl doc rendition add ISO-1001 B "$(pdf ISO-1001-B)" --project P1 --kind pdf --pages 1 >/dev/null
  out="$(as alice tl doc rev issue ISO-1001 B --project P1 --status IFR)"; echo "$out"
  expect "issued ISO-1001@B as IFR" "$out"
  out="$(as alice tl doc register ISO-2001 --project P2 --title "Isometric drawing on P2")"; echo "$out"
  expect "document ISO-2001" "$out"
  as alice tl doc rev create ISO-2001 --project P2 --purpose "First issue" >/dev/null
  refuse "forbidden" as alice tl doc rev issue ISO-2001 A --project P2 --status IFR
  out="$(as alice tl doc register ISO-1002 --project P1 --title "Restricted unit 47")"; echo "$out"
  out="$(as dora tl doc confidentiality ISO-1002 --project P1 --class restricted --reason demo)"; echo "$out"
  expect "confidentiality of ISO-1002: - -> restricted" "$out"
  refuse "no document 'ISO-1002'" as alice tl doc show ISO-1002 --project P1
  clause 2

  step "[$backend] clause 3: dora, a viewer of documents on P2, is refused there and still issues in P1"
  out="$(as ada tl admin roles grant dora --project P2 --module documents --role viewer --reason demo)"; echo "$out"
  expect "granted viewer on documents for project:P2 to dora" "$out"
  p2doc="$(as alice tl doc show ISO-2001 --project P2 | awk '/^id:/{print $2}')"
  [ -n "$p2doc" ] || fail "the P2 document has no id"
  driver clause3 "$p2doc"
  as alice tl doc register ISO-1003 --project P1 --title "Isometric drawing unit 48" >/dev/null
  as alice tl doc rev create ISO-1003 --project P1 --purpose "First issue" >/dev/null
  as alice tl doc rendition add ISO-1003 A "$(pdf ISO-1003-A)" --project P1 --kind pdf --pages 1 >/dev/null
  out="$(as dora tl doc rev issue ISO-1003 A --project P1 --status IFR)"; echo "$out"
  expect "issued ISO-1003@A as IFR" "$out"
  clause 3

  step "[$backend] clause 4: the effective roles; alice cannot grant; GET /events hides the grants from alice"
  out="$(as ada tl admin roles effective alice --project P1)"; echo "$out"
  expect "documents  superuser  granted" "$out"
  refuse "needs the admin role" as alice tl admin roles grant bob --project P1 --module documents --role user --reason demo
  driver clause4
  clause 4

  step "[$backend] clause 5: an agent's propose_import_documents proposal: bob and alice are refused, dora's accept runs"
  driver doc-schema "$workdir/doc-list.yaml"
  out="$(as ada tl derive schema register "$workdir/doc-list.yaml" --company)"; echo "$out"
  printf 'number,title\nDOC-0501,Register unit 501\nDOC-0502,Register unit 502\n' >"$workdir/register-5.csv"
  as alice tl doc register ISD-1004 --project P1 --title "Register for a proposal" >/dev/null
  as alice tl doc rev create ISD-1004 --project P1 --purpose "First issue" >/dev/null
  as alice tl doc rendition add ISD-1004 A "$(pdf ISD-1004-A)" --project P1 --kind pdf --pages 1 >/dev/null
  out="$(as alice tl derive open ISD-1004 A --schema doc-list --project P1)"; echo "$out"
  expect "opened ISD-1004@A/doc-list" "$out"
  key="ISD-1004@A/doc-list"
  as alice tl derive content "$key" "$workdir/register-5.csv" --project P1 >/dev/null
  as alice tl derive start "$key" --project P1 >/dev/null
  as alice tl derive worker --once >/dev/null
  out="$(as alice tl derive show "$key" --project P1)"; echo "$out"
  expect "state Valid" "$out"
  driver clause5 "$key"
  out="$(as dora tl doc ls --project P1)"; echo "$out"
  expect "DOC-0501" "$out"
  expect "DOC-0502" "$out"
  clause 5

  step "[$backend] clause 6: a company grant for a stand-in module with company_roles; refused on documents"
  driver clause6
  clause 6

  step "[$backend] clause 7: the offline class; a device node is refused at start-up"
  driver clause7
  code=0
  out="$(TL_NODE_KIND=device tl serve 2>&1)" || code=$?
  echo "$out"
  [ "$code" = 2 ] || fail "TL_NODE_KIND=device tl serve must exit 2, not $code"
  expect "offline replicas arrive in Phase 3" "$out"
  clause 7

  step "[$backend] clause 8: the record types route and the Offline class line"
  driver clause8
  clause 8

  step "[$backend] clause 9: the readiness registry, the reserved identifiers and the settings"
  driver clause9
  clause 9

  step "[$backend] clause 10: the load targets; a tag list through the tags target; a derived document through the documents target"
  out="$(as ada tl standards load "$STANDARDS")"; echo "$out"
  expect "loaded co.acme.standards@1.0.0" "$out"
  out="$(as ada tl load targets)"; echo "$out"
  expect "tags  legacy  project" "$out"
  expect "documents  legacy  project" "$out"
  out="$(as ada tl load open dev/seed/legacy/instrument-index.csv --project P1 --loader instrument-index)"; echo "$out"
  expect "opened instr/index#1" "$out"
  as ada tl load extract instr/index#1 --project P1 >/dev/null
  as ada tl load profile instr/index#1 --project P1 >/dev/null
  out="$(as ada tl load plan instr/index#1 --project P1)"; echo "$out"
  expect "new 11 existing 0 invalid 3" "$out"
  out="$(as ada tl load load instr/index#1 --project P1 --expect-new 11)"; echo "$out"
  expect "created 11 existing 0 invalid 3" "$out"
  out="$(as ada tl load reconcile instr/index#1 --project P1)"; echo "$out"
  expect "mismatches 0" "$out"
  as alice tl doc register ISD-1005 --project P1 --title "Document list unit 47" >/dev/null
  as alice tl doc rev create ISD-1005 --project P1 --purpose "First issue" >/dev/null
  as alice tl doc rendition add ISD-1005 A "$(pdf ISD-1005-A)" --project P1 --kind pdf --pages 1 >/dev/null
  printf 'number,title\nDOC-0301,First\nDOC-0302,Second\n' >"$workdir/doc-list.csv"
  out="$(as alice tl derive open ISD-1005 A --schema doc-list --project P1)"; echo "$out"
  expect "opened ISD-1005@A/doc-list" "$out"
  key="ISD-1005@A/doc-list"
  as alice tl derive content "$key" "$workdir/doc-list.csv" --project P1 >/dev/null
  as alice tl derive start "$key" --project P1 >/dev/null
  as alice tl derive worker --once >/dev/null
  out="$(as alice tl derive show "$key" --project P1)"; echo "$out"
  expect "state Valid" "$out"
  refuse "forbidden" as alice tl derive publish "$key" --project P1 --apply
  out="$(as dora tl derive publish "$key" --project P1 --apply)"; echo "$out"
  expect "published 2 records from $key" "$out"
  out="$(as dora tl doc ls --project P1)"; echo "$out"
  expect "DOC-0301" "$out"
  expect "DOC-0302" "$out"
  clause 10

  step "[$backend] clause 11: the state report is short; the relay lint passes on the good file and fails on the bad one"
  out="$(just state P2-W0)"
  lines="$(printf '%s\n' "$out" | wc -l)"
  echo "just state P2-W0: $lines lines"
  [ "$lines" -le 40 ] || fail "just state P2-W0 printed $lines lines"
  quiet just relay-lint docs/tickets/P2-W0/provided/relay-ok.txt >/dev/null || fail "relay-lint refused relay-ok.txt"
  if quiet just relay-lint docs/tickets/P2-W0/provided/relay-bad.txt >/dev/null 2>&1; then
    fail "relay-lint accepted relay-bad.txt"
  fi
  clause 11

  drop_pg
  echo "[$backend] clauses 1-11 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-W0 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
