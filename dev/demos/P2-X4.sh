#!/usr/bin/env bash
# Demo for P2-X4 (module hooks and the new-module guide, P2-X4-T01 to T05): `just demo P2-X4`.
#
# The seven clauses (docs/tickets/P2-X4/README.md, "Demo"; amended by decisions D7, D13 and D14 in
# docs/tickets/P2-X4/STATE.md), each ending in a `PASS clause N: ...` line that is printed only
# after its check returned success:
#   1  `tl new module probe` scaffolds the module: 15 `created` lines, including the route, tool and
#      CLI group files; the driver checks the spec's three hooks resolve and that no platform
#      source names the probe module (driver mode clause1).
#      D7: the scaffold carries no example command; the demo shows the route, tool and CLI group.
#      D13: clauses 1 and 2 show the scaffold's route, tool and CLI group, not a command.
#   2  inside `use_modules`, the probe module's hooks load with no failures; the OpenAPI document has
#      /modules/probe/ping, the agent server lists probe_ping, and `probe ping` prints `probe`
#      (driver mode clause2).
#   3  ext_demo (the worked module, never installed): an API add by a person with the module word
#      files and reads back; a viewer is refused (403); the agent bot is refused (403, it must
#      propose); the CLI adds a note (ext clause3).
#   4  D14: the demo's tool is the read tool `ext_demo_get_note`. ExtDemoAddNote is excluded from
#      proposals (`excluded:reserved`), so no proposal is filed. The read is closed until
#      `mcp.ext_demo_get_note` is allowed, then the agent reads an open note; a hidden and a missing
#      note raise one identical text (ext clause4).
#   5  the five readers (anonymous, bot, bob, ctl, boss) each read the notes their class allows
#      (ext clause5).
#   6  a module hook that cannot be resolved (`ghost`) is reported by name in hook_failures; the
#      failure text names no ghost package, the module commands rows are unchanged, and the app
#      still builds (driver mode clause6).
#   7  the committed OpenAPI document matches the routes (`tl_api.openapi --check` exits 0) and the
#      baseline compare passes, additive changes allowed (`tl_api.openapi --compat` exits 0).
#
# The scaffold, the driver checks and the ext_demo reads are the Python drivers
# dev/demos/p2_x4_demo.py and dev/demos/p2_x4_ext_demo.py; the rest is `tl` commands and the
# OpenAPI module. Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres".
# Postgres is a throw-away database on TL_PG_URL (`just dev up`), dropped afterwards; an unreachable
# server is a failure, not a skip. The drivers run the API in process (no `tl serve`, no `as`
# sessions). Nothing is left behind. Exits non-zero (and prints DEMO FAILED) when any clause is not
# met.
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
export P2_X4_WORKDIR="$workdir"
export TL_LAKE_DIR="$workdir/lake"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2"; }
driver() { # driver MODE: the scaffold and the module checks; its output is shown
  uv run python dev/demos/p2_x4_demo.py "$@" 2>"$workdir/driver.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/driver.err" >&2; fail "a clause was not met: $*"; }
}
ext() { # ext MODE: the ext_demo module's notes, readers and refusals; its output is shown
  uv run python dev/demos/p2_x4_ext_demo.py "$@" 2>"$workdir/ext.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/ext.err" >&2; fail "a clause was not met: $*"; }
}

run_backend() {
  local backend="$1" created count
  step "[$backend] a new ledger"
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake" "$workdir"/*.db "$workdir/scaf"
  mkdir -p "$workdir/scaf"
  case "$backend" in
    sqlite) export TL_DB="$workdir/$backend.db" ;;
    postgres)
      pg_url="$(quiet uv run python dev/demos/p1_i0_demo.py pg-create)" || fail "Postgres is not reachable at TL_PG_URL (try: just dev up)"
      export TL_DB="$pg_url"
      ;;
    *) fail "unknown backend $backend" ;;
  esac
  tl init --dev 2>"$workdir/init.err" >/dev/null || { cat "$workdir/init.err" >&2; fail "tl init --dev"; }

  step "[$backend] clause 1: tl new module probe scaffolds 15 files; the spec's hooks resolve; no platform edit"
  tl new module probe --root "$workdir/scaf" >"$workdir/new.out" 2>"$workdir/new.err" \
    || { cat "$workdir/new.err" >&2; fail "tl new module probe"; }
  created="$(grep -c '^created ' "$workdir/new.out" || true)"
  [ "$created" = "15" ] || fail "tl new module printed $created created lines, expected 15"
  for file in routes.py tools.py cli.py; do
    grep -q "^created .*/$file\$" "$workdir/new.out" || fail "tl new module did not create $file"
  done
  echo "ok tl new module probe: 15 created lines, routes.py, tools.py and cli.py among them"
  driver clause1
  clause 1 "the scaffold has 15 files including the route, tool and CLI group; its hooks resolve; no platform edit"

  step "[$backend] clause 2: the probe hooks load in use_modules; the route, the tool and the CLI group answer"
  driver clause2
  clause 2 "the probe module's hooks load; /modules/probe/ping, probe_ping and probe ping answer"

  step "[$backend] clause 3: ext_demo's notes; a viewer and the agent bot are refused; the CLI adds a note"
  ext clause3
  clause 3 "ext_demo: the word files a note over the API, a viewer is refused, the agent bot must propose, the CLI adds one"

  step "[$backend] clause 4: the read tool is closed until allowed (D14); a hidden and a missing note read alike"
  ext clause4
  clause 4 "ext_demo_get_note is closed until mcp.ext_demo_get_note is allowed; hidden and missing notes raise one text"

  step "[$backend] clause 5: the five readers read the notes their class allows"
  ext clause5
  clause 5 "five readers: anonymous 0 of 3, bot 1, bob 1, ctl 2, boss 2"

  step "[$backend] clause 6: an unresolvable hook is named; the failure text names no ghost; the app builds"
  driver clause6
  clause 6 "hook_failures names the ghost module without its package text; module commands unchanged; the app builds"

  step "[$backend] clause 7: the OpenAPI document matches the routes; the baseline compare passes"
  compat_rc=0
  quiet uv run python -m tl_api.openapi --compat >/dev/null || compat_rc=$?
  [ "$compat_rc" -eq 0 ] || fail "tl_api.openapi --compat exited $compat_rc"
  echo "ok tl_api.openapi --compat exit $compat_rc"
  check_rc=0
  quiet uv run python -m tl_api.openapi --check >/dev/null || check_rc=$?
  [ "$check_rc" -eq 0 ] || fail "tl_api.openapi --check exited $check_rc"
  echo "ok tl_api.openapi --check exit $check_rc"
  clause 7 "the baseline compare passes (additive changes allowed) and the committed OpenAPI document matches the routes"

  drop_pg
  echo "[$backend] clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-X4 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
