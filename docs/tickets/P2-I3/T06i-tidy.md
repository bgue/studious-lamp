# P2-I3-T06i — Tidy-up: receipt entry cursor and KEYS style; an amber note line in the layout

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06b, T06e (merged); decisions Q9 = YES (amber note), D47
Branch: `p2/i3-t06i-tidy`   (from p2/i3; check `git rev-list --left-right --count p2/i3...HEAD` is `0 0`)

## Goal
Three small leftovers, one ticket (rule 12, coherent: they touch the same two screens and the layout):
1. In `ReceiptEntryScreen`, after `Delete` removes a line the cursor jumps to row 0. It must stay on the row that was removed (the next line moves up under it), or on the new last row when the last line went. An empty list has no cursor.
2. The keys row of the entry screen mixes two styles. Every other module's keys row is `<key> <lowercase verb>` (`o open only  m missing MTR  / filter  F5 reload  Esc close`). `KEYS` becomes
   `Ctrl+S save  Enter add line  Del remove line  Esc close` (the key is still `Delete`; the row names it `Del`). Update the pinned text in `dev/accept/P2-I3/T06e.py` and the Receipt entry bullet of `text-contracts.md`.
3. Layout: a styled note line, so the receipt's `MTR required to accept` is amber (D39 asked for amber, T06b shipped it plain, Q9). Add to `layout.py` an item type `Note(text, style=WAITING_STYLE)` (a one-line prose item that carries a style; a plain `str` has none), draw it in `_section_lines`, and use it in `receipt_text.py` for `MTR_NOTE`.

## Brief references (pasted)
> Layout skill `tui-layout`: state colour is green done, amber waiting, red overdue or refused; `layout.WAITING_STYLE = "yellow"`. A section `note` shows only when a section has no items and stays plain.
> D39: the MTR line is a plain-prose item before the Files table, no fake row; the section note `No files` is unchanged.

## Interfaces (verbatim from repo at the branch point)
```python
# layout.py
Item = Prop | str | TableRow  # a str is a line of prose or a list entry, printed as it is
@dataclass(frozen=True)
class Section:
    heading: str
    items: tuple[Item, ...] = ()
    note: str = ""
# _section_lines(section, width): `else:` branch handles a str item:
#     flush(); for text in item.split("\n"): lines.extend([(part, "")] for part in wrap_words(text, width))
# receipt_text.py:  MTR_NOTE = "MTR required to accept"   used at items.append(MTR_NOTE) in the Files section
# widgets/receipt_entry.py
def action_remove_line(self) -> None:   # del self.lines[table.cursor_row]; self._refresh_lines()
def _refresh_lines(self) -> None:       # table.clear(); add rows; table.move_cursor(row=min(table.cursor_row or 0, len(self.lines)-1))  <- cursor_row is 0 after clear()
```
New in `layout.py` (names are the contract; the web twin reads them):
```python
@dataclass(frozen=True)
class Note:
    """One line of prose with a style (an amber ``MTR required to accept``); a plain ``str`` has none."""
    text: str
    style: str = WAITING_STYLE
Item = Prop | str | TableRow | Note
```
`_section_lines`: a `Note` flushes props and table like a `str`, wraps like a `str` (`wrap_words`), and draws each part with `item.style`. `limited(...)`, `group_items(...)` need no change beyond the type.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/layout.py` (Item, Section, `_section_lines`, `WAITING_STYLE`)
- `packages/tl-tui/src/tl_tui/receipt_text.py` (`MTR_NOTE`, the Files section builder)
- `packages/tl-tui/src/tl_tui/widgets/receipt_entry.py` (`action_remove_line`, `_refresh_lines`) and `receipt_entry_text.py` (`KEYS`)
- `dev/accept/P2-I3/T06e.py`, `T06b.py` (copy their helpers; edit only the lines that pin the changed facts)
may explore: any place that iterates `section.items` (grep); if pyright flags a consumer of `Item`, handle `Note` there in the same way as `str` and list it.

## Allowed paths
- `packages/tl-tui/src/tl_tui/layout.py`, `receipt_text.py`, `receipt_entry_text.py`, `widgets/receipt_entry.py`
- `dev/accept/P2-I3/T06e.py`, `dev/accept/P2-I3/T06b.py` (consequential pins, rule 12; list them)
- `docs/tickets/P2-I3/text-contracts.md` (the Receipt entry bullet only), `docs/reports/P2-I3/T06i.md` (create)
No test file (T11). No new dependency.

## Acceptance (run once; no pytest)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
uv run python dev/accept/P2-I3/S3.py --keep .accept/p2-i3.db
just check
uv run python dev/accept/P2-I3/T06e.py
uv run python dev/accept/P2-I3/T06b.py
uv run python dev/accept/P2-I3/T06c.py
```
Expected, exit 0 each. Extend `T06e.py` (one `PASS` line each): add three lines, move to line 2, `Delete`: the table has 2 rows and the cursor is on row 1 (the old line 3); `Delete` again then on the last row: the cursor is on the new last row; the keys row reads `Ctrl+S save  Enter add line  Del remove line  Esc close` (grep the SVG for `Del&#160;remove&#160;line`). Extend `T06b.py`: for a receipt that needs its MTR and has none, the Files section's first item is a `Note` whose style is `layout.WAITING_STYLE`, and the rendered lines carry that style on `MTR required to accept`; a receipt with the MTR attached has no Note; the section note `No files` is still plain.

## Tests to add
None (T11).

## Report requirements
Standard report (`docs/templates/haiku-report.md`, ≤ 60 lines) plus: the pins you changed, and the output of each acceptance command (≤ 5 lines each). The expected diff is small; more than 7 files means stop and say why.
Commit subjects `P2-I3-T06i: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report *Blocked* if a consumer of `Item` outside `tl_tui` breaks, or a snapshot under `packages/tl-tui/tests/__snapshots__` changes (the web twin and T11 own those).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
