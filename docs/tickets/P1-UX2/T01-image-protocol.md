# P1-UX2-T01 — image_protocol: which inline-image protocol the terminal speaks

Status: ready
Tier: haiku
Labels: tui
Depends on: —
Branch: `p1/ux2-t01-image-protocol`
Review: full

## Goal
A pure function that reads an environment mapping and says which inline-image protocol to use for the page-1 preview
(`kitty`, `iterm2`, `sixel`) or `none`. It never queries the terminal and never imports an image library.

## Brief references (pasted)
> SCOPE §4: where the terminal can show images (kitty, iTerm2, WezTerm, Windows Terminal/sixel) the panel shows page 1 as
> a picture; elsewhere page count, size and title. Tests use the text fallback.
Rules, first match wins:
1. `TL_IMAGES` set: `off` or `none` -> `none`; `kitty`, `iterm2`, `sixel` -> that; any other value -> `none`.
2. `TERM` is `dumb`, or `TMUX` or `STY` is set (multiplexers swallow images) -> `none`.
3. `KITTY_WINDOW_ID` set, or `TERM == "xterm-kitty"`, or `TERM_PROGRAM == "ghostty"` -> `kitty`.
4. `TERM_PROGRAM` is `iTerm.app` or `WezTerm` -> `iterm2`.
5. `WT_SESSION` set (Windows Terminal), or `TERM` contains `sixel`, or `TERM` starts with `foot` or `mlterm` -> `sixel`.
6. otherwise `none`.

## Interfaces
```python
# packages/tl-tui/src/tl_tui/preview/terminal.py
from collections.abc import Mapping
from typing import Literal
ImageProtocol = Literal["kitty", "iterm2", "sixel", "none"]
def image_protocol(env: Mapping[str, str]) -> ImageProtocol: ...
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/text.py` (module style: docstring, `from __future__ import annotations`)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/preview/__init__.py` (create: one-line module docstring "Page-1 preview of files: terminal capability, rendering, cache.")
- `packages/tl-tui/src/tl_tui/preview/terminal.py` (create)
- `packages/tl-tui/tests/test_preview_terminal.py` (create: copy `docs/tickets/P1-UX2/provided/test_preview_terminal.py` byte for byte)
- `docs/reports/P1-UX2/T01.md` (create)

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_preview_terminal.py
```
Expected: gate PASS; `just check` clean. Module has a docstring and the function a one-line docstring.

## Tests to add
The provided file only.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- A provided test expectation disagrees with the rules above: stop, write *Blocked*.
