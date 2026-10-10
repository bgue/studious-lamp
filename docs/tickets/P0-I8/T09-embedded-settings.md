# P0-I8-T09 — The embedded TUI client serves settings

Status: merged
Tier: haiku
Labels: tui
Depends on: — (the contract in `tl_tui/client.py`, the fake and the remote pass-through are on the base)
Branch: `p0/i8a-t09-embedded-settings`

## Goal
The TUI in embedded mode can read and change settings: the seven settings methods of `EmbeddedClient` (`list_settings`, `get_setting`, `setting_history`, `set_setting`, `reset_setting`, `lock_setting`, `revert_setting`) call `tl_core.settings` in a unit of work, recording the client's actor with source `tui`. The constructor, `for_sqlite` and `main.py` already carry the `actor`; the seven bodies raise `NotImplementedError`. A provided test file (10 tests) must pass; the last of them runs the same script on the real client and on `FakeClient` and compares the answers.

## Brief references (pasted)
> **30.2 Layers and resolution.** `platform default -> company -> project -> user (UI keys only)`. The **effective value** shows its origin. Values set at the current scope are marked ● (like about:config's "modified"). A company can **lock** a key, so projects cannot override it, or constrain the range projects may use.
> **30.3 Change control.** Every change is a `Setting.Changed` event: old value, new value, actor, reason (required for `advanced` and `dangerous` keys), and effective time. **Scheduled changes** take effect at a future time. **Dangerous keys** need explicit confirmation ("I accept the risk"). Changes apply live. Full per-key history, with revert.
> **30.4 Interfaces.** CLI: `tl config get | set | reset | lock | diff | export | import`. API: `/settings` endpoints. MCP: `get_settings` (read), `propose_setting_change` (draft for human approval). Export/import as YAML for templates and reviews.
> **4** Screens use one client interface; the embedded implementation calls the services in process and the remote one calls the API; there is no logic in the client beyond that.

### Specification
Follow the other methods of the class: open the unit of work with `self._uow(readonly)`, make one service call, return its answer. Reads use `self._uow(True)`, writes `self._uow(False)`. A write answers with the key as seen at the layer it changed: call `view_at(uow.conn(), key, layer)` inside the same `with` block, after the service call. `lock_setting` answers with `view_at(uow.conn(), key, "company")`. Do not catch exceptions: the screens handle the service exceptions. Do not call `self.own_writes.note` (settings changes are not records).

The names `settings_history`, `lock_in_force`, `reset_in_force`, `revert_in_force`, `set_in_force`, `get_view`, `list_views` and `view_at` are the import aliases listed below (the service functions share their names with the client methods).

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I8/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I8/<ticket-id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring and from every docstring or comment you fill in.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py` (it shadows the standard library); run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. The base is green: if a test outside your Allowed paths fails, report it under *Blocked* with the output.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/embedded.py (the seven stubs you complete)
    # --- settings (P0-I8) ---------------------------------------------------------------------

    def list_settings(
        self,
        *,
        project: str | None = None,
        user: str | None = None,
        prefix: str | None = None,
        modified_only: bool = False,
    ) -> list[SettingView]:
        """STUB (P0-I8-T09): remove this paragraph when you implement the body.

        ``list_views(uow.conn(), project=, user=, prefix=, modified_only=)`` in a
        read-only unit of work.
        """
        raise NotImplementedError("STUB: P0-I8-T09")

    def get_setting(
        self, key: str, *, project: str | None = None, user: str | None = None
    ) -> SettingView:
        """STUB (P0-I8-T09): remove this paragraph when you implement the body.

        ``get_view(uow.conn(), key, project=, user=)`` in a read-only unit of work.
        """
        raise NotImplementedError("STUB: P0-I8-T09")

    def setting_history(self, key: str, *, layer: str | None = None) -> list[SettingChange]:
        """STUB (P0-I8-T09): remove this paragraph when you implement the body.

        ``settings_history(uow.conn(), key, layer=layer)`` in a read-only unit of work.
        """
        raise NotImplementedError("STUB: P0-I8-T09")

    def set_setting(
        self,
        key: str,
        *,
        layer: str,
        value: Any,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        """STUB (P0-I8-T09): remove this paragraph when you implement the body.

        One writable unit of work: ``set_in_force(uow, key=, layer=, value=,
        actor=self.actor, source=SOURCE, reason=, accept_risk=, applies_at=)``, then
        ``view_at(uow.conn(), key, layer)`` (still inside the unit of work) is the answer.
        """
        raise NotImplementedError("STUB: P0-I8-T09")

    def reset_setting(
        self,
        key: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        """STUB (P0-I8-T09): remove this paragraph when you implement the body.

        As ``set_setting`` with ``reset_in_force`` (no value).
        """
        raise NotImplementedError("STUB: P0-I8-T09")

    def lock_setting(
        self,
        key: str,
        *,
        locked: bool,
        reason: str,
        bounds: dict[str, Any] | None = None,
    ) -> SettingView:
        """STUB (P0-I8-T09): remove this paragraph when you implement the body.

        As ``set_setting`` with ``lock_in_force(uow, key=, locked=, bounds=, actor=,
        source=, reason=)``; the answer is ``view_at(uow.conn(), key, "company")``.
        """
        raise NotImplementedError("STUB: P0-I8-T09")

    def revert_setting(
        self,
        key: str,
        *,
        layer: str,
        seq: int,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> SettingView:
        """STUB (P0-I8-T09): remove this paragraph when you implement the body.

        As ``set_setting`` with ``revert_in_force(uow, key=, layer=, seq=, actor=,
        source=, reason=, accept_risk=)``.
        """
        raise NotImplementedError("STUB: P0-I8-T09")
```
```python
# imports to add to embedded.py (the stub's autofix removed them):
from tl_core.settings import history as settings_history
from tl_core.settings import lock_setting as lock_in_force
from tl_core.settings import reset_setting as reset_in_force
from tl_core.settings import revert_setting as revert_in_force
from tl_core.settings import set_setting as set_in_force
from tl_core.settings.views import get_view, list_views, view_at
# history(conn, key, *, layer=None) -> list[SettingChange]
# set_setting(uow, *, key, layer, value, actor, source, reason=None, accept_risk=False, applies_at=None)
# reset_setting(uow, *, key, layer, actor, source, reason=None, accept_risk=False, applies_at=None)
# lock_setting(uow, *, key, locked, bounds, actor, source, reason)
# revert_setting(uow, *, key, layer, seq, actor, source, reason=None, accept_risk=False)
# list_views(conn, *, project=None, user=None, prefix=None, modified_only=False) -> list[SettingView]
# get_view(conn, key, *, project=None, user=None) -> SettingView
# view_at(conn, key, layer) -> SettingView
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-tui/src/tl_tui/embedded.py`
- `packages/tl-tui/src/tl_tui/client.py` (the contract; read only)
- `docs/tickets/P0-I8/provided/t09-test_embedded_settings.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/embedded.py` (edit: the seven bodies and the imports)
- `packages/tl-tui/tests/test_embedded_settings.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I8/P0-I8-T09.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I8/provided/t09-test_embedded_settings.py.txt packages/tl-tui/tests/test_embedded_settings.py`
2. Implement the seven methods; delete the STUB paragraphs; add the imports.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-tui/tests/test_embedded_settings.py packages/tl-tui/tests/test_fakes_settings.py -q
uv run pytest packages/tl-tui -q
just check
```
Expected: 10 tests pass; the whole TUI package stays green (the snapshot tests need no update); `just check` clean.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo, or if the parity test fails because the fake (not your code) differs: say how.

## Blocked
(implementer writes here)

## Decision
Reviewed in a fresh context: pass. Merged into p0/i8a as 4c4feea.
