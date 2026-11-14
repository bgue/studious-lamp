# P2-X1-T05 — OpenAPI baseline file, `just openapi-baseline`, step in `just check`

Status: ready (dispatch r3)
Tier: haiku
Kind: ticket
Review: full
Labels: api, tooling
Depends on: T04 (merged: `tl_schema.compat.diff_openapi`)
Branch: `p2/x1-t05-openapi-baseline`
Worktree: `/home/user/wt/x1/t05`

## Goal
A removed or renamed API field, a removed route, or a removed or re-statused error code fails `just check`. The baseline is a committed
file refreshed only as a release step.

## Brief references (pasted)
- Owner rule Q1 (2026-11-13): the baseline is refreshed only as a release step. A breaking change between releases needs an
  `APPROVALS.md` line naming what breaks and a note in `api-compat.md`. Removals are deprecated for at least one release first.
  Put this rule in the module docstring and in the failure message of the check (one sentence each).
- Additive changes pass without refreshing the baseline (a stale baseline is fine, as for `tl_schema.compat --check`).
- Error rows: `tl_api.errors.ERROR_TABLE` is a tuple of `ErrorSpec` with `.error` (code string) and `.status` (int); the OpenAPI document
  does not carry them. The baseline file stores them next to the document, so the S1 rows (`invalid_idempotency_key` 422,
  `idempotency_mismatch` 409, `idempotency_in_progress` 409) are in it. Breaking: a code removed, or its status changed. A new code is fine.

## Interfaces (verbatim)
```python
# tl_schema/compat.py (merged, T04)
def diff_openapi(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]: ...
# tl_api/openapi.py (existing)
def build_openapi() -> dict[str, Any]: ...
def main(argv: Sequence[str] | None = None) -> int:   # today handles [] and ["--check"]
# justfile (existing)
check:
    ...
    uv run python -m tl_api.openapi --check
    uv run python dev/tools/check_licences.py
```

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/openapi.py`
- `packages/tl-api/src/tl_api/errors.py` (lines 1-60 and 424-445 only)
- `packages/tl-schema/src/tl_schema/compat.py` (lines 148-225)
- `justfile` (lines 1-40)
- `packages/tl-schema/tests/test_compat_openapi.py` (style only)

## Allowed paths
- `packages/tl-api/src/tl_api/openapi.py` (add `--compat` and `--baseline` modes; keep `--check` and the no-arg mode)
- `packages/tl-api/tests/test_openapi_baseline.py` (new)
- `docs/reference/openapi.baseline.json` (new, generated)
- `justfile` (one recipe, one `check` line)

## Steps
1. Baseline format: `{"openapi": <document>, "errors": {"<code>": <status>, ...}}`, `json.dumps(indent=2, sort_keys=True)`, trailing newline.
2. `python -m tl_api.openapi --compat`: exit 1 and print one line per breaking change (from `diff_openapi` plus one line per removed or
   re-statused error code) then the rule sentence; exit 0 otherwise. A missing baseline file exits 1 with a one-line message.
3. `python -m tl_api.openapi --baseline`: write the file from the current document and `ERROR_TABLE`; refuse (exit 1, same lines) when
   the change is breaking, so a refresh never hides one. Add `just openapi-baseline` running it; add `uv run python -m tl_api.openapi --compat`
   to `check` after the `--check` line. Run it once to create the file and commit it.

## Acceptance
```
just check
just gate packages/tl-api/tests/test_openapi_baseline.py
```
Do not run any wider directory.

## Tests to add (`test_openapi_baseline.py`; call `main([...])` on copies in `tmp_path`, never write the repo baseline)
- The committed baseline passes `--compat` today.
- A scratch baseline with an extra response field that the current document lacks fails and names the path and field.
- A current document with an added optional field passes (monkeypatch `build_openapi`).
- A removed route fails; a removed error code fails; a changed status fails; a new error code passes.
- The committed baseline lists the three S1 error codes with 422, 409, 409.
- `--baseline` refuses a breaking change and leaves the file unchanged.

## Report requirements
Standard report. Quote the failure message for one removed field. Say the baseline size in KB.

## Escalation triggers
- Stop if `tl_api` cannot import `tl_schema.compat` without a new dependency.
- Stop if the baseline file is over 2 MB.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
