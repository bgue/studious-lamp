# P2-QR-T04 - Scan card for awp.IWP

Status: ready (written r3; base `p2/ip-r3`; needs only the merged card contract and harness, QR-S1 and QR-T03)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, read, confidentiality, scan-card
Depends on: P2-QR-S1 (contract `tl_core/qr/types.py`, registry), P2-QR-T03 (harness `tests/contract/scan_card_harness.py`), both merged
Branch: `p2/qr-t04-awp-iwp-card`
Worktree: harness-created under `/home/user/wt/qr/t04` (from `p2/ip-r3`)

## Goal
The awp module ships the status card of an IWP: `tl_mod_awp.scan_card.provider()` returns a `ScanCardProvider` for `awp.IWP`, registered in the entry-point group `throughline.scan_cards`. A scan of an IWP label then shows the banner, key, title, as-of time and up to six lines. A pure read under the viewer: it never writes, never raises for a bad id, answers `None` for a record the viewer cannot read, a voided record, a record of another type and an id that is not a record.

## Rules (decided at r3)
- `record_type = "awp.IWP"`, `view_word = "awp.view"` (`schema/settings/access-words.yaml`).
- Read under the viewer: wrap the reads in `confidentiality.use_viewer(viewer)`; first `confidentiality.is_hidden(conn, record_id, viewer)` then one lookup of scope and key from `cur_core_record` (`type = 'awp.IWP'`, `voided = 0`); then `iwp_detail(conn, scope, key)` (it applies the viewer filter itself) and `readiness_of(conn, record_id)`. Any `None` gives `None`.
- Banner and tone by workflow state `d.state` (`names.IWP_*`):
  - `Issued` or `In progress`: `ISSUED`, go.
  - `On hold`: `ON HOLD`, stop.
  - `Closed`, `Field complete`, `Cancelled`, `Split`: the state in capitals, neutral.
  - any other state with an evaluation: `READY k/n`, `k` = checks in state `ok`, `n` = checks not `n_a`; tone go when `k == n` and `n > 0`, else caution.
  - any other state without an evaluation: the state in capitals, neutral.
- Lines (label: value; values cut to the contract bounds; a missing value is left out, never "None"): `Foreman`, `Window` (`planned_start` to `planned_finish`), `Readiness` (`k/n checks ok`, only with an evaluation), `Open constraints` (`open_constraints`), `Scope` (`scope_count` items), `CWP` (`cwp_number`).
- `as_of = now`; `valid_until = None`; `open_path = None` (no web record page for an IWP exists yet; the web has only the log `/web/p/{project}/iwps`). "Drawings stale n" of the spec is deferred: no cheap source exists; do not invent one.
- No SQL of your own beyond the one scope/key lookup; no import of `tl_mod_qr`, `tl_api` or `tl_web`.

## Brief references
> A provider is a pure read under the viewer's filter and answers `None` for a record the viewer cannot see. IWP card: `ISSUED` go, `ON HOLD` stop, `READY 6/7` caution; lines: foreman, window, readiness counts, open constraints (qr-workface section 3). Bounds: at most 8 lines, label 24, value 80, banner 40, title 120 characters; `ScanCard` refuses more.

