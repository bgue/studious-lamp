# P2-INSP-T09 - Scan card for quality.Inspection

Status: ready (written r4; base `p2/ip-r3`; INSP-T01 merged, QR-S1, QR-T03, QR-T04 merged; copies QR-T04)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality, scan-card
Depends on: P2-INSP-T01 (`insp_views`), P2-QR-S1 (contract), P2-QR-T03 (harness), P2-QR-T04 (the pattern), all merged
Branch: `p2/insp-t09-scan-card`
Worktree: `/home/user/wt/insp/t09` (from `p2/ip-r3`)

## Goal
The quality module ships the status card of an inspection: `tl_mod_quality.scan_card.provider()` returns a `ScanCardProvider` for `quality.Inspection`, registered in the entry-point group `throughline.scan_cards`. A pure read under the viewer: it never writes, never raises for a bad id, answers `None` for an inspection the viewer cannot read (hidden through its subject), a record of another type and an id that is not a record.

## Rules (decided at r4)
- `record_type = "quality.Inspection"` (`names.INSPECTION`), `view_word = "quality.view"`.
- Read as QR-T04 reads: inside `confidentiality.use_viewer(viewer)`, `is_hidden(conn, record_id, viewer)` first, one lookup of `scope` and `key` from `cur_core_record` (`type = :t`, `voided = :no` bound False), then `insp_views.inspection_detail(conn, scope, key, viewer=viewer)`; any `None` gives `None`. No other SQL; no import of `tl_mod_qr`, `tl_api`, `tl_web`.
- Banner and tone from `d.row.state`, `d.row.point`, `d.row.result` (`names.PLANNED`, `SCHEDULED`, `DONE`, `VERIFIED`, `CANCELLED`; results `accept`, `reject`, `conditional`):
  - `Cancelled`: `CANCELLED`, neutral.
  - `Planned` or `Scheduled` with point `hold`: `HOLD POINT - not released`, stop.
  - `Scheduled`: `SCHEDULED <d Mon>` from `scheduled_for` (e.g. `SCHEDULED 18 Nov`; the bare word when it is unset), neutral. `Planned`: `PLANNED`, neutral.
  - `Done`: result `accept` is `DONE - to verify`, caution; `reject` is `REJECTED`, stop; `conditional` is `CONDITIONAL`, caution.
  - `Verified`: `accept` is `ACCEPTED`, go; `reject` is `REJECTED`, stop; `conditional` is `CONDITIONAL`, caution.
  - any other combination: the state in capitals, neutral.
- Lines (label: value, cut to the bounds, a missing value left out, never "None"): `Point`, `Checklist` (`<key> v<version>` from `checklist_key`, `checklist_version`), `Inspector`, `Area`, `For` (`for_key`), `Subject` (`subject_key`), `Punch items` (`punch_count` raised; only when > 0). At most 7 lines.
- `as_of = now`; `valid_until = None`; `open_path = None` (no web record page for an inspection exists).

## Brief references (pasted)
> A provider is a pure read under the viewer's filter and answers `None` for a record the viewer cannot see. Inspection card: `SCHEDULED 18 Nov` neutral, `ACCEPTED` go, `REJECTED` stop, `HOLD POINT - not released` stop; lines: point, checklist, inspector, open punch items, for IWP (qr-workface section 3).

## Interfaces (verbatim)
`packages/tl-core/src/tl_core/qr/types.py` (abridged to what a provider uses): `ScanLine(label, value)` (label <= 24, value <= 80), `ScanCard(record_type, key, title <= 120, banner <= 40, tone, as_of (aware), valid_until, lines (<= 8), open_path (starts with /web/ when set))`, `Tone = Literal["go", "caution", "stop", "neutral"]`, `SCAN_CARD_ENTRY_POINT = "throughline.scan_cards"`,
```python
class ScanCardProvider(Protocol):
    record_type: str
    view_word: str
    def card(self, conn: Connection, record_id: str, viewer: Viewer, now: datetime) -> ScanCard | None: ...
```
Finished pattern to copy (merged): `packages/tl-modules/awp/src/tl_mod_awp/scan_card.py`, its test `packages/tl-modules/awp/tests/test_scan_card.py`, its report `docs/reports/P2-QR/T04.md`.

`packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` (abridged): `InspectionRow(id, key, title, subject_key, for_key, state, point, area, planned_on, scheduled_for, inspector, result, done_on, punch_count)`; `InspectionDetail(row, checklist_key, checklist_version, answers, note, done_at, recorded_by, verified_by, verified_on, reinspection_of_key, cancel_reason, punch_keys, version)`; `inspection_detail(conn, scope, key, *, viewer=LOWEST) -> InspectionDetail | None`.
Entry point to add to `packages/tl-modules/quality/pyproject.toml` (a new table after the modules one; later tickets only append lines):
```
[project.entry-points."throughline.scan_cards"]
quality_inspection = "tl_mod_quality.scan_card:provider"
```

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/scan_card.py` (the pattern), `packages/tl-core/src/tl_core/qr/types.py`, `tests/contract/scan_card_harness.py` (signature of `check_scan_card_contract`)
- `packages/tl-modules/quality/src/tl_mod_quality/insp_views.py` (dataclasses and `inspection_detail` only), `packages/tl-modules/quality/tests/insp_world.py` (`InspWorld.plan`, `scheduled`, `recorded`, `hidden_record`), `packages/tl-modules/quality/tests/test_insp_visibility.py` lines 1-40 (how a hidden inspection is made)
- `packages/tl-modules/awp/tests/test_scan_card.py` (the test pattern; registry test over an injected `EntryPoint`)

## Allowed paths
- `packages/tl-modules/quality/src/tl_mod_quality/scan_card.py` (create)
- `packages/tl-modules/quality/pyproject.toml` (the entry-point table above only)
- `packages/tl-modules/quality/tests/test_insp_scan_card.py` (create)
- `docs/reports/P2-INSP/T09.md` (create)
A registry pin or count test that lists installed scan-card providers and breaks only because of this entry point is updated here and listed (rule 12).

## Tests to add (`test_insp_scan_card.py`)
1. `check_scan_card_contract(provider(), conn, visible_id=<inspection>, hidden_id=<inspection of a restricted subject>, privileged=<cleared viewer>, now=...)` passes.
2. Banner and tone for each row of the Rules list: Planned (neutral), Scheduled with hold point (stop), Scheduled with a date (`SCHEDULED 18 Nov`), Done-accept, Done-reject, Done-conditional, Verified-accept (go), Verified-reject, Cancelled. Walk the real commands of `InspWorld` (as T04's report advises: `set_status` does not move the workflow state).
3. Lines within bounds, a missing inspector or area left out, no `None` text, no id in the card text; `Punch items` only after a failed answer raised one.
4. A voided record, a record of another type (a punch item, a checklist) and a made-up id give `None`.
5. The five readers (as the quality visibility tests name them) see the card or `None` as the class says.
6. `load_scan_cards()` from `tl_core.qr.registry` over an injected `EntryPoint("quality_inspection", "tl_mod_quality.scan_card:provider", SCAN_CARD_ENTRY_POINT)` returns a provider for `quality.Inspection`.

## Acceptance
```
uv run ruff format --check packages/tl-modules/quality packages/tl-modules/quality/tests/test_insp_scan_card.py
uv run ruff check packages/tl-modules/quality packages/tl-modules/quality/tests/test_insp_scan_card.py
uv run pyright packages/tl-modules/quality packages/tl-modules/quality/tests/test_insp_scan_card.py
just gate packages/tl-modules/quality/tests/test_insp_scan_card.py tests/contract/test_scan_card_contract.py
```
Expected: clean on those paths; `gate: PASS`. No `just check` (the orchestrator runs it at DONE), no whole-repo pyright.

## Escalation triggers
The card needs a column or a view the module's views do not give; a hidden record cannot be made with the world's helper; the harness fails a rule the ticket does not explain; any change to `tl_core/qr/types.py` (frozen).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins updated outside Allowed paths. Commit subjects `P2-INSP-T09: ...` with the trailers the dispatch message names; no model names in committed text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
