#!/usr/bin/env bash
# Demo for P1-I8 part 1 (the schema workbench on the command line: packages, governance,
# adoption, waivers, crosswalk, git export and import): `just demo P1-I8`.
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
#      edited by hand makes import-git print a problem and exit 1.
#
# Part 2 (loaders, marts, the Phase 1 exit chain) is appended to this script by P1-I8-T09b.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. No server is
# needed: the `tl schema` commands work on the ledger. Nothing is left behind.
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

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i8_demo.py "$@" || fail "an exit clause was not met"; }
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

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, two people"
  drop_pg
  rm -rf "$workdir/git"
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

  drop_pg
  echo "[$backend] clauses 1-4 passed"
}

driver prepare "$workdir"
for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I8 demo part 1 OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
