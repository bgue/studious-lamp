# P2-PTW-T09 - Scan card for permits.Permit

Status: ready (written r4; base `p2/ip-r3`; PTW-T01 merged, QR-S1, QR-T03, QR-T04 merged; copies QR-T04)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality, scan-card, safety
Depends on: P2-PTW-T01 (`views`, `rules`), P2-QR-S1 (contract), P2-QR-T03 (harness), P2-QR-T04 (the pattern), all merged
Branch: `p2/ptw-t09-scan-card`
Worktree: `/home/user/wt/ptw/t09` (from `p2/ip-r3`)

## Goal
The permits module ships the status card of a permit: `tl_mod_permits.scan_card.provider()` returns a `ScanCardProvider` for `permits.Permit`, registered in the entry-point group `throughline.scan_cards`. A scan of a permit label shows whether work may go on. A pure read under the viewer: never writes, never raises for a bad id, answers `None` for a permit the viewer cannot read (hidden through its for-record), a record of another type and an id that is not a record.

## Rules (decided at r4)
- `record_type = "permits.Permit"` (`names.PERMIT`), `view_word = "permits.view"` (`names.VIEW`).
- Read as QR-T04 reads: inside `confidentiality.use_viewer(viewer)`, `is_hidden(conn, record_id, viewer)` first, one lookup of `scope` and `key` from `cur_core_record` (`type = :t`, `voided = :no` bound False), then `views.permit_detail(conn, scope, key, now=now, viewer=viewer)`; any `None` gives `None`. The shown state is the view's (`Lapsed` in place of `Active`, through `rules.effective_state`); the card never recomputes it, and reads no clock beyond the `now` it is given. No other SQL; no import of `tl_mod_qr`, `tl_api`, `tl_web`.
- Banner and tone from `d.row.state` (a safety card fails to the stop side):
  - `Active`: `ACTIVE until HH:MM UTC` from `valid_until` (the bare `ACTIVE` when it is unset), go.
  - `Lapsed`: `LAPSED - revalidate`, stop. `Suspended`: `SUSPENDED`, stop.
  - `Approved`: `APPROVED - not issued`, caution. `Requested`: `REQUESTED - not approved`, caution.
  - `Handed back`: `HANDED BACK`, neutral. `Closed`, `Rejected`, `Cancelled`: the state in capitals, neutral.
  - any other state: `NOT VALID`, stop.
- `valid_until = d.row.valid_until` for Active, Lapsed and Suspended, else `None`; `as_of = now`; `open_path = None`.
- Lines (label: value, cut to the bounds, a missing value left out, never "None"): `Type` (readable form of `permit_type`, e.g. `hot_work` -> `Hot work`), `Area`, `Holder`, `Location` (`location_text`), `For` (`for_key`), `Revalidated` (`<n> times`, only when n > 0). Gas-test and isolation lines ("last gas test and result", "isolations verified n/m" of the spec) are deferred: their views come with PTW-T02; do not read those tables here.

## Brief references (pasted)
> A provider is a pure read under the viewer's filter and answers `None` for a record the viewer cannot see. Permit card: `ACTIVE until 18:00` go, `LAPSED - revalidate` stop, `SUSPENDED` stop, `APPROVED - not issued` caution, `CLOSED` neutral; lines: type, area, holder, last gas test and result, isolations verified n/m, revalidated (qr-workface section 3).

## Interfaces (verbatim)
`packages/tl-core/src/tl_core/qr/types.py` (abridged to what a provider uses): `ScanLine(label, value)` (label <= 24, value <= 80), `ScanCard(record_type, key, title <= 120, banner <= 40, tone, as_of (aware), valid_until, lines (<= 8), open_path (starts with /web/ when set))`, `Tone = Literal["go", "caution", "stop", "neutral"]`, `SCAN_CARD_ENTRY_POINT = "throughline.scan_cards"`,
```python
class ScanCardProvider(Protocol):
    record_type: str
    view_word: str
    def card(self, conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None: ...
```
Finished pattern to copy (merged): `packages/tl-modules/awp/src/tl_mod_awp/scan_card.py`, its test `packages/tl-modules/awp/tests/test_scan_card.py`, its report `docs/reports/P2-QR/T04.md`.

