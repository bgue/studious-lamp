# P2-W0-RM-S3-L — four low review findings of the module roles surfaces

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tui, cli
Depends on: RM-S3 (merged)
Branch: `p2/w0-t07-roles-lows`

## Goal
Four small fixes from the RM-S3 review. No new behaviour beyond them.

## Brief references (pasted)
> F1 `tl_tui/admin_text.py` `effective_line`: an empty value reads `—`, not `none` (tui-layout, empty values).
> F2 `effective_page`: a panel carries a one-line summary after the state (tui-layout, "Panels"): the facts joined by ` · `.
> F3 `widgets/admin_screen.py` `action_module_roles`: fail closed, a missing `is_admin` means not admin.
> F4 `tl_cli/admin_roles.py`: delete the two comment lines that describe the command template (they restate the code).

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/admin_text.py (existing, lines 159-163)
def effective_line(view: EffectiveRoleView) -> str:
    """``superuser (granted)`` or ``none``: the value of one module's property line."""
    if not view.roles:
        return "none"
# lines 166-180
def effective_page(display_name: str, views: Sequence[EffectiveRoleView]) -> Page:
    return Page(identity=display_name, state=state_line(role_state(views)), sections=(Section("Effective roles", ..., note="No modules."),))
# packages/tl-tui/src/tl_tui/widgets/admin_screen.py line ~294
if not getattr(self.app, "is_admin", True):
# packages/tl-cli/src/tl_cli/admin_roles.py lines 34-35
# Every command starts: admin = require_admin(ctx.obj); backend = backend_of(ctx). Service calls
# run inside `with service_errors():`. Do not catch service exceptions yourself.
# packages/tl-tui/src/tl_tui/layout.py
EMPTY = "—" is in tl_tui.layout (and tl_tui.text); join_facts(*facts) -> str drops empty facts and joins with " · "; Page(identity, state, sections, summary="")
```
Edits:
1. F1: `effective_line` returns `EMPTY` (import from `tl_tui.layout`, where `admin_text` already imports `Page`); fix the docstring.
2. F2: `effective_page` passes `summary=join_facts(f"{n} of {len(views)} modules" if views else "")` where `n` = number of views with roles (import `join_facts` from `tl_tui.layout`). The state line already says where the roles come from, so the summary says only the count.
3. F3: default `False`: `getattr(self.app, "is_admin", False)`.
4. F4: delete the two comment lines and the blank line that only separated them, nothing else.

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `.claude/skills/tui-layout/SKILL.md` (panels, empty values)
- the four places above
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/admin_text.py` (modify)
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py` (modify)
- `packages/tl-cli/src/tl_cli/admin_roles.py` (modify)
- `docs/reports/P2-W0/RM-S3-L.md` (create)

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
just check
uv run python dev/accept/P2-W0/RM-S3.py | tail -15
```
Expected: `just check` clean; the acceptance script still exits 0 (it does not pin `none`; if a PASS line changes because of F1/F2, name it in the report). Also run `grep -rn "effective_line\|\"none\"" packages/tl-tui/tests/test_admin_text.py packages/tl-tui/tests/test_admin_plain.py` and list any test line that pins the old text (do not edit tests; the end run's TA reads the list).

## Tests to add
None.

## Report requirements
Standard report plus the pasted outputs and the list of old-text pins.

## Escalation triggers
- Stop and report *Blocked* if `join_facts` or `EMPTY` cannot be imported without a cycle, or the acceptance script fails for a reason other than the wording.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
