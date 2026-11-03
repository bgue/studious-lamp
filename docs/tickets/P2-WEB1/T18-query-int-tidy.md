# P2-WEB1-T18 — oversized digit strings in ?version= and ?depth=

Status: ready (r9)
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: T16, T10 (both merged)
Branch: `p2/web1-t18-query-int`

## Goal
`GET /web/p/{project}/path?version=<5000 digits>` answers 500 (T16 review F1, LO): `str.isdigit()` is true, `int()` then raises `ValueError` (Python's 4300-digit limit). `wbs.py` `_depth` has the same shape (`?depth=<5000 digits>`). After this ticket a digit string longer than 9 characters is "absent" in both, like any other bad value: the current version, the unfiltered tree.

## Pins
1. `pages/path.py::_version`: accept only `raw.isascii() and raw.isdigit() and len(raw) <= 9`, then `int(raw) >= 1`; else `None`. Same one-line guard in `pages/wbs.py::_depth` (`len(raw) <= 9` before `int`). No other behaviour changes (`?version=99` stays the one 404, `?version=0` stays absent).
2. Do not touch `record_trace.py` or `record_thread.py` (they catch `ValueError` already) nor any other page.
3. Tests: in `test_web_path_log.py` add `"9" * 5000` and `"0" * 5000` to the parametrisation of `test_a_bad_version_is_the_current_version` (or a twin test of the same shape); in `test_web_wbs_log.py` add `"9" * 5000` to the bad-depth cases (`test_a_bad_depth_is_as_if_absent`). Each asserts 200 and the same rows as the absent query.

## Context (read these, nothing else)
- `packages/tl-web/src/tl_web/pages/path.py` (`_version`), `packages/tl-web/src/tl_web/pages/wbs.py` (`_depth`)
- `packages/tl-web/tests/test_web_path_log.py` (the bad-version test), `packages/tl-web/tests/test_web_wbs_log.py` (the bad-depth test)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/path.py`
- `packages/tl-web/src/tl_web/pages/wbs.py`
- `packages/tl-web/tests/test_web_path_log.py`
- `packages/tl-web/tests/test_web_wbs_log.py`
- `docs/reports/P2-WEB1/T18.md` (create)

## Acceptance (once; do not run `just gate`)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run pytest packages/tl-web/tests/test_web_path_log.py packages/tl-web/tests/test_web_wbs_log.py -q
```
Paste the last 5 lines of each. Report `docs/reports/P2-WEB1/T18.md`, at most 30 lines, deviations first. Commit subject `P2-WEB1-T18: ...`, no model names in any file; end the message with the attribution trailer the harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer.

## Escalation triggers
- *Blocked* if another page reads a query integer without a guard (name the file and line in the report; do not fix it).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
