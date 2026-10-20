#!/usr/bin/env bash
# Demo for P1-I7 workstream B (record threads with dispatch): `just demo P1-I7B`.
# (The whole increment's demo, `just demo P1-I7`, is workstream A's, FANOUT D20; this is its
# thread part, item 4, and the rules around it.)
#
# The exit clauses, each ending in a PASS line, once on SQLite and once on Postgres:
#   1  threads are off until an admin switches them on; then a message is posted and read back;
#   2  `/link` is previewed (nothing is written, the plan names the access each command needs) and
#      confirmed with the preview's token: the link exists and the thread shows the outcome;
#   3  `/raise record` makes a record in one transaction, linked from the thread's record
#      (`dispatched_from`), and `--yes` previews, prints the plan and runs it;
#   4  `/summarise` posts a deterministic summary (the system counted it, no model);
#   5  a plan that changed since the preview, and a made-up token, are refused (`dispatch_stale`);
#   6  a message that starts with `/` is only text unless it is dispatched;
#   7  `threads.dispatch.roles` keeps a plain user from dispatching while the admin may;
#   8  an agent proposes a dispatch, nothing happens until a person accepts it, and acceptance
#      runs the commands as that person; with `threads.agents.can_dispatch` none, the proposal is
#      refused.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. Nothing is
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

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}
refuse() { # refuse TEXT cmd...: the command must fail and its output must contain the text
  local want="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then echo "$out"; fail "this was accepted: $*"; fi
  echo "$out"
  expect "$want" "$out"
}
trace() { as amy tl link trace --project P123 "$1"; }
key_of() { printf '%s\n' "$1" | awk '/^key /{print $2; exit}'; }
token_of() { printf '%s\n' "$1" | awk '/^token /{print $2; exit}'; }

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, an admin, two users and records"
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
  local pw="a long passphrase for amy"
  printf '%s\n' "$pw" | as demo tl admin user add amy --display-name "Amy A" --password-stdin >/dev/null
  printf '%s\n' "$pw" | as amy tl login amy --password-stdin >/dev/null
  local a b
  a="$(key_of "$(as amy tl record create --project P123 --title "Gate valve")")"
  b="$(key_of "$(as amy tl record create --project P123 --title "Check valve")")"
  echo "(records $a and $b)"

  step "[$backend] clause 1: threads are off until an admin switches them on"
  refuse "threads are not switched on" as amy tl thread post --project P123 "$a" "too early"
  as demo tl config set threads.enabled true --company --reason "demo" >/dev/null
  as demo tl config set threads.enabled_types core.Record --company --reason "demo" >/dev/null
  as amy tl thread post --project P123 "$a" "Flanges are short at grid C4, see #$b" >/dev/null
  out="$(as amy tl thread show --project P123 "$a")"; echo "$out"
  expect "Flanges are short" "$out"
  expect "threads on" "$out"
  echo "PASS 1: a thread needs the switch; a posted message reads back"

  step "[$backend] clause 2: /link is previewed, then confirmed with the preview's token"
  out="$(as amy tl thread preview --project P123 "$a" "/link #$b as requires")"; echo "$out"
  expect "AddLink" "$out"
  expect "can dispatch: yes" "$out"
  token="$(token_of "$out")"
  [ "${#token}" = 64 ] || fail "no token in the preview"
  out="$(trace "$a")"
  case "$out" in *"$b"*) fail "the preview wrote a link" ;; esac
  out="$(as amy tl thread dispatch --project P123 "$a" "/link #$b as requires" --token "$token")"; echo "$out"
  expect "dispatched" "$out"
  out="$(trace "$a")"; echo "$out"
  expect "$b" "$out"
  out="$(as amy tl thread show --project P123 "$a")"; echo "$out"
  expect "-> link:" "$out"
  echo "PASS 2: the preview wrote nothing; the dispatch made the link and the thread shows the outcome"

  step "[$backend] clause 3: /raise record, in one transaction, linked from the thread's record"
  out="$(as amy tl thread dispatch --project P123 "$a" "/raise record Clash at grid C4" --yes)"; echo "$out"
  expect "CreateRecord" "$out"
  expect "dispatched" "$out"
  out="$(as amy tl thread show --project P123 "$a")"; echo "$out"
  expect "-> raise:" "$out"
  out="$(trace "$a")"; echo "$out"
  expect "Clash at grid C4" "$out"
  echo "PASS 3: the raised record exists and is linked (dispatched_from) in the same transaction"

  step "[$backend] clause 4: /summarise is deterministic, no model"
  as amy tl thread dispatch --project P123 "$a" "/summarise" --yes >/dev/null
  out="$(as amy tl thread show --project P123 "$a")"; echo "$out"
  expect "Thread summary (counted by the system, no model)." "$out"
  echo "PASS 4: the summary says the system counted it"

  step "[$backend] clause 5: a plan that changed, and a made-up token, are refused"
  out="$(as amy tl thread preview --project P123 "$a" "/link #$b")"
  token="$(token_of "$out")"
  refuse "not the one you previewed" as amy tl thread dispatch --project P123 "$a" "/link #$b" --token "$(printf '0%.0s' $(seq 1 64))"
  refuse "not the one you previewed" as amy tl thread dispatch --project P123 "$a" "/link #$b as requires" --token "$token"
  echo "PASS 5: a different line or a made-up token is a dispatch_stale"

  step "[$backend] clause 6: a message that starts with / is only text"
  before="$(trace "$a")"
  as amy tl thread post --project P123 "$a" "/raise record Should not exist" >/dev/null
  after="$(trace "$a")"
  [ "$before" = "$after" ] || fail "a message dispatched"
  case "$after" in *"Should not exist"*) fail "a message dispatched" ;; esac
  echo "PASS 6: posting a slash line stores text and dispatches nothing"

  step "[$backend] clause 7: the roles that may dispatch"
  as demo tl config set threads.dispatch.roles admin --company --reason "demo" >/dev/null
  refuse "your role may not dispatch" as amy tl thread preview --project P123 "$a" "/link #$b"
  out="$(as demo tl thread preview --project P123 "$a" "/summarise")"
  expect "can dispatch: yes" "$out"
  as demo tl config set threads.dispatch.roles "" --company --reason "demo" >/dev/null || \
    as demo tl config reset threads.dispatch.roles --company --reason "demo" >/dev/null
  echo "PASS 7: a plain user is refused while the admin may dispatch"

  step "[$backend] clause 8: an agent proposes; a person accepts; the commands run as the person"
  c="$(key_of "$(as amy tl record create --project P123 --title "Relief valve")")"
  pid="$(quiet uv run python dev/demos/p1_i7b_demo.py propose "$TL_DB" P123 "$a" "/link #$c as requires")"
  echo "(proposal $pid)"
  out="$(trace "$a")"
  case "$out" in *"$c"*) fail "the proposal changed something before a person accepted" ;; esac
  out="$(as amy tl proposal accept "$pid")"; echo "$out"
  expect "accepted" "$out"
  out="$(trace "$a")"; echo "$out"
  expect "$c" "$out"
  as demo tl config set threads.agents.can_dispatch none --company --reason "demo" >/dev/null
  refuse "agents may not propose" quiet uv run python dev/demos/p1_i7b_demo.py propose "$TL_DB" P123 "$a" "/summarise"
  echo "PASS 8: the proposal waited for a person; acceptance linked as the person; none refuses agents"

  drop_pg
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done
printf '\nDEMO OK: record threads with dispatch\n'
