#!/usr/bin/env bash
# Demo for P2-FORMS (general forms: publish, fill, submit, review): `just demo P2-FORMS`.
#
# The V3-F1a, F1s, F1b, F2, F3 and F4 clauses of docs/tickets/P2-FORMS/README.md "Demo", each ending in a `PASS clause N: ...`
# line that is printed only after its check returned success (a command's exit code and output, or
# a driver comparison in dev/demos/p2_forms_demo.py). Each clause prints its wall time; the forms
# list reads of the API are timed in the `budget` check and fail the demo over one second.
#   1  a controller publishes a template from a file (CLI); the API reads it back as JSON Schema and as
#      SurveyJS, both equal to the projection of its fields; the ETag answers 304;
#   2  a user saves a draft and submits it (CLI): the number is allocated at submit, not at the save;
#   3  a user fills a template through the runner model (one field at a time) and submits it;
#   4  a user saves a draft, resumes it with `tl form fill TEMPLATE --resume`, and submits it: the number
#      appears only at submit (V3-F2);
#   5  a controller other than the submitter accepts it; the submitter's own review is refused with the
#      exact text; a second controller accepts a controller's own form;
#   6  an inspection's result is filled through its form binding (CLI: `tl form for`, `tl form record`);
#      the inspection then reads Done with the result, and its form is closed (V3-F1s);
#   7  a submission only its author may read answers as a missing one on every forms read (CLI and
#      API, and the MCP tools in V3-F2), byte for byte, for five readers;
#   8  a draft is invisible to every reader but its author (CLI and API).
#   9  in a browser (Playwright, Chromium, the web client's own CSP): cbrooks fills a general template and
#      sends it; hsato opens a scan card, follows its link and fills an inspection; both read back through
#      the API, answers equal to what was typed, source `web`; no CSP violation (V3-F3);
#  11  the terminal app: the forms log opens, a template is filled through the runner screen and sent;
#      the new number is in the log (V3-F1b).
#  10  intake, signed in (V3-F4): a controller issues a code (printed once, only its hash stored), one item is
#      staged by a dev-only helper (the public route is not built), accepted as the record it proposes and read
#      back, a second rejected, the due text purged; no secret in any read, CLI output or ledger row.
#
# The ledger is the whole demo project P200 (its `forms` section included). On SQLite it is the full
# ledger tests/perf caches under .gate/demo-full (built once, about four minutes, then copied); on
# Postgres it is built into a throw-away database on TL_PG_URL (default
# postgresql://postgres:postgres@localhost:5432/tl_test, `just dev up`), dropped afterwards.
# `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". The API is `tl serve` on a
# free loopback port, stopped afterwards. Exits non-zero (and prints DEMO FAILED) when a clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
ROOT="$PWD"
workdir="$(mktemp -d)"
server_pid=""
pg_url=""
stop_group() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || true
  sleep 0.2
  kill -KILL -- "-$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
stop_server() { stop_group "$server_pid"; server_pid=""; }
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'stop_server; drop_pg; rm -rf "${workdir:?}"' EXIT

PROJECT=P200
PASS_WORD="p200-demo-pass" # demo data only (dev/seed/demo_project/core.py)
export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_LAKE_DIR="$workdir/lake"
export TL_SCHEMA_DIR="$ROOT/dev/data/demo-project-schema"
unset TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2 (${3} s)"; }
driver() {
  quiet uv run python dev/demos/p2_forms_demo.py "$@" 2>"$workdir/driver.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/driver.err" >&2; fail "a check was not met: $*"; }
}
as() { local who="$1"; shift; TL_SESSION_FILE="$workdir/session-$who.json" "$@"; }
expect() { case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac; }
refuse() { # refuse TEXT cmd...: the command must fail and say TEXT
  local text="$1" out; shift
  if out="$("$@" 2>&1)"; then echo "$out"; fail "this was accepted: $*"; fi
  echo "$out"; expect "$text" "$out"
}
last_word() { awk '{print $NF}' <<<"$1"; }

