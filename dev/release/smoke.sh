#!/usr/bin/env bash
# Prove the release works the way a user gets it: a clean install and both server paths (P2-REL-T05).
#
# Usage: dev/release/smoke.sh <release dir>   (for example dist/release-0.1.0: build.sh and starter.sh first)
#        dev/release/smoke.sh --list           (prints the step names, one per line; runs nothing else)
# Steps, each a bash function that prints one line:
#   install       uv venv --python 3.12; uv pip install --find-links <dir> tl-cli; `tl --version` and
#                 `tl-tui --version` equal the version in the SHA256SUMS names; tl_core is not imported from
#                 the repository.
#   try-it        unpack the starter; the START.txt environment; `tl serve` on a free loopback port (stopped by
#                 pid); /health with at most 30 tries of 1 s; sign in as the demo account; the P200 records route
#                 is a non-empty list; one `tl awp package ls` read with --db exits 0.
#   real-server   only when TL_PG_URL is set (else "skip real-server: no Postgres" and the run still passes): a new
#                 database; tl init; admin bootstrap as boss; tl serve --host 0.0.0.0 with TL_ENV=prod; boss signs
#                 in; no demo account; a token from a dev token file is refused; TL_ENV unset exits 2 (S2).
#   session-file after `tl login` the session file is mode 600.
# The run ends `smoke: PASS`, or `smoke: FAIL <step>` (exit 1). Exit 2 on bad arguments.
#
# Isolation: a mktemp -d outside the repository (TMPDIR), a cd there, and every command under `env -i` with only
# BASE_ENV (HOME inside the temp dir, PATH, the proxy and CA variables, TL_SESSION_FILE). Passwords and tokens go
# through files (mode 600) and stdin, never argv or output. Servers are stopped by `kill <pid>` in an EXIT trap.
# SMOKE_KEEP=1 keeps the temp dir for a post-mortem.
set -Eeuo pipefail

STEPS=(install try-it real-server session-file)
if [ "${1:-}" = "--list" ]; then
  printf '%s\n' "${STEPS[@]}"
  exit 0
fi
if [ $# -ne 1 ]; then
  echo "usage: dev/release/smoke.sh <release dir> | --list" >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ ! -d "$1" ]; then
  echo "smoke: no release directory $1" >&2
  exit 2
fi
rel="$(cd "$1" && pwd)"
if [ ! -f "$rel/SHA256SUMS" ]; then
  echo "smoke: no SHA256SUMS in $rel" >&2
  exit 2
fi

