# P2-QR-T02 — Label renderer: URL, code groups and one printable HTML page

Status: ready (dispatch after QR S1 is merged to `p2/ip`; the provided test is committed)
Tier: haiku
Kind: ticket
Review: lite
Labels: core-module, tests
Depends on: S1 (merged: the package `packages/tl-modules/qr` exists)
Branch: `p2/qr-t02-labels`
Worktree: harness-created under `/home/user/wt/qr/t02` (from `p2/ip` head)

## Goal
`tl_mod_qr.labels` turns a base address, a code and a short text into one printable HTML page with the QR drawn as
inline SVG. Pure: no database, no network, no clock. The QR library `segno` is optional (the `labels` extra of
`tl-mod-qr`); without it `make_svg` answers `None` and the page carries a fixed note. Only the `tag` size is built.

## Brief references (pasted)
> The QR holds exactly `<api.public_base_url>/web/q/<code>`. The code is 16 characters `[A-Z0-9]`, printed under the
> QR in four groups (`7KQ2-M9XA-4TTC-P0HV`) so it can be typed. A label never prints state, and never prints the URL
> or the run-together code. Text beside the QR is at most 40 characters. `tag` is 50 x 80 mm. The page is
> script-free and loads nothing from outside. Base address pattern (the setting's):
> `^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$|^http://(localhost|127\.0\.0\.1)(:[0-9]{1,5})?$` (empty is refused here).

## Interfaces (final; create exactly these names in `labels.py`)
```python
LABEL_SIZES: dict[str, tuple[int, int]] = {"tag": (50, 80)}   # millimetres, width x height
NO_QR_NOTE: str   # a fixed sentence: the QR library is not installed, install the `labels` extra; no label was drawn
class LabelError(ValueError): ...
def format_code(code: str) -> str                              # "7KQ2M9XA4TTCP0HV" -> "7KQ2-M9XA-4TTC-P0HV"; LabelError unless ^[A-Z0-9]{16}$
def label_url(base_url: str, code: str) -> str                 # f"{base_url}/web/q/{code}"; LabelError for a bad base or code
def make_svg(url: str) -> str | None                           # lazy `import segno`; None on ImportError; else segno.make(url, error="q").svg_inline(scale=4, border=2)
def render_label(*, code: str, text: str | None, size: str = "tag", svg: str | None) -> str
```
`render_label`: `<!doctype html>`; one `<style>` block with `@page { size: <w>mm <h>mm; margin: 0 }`; the SVG when given,
else `NO_QR_NOTE`; the grouped code; the text in an element with `class="text"` only when text is given (escaped with
`html.escape`; more than 40 characters is a `LabelError`). Sizes `card` and `sheet` raise `LabelError` whose message
contains "not available"; any other size raises `LabelError`. No `<script>`, `src=`, `href=`, `<img>`, `<link>`,
`url(`, `@import` or absolute URL in the output.

## Context (read these, nothing else)
- `docs/tickets/P2-QR/provided/T02_test_labels.py` (the test; copy it byte-identical)
- `packages/tl-modules/qr/pyproject.toml`
may explore: (none)

## Allowed paths
- `packages/tl-modules/qr/src/tl_mod_qr/labels.py` (create)
- `packages/tl-modules/qr/tests/test_labels.py` (create: a byte-identical copy of the provided test)
- `docs/reports/P2-QR/T02.md` (create)

## Acceptance
```
just check
just gate packages/tl-modules/qr/tests/test_labels.py
```
Expected: all pass, `gate: PASS`. No dependency is added (`segno` stays an optional extra declared by S1).

## Tests to add
The provided test only; copy it, change nothing.

## Report requirements
Standard report (`docs/templates/haiku-report.md`); first line says whether the test copy is byte-identical (phrase 101).

## Escalation triggers
- Stop and report *Blocked* if `packages/tl-modules/qr` is missing or the S1 extra `labels` is not declared.
- Stop if a pattern in the ticket disagrees with `schema/settings/platform.yaml` `api.public_base_url`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