clause4_run() { # clause 4 (V3-F2): self-contained; needs $PROJECT, $tpl, the sessions
  local out began=$SECONDS draft key
  step "[$backend] clause 4: save a draft, resume it with --resume, submit it; the number comes at submit"
  out="$(as cbrooks tl form fill "$tpl" --project "$PROJECT" --answer topic="Resumed talk" --answer talk_date=2026-11-06)"; echo "$out"
  expect "saved " "$out"
  draft="$(last_word "$out")"
  out="$(as cbrooks tl form fill "$tpl" --resume --project "$PROJECT" --answer led_by=Callum)"; echo "$out"
  [ "$(last_word "$out")" = "$draft" ] || fail "--resume saved another draft than $draft"
  out="$(as cbrooks tl form show "$draft" --submission --project "$PROJECT")"; echo "$out"
  expect "Draft" "$out"
  out="$(as cbrooks tl form submit "$draft" --project "$PROJECT" --answer 'hazards_covered=Falls' \
    --answer ppe_checked=yes --answer attendees=6)"; echo "$out"
  expect "submitted P200-FRM-" "$out"
  key="$(last_word "$out")"
  driver clause4 "$key" "$draft"
  clause 4 "$draft saved, resumed (--resume), submitted as $key; no number until submit" "$((SECONDS - began))"
}

clause6_run() { # clause 6 (V3-F1s): self-contained; needs $PROJECT, $workdir, the sessions and the API
  local insp out began=$SECONDS
  step "[$backend] clause 6: an inspection result is filled through its form binding (CLI)"
  insp="$(driver clause6-pick)"; echo "$insp"
  out="$(as hsato tl form for "$insp" --project "$PROJECT")"; echo "$out"
  expect "command RecordInspectionResult  answers go in answers" "$out"
  driver clause6-answers "$insp" "$workdir/insp-answers.json"
  out="$(as hsato tl form record "$insp" --project "$PROJECT" --answers-file "$workdir/insp-answers.json")"; echo "$out"
  expect "recorded RecordInspectionResult on $insp" "$out"
  out="$(as hsato tl insp show "$insp" --project "$PROJECT")"; echo "$out"
  expect "Done" "$out"
  driver clause6 "$insp"
  clause 6 "$insp: result recorded through its form binding by the inspection's own command; read back as Done" "$((SECONDS - began))"
}

clause9_run() { # clause 9 (V3-F3): self-contained; needs $PROJECT, $workdir, $url, $tpl and the API
  local began=$SECONDS out tok key code tid
  wd() { quiet uv run python dev/demos/p2_forms_web_demo.py "$@" 2>"$workdir/driver.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/driver.err" >&2; fail "a check was not met: $*"; }; }
  step "[$backend] clause 9: a person fills a general form and an inspection in a browser"
  wd general-plan "$tpl" "$workdir/web-general.json"
  tid="$(wd template-id "$tpl")"; tok="$(wd token cbrooks)"
  out="$(node dev/tools/surveyjs_probe/page_probe.mjs "$url" "$tok" "/web/forms/t/$tid?project=$PROJECT" \
    "$(cat "$workdir/web-general.json")" "$workdir/clause9-general.png")" || { echo "$out"; fail "the browser leg of the general form failed"; }
  echo "$out"
  key="$(sed -n 's|^result .*/web/forms/done/\(P[0-9A-Za-z-]*\)?.*|\1|p' <<<"$out" | head -1)"
  [ -n "$key" ] || fail "the browser did not land on a received page"
  expect "Received $key" "$(sed -n 's/^result //p' <<<"$out")"
  wd general-check "$key" "$workdir/web-general.json"
  out="$(wd inspection-plan "$workdir/web-insp.json")"; echo "$out"
  key="$(awk '{print $1}' <<<"$out")"; code="$(awk '{print $2}' <<<"$out")"; tok="$(wd token hsato)"
  out="$(PAGE_PROBE_CLICK="Open record" node dev/tools/surveyjs_probe/page_probe.mjs "$url" "$tok" "/web/q/$code" \
    "$(cat "$workdir/web-insp.json")" "$workdir/clause9-inspection.png")" || { echo "$out"; fail "the browser leg of the inspection failed"; }
  echo "$out"
  expect "followed the link to /web/forms/for/$key" "$out"
  wd inspection-check "$key" "$workdir/web-insp.json"
  clause 9 "cbrooks filled $tpl and hsato filled $key from its scan card, in a browser; both read back through the API; no CSP violation" "$((SECONDS - began))"
}