`packages/tl-modules/permits/src/tl_mod_permits/views.py` (abridged): `PermitRow(id, key, subject, permit_type, state, area, holder, issued_at, valid_until, revalidation_count, closed_by, for_key)`; `PermitDetail(row, description, location_text, requested_by, needed_from, needed_until, approved_by, issued_by, precautions, suspend_reason, handback_note, reject_reason, cancel_reason, version)`; `permit_detail(conn, scope, number, *, now, viewer=LOWEST) -> PermitDetail | None`.
Entry point to add to `packages/tl-modules/permits/pyproject.toml` (a new table after the modules one; later tickets only append lines):
```
[project.entry-points."throughline.scan_cards"]
permits_permit = "tl_mod_permits.scan_card:provider"
```

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/scan_card.py` (the pattern), `packages/tl-core/src/tl_core/qr/types.py`, `tests/contract/scan_card_harness.py` (signature of `check_scan_card_contract`)
- `packages/tl-modules/permits/src/tl_mod_permits/views.py` (dataclasses and `permit_detail` signature only), `packages/tl-modules/permits/tests/permit_world.py` (`World.request`, `approved`, `active`, `issue`, `hidden_record`, `at`), `packages/tl-modules/permits/tests/test_permit_visibility.py` lines 1-30
- `packages/tl-modules/awp/tests/test_scan_card.py` (the test pattern; registry test over an injected `EntryPoint`)

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/scan_card.py` (create)
- `packages/tl-modules/permits/pyproject.toml` (the entry-point table above only)
- `packages/tl-modules/permits/tests/test_scan_card.py` (create)
- `docs/reports/P2-PTW/T09.md` (create)
A registry pin or count test that lists installed scan-card providers and breaks only because of this entry point is updated here and listed (rule 12).

## Tests to add (`test_scan_card.py`)
1. `check_scan_card_contract(provider(), conn, visible_id=<permit>, hidden_id=<permit for a restricted record>, privileged=<cleared viewer>, now=...)` passes.
2. Banner and tone for Requested, Approved, Active (with the `until` time), Lapsed (move `now` past `valid_until`: the card and `views.permit_detail` agree), Suspended, Handed back, Closed, Rejected, Cancelled; an Active card never shows go once `now` is past its end.
3. Lines within bounds, a missing for-record or area left out, no `None` text, no id in the card text; `Revalidated` only after a revalidation.
4. A voided record, a record of another type (an isolation, a gas test) and a made-up id give `None`.
5. The five readers see the card or `None` as the class says; a permit of a restricted for-record answers `None` to the lowest viewer.
6. `load_scan_cards()` from `tl_core.qr.registry` over an injected `EntryPoint("permits_permit", "tl_mod_permits.scan_card:provider", SCAN_CARD_ENTRY_POINT)` returns a provider for `permits.Permit`.

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-modules/permits/tests/test_scan_card.py
uv run ruff check packages/tl-modules/permits packages/tl-modules/permits/tests/test_scan_card.py
uv run pyright packages/tl-modules/permits packages/tl-modules/permits/tests/test_scan_card.py
just gate packages/tl-modules/permits/tests/test_scan_card.py tests/contract/test_scan_card_contract.py
```
Expected: clean on those paths; `gate: PASS`. No `just check` (the orchestrator runs it at DONE), no whole-repo pyright.

## Escalation triggers
The card needs a column or a view the module's views do not give; a hidden record cannot be made with the world's helper; the harness fails a rule the ticket does not explain; any change to `tl_core/qr/types.py` (frozen).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins updated outside Allowed paths. Commit subjects `P2-PTW-T09: ...` with the trailers the dispatch message names; no model names in committed text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