# The version of this release, from the wheel names in SHA256SUMS (tl_cli and tl_tui must agree).
want="$(awk '$NF ~ /^tl_cli-[0-9]/ { split($NF, p, "-"); print p[2]; exit }' "$rel/SHA256SUMS")"
want_tui="$(awk '$NF ~ /^tl_tui-[0-9]/ { split($NF, p, "-"); print p[2]; exit }' "$rel/SHA256SUMS")"
if [[ ! "$want" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || [ "$want" != "$want_tui" ]; then
  echo "smoke: FAIL install"
  echo "install: no tl_cli and tl_tui wheel with one X.Y.Z version in $rel/SHA256SUMS" >&2
  exit 1
fi

CURRENT_STEP=setup
DONE=0
SERVERS=()
PG_DB=""
MAIN_PID="${BASHPID:-$$}"

work="$(mktemp -d "${TMPDIR:-/tmp}/tl-smoke.XXXXXX")"
case "$work" in "$root"|"$root"/*) echo "smoke: the temp dir is inside the repository" >&2; exit 2 ;; esac
venv="$work/venv"

# Only these variables reach the release commands: the proxy and CA settings uv and curl need, nothing else.
BASE_ENV=("HOME=$work/home" "PATH=$PATH" "LANG=C.UTF-8" "TMPDIR=$work" "TL_SESSION_FILE=$work/session/session.json")
for name in HTTPS_PROXY HTTP_PROXY NO_PROXY https_proxy http_proxy no_proxy SSL_CERT_FILE REQUESTS_CA_BUNDLE \
  UV_NATIVE_TLS UV_INDEX_URL UV_DEFAULT_INDEX UV_PYTHON_INSTALL_DIR; do
  if [ -n "${!name:-}" ]; then BASE_ENV+=("$name=${!name}"); fi
done
if uv_cache="$(uv cache dir 2>/dev/null)" && [ -n "$uv_cache" ]; then BASE_ENV+=("UV_CACHE_DIR=$uv_cache"); fi
mkdir -p "$work/home" "$work/session"

cleanup() {
  local rc=$? p
  [ "${BASHPID:-$$}" = "$MAIN_PID" ] || return 0
  for p in ${SERVERS[@]+"${SERVERS[@]}"}; do kill "$p" 2>/dev/null || true; done
  for p in ${SERVERS[@]+"${SERVERS[@]}"}; do wait "$p" 2>/dev/null || true; done
  if [ -n "$PG_DB" ] && [ -n "${TL_PG_URL:-}" ] && [ -x "$venv/bin/python" ]; then
    env -i "${BASE_ENV[@]}" SMOKE_PG_URL="$TL_PG_URL" SMOKE_PG_DB="$PG_DB" "$venv/bin/python" -I -c \
      'import os; from tl_adapters.postgres.admin import drop_database; drop_database(os.environ["SMOKE_PG_URL"], os.environ["SMOKE_PG_DB"])' \
      >/dev/null 2>&1 || echo "smoke: could not drop the test database $PG_DB" >&2
  fi
  if [ "$rc" -ne 0 ] && [ "$DONE" -ne 1 ]; then echo "smoke: FAIL $CURRENT_STEP"; fi
  if [ "${SMOKE_KEEP:-0}" = 1 ]; then echo "smoke: kept $work" >&2; else rm -rf "$work"; fi
}
trap cleanup EXIT

die() { echo "$CURRENT_STEP: $*" >&2; exit 1; }
xenv() { env -i "${BASE_ENV[@]}" "$@"; }
py() { "$venv/bin/python" -I -c "$@"; }

verify_sums() {
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$1" && sha256sum -c --quiet SHA256SUMS)
  else
    (cd "$1" && shasum -a 256 -c --quiet SHA256SUMS)
  fi
}

free_port() {
  py 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

wait_health() { # wait_health <base url>: at most 30 tries, 1 s apart (start-up readiness only)
  local base="$1" i
  for ((i = 0; i < 30; i++)); do
    if curl -fsS --max-time 2 -o "$work/health.json" "$base/health" 2>/dev/null; then return 0; fi
    sleep 1
  done
  return 1
}

stop_server() { kill "$1" 2>/dev/null || true; wait "$1" 2>/dev/null || true; }

file_mode() { # GNU stat first, then BSD stat
  if stat -c %a "$1" 2>/dev/null; then return 0; fi
  stat -f %Lp "$1"
}

write_auth_conf() { # write_auth_conf <sign-in json> <curl config>: header only, mode 600
  (umask 077 && py 'import json, sys; t = json.load(open(sys.argv[1]))["token"]; open(sys.argv[2], "w").write("header = \"Authorization: Bearer %s\"\n" % t)' "$1" "$2")
}

sign_in() { # sign_in <base url> <username> <password file> <curl config>; 0 only on HTTP 200
  local code
  code="$(py 'import json, sys; pw = open(sys.argv[2], encoding="utf-8").read().rstrip("\n"); print(json.dumps({"username": sys.argv[1], "password": pw}))' "$2" "$3" \
    | curl -sS -o "$work/signin.json" -w '%{http_code}' -H 'Content-Type: application/json' --data-binary @- "$1/auth/sign-in")" || return 1
  [ "$code" = 200 ] || return 1
  write_auth_conf "$work/signin.json" "$4"
}

step_install() {
  CURRENT_STEP=install
  verify_sums "$rel" || die "SHA256SUMS does not match the files in $rel"
  xenv uv venv --python 3.12 --quiet "$venv" >"$work/venv.log" 2>&1 || { tail -n 5 "$work/venv.log" >&2; die "uv venv --python 3.12 failed"; }
# tl-cli is pinned to the release version: PyPI has an unrelated project named tl-cli (0.2), which uv would
  # otherwise pick over the local wheel.
  xenv uv pip install --python "$venv/bin/python" --find-links "$rel" "tl-cli==$want" >"$work/install.log" 2>&1 \
    || { tail -n 5 "$work/install.log" >&2; die "uv pip install --find-links $rel tl-cli==$want failed"; }
  local tl_v tui_v core_file
  tl_v="$(xenv "$venv/bin/tl" --version)" || die "tl --version failed"
  tui_v="$(xenv "$venv/bin/tl-tui" --version)" || die "tl-tui --version failed"
  [ "${tl_v##* }" = "$want" ] || die "tl --version says '$tl_v', the release is $want"
  [ "${tui_v##* }" = "$want" ] || die "tl-tui --version says '$tui_v', the release is $want"
  core_file="$(cd "$work" && xenv "$venv/bin/python" -I -c 'import tl_core; print(tl_core.__file__)')" || die "import tl_core failed"
  case "$core_file" in "$root"/*) die "tl_core is imported from the repository: $core_file" ;; esac
  case "$core_file" in "$venv"/*) ;; *) die "tl_core is not imported from the venv: $core_file" ;; esac
  echo "install: ok tl $want and tl-tui $want from a clean venv; tl_core not from the repository"
}

step_try_it() {
  CURRENT_STEP=try-it
  local starter="$rel/starter-p200-$want.tar.gz" start="$work/starter" line port base code n serve_pid pw_line
  [ -f "$starter" ] || die "no $starter (run just release-starter first)"
  mkdir -p "$start"
  tar -xzf "$starter" -C "$start" || die "could not unpack $starter"

  START_ENV=()
  while IFS= read -r line; do
    case "$line" in
      "   export "*) read -r -a words <<< "${line#   export }"; START_ENV+=("${words[@]}") ;;
    esac
  done < "$start/START.txt"
  [ "${#START_ENV[@]}" -gt 0 ] || die "START.txt has no export line"

  pw_line="$(sed -n 's/.*sign in: user \([A-Za-z0-9_.-]*\), password \([^ ]*\).*/\1 \2/p' "$start/START.txt")"
  DEMO_USER="${pw_line%% *}"
  [ -n "$DEMO_USER" ] && [ "$DEMO_USER" != "$pw_line" ] || die "START.txt names no demo sign-in"
  (umask 077 && printf '%s\n' "${pw_line#* }" > "$work/demo.pw")
  DEMO_PW_FILE="$work/demo.pw"

  port="$(free_port)"
  base="http://127.0.0.1:$port"
  (cd "$start" && exec env -i "${BASE_ENV[@]}" "${START_ENV[@]}" "$venv/bin/tl" serve --port "$port") \
    >"$work/try-it-serve.log" 2>&1 &
  serve_pid=$!
  SERVERS+=("$serve_pid")
  wait_health "$base" || die "no /health after 30 s (log in $work/try-it-serve.log)"
  py 'import json, sys; h = json.load(open(sys.argv[1])); assert h["status"] == "ok" and h["version"] == sys.argv[2], h' \
    "$work/health.json" "$want" || die "/health does not carry version $want"

  sign_in "$base" "$DEMO_USER" "$DEMO_PW_FILE" "$work/demo.conf" || die "sign-in as the demo account failed"
  code="$(curl -sS -K "$work/demo.conf" -o "$work/records.json" -w '%{http_code}' "$base/records?scope=project%3AP200")" \
    || die "the records request failed"
  [ "$code" = 200 ] || die "GET /records?scope=project:P200 answered $code"
  n="$(py 'import json, sys; rows = json.load(open(sys.argv[1])); assert isinstance(rows, list) and rows; print(len(rows))' "$work/records.json")" \
    || die "the P200 records list is empty"
  stop_server "$serve_pid"

  (cd "$start" && xenv "${START_ENV[@]}" "$venv/bin/tl" --db ./ledger/p200.db awp package ls --project P200) >"$work/awp.out" 2>&1 \
    || { tail -n 3 "$work/awp.out" >&2; die "tl awp package ls --project P200 --db failed"; }
  echo "try-it: ok demo sign-in, P200 records $n rows, $(head -n 1 "$work/awp.out") (tl awp package ls exit 0), health $want"
}

step_real_server() {
  CURRENT_STEP=real-server
  if [ -z "${TL_PG_URL:-}" ]; then
    echo "skip real-server: no Postgres"
    return 0
  fi
  local real="$work/real" db target secret port base code prod rc tmo=() pwd_file="$work/boss.pw"
  mkdir -p "$real"
  db="$(py 'import secrets; print("tl_smoke_" + secrets.token_hex(4))')"
  PG_DB="$db"
  env -i "${BASE_ENV[@]}" SMOKE_PG_URL="$TL_PG_URL" SMOKE_PG_DB="$db" "$venv/bin/python" -I -c \
    'import os; from tl_adapters.postgres.admin import create_database; create_database(os.environ["SMOKE_PG_URL"], os.environ["SMOKE_PG_DB"])' \
    >"$work/pg-create.log" 2>&1 || die "could not create the new database (log in $work/pg-create.log)"
  target="$(env -i "${BASE_ENV[@]}" SMOKE_PG_URL="$TL_PG_URL" SMOKE_PG_DB="$db" "$venv/bin/python" -I -c \
    'import os; from tl_adapters.postgres.admin import database_url; print(database_url(os.environ["SMOKE_PG_URL"], os.environ["SMOKE_PG_DB"]))' 2>/dev/null)" \
    || die "could not build the URL of the new database"
  secret="$(py 'import secrets; print(secrets.token_urlsafe(32))')"
  prod=(TL_ENV=prod "TL_OBJECT_SECRET=$secret" "TL_DB=$target")

  (cd "$real" && xenv "${prod[@]}" "$venv/bin/tl" init) >"$work/real-init.log" 2>&1 \
    || die "tl init on the new database failed (log in $work/real-init.log)"
  (umask 077 && py 'import secrets; print(secrets.token_urlsafe(18))' > "$pwd_file")
  (cd "$real" && xenv "${prod[@]}" "$venv/bin/tl" admin bootstrap --username boss --password-stdin) \
    <"$pwd_file" >"$work/real-bootstrap.log" 2>&1 || die "tl admin bootstrap failed (log in $work/real-bootstrap.log)"

  # A dev token file in the place the server would read it: prod mode must ignore it.
  (umask 077 && py 'import json, pathlib, secrets, sys
t = secrets.token_urlsafe(24)
p = pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps({t: "user:smoke"}))
pathlib.Path(sys.argv[2]).write_text("header = \"Authorization: Bearer %s\"\n" % t)' \
    "$real/dev/data/tokens.json" "$work/devtoken.conf")

  port="$(free_port)"
  base="http://127.0.0.1:$port"
  (cd "$real" && exec env -i "${BASE_ENV[@]}" "${prod[@]}" TL_TRUSTED_PROXY_HEADER=X-Forwarded-For \
    "$venv/bin/tl" serve --host 0.0.0.0 --port "$port") >"$work/real-serve.log" 2>&1 &
  SERVERS+=("$!")
  local serve_pid=$!
  wait_health "$base" || die "no /health on the prod server after 30 s (log in $work/real-serve.log)"

  sign_in "$base" boss "$pwd_file" "$work/boss.conf" || die "sign-in as boss failed"
  code="$(curl -sS -K "$work/boss.conf" -o "$work/accounts.json" -w '%{http_code}' "$base/admin/accounts")" || die "the accounts request failed"
  [ "$code" = 200 ] || die "GET /admin/accounts answered $code"
  py 'import json, sys; names = [a["username"] for a in json.load(open(sys.argv[1]))]; assert "boss" in names and "demo" not in names, "accounts exist"' \
    "$work/accounts.json" || die "the demo account exists on a prod server, or boss is missing"

  code="$(curl -sS -K "$work/devtoken.conf" -o /dev/null -w '%{http_code}' "$base/records?scope=project%3AP200")" || die "the dev-token request failed"
  case "$code" in 401|403) ;; *) die "a token from the dev token file answered $code on a prod server" ;; esac
  stop_server "$serve_pid"

  if command -v timeout >/dev/null 2>&1; then tmo=(timeout 30); fi
  rc=0
  (cd "$real" && ${tmo[@]+"${tmo[@]}"} env -i "${BASE_ENV[@]}" "TL_OBJECT_SECRET=$secret" "TL_DB=$target" \
    "$venv/bin/tl" serve --host 0.0.0.0 --port "$(free_port)") >"$work/real-refuse.log" 2>&1 || rc=$?
  [ "$rc" = 2 ] || die "tl serve --host 0.0.0.0 with TL_ENV unset exited $rc, want 2"
  grep -q 'refusing to bind' "$work/real-refuse.log" || die "the refusal text is not the bind rule"
  echo "real-server: ok new database, tl init, boss signs in, no demo account, dev token refused ($code), TL_ENV unset exits 2"
}

step_session_file() {
  CURRENT_STEP=session-file
  local sess="$work/session/session.json" mode
  [ -n "${DEMO_USER:-}" ] || die "no demo account from try-it"
  (cd "$work/starter" && xenv "${START_ENV[@]}" "$venv/bin/tl" login "$DEMO_USER" --password-stdin) \
    <"$DEMO_PW_FILE" >"$work/login.log" 2>&1 || die "tl login failed (log in $work/login.log)"
  [ -f "$sess" ] || die "no session file at $sess after tl login"
  mode="$(file_mode "$sess")" || die "could not read the mode of the session file"
  [ "$mode" = 600 ] || die "the session file has mode $mode, want 600"
  echo "session-file: ok session file mode 600 after tl login"
}

main() {
  step_install
  step_try_it
  step_real_server
  step_session_file
  DONE=1
  echo "smoke: PASS"
}
main