clause10_run() { # clause 10 (V3-F4): self-contained; needs $PROJECT, $workdir, $tpl, the sessions and the API
  local began=$SECONDS out itpl code code_id ids item_a item_b log="$workdir/clause10.out"
  step "[$backend] clause 10: intake, signed in: issue a code, accept one item, reject one, purge"
  : >"$log"
  out="$(as mokafor tl form publish schema/fixtures/forms/templates/intake/scaffold-request.yaml)"; echo "$out"
  expect "published TPL-" "$out"
  itpl="$(awk '{print $2}' <<<"$out")"
  out="$(as mokafor tl intake code issue --project "$PROJECT" --template "$itpl" --heading "Poster at gate 3" \
    --controller-role controller --expires-on "$(date -d '+10 days' +%F)")"; echo "$out"
  expect "issued " "$out"; expect "code " "$out"
  code_id="$(awk 'NR==1{print $2}' <<<"$out")"; code="$(sed -n 's/^code //p' <<<"$out")"
  out="$(as mokafor tl intake code ls --project "$PROJECT")"; echo "$out" | tee -a "$log"
  expect "Poster at gate 3" "$out"
  ids="$(driver clause10-stage "$code_id")"; item_a="$(awk '{print $1}' <<<"$ids")"; item_b="$(awk '{print $2}' <<<"$ids")"
  out="$(as mokafor tl intake ls --project "$PROJECT" --state Pending)"; echo "$out" | tee -a "$log"
  expect "$item_a" "$out"; expect "$item_b" "$out"
  out="$(as mokafor tl intake show "$item_a" --project "$PROJECT")"; echo "$out"
  expect "Pending" "$out"; expect "Sam Smith" "$out"
  driver clause10-args "$tpl" "$workdir/intake-args.json" >/dev/null
  out="$(as mokafor tl intake accept "$item_a" --project "$PROJECT" --as SubmitForm --args-file "$workdir/intake-args.json")"; echo "$out"
  expect "accepted $item_a as SubmitForm" "$out"
  out="$(as mokafor tl intake reject "$item_b" --project "$PROJECT" --reason spam)"; echo "$out"
  expect "rejected $item_b" "$out"
  out="$(as mokafor tl intake purge --project "$PROJECT")"; echo "$out"
  expect "purged 1" "$out"
  out="$(as mokafor tl intake ls --project "$PROJECT")"; echo "$out" | tee -a "$log"
  expect "SubmitForm" "$out"; expect "spam" "$out"
  out="$(as mokafor tl intake code ls --project "$PROJECT")"; echo "$out" | tee -a "$log"
  refuse "forbidden" as cbrooks tl intake ls --project "$PROJECT"
  driver clause10 "$item_a" "$item_b" "$tpl" "$log" <<<"$code"
  clause 10 "a code issued (printed once); $item_a accepted as the record it proposes and read back; $item_b rejected and purged; no secret in any read" "$((SECONDS - began))"
}