## Interfaces (verbatim)
`packages/tl-core/src/tl_core/qr/types.py` (abridged to the parts a provider uses):
```python
SCAN_CARD_ENTRY_POINT = "throughline.scan_cards"
Tone = Literal["go", "caution", "stop", "neutral"]

class ScanLine(BaseModel):  # extra="forbid"
    label: str = Field(max_length=MAX_LABEL_CHARS)
    value: str = Field(max_length=MAX_VALUE_CHARS)

class ScanCard(BaseModel):  # extra="forbid"
    record_type: str
    key: str
    title: str = Field(max_length=MAX_TITLE_CHARS)
    banner: str = Field(max_length=MAX_BANNER_CHARS)
    tone: Tone
    as_of: datetime  # must be timezone aware
    valid_until: datetime | None = None
    lines: list[ScanLine] = Field(default_factory=list[ScanLine], max_length=MAX_LINES)
    open_path: str | None = None  # must start with /web/ when set

@runtime_checkable
class ScanCardProvider(Protocol):
    record_type: str
    view_word: str
    def card(
        self, conn: Connection, record_id: str, viewer: Viewer, now: datetime
    ) -> ScanCard | None: ...
```
`packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py` (abridged):
```python
class IwpRow(BaseModel):  # id, number, title, state, discipline, planned_start, planned_finish,
    foreman: str | None   # foreman, estimated_hours, cwp_number, scope_count: int
class IwpDetail(IwpRow):  # crew_text, signoffs, pin_count, open_constraints: int, scope_by_type
def iwp_detail(conn: Connection, scope: str, number: str) -> IwpDetail | None:
    """None for a missing, hidden or voided IWP (the same answer for each)."""
```
`packages/tl-modules/awp/src/tl_mod_awp/readiness/views.py` (abridged):
```python
class ReadinessView(BaseModel):  # iwp_id, evaluated_at, today, ready: bool, facts_hash,
    checks: list[CheckResult]    # CheckResult.state in "ok" | "blocked" | "pending" | "n_a" | "unknown"
def readiness_of(conn: Connection, iwp_id: str) -> ReadinessView | None:
    """None when it was never evaluated."""
```
Entry point to add to `packages/tl-modules/awp/pyproject.toml` (a new table; later tickets only append lines, never reorder):
```
[project.entry-points."throughline.scan_cards"]
awp_iwp = "tl_mod_awp.scan_card:provider"
```

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/qr/types.py`, `tests/contract/scan_card_harness.py` (signature of `check_scan_card_contract`)
- `packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py`, `packages/tl-modules/awp/src/tl_mod_awp/readiness/views.py`
- `packages/tl-modules/awp/tests/awp_world.py` (`World.iwp`, `hidden_record`), `packages/tl-modules/awp/tests/test_five_readers.py` lines 30-110 (the test-only confidential source that gives awp records a class; copy the pattern for a hidden IWP)
- `packages/tl-modules/awp/tests/test_iwp_signoff.py` lines 26-50 (how a test makes, signs and issues an IWP)

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/scan_card.py` (create)
- `packages/tl-modules/awp/pyproject.toml` (the entry-point table above only)
- `packages/tl-modules/awp/tests/test_scan_card.py` (create)
- `docs/reports/P2-QR/T04.md` (create)
A registry pin or count test that lists the installed scan-card providers and breaks only because of this entry point is updated in this ticket and listed in the report (rule 12); anything else outside the paths stops.

## Tests to add (`packages/tl-modules/awp/tests/test_scan_card.py`)
1. `check_scan_card_contract(provider(), conn, visible_id=<IWP>, hidden_id=<hidden IWP>, privileged=<viewer who reads it>, now=...)` passes (hidden IWP by the test-only confidential source pattern).
2. Banner and tone for a Draft IWP with no evaluation (`DRAFT`, neutral), an Issued one (`ISSUED`, go) and an On hold one (`ON HOLD`, stop; move it with the hold rule or by `set_status` as the awp tests do).
3. `READY k/n` with caution: store an evaluation through the readiness engine as the awp readiness tests do, or insert the check rows the way `tests/readiness` does; one case k < n (caution) and one k == n (go).
4. Lines are within the bounds, a missing foreman is left out, and the card text holds no id.
5. A voided IWP, a record of another type and a made-up id give `None`; the five readers (`READERS` of `test_five_readers.py`) see the card or `None` as the class says; an agent with no account sees `None` of the hidden IWP.
6. `load_scan_cards()` from `tl_core.qr.registry` over an injected `EntryPoint("awp_iwp", "tl_mod_awp.scan_card:provider", SCAN_CARD_ENTRY_POINT)` returns a provider for `awp.IWP` (no reinstall needed).

## Acceptance
```
just check
just gate packages/tl-modules/awp/tests/test_scan_card.py tests/contract/test_scan_card_contract.py
```
Expected: `just check` exit 0; `gate: PASS`.

## Escalation triggers
The card needs a column or a view the awp views do not give; a hidden IWP cannot be made with the pattern above; the harness fails a rule the ticket does not explain; any change to `tl_core/qr/types.py` (frozen).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list pins updated outside Allowed paths. Commit subjects `P2-QR-T04: ...` with the session trailers; no model names in committed text.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
