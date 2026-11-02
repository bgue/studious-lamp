#!/usr/bin/env bash
# Demo for P2-WEB1 (the web client, clauses 1 to 5 of the web client spec, over HTTP): `just demo P2-WEB1`.
#
# The five clauses, each ending in a PASS line, once on SQLite and once on Postgres, over HTTP with
# curl and a cookie jar against a real `tl serve` on a free loopback port:
#   1  sign-in (`curl -c jar ... /web/sign-in`) gives 303 and a session cookie with HttpOnly and
#      SameSite=Strict; the JSON API ignores the cookie (401 on /commands/AnswerTechnical);
#   2  GET /web/p/P123/rfis has the region ids in order; its rows match `tl rfi ls` for P123; the
#      restricted RFI is absent for amy and present for dora (a controller); its number answers amy
#      with the generic 404 page;
#   3  selecting an RFI shows its panel and only the offered actions; POST .../do/AnswerTechnical
#      without X-CSRF-Token is 403 csrf_refused; with it, 200 and the panel shows the new state;
#   4  the document log shows a page-1 image for a PDF revision; /web/p/P123/files/{id}/view serves
#      the viewer with the CSP header; /web/files/{id}/content returns bytes whose SHA-256 the file
#      info states;
#   5  ?mode=technical shows record ids for the admin (demo) and the "for admins" status line for amy.
# The script holds no business logic: it drives the CLI to seed and the server to check.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. The server
# runs in its own process group and is stopped on exit. Nothing is left behind.
# Exits non-zero (and prints DEMO FAILED) when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
pg_url=""
stop_server() { # the server has its own process group (setsid): stop the whole group
  [ -n "$server_pid" ] || return 0
  kill -TERM -- "-$server_pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    curl -fs "${TL_DEMO_URL:-http://127.0.0.1:1}/health" >/dev/null 2>&1 || break
    sleep 0.1
  done
  kill -KILL -- "-$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  server_pid=""
}
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'stop_server; drop_pg; rm -rf "$workdir"' EXIT

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
DOC_STANDARDS=schema/fixtures/standards/co.acme.documents@1.0.0.yaml
# The region ids of the RFI log in page order, as log.html and its includes (crumb, filter, body,
# table, panel, actions, keys, status) render them. log-open is the conditional Enter link: not compared.
REGION_IDS='id="log-crumb" id="log-filter" id="log-body" id="log-table" id="log-panel" id="log-actions" id="log-keys" id="log-status"'

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
password_file() { # password_file NAME TEXT: the password goes to a file, never to a command line
  printf '%s' "$2" > "$workdir/$1.pw"
}
fetch() { # fetch JAR NAME METHOD PATH [curl options]: status in $code; body and headers in $workdir/NAME.*
  local jar="$1" name="$2" method="$3" path="$4"
  shift 4
  code="$(curl -s -b "$jar" -o "$workdir/$name.body" -D "$workdir/$name.head" -w '%{http_code}' -X "$method" "$@" "$TL_DEMO_URL$path")"
}
expect_code() { [ "$1" = "$2" ] || fail "$3: expected HTTP $2, got $1"; }
has() { grep -q -- "$2" "$1" || fail "$3"; } # has FILE PATTERN MESSAGE
lacks() { ! grep -q -- "$2" "$1" || fail "$3"; }
rows() { grep -o 'data-number="[^"]*"' "$1" | sed 's/^data-number="//; s/"$//'; }
record_of() { # record_of FILE NUMBER: the record id of a log row, from its data-open link
  sed -n "s#.*data-number=\"$2\"[^>]*data-open=\"[^\"]*/records/\([^\"?]*\)[^\"]*\".*#\1#p" "$1" | head -1
}
csrf_of() { sed -n 's/.*csrf-token" content="\([^"]*\)".*/\1/p' "$1" | head -1; }
sign_in() { # sign_in JAR NAME: a web sign-in; the cookie goes into JAR
  code="$(curl -s -c "$1" -o "$workdir/$2.body" -D "$workdir/$2.head" -w '%{http_code}' \
    --data-urlencode "username=$2" --data-urlencode "password@$workdir/$2.pw" \
    "$TL_DEMO_URL/web/sign-in")"
}

run_backend() {
  local backend="$1" port needed out first second third csrf rid pdf_id token sha bytes_sha
  step "[$backend] a new ledger: an admin, a plain user, a document controller"
  stop_server
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
  password_file demo "demo"
  password_file amy "a long passphrase for amy"
  password_file dora "a long passphrase for dora"
  printf 'demo\n' | as demo tl login demo --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for amy" | as demo tl admin user add amy --display-name "Amy A" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for dora" | as demo tl admin user add dora --display-name "Dora C" --password-stdin >/dev/null
  as demo tl admin user roles dora --add document_controller >/dev/null
  printf '%s\n' "a long passphrase for amy" | as amy tl login amy --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for dora" | as dora tl login dora --password-stdin >/dev/null

  step "[$backend] seed: three RFIs (one drafted, one issued, one restricted by dora), a document with a 3-page PDF"
  as demo tl standards load "$STANDARDS" >/dev/null
  as demo tl standards load "$DOC_STANDARDS" >/dev/null
  needed="$(python3 -c 'import datetime as d; print(d.date.today() + d.timedelta(days=10))')"
  out="$(as amy tl rfi raise --project P123 --subject "Beam B12 routing" --question "Which routing applies to beam B12 in revision C?" --discipline structural --required-by "$needed" --to "Meridian:pm@meridian.example")"
  first="$(echo "$out" | awk '/^raised/ {print $2}')"
  [ -n "$first" ] || fail "no number for the first RFI"
  out="$(as amy tl rfi raise --project P123 --subject "Gasket class at line 47-P-102" --question "Which gasket class applies to the new flange at line 47-P-102?" --discipline piping --required-by "$needed" --to "Meridian:pm@meridian.example")"
  second="$(echo "$out" | awk '/^raised/ {print $2}')"
  [ -n "$second" ] || fail "no number for the second RFI"
  as amy tl rfi submit "$second" --project P123 >/dev/null
  as dora tl rfi issue "$second" --project P123 >/dev/null
  out="$(as amy tl rfi raise --project P123 --subject "Cable tray support spacing on rack R-2" --question "Confirm 1.5 m support spacing for the cable trays on rack R-2." --discipline structural --required-by "$needed" --to "Meridian:pm@meridian.example")"
  third="$(echo "$out" | awk '/^raised/ {print $2}')"
  [ -n "$third" ] || fail "no number for the third RFI"
  as amy tl rfi submit "$third" --project P123 >/dev/null
  as dora tl corr class set "$third" --project P123 --to restricted --reason "commercial terms" >/dev/null
  as amy tl doc register ISO-1234 --project P123 --title "Isometric, line 47-P-101" --type ISO --discipline PIP --originator "Acme Piping" >/dev/null
  as amy tl doc rev create ISO-1234 --project P123 --purpose "For review" >/dev/null
  python3 - "$workdir/iso-1234.pdf" <<'PY'
import sys

# A three-page PDF (stdlib only): one text line per page, a correct cross-reference table.
pages = 3
objs = ["<< /Type /Catalog /Pages 2 0 R >>"]
kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(pages))
objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>")
for i in range(pages):
    objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R /Resources << >> >>")
    text = f"BT /F1 24 Tf 72 720 Td (Isometric line 47-P-101 page {i + 1} of {pages}) Tj ET"
    objs.append(f"<< /Length {len(text)} >>\nstream\n{text}\nendstream")
out = bytearray(b"%PDF-1.4\n")
offsets = []
for n, body in enumerate(objs, start=1):
    offsets.append(len(out))
    out += f"{n} 0 obj\n{body}\nendobj\n".encode()
xref = len(out)
out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
for off in offsets:
    out += f"{off:010d} 00000 n \n".encode()
out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
open(sys.argv[1], "wb").write(bytes(out))
PY
  as amy tl doc rendition add ISO-1234 A "$workdir/iso-1234.pdf" --project P123 --kind pdf >/dev/null
  as demo tl doc rev issue ISO-1234 A --project P123 --status IFR >/dev/null

  step "[$backend] the server on a free loopback port, waiting on /health"
  port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  export TL_DEMO_URL="http://127.0.0.1:$port"
  export TL_TOKENS="$workdir/tokens-$backend.json"
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

  step "[$backend] clause 1: sign-in sets an HttpOnly, SameSite=Strict cookie; the JSON API ignores it"
  sign_in "$workdir/jar-amy" amy
  expect_code "$code" 303 "sign-in"
  has "$workdir/amy.head" "^[Ss]et-[Cc]ookie: tl_session=" "the sign-in sets no session cookie"
  has "$workdir/amy.head" "HttpOnly" "the session cookie is not HttpOnly"
  has "$workdir/amy.head" "SameSite=Strict" "the session cookie is not SameSite=Strict"
  fetch "$workdir/jar-amy" api-refused GET /commands/AnswerTechnical
  expect_code "$code" 401 "the JSON API with a cookie"
  echo "PASS clause 1"

  step "[$backend] clause 2: the RFI log, its rows against tl rfi ls, the restricted RFI"
  fetch "$workdir/jar-amy" amy-log GET /web/p/P123/rfis
  expect_code "$code" 200 "the RFI log for amy"
  regions="$(grep -o 'id="[a-z-]*"' "$workdir/amy-log.body" | grep -v '^id="log-open"$' | paste -sd' ' -)"
  [ "$regions" = "$REGION_IDS" ] || fail "the region ids are: $regions"
  as amy tl rfi ls --project P123 | awk '/^P123-RFI-/ {print $1}' > "$workdir/cli-rows.txt"
  rows "$workdir/amy-log.body" > "$workdir/web-rows.txt"
  diff "$workdir/cli-rows.txt" "$workdir/web-rows.txt" >/dev/null || fail "the log rows differ from tl rfi ls"
  lacks "$workdir/amy-log.body" "data-number=\"$third\"" "the restricted RFI is listed for amy"
  sign_in "$workdir/jar-dora" dora
  expect_code "$code" 303 "the dora sign-in"
  fetch "$workdir/jar-dora" dora-log GET /web/p/P123/rfis
  expect_code "$code" 200 "the RFI log for dora"
  has "$workdir/dora-log.body" "data-number=\"$third\"" "the restricted RFI is not listed for dora"
  fetch "$workdir/jar-amy" amy-404 GET "/web/p/P123/rfis/panel/$third"
  expect_code "$code" 404 "the restricted RFI for amy"
  has "$workdir/amy-404.body" "<title>Not found" "the restricted RFI does not answer with the generic 404 page"
  echo "PASS clause 2"

  step "[$backend] clause 3: the panel offers only the rule-table actions; a POST without the token is refused, with it answered"
  fetch "$workdir/jar-amy" amy-panel GET "/web/p/P123/rfis/panel/$second"
  expect_code "$code" 200 "the panel of the issued RFI"
  has "$workdir/amy-panel.body" "$second" "the panel does not name the RFI"
  offered="$(grep -o 'data-command="[A-Za-z]*"' "$workdir/amy-panel.body" | sed 's/^data-command="//; s/"$//' | paste -sd' ' -)"
  # a plain user on an awaiting-response technical item: the two user actions of that state (actions.py rules)
  [ "$offered" = "AnswerTechnical CloseTechnical" ] || fail "the panel offers: $offered"
  fetch "$workdir/jar-amy" amy-log-2 GET /web/p/P123/rfis
  csrf="$(csrf_of "$workdir/amy-log-2.body")"
  [ -n "$csrf" ] || fail "the page carries no CSRF token"
  rid="$(record_of "$workdir/amy-log-2.body" "$second")"
  [ -n "$rid" ] || fail "no record id for $second"
  answer_path="/web/p/P123/records/$rid/do/AnswerTechnical"
  fetch "$workdir/jar-amy" refused POST "$answer_path" -H "Origin: $TL_DEMO_URL" \
    --data-urlencode "answer=Use the original routing." -d cost_impact=no -d schedule_impact=no
  expect_code "$code" 403 "the answer without X-CSRF-Token"
  has "$workdir/refused.body" '"csrf_refused"' "the refusal is not csrf_refused"
  fetch "$workdir/jar-amy" answered POST "$answer_path" -H "Origin: $TL_DEMO_URL" -H "X-CSRF-Token: $csrf" \
    --data-urlencode "answer=Use the original routing." -d cost_impact=no -d schedule_impact=no
  expect_code "$code" 200 "the answer with X-CSRF-Token"
  fetch "$workdir/jar-amy" amy-panel-2 GET "/web/p/P123/rfis/panel/$second"
  has "$workdir/amy-panel-2.body" "Answered" "the panel does not show the new state"
  echo "PASS clause 3"

  step "[$backend] clause 4: the page-1 image, the viewer with its CSP, the bytes against the SHA-256 of the file info"
  fetch "$workdir/jar-amy" amy-docs GET /web/p/P123/documents
  expect_code "$code" 200 "the document log"
  has "$workdir/amy-docs.body" 'alt="Page 1"' "the document log shows no page-1 image"
  pdf_id="$(sed -n 's#.*src="/web/files/\([^/"]*\)/page1.png.*#\1#p' "$workdir/amy-docs.body" | head -1)"
  [ -n "$pdf_id" ] || fail "no page-1 image file"
  fetch "$workdir/jar-amy" page1 GET "/web/files/$pdf_id/page1.png?scope=project%3AP123"
  expect_code "$code" 200 "the page-1 image"
  fetch "$workdir/jar-amy" viewer GET "/web/p/P123/files/$pdf_id/view"
  expect_code "$code" 200 "the viewer"
  has "$workdir/viewer.head" "^[Cc]ontent-[Ss]ecurity-[Pp]olicy:" "the viewer has no CSP header"
  has "$workdir/viewer.body" 'id="pdf-view"' "the viewer page has no PDF view"
  fetch "$workdir/jar-amy" content GET "/web/files/$pdf_id/content?scope=project%3AP123"
  expect_code "$code" 200 "the file content"
  printf '{"username":"amy","password":"%s"}' "a long passphrase for amy" > "$workdir/amy.json"
  token="$(curl -s -H 'Content-Type: application/json' -d "@$workdir/amy.json" "$TL_DEMO_URL/auth/sign-in" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')"
  [ -n "$token" ] || fail "the API sign-in gave no token"
  curl -s -H "Authorization: Bearer $token" "$TL_DEMO_URL/files/$pdf_id?scope=project%3AP123" -o "$workdir/file-info.json"
  sha="$(sed -n 's/.*"sha256":"\([0-9a-f]*\)".*/\1/p' "$workdir/file-info.json")"
  [ -n "$sha" ] || fail "the file info states no SHA-256"
  bytes_sha="$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$workdir/content.body")"
  [ "$bytes_sha" = "$sha" ] || fail "the bytes do not match the SHA-256 the file info states"
  echo "PASS clause 4"

  step "[$backend] clause 5: ?mode=technical shows record ids to the admin and a status line to amy"
  sign_in "$workdir/jar-demo" demo
  expect_code "$code" 303 "the admin sign-in"
  fetch "$workdir/jar-demo" demo-panel GET "/web/p/P123/rfis/panel/$second?mode=technical"
  expect_code "$code" 200 "the technical panel for the admin"
  has "$workdir/demo-panel.body" "Record id" "the admin sees no record id"
  has "$workdir/demo-panel.body" "$rid" "the admin's record id is not the record's"
  fetch "$workdir/jar-amy" amy-tech GET "/web/p/P123/rfis?mode=technical"
  expect_code "$code" 200 "the technical log for amy"
  has "$workdir/amy-tech.body" "for admins" "amy sees no 'for admins' status line"
  lacks "$workdir/amy-tech.body" "Record id" "amy sees a record id in the log"
  fetch "$workdir/jar-amy" amy-tech-panel GET "/web/p/P123/rfis/panel/$second?mode=technical"
  expect_code "$code" 200 "the technical panel for amy"
  lacks "$workdir/amy-tech-panel.body" "Record id" "amy sees a record id in the panel"
  echo "PASS clause 5"

  stop_server
  drop_pg
  echo "[$backend] clauses 1-5 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-WEB1 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