run_backend() {
  local backend="$1" port url out began tpl draft key own hsato_draft h m who
  step "[$backend] the demo project P200"
  drop_pg
  rm -rf "${workdir:?}/objects" "${workdir:?}/lake"
  rm -f "${workdir:?}"/session-* "${workdir:?}"/*.out "${workdir:?}"/*.yaml
  began=$SECONDS
  case "$backend" in
    sqlite)
      export TL_DB="$workdir/$backend.db"
      driver ledger "$TL_DB"
      ;;
    postgres)
      pg_url="$(quiet uv run python dev/demos/p1_i0_demo.py pg-create)" || fail "Postgres is not reachable at TL_PG_URL (try: just dev up)"
      export TL_DB="$pg_url"
      quiet uv run python -m dev.seed.demo_project --db "$pg_url" --objects "$workdir/objects" >"$workdir/build.out" \
        || { tail -20 "$workdir/build.out" >&2; fail "the demo project did not build on Postgres"; }
      tail -3 "$workdir/build.out"
      ;;
    *) fail "unknown backend $backend" ;;
  esac
  echo "(ledger ready: $((SECONDS - began)) s)"
  for who in mokafor ipetrov cbrooks pnair hsato treyes; do
    printf '%s\n' "$PASS_WORD" | as "$who" tl login "$who" --password-stdin >/dev/null
  done
  as mokafor tl admin roles grant ipetrov --project "$PROJECT" --module forms --role superuser \
    --reason "demo: reviews forms" >/dev/null

  port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  url="http://127.0.0.1:$port"
  export TL_API_URL="$url"
  setsid uv run tl serve --port "$port" >"$workdir/server-$backend.log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 150); do
    curl -fs "$url/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  curl -fs "$url/health" | grep -q '"status":"ok"' || { cat "$workdir/server-$backend.log" >&2; fail "the server did not start"; }
  echo "(serving $backend at $url)"

  step "[$backend] clause 1: publish a template (CLI); read it back as JSON Schema and SurveyJS (API)"
  began=$SECONDS
  driver template-file "$workdir/induction.yaml" >/dev/null
  out="$(as mokafor tl form publish "$workdir/induction.yaml")"; echo "$out"
  expect "published TPL-" "$out"
  tpl="$(awk '{print $2}' <<<"$out")"
  out="$(as cbrooks tl form ls)"; echo "$out"
  expect "$tpl" "$out"
  driver clause1 "$tpl"
  clause 1 "$tpl published; JSON Schema and SurveyJS equal the projections; the ETag answers 304" "$((SECONDS - began))"

  step "[$backend] clause 2: save a draft and submit it from the CLI; the number is taken at submit"
  began=$SECONDS
  out="$(as cbrooks tl form fill "$tpl" --project "$PROJECT" --answer topic="Scaffold tag check" --answer talk_date=2026-11-05)"; echo "$out"
  expect "saved " "$out"
  draft="$(last_word "$out")"
  out="$(as cbrooks tl form drafts --project "$PROJECT")"; echo "$out"
  expect "$draft" "$out"
  out="$(as cbrooks tl form submit "$draft" --project "$PROJECT" --answer led_by=Callum \
    --answer 'hazards_covered=Falls,Lifting' --answer ppe_checked=yes --answer attendees=9)"; echo "$out"
  expect "submitted P200-FRM-" "$out"
  key="$(last_word "$out")"
  as cbrooks tl form show "$key" --submission --project "$PROJECT"
  driver clause2 "$key" "$draft"
  clause 2 "$draft saved with no number, submitted as $key" "$((SECONDS - began))"

  step "[$backend] clause 3: fill through the runner model and submit"
  began=$SECONDS
  out="$(driver clause3 "$tpl")"; echo "$out"
  clause 3 "the runner walked $tpl one field at a time; the submission holds the confirmed answers" "$((SECONDS - began))"

  step "[$backend] clause 5: a controller who did not fill it accepts; the submitter's own review is refused"
  began=$SECONDS
  out="$(as ipetrov tl form review "$key" accept --note "Checked and filed." --project "$PROJECT")"; echo "$out"
  expect "accepted $key" "$out"
  out="$(as ipetrov tl form submit "$tpl" --project "$PROJECT" --answer topic="Controller's own talk" --answer talk_date=2026-11-05 \
    --answer led_by=Ivan --answer 'hazards_covered=Electrical' --answer ppe_checked=yes --answer attendees=4)"; echo "$out"
  own="$(last_word "$out")"
  refuse "error: the person who filled a form may not review it" \
    as ipetrov tl form review "$own" accept --project "$PROJECT"
  out="$(as mokafor tl form review "$own" accept --project "$PROJECT")"; echo "$out"
  expect "accepted $own" "$out"
  driver clause5 "$key" "$own"
  clause 5 "$key accepted by ipetrov (not its author); ipetrov's own review of $own refused with the exact text; mokafor accepted it" "$((SECONDS - began))"

  clause4_run

  clause6_run
  clause9_run

  step "[$backend] clause 7: a hidden submission answers as a missing one on every forms read"
  began=$SECONDS
  for who in mokafor ipetrov treyes cbrooks pnair; do
    h="$(as "$who" tl form show P200-FRM-0012 --submission --project "$PROJECT" 2>&1 || true)"
    m="$(as "$who" tl form show P200-FRM-9999 --submission --project "$PROJECT" 2>&1 || true)"
    [ "${h//P200-FRM-0012/<ref>}" = "${m//P200-FRM-9999/<ref>}" ] || { echo "$h"; echo "$m"; fail "$who: hidden differs from missing (CLI show)"; }
    expect "no submission" "$h"
    h="$(as "$who" tl form review P200-FRM-0012 accept --project "$PROJECT" 2>&1 || true)"
    m="$(as "$who" tl form review P200-FRM-9999 accept --project "$PROJECT" 2>&1 || true)"
    [ "${h//P200-FRM-0012/<ref>}" = "${m//P200-FRM-9999/<ref>}" ] || { echo "$h"; echo "$m"; fail "$who: hidden differs from missing (CLI review)"; }
    expect "no submission" "$h"
    out="$(as "$who" tl form ls --submissions --project "$PROJECT")"
    case "$out" in *P200-FRM-0012*) fail "$who: the list shows the hidden submission" ;; esac
    echo "$who: CLI show, review and list: the same as a missing key"
  done
  driver clause7 P200-FRM-0012
  driver clause7-mcp P200-FRM-0012
  clause 7 "P200-FRM-0012 (a privileged form) is a missing key for mokafor, ipetrov, treyes, cbrooks and pnair on CLI show, review, list and the API, and for an agent and three people on the MCP tools, byte for byte" "$((SECONDS - began))"

  step "[$backend] clause 8: a draft is invisible to every reader but its author"
  began=$SECONDS
  hsato_draft="$(as hsato tl form drafts --project "$PROJECT" | awk 'NR==2{print $1}')"
  [ -n "$hsato_draft" ] || fail "hsato has no draft"
  for who in mokafor ipetrov treyes cbrooks pnair; do
    h="$(as "$who" tl form show "$hsato_draft" --submission --project "$PROJECT" 2>&1 || true)"
    m="$(as "$who" tl form show 01J000000000000000000000 --submission --project "$PROJECT" 2>&1 || true)"
    [ "${h//$hsato_draft/<ref>}" = "${m//01J000000000000000000000/<ref>}" ] || { echo "$h"; fail "$who: the draft differs from a missing id"; }
    out="$(as "$who" tl form ls --submissions --state Draft --project "$PROJECT")"
    case "$out" in *"$hsato_draft"*) fail "$who: the list shows the draft" ;; esac
  done
  out="$(as hsato tl form show "$hsato_draft" --submission --project "$PROJECT")"; echo "$out"
  expect "Draft" "$out"
  driver clause8 "$hsato_draft" hsato
  clause 8 "hsato's draft is a missing id for five other readers (CLI show and list, API); hsato reads it" "$((SECONDS - began))"

  clause10_run

  step "[$backend] clause 11: the terminal app: open the forms log, fill a template through the runner screen"
  began=$SECONDS
  out="$(driver clause11 "$tpl")"; echo "$out"
  expect "submitted P200-FRM-" "$out"
  clause 11 "the forms log opened in the terminal app; $tpl filled through the runner screen and sent; the new number is in the log" "$((SECONDS - began))"

  step "[$backend] the forms list reads are under one second"
  driver budget

  stop_server
  drop_pg
  echo "[$backend] clauses 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-FORMS demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
