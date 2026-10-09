# <ticket-id> — <title>

Status: draft | ready | in-progress | in-review | changes-requested | escalated | merged | abandoned
Tier: haiku
Labels: <adapter | core | tui | api | mcp | cli | docs | tests | schema>
Depends on: <ticket ids or —>
Branch: `p<n>/i<m>/t<nn>-<slug>`
Approver (schema tickets only): <human name>

## Goal
One paragraph: what exists after this ticket that did not before.

## Brief references (pasted)
> Paste the exact table rows or bullets. The implementer does not open the brief.

## Interfaces (verbatim from repo at the branch point)
```python
```

## Context (read these, nothing else)
- `path/one.py`
- `path/two.py`
may explore: (none)

## Allowed paths
- `packages/.../file.py` (create)
- `packages/.../tests/test_x.py` (create)

## Steps (optional)
1. …

## Acceptance
```
just check
uv run pytest packages/<pkg>/tests/test_x.py -q
```
Expected: all pass; `just check` reports no drift.

## Tests to add
- `packages/<pkg>/tests/test_x.py`: covers …

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: …

## Escalation triggers
- Stop and report *Blocked* if …

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
