#!/usr/bin/env bash
# Demo for P2-I3 (materials: the company library, locations, receipts with MTRs, stock and its
# movements, the take-off into an MTO, and the API, TUI and MCP agreeing): `just demo P2-I3`.
#
# The exit clauses (m4-materials.md section 10), each ending in a `PASS clause N` line, once on
# SQLite and once on Postgres:
#   1  an admin loads co.acme.materials@1.0.0 (twice: no change) and the 50-item library with
#      `tl load --company` (plan, load, reconcile 0 mismatches); mara (company materials superuser)
#      may DefineItem, pete (project user) may not (driver);
#   2  sue (project superuser) defines the location chain P123 > WH1 > L2 > TC1 > GB1; pete's
#      DefineLocation is refused (driver);
#   3  a receipt of two flange lines, heat H-7781, against PO line 4471-3: accept without the MTR is
#      refused with the fixed message; with the MTR attached, two lots are on hand at L2;
#   4  an issue to a crew against a cost code, a transfer, a return, a superuser adjust with a
#      reason; a user's adjust and an over-issue are refused; a consumable without a cost code is
#      refused (driver); stock equals the sum of movements and a rebuild gives the same rows (driver);
#   5  `tl mat report heat_trace` for H-7781 shows the lots, the receipt, the MTR, the locations and
#      the issue;
#   6  the awp package P123-CWP-PIP-0001 is made by CreateCwp (driver: `CWP via awp`); a derived
#      take-off is published into an MTO for it, compensated, and republished (driver);
#   7  a reservation against an MTO line; over-reserving is refused; `shortages` lists the rest; the
#      materials_reserved check keeps the readiness contract (driver);
#   8  the API, the TUI screens (stock, receipts, MTO lines at 170 columns) and the MCP tools agree;
#      an agent's propose_reservation is pending until sue accepts it (driver);
#   9  a quantity with Arabic-Indic digits, a negative, 4 decimal places or over the bound is refused
#      with the fixed message, on the CLI and through the API (driver);
#   10 the item library shows the 51 items (the 50 sample items and mara's probe) with project
#      counts, and the locations screen shows the
#      five-level tree with lot counts, at 170 columns (driver);
#   11 the movement log lists the clause-4 movements in order with kind, from, to and by, and
#      filtered by kind `issue` shows one row.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. The API, TUI
# and MCP clauses run in dev/demos/p2_i3_demo.py. Nothing is left behind.
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
MATERIALS=schema/fixtures/standards/co.acme.materials@1.0.0.yaml
SAMPLES=packages/tl-modules/materials/src/tl_mod_materials/samples

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_LAKE_DIR="$workdir/lake"
export P2_I3_WORKDIR="$workdir"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1"; }
driver() { # driver MODE [ARG]: the API, TUI and MCP checks; their output is shown, stderr is kept
  uv run python dev/demos/p2_i3_demo.py "$@" 2>"$workdir/driver.err" \
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
movement_is() { # movement_is KIND FROM TO BY LISTING: the first row of KIND has that from, to and by
  local row
  row="$(printf '%s\n' "$5" | awk -v k="$1" '$2 == k' | head -n 1)"
  [ -n "$row" ] || fail "no $1 movement in the listing"
  printf '%s\n' "$row" | awk -v f="$2" -v t="$3" -v b="$4" '$7 == f && $8 == t && $9 == b { ok = 1 } END { exit !ok }' \
    || fail "the $1 movement is not from $2 to $3 by $4: $row"
}
pdf() { # pdf NAME: a rendition file for a revision (the rendition step checks the kind, not the bytes)
  printf '%%PDF-1.7 %s\n' "$1" >"$workdir/$1.pdf"
  echo "$workdir/$1.pdf"
}

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger: ada (admin), mara, pete, sue, plain (no grant)"
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
  printf '%s\n' "a long passphrase for mara" | as demo tl admin user add mara --display-name "Mara" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for pete" | as demo tl admin user add pete --display-name "Pete" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for sue" | as demo tl admin user add sue --display-name "Sue" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for plain" | as demo tl admin user add plain --display-name "Plain" --password-stdin >/dev/null
  for who in ada mara pete sue plain; do
    printf '%s\n' "a long passphrase for $who" | as "$who" tl login "$who" --password-stdin >/dev/null
  done
  out="$(as ada tl admin roles grant mara --project company --module materials --role superuser --reason demo)"; echo "$out"
  expect "granted superuser on materials for company to mara" "$out"
  out="$(as ada tl admin roles grant pete --project P123 --module materials --role user --reason demo)"; echo "$out"
  expect "granted user on materials for project:P123 to pete" "$out"
  out="$(as ada tl admin roles grant sue --project P123 --module materials --role superuser --reason demo)"; echo "$out"
  expect "granted superuser on materials for project:P123 to sue" "$out"

  step "[$backend] clause 1: the standards load twice; the 50-item library loads with plan, load and reconcile"
  out="$(as ada tl standards load "$STANDARDS")"; echo "$out"
  expect "loaded co.acme.standards@1.0.0" "$out"
  out="$(as ada tl standards load "$MATERIALS")"; echo "$out"
  expect "loaded co.acme.materials@1.0.0" "$out"
  out="$(as ada tl standards load "$MATERIALS")"; echo "$out"
  expect "code_list  create=0  skip=5" "$out"
  out="$(as ada tl load open "$SAMPLES/items.csv" --company --loader mat-items)"; echo "$out"
  expect "opened mat/items#1" "$out"
  as ada tl load extract "mat/items#1" --company >/dev/null
  as ada tl load profile "mat/items#1" --company >/dev/null
  out="$(as ada tl load plan "mat/items#1" --company)"; echo "$out"
  expect "new 50 existing 0 invalid 0" "$out"
  out="$(as ada tl load load "mat/items#1" --company --expect-new 50)"; echo "$out"
  expect "created 50 existing 0 invalid 0" "$out"
  out="$(as ada tl load reconcile "mat/items#1" --company)"; echo "$out"
  expect "mismatches 0" "$out"
  driver clause1-people
  clause 1

  step "[$backend] clause 2: sue defines the five-level location chain; pete's DefineLocation is refused"
  driver clause2
  out="$(as pete tl mat loc --project P123)"; echo "$out"
  expect "locations: 5" "$out"
  clause 2

  step "[$backend] clause 3: a receipt of two flange lines against PO line 4471-3; accept needs the MTR"
  out="$(as ada tl load open "$SAMPLES/po_lines.csv" --project P123 --loader mat-po-lines)"; echo "$out"
  expect "opened mat/po_lines#1" "$out"
  as ada tl load extract "mat/po_lines#1" --project P123 >/dev/null
  as ada tl load profile "mat/po_lines#1" --project P123 >/dev/null
  out="$(as ada tl load plan "mat/po_lines#1" --project P123)"; echo "$out"
  expect "new 15 existing 0 invalid 0" "$out"
  out="$(as ada tl load load "mat/po_lines#1" --project P123 --expect-new 15)"; echo "$out"
  expect "created 15 existing 0 invalid 0" "$out"
  out="$(as ada tl load reconcile "mat/po_lines#1" --project P123)"; echo "$out"
  expect "mismatches 0" "$out"
  out="$(as ada tl config set materials.receipt.mtr_required_categories flange --project P123)"; echo "$out"
  expect "set materials.receipt.mtr_required_categories project:P123" "$out"
  out="$(as pete tl mat receipt receive --project P123 --location L2 --received-on 2026-10-28 \
    --po-line 4471-3 --supplier "Acme Valves" --delivery-ref DN-8841 \
    --line FLG-WN-6-150-A105:12:H-7781 --line FLG-WN-6-150-A105:8:H-7781)"; echo "$out"
  expect "received P123-RCPT-0001  2 lines" "$out"
  out="$(as pete tl mat receipt inspect P123-RCPT-0001 --project P123)"; echo "$out"
  expect "P123-RCPT-0001 is Inspected" "$out"
  refuse "an MTR is required for 2 lines; attach it in the MTR slot" \
    as pete tl mat receipt accept P123-RCPT-0001 --project P123
  out="$(as pete tl file put "$(pdf mtr-h7781)" --project P123 --record P123-RCPT-0001 --slot mtr)"; echo "$out"
  expect "status available" "$out"
  out="$(as pete tl mat receipt accept P123-RCPT-0001 --project P123)"; echo "$out"
  expect "P123-RCPT-0001 is Accepted" "$out"
  out="$(as pete tl mat stock --project P123 --location L2)"; echo "$out"
  expect "P123-RCPT-0001@1" "$out"
  expect "on hand 12.000" "$out"
  expect "P123-RCPT-0001@2" "$out"
  expect "on hand 8.000" "$out"
  clause 3

  step "[$backend] clause 4: issue against a cost code, transfer, return, a superuser adjust; refusals"
  out="$(as pete tl mat receipt receive --project P123 --location L2 --received-on 2026-10-28 --line CON-WELD-E7018-3.2:5:H-CON1)"; echo "$out"
  expect "received P123-RCPT-0002  1 lines" "$out"
  as pete tl mat receipt inspect P123-RCPT-0002 --project P123 >/dev/null
  out="$(as pete tl mat receipt accept P123-RCPT-0002 --project P123)"; echo "$out"
  expect "P123-RCPT-0002 is Accepted" "$out"
  printf 'code,description,parent,uom,quantity_budget,quantity_actual,quantity_eac,hours_budget\n4210,Piping,,,1000,400,1100,5000\n4210-PIP,Pipe installation,4210,in-dia,600,450,600,3000\n4210-WLD,Welding,4210,,400,150,500,2000\n' >"$workdir/cost-2026-10.csv"
  out="$(as ada tl cost import "$workdir/cost-2026-10.csv" --project P123 --period 2026-10 --as-of 2026-10-31 --apply)"; echo "$out" | tail -1
  expect "applied 2026-10@1" "$out"
  cc="$(as pete tl record show 4210-PIP --project P123 | awk '/^id:/{print $2}')"
  [ -n "$cc" ] || fail "the cost code 4210-PIP has no id"
  out="$(as pete tl mat move issue --project P123 --lot P123-RCPT-0001@1 --qty 2 --uom EA --from L2 --for-cost-code "$cc" --person "Crew A")"; echo "$out"
  expect "issue 2 EA lot P123-RCPT-0001@1" "$out"
  out="$(as pete tl mat move transfer --project P123 --lot P123-RCPT-0001@1 --qty 3 --uom EA --from L2 --to TC1)"; echo "$out"
  expect "transfer 3 EA lot P123-RCPT-0001@1" "$out"
  out="$(as pete tl mat move return --project P123 --lot P123-RCPT-0001@1 --qty 1 --uom EA --to L2)"; echo "$out"
  expect "return 1 EA lot P123-RCPT-0001@1" "$out"
  refuse "needs the controller access word" as pete tl mat move adjust --project P123 \
    --lot P123-RCPT-0001@2 --qty 1 --uom EA --from L2 --direction out --reason count_correction
  out="$(as sue tl mat move adjust --project P123 --lot P123-RCPT-0001@2 --qty 1 --uom EA --from L2 --direction out --reason count_correction)"; echo "$out"
  expect "adjust 1 EA lot P123-RCPT-0001@2" "$out"
  refuse "more than is available" as pete tl mat move issue --project P123 \
    --lot P123-RCPT-0001@1 --qty 1000 --uom EA --from TC1 --for-cost-code "$cc" --person "Crew A"
  driver clause4
  clause 4

  step "[$backend] clause 5: the heat trace of H-7781 shows the lots, the receipt, the MTR, the locations and the issue"
  out="$(as pete tl mat report heat_trace --project P123 --heat H-7781)"; echo "$out"
  expect "P123-RCPT-0001@1" "$out"
  expect "P123-RCPT-0001  mtr-h7781.pdf" "$out"
  expect "Issued" "$out"
  expect "TC1" "$out"
  clause 5

  step "[$backend] clause 6: the awp package by CreateCwp; the take-off published into its MTO, compensated, republished"
  out="$(as ada tl awp cwa define PIPE-AREA --project P123 --title "Piping area")"; echo "$out"
  expect "defined CWA PIPE-AREA" "$out"
  as pete tl doc register ISO-1234 --project P123 --title "Piping isometric ISO-1234" >/dev/null
  as pete tl doc rev create ISO-1234 --project P123 --purpose "First issue" >/dev/null
  as pete tl doc rendition add ISO-1234 A "$(pdf ISO-1234-A)" --project P123 --kind pdf --pages 1 >/dev/null
  cat >"$workdir/takeoff.yaml" <<'YAML'
code: takeoff
semver: "1.0.0"
title: Material take-off
json_schema:
  type: object
  required: [line, item, qty, uom]
  properties:
    line: {type: string}
    item: {type: string}
    qty: {type: string}
    uom: {type: string}
    tag: {type: string}
key_column: line
target_kind: mto
mapping:
  target: mto
  key_column: line
  columns:
    - {column: line, to: number}
    - {column: item, to: item_code}
    - {column: qty, to: qty}
    - {column: uom, to: uom}
    - {column: tag, to: tag}
YAML
  printf 'line,item,qty,uom,tag\n1,FLG-WN-6-150-A105,20,EA,\n2,ELB-LR-90-6-SCH40,8,EA,\n3,PIPE-CS-6-SCH40-A106,120,m,\n' >"$workdir/takeoff.csv"
  out="$(as ada tl derive schema register "$workdir/takeoff.yaml" --company)"; echo "$out"
  expect "registered takeoff@1.0.0 company" "$out"
  key="ISO-1234@A/takeoff"
  out="$(as pete tl derive open ISO-1234 A --schema takeoff --project P123)"; echo "$out"
  expect "opened $key" "$out"
  as pete tl derive content "$key" "$workdir/takeoff.csv" --project P123 >/dev/null
  as pete tl derive start "$key" --project P123 >/dev/null
  as pete tl derive worker --once >/dev/null
  out="$(as pete tl derive show "$key" --project P123)"; echo "$out"
  expect "state Valid" "$out"
  driver clause6 "$key"
  clause 6

  step "[$backend] clause 7: a reservation against an MTO line; over-reserving refused; shortages; readiness"
  mto1="$(as pete tl mat mto list --project P123 | awk 'NR==1{print $1}')"
  [ -n "$mto1" ] || fail "the take-off has no lines"
  lid="$(as pete tl record show "$mto1" --project P123 | awk '/^id:/{print $2}')"
  out="$(as pete tl mat move reserve --project P123 --lot P123-RCPT-0001@1 --qty 4 --uom EA --from L2 --for-line "$lid")"; echo "$out"
  expect "reserve 4 EA lot P123-RCPT-0001@1" "$out"
  refuse "more than is available" as pete tl mat move reserve --project P123 \
    --lot P123-RCPT-0001@2 --qty 100000 --uom EA --from L2 --for-line "$lid"
  out="$(as pete tl mat report shortages --project P123)"; echo "$out"
  expect "$mto1  FLG-WN-6-150-A105" "$out"
  expect "ELB-LR-90-6-SCH40" "$out"
  driver clause7
  clause 7

  step "[$backend] clause 8: the API, the TUI and the MCP tools agree; an agent's proposal waits for a person"
  driver clause8
  clause 8

  step "[$backend] clause 9: four quantities refused on the CLI, each with its fixed message"
  refuse "movement 1 qty must be ASCII digits with at most 3 decimals, as 12.500" \
    as pete tl mat move issue --project P123 --lot P123-RCPT-0001@1 --qty "١٢" --uom EA \
    --from L2 --for-cost-code "$cc" --person "Crew A"
  refuse "movement 1 qty must be ASCII digits with at most 3 decimals, as 12.500" \
    as pete tl mat move issue --project P123 --lot P123-RCPT-0001@1 --qty -1 --uom EA \
    --from L2 --for-cost-code "$cc" --person "Crew A"
  refuse "movement 1 qty must be ASCII digits with at most 3 decimals, as 12.500" \
    as pete tl mat move issue --project P123 --lot P123-RCPT-0001@1 --qty 1.2345 --uom EA \
    --from L2 --for-cost-code "$cc" --person "Crew A"
  refuse "movement 1 qty must be at most 1000000000" \
    as pete tl mat move issue --project P123 --lot P123-RCPT-0001@1 --qty 1000000001 --uom EA \
    --from L2 --for-cost-code "$cc" --person "Crew A"
  driver clause9
  clause 9

  step "[$backend] clause 10: the item library and the location tree at 170 columns"
  driver clause10-11
  clause 10

  step "[$backend] clause 11: the movement log in order; filtered by kind issue shows one row"
  out="$(as pete tl mat movements --project P123)"; echo "$out"
  kinds="$(printf '%s\n' "$out" | awk '$2 ~ /^(receive|issue|transfer|return|adjust)$/ {printf "%s ", $2}')"
  [ "$kinds" = "receive receive receive issue transfer return adjust " ] || fail "the movement kinds are: $kinds"
  movement_is issue L2 - user:pete "$out"
  movement_is transfer L2 TC1 user:pete "$out"
  movement_is return - L2 user:pete "$out"
  movement_is adjust L2 - user:sue "$out"
  out="$(as pete tl mat movements --project P123 --kind issue)"; echo "$out"
  expect "movements: 1" "$out"
  filtered="$(printf '%s\n' "$out" | awk 'NR > 1 {printf "%s ", $2}')"
  [ "$filtered" = "issue " ] || fail "the kind issue filter shows the kinds: $filtered"
  clause 11

  drop_pg
  echo "[$backend] clauses 1-11 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-I3 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
