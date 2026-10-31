# P2-W0-OC-T2 — the record screen shows the offline class in technical mode

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: OC-T1 (`T04`; branch from its head, or from `p2/w0` once it is merged)
Branch: `p2/w0-t05-offline-row`

## Goal
The Details tab of any record shows one row `Offline class  Draft only: drafted offline, issued online` in the
**Technical details** section, in technical mode only. Plain mode shows nothing new (no word of offline until a node can be a
replica; Phase 3 adds the `◌` mark and `Online only`).

## Brief references (pasted)
> offline-classes spec 5.6: "The record screen's Details tab shows, in **technical mode only**, `Offline class  Draft only:
> drafted offline, issued online` (tui-layout: technical tier). Plain mode shows nothing until a node can be a replica."
> Supervisor decisions (this ticket only): the spec's path `details/technical.py` is the RFI renderer, not the generic one;
> the row is added in `details_for` (`details/__init__.py`) for every record type, after the renderer's rows, so no renderer
> changes; one read of `client.record_types()` per call, an error leaves the row out (a label that is missing never breaks the
> screen, as in `labels_load.py`); the row is `panel=False` (record screen only, not in a log's panel). Wording:
> `full` "Full: created and edited offline"; `draft_only` "Draft only: drafted offline, issued online"; `none` "None: online only".

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/details/__init__.py (existing)
TECHNICAL_SECTION = "Technical details"
@dataclass(frozen=True)
class DetailRow:
    label: str; value: str; technical: bool = False; section: str = ""; panel: bool = True; ...
def details_for(client: ClientInterface, project: str, record: dict[str, Any], labels: Labels, mode: DisplayMode) -> list[DetailRow]:
    ...  # ends: return [row for row in rows if mode.technical or not row.technical]
# packages/tl-tui/src/tl_tui/details/generic.py (existing)
def technical_rows(record: dict[str, Any]) -> list[DetailRow]:
    return [DetailRow("Key", _or_empty(record.get("key")), True, TECHNICAL_SECTION, False), ...]
# from OC-T1 (not yet in the tree if you branched from p2/w0 before it merged; read T04 for the contract)
ClientInterface.record_types(self) -> list[RecordTypeRow]    # tl_core.offline.RecordTypeRow: record_type, label, module, offline, drafting_commands
```
New, to write:
```python
# tl_tui/display.py
OFFLINE_WORDS: Final[Mapping[str, str]] = {"full": ..., "draft_only": ..., "none": ...}   # the wording above
def offline_words(offline: str) -> str       # OFFLINE_WORDS.get(offline, offline)
# tl_tui/details/generic.py
def offline_rows(client: ClientInterface, record_type: str) -> list[DetailRow]
    # [] when record_types() raises or has no row for record_type; else one DetailRow("Offline class", offline_words(...), True, TECHNICAL_SECTION, False)
```
In `details_for`: when `mode.technical`, append `offline_rows(client, str(record.get("type")))` to `rows` before the final filter.

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `.claude/skills/tui-layout/SKILL.md` (technical tier, property:value lines)
- `packages/tl-tui/src/tl_tui/details/__init__.py` (lines 36-105)
- `packages/tl-tui/src/tl_tui/details/generic.py`
- `packages/tl-tui/src/tl_tui/display.py` (lines 1-60 and 212-240: `DisplayMode`)
- `dev/accept/P2-W0/RM-S3.py` (lines 1-45: how a script imports the TUI fake `FakeClient`)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/display.py` (modify)
- `packages/tl-tui/src/tl_tui/details/generic.py` (modify)
- `packages/tl-tui/src/tl_tui/details/__init__.py` (modify)
- `dev/accept/P2-W0/OC-T2.py` (create)
- `docs/reports/P2-W0/OC-T2.md` (create)

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
`dev/accept/P2-W0/OC-T2.py` (exit 0, one `PASS <check>` line each; fake client from `packages/tl-tui/tests`; `Labels()`). Checks:
(a) for a record type of each class that has no renderer in `details._RENDERERS` (print the three chosen; `core.Record` is `full`),
`details_for(..., DisplayMode(technical=True))` has one `Offline class` row with the wording of its class, in `TECHNICAL_SECTION`;
(b) with `DisplayMode(technical=False)` no row has the label `Offline class`; (c) `rows_page(rows, technical=False)` text holds no
`offline` word (case-insensitive); (d) a client whose `record_types` raises leaves the other rows unchanged and raises nothing;
(e) the row is not in `rows_page(..., technical=True, panel=True)` (record screen only).
```
just check
uv run python dev/accept/P2-W0/OC-T2.py
```
Expected: `just check` clean; every check `PASS`, exit 0. Paste the last 10 lines of each.

## Tests to add
None here. The end run (TB) writes `packages/tl-tui/tests/test_details_offline_row.py`. Consequential pins (rule 12): a snapshot or test
outside Allowed paths that breaks only because technical mode now shows this row is listed in the report, not edited (tests are not run now).

## Report requirements
Standard report plus the two pasted outputs, a line that no pytest was run, and the list of existing tests/snapshots you expect to change.

## Escalation triggers
- Stop and report *Blocked* if `record_types` is not on `ClientInterface` (T04 not in your tree), or `details_for` is called per keystroke in a way that makes one extra read per call unsafe (say where).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
