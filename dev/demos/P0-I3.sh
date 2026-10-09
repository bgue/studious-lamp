#!/usr/bin/env bash
# Demo for P0-I3 (links, numbering, workflow; palette, link picker, trace): a record gets its key from
# a numbering pattern, a workflow transition is blocked by a missing expected link and allowed once
# the link exists, links go through their lifecycle, and the TUI screens run against the services.
# Run with `just demo P0-I3` from the repository root. Uses a temporary ledger; nothing is left
# behind. Fails (exit 1) when an expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
export TL_DB="$workdir/tl.db"
unset TL_SCHEMA_DIR

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
expect() { # expect <text> <pattern>: fail the demo if the pattern is missing
  if ! grep -Eq -- "$2" <<<"$1"; then
    echo "DEMO FAILED: expected /$2/ in:" >&2
    echo "$1" >&2
    exit 1
  fi
}
refuse() { # refuse <description> <command...>: the command must fail; its stderr is printed
  local what="$1"
  shift
  if "$@" 2>"$workdir/refused.err"; then
    echo "DEMO FAILED: $what was accepted" >&2
    exit 1
  fi
  cat "$workdir/refused.err"
}

step "tl init ; two records get their keys from the numbering pattern (no key given)"
tl init
out="$(tl record create --project P123 --title "NCR: weld porosity")"
echo "$out"
expect "$out" '^key P123-REC-0001$'
out="$(tl record create --project P123 --title "Weld map WM-12")"
expect "$out" '^key P123-REC-0002$'
echo "$out"
ncr=P123-REC-0001
support=P123-REC-0002

step "the key sequence has no gap: Numbering.Allocated is in the ledger before each Record.Created"
quiet uv run python - "$TL_DB" <<'PY'
import json, sqlite3, sys

rows = sqlite3.connect(sys.argv[1]).execute(
    "SELECT payload FROM events WHERE event_type = 'Numbering.Allocated' ORDER BY seq"
).fetchall()
keys = [json.loads(p)["key"] for (p,) in rows]
print("allocated:", keys)
assert keys == ["P123-REC-0001", "P123-REC-0002"], keys
PY

step "tl wf show   (workflow state and what each transition needs)"
out="$(tl wf show --project P123 "$ncr")"
echo "$out"
expect "$out" '^state: Draft$'
expect "$out" '^option submit -> Review allowed$'

step "tl wf transition submit"
out="$(tl wf transition --project P123 "$ncr" submit)"
echo "$out"
expect "$out" "^transitioned $ncr Draft -> Review$"

step "approve is blocked: the NCR is expected to have a supporting record (exit 1)"
refuse "approve without the expected link" tl wf transition --project P123 "$ncr" approve | tee "$workdir/blocked.txt"
expect "$(cat "$workdir/blocked.txt")" 'guard expected_links FAILED'

step "tl link list   (the expected link is shown as missing)"
out="$(tl link list --project P123 "$ncr")"
echo "$out"
expect "$out" '^missing supporting record '

step "tl link add   (the NCR references the weld map)"
out="$(tl link add --project P123 "$ncr" "$support")"
echo "$out"
expect "$out" '^added '
link_id="$(head -1 <<<"$out" | cut -d' ' -f2)"
out="$(tl link list --project P123 "$support")"
echo "$out"
expect "$out" "^in  referenced by  $ncr  active  floating  $link_id\$"

step "approve is allowed now"
out="$(tl wf transition --project P123 "$ncr" approve)"
echo "$out"
expect "$out" "^transitioned $ncr Review -> Approved$"

step "issue needs the manager role (a stub list until auth exists): refused, then allowed"
refuse "issue without the role" tl wf transition --project P123 "$ncr" issue | tee "$workdir/role.txt"
expect "$(cat "$workdir/role.txt")" 'needs one of the roles: manager'
out="$(tl wf transition --project P123 "$ncr" issue --role manager)"
echo "$out"
expect "$out" "^transitioned $ncr Approved -> Issued$"

step "link lifecycle: suggest, accept, flag stale, re-pin, retract; a declined suggestion is not made again"
third="$(tl record create --project P123 --title "Inspection report" | sed -n 's/^key //p')"
out="$(tl link suggest --project P123 "$support" "$third" --confidence 0.8)"
expect "$out" '^status suggested$'
sid="$(head -1 <<<"$out" | cut -d' ' -f2)"
tl link accept --project P123 "$sid"
tl link flag --project P123 "$sid" --status stale --reason "revision B issued"
out="$(tl link list --project P123 "$support")"
echo "$out"
expect "$out" "out  references  $third  stale  floating  $sid"
tl link repin --project P123 "$sid" --pin B
tl link verify --project P123 "$sid"
tl link retract --project P123 "$sid" --reason "superseded"
out="$(tl link suggest --project P123 "$third" "$ncr")"
did="$(head -1 <<<"$out" | cut -d' ' -f2)"
tl link decline --project P123 "$did" --reason "not related"
refuse "a declined suggestion" tl link suggest --project P123 "$third" "$ncr" | tee "$workdir/declined.txt"
expect "$(cat "$workdir/declined.txt")" 'was declined before'

step "tl link trace   (records reachable through links)"
out="$(tl link trace --project P123 "$ncr")"
echo "$out"
expect "$out" "^  references: $support  Weld map WM-12$"

step "every link and workflow change is an event"
out="$(tl events tail --project P123 -n 40)"
for kind in Link.Added Link.Suggested Link.Accepted Link.Flagged Link.Repinned Link.Verified \
  Link.Retracted Link.Declined Workflow.Transitioned Numbering.Allocated; do
  expect "$out" "$kind"
done
echo "ok: all ten event types present"

step "atomic edit: a form save is all or nothing (EditRecord, real services)"
edit="$(quiet uv run pytest tests/services/test_edit_record.py -q 2>&1 | tail -1)" || true
echo "$edit"
expect "$edit" '^12 passed'

step "TUI over the same services: links tab, picker, palette, tray, trace tab, workflow menu (snapshots)"
snaps="$(quiet uv run pytest packages/tl-tui/tests/test_snapshots_links.py -q 2>&1 | tail -1)" || true
echo "$snaps"
expect "$snaps" '^8 passed'

step "TUI screens against the fake client: tests of the P0-I3 widgets"
tui="$(quiet uv run pytest packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_link_picker.py \
  packages/tl-tui/tests/test_links_tab.py packages/tl-tui/tests/test_ref_tray.py \
  packages/tl-tui/tests/test_trace_tab.py packages/tl-tui/tests/test_workflow_menu.py -q 2>&1 | tail -1)" || true
echo "$tui"
expect "$tui" ' passed'
if grep -q failed <<<"$tui"; then echo "DEMO FAILED: $tui" >&2; exit 1; fi

printf '\nP0-I3 demo ok\n'
