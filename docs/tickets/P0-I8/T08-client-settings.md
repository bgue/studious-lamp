# P0-I8-T08 — `ApiClient` settings methods

Status: ready
Tier: haiku
Labels: api
Depends on: — (the `/settings` routes are on the base; `SettingsApi` is already mixed into `ApiClient`)
Branch: `p0/i8a-t08-client-settings`

## Goal
The HTTP client can read and change settings: `tl_api/client/settings.py` has ten methods (`list_settings`, `get_setting`, `setting_history`, `set_setting`, `reset_setting`, `lock_setting`, `revert_setting`, `diff_settings`, `export_settings`, `import_settings`), one per `/settings` route, with the parameters and docstrings in the stub; their bodies raise `NotImplementedError`. A provided test file (10 tests) must pass.

## Brief references (pasted)
> **30.2 Layers and resolution.** `platform default -> company -> project -> user (UI keys only)`. The **effective value** shows its origin. Values set at the current scope are marked ● (like about:config's "modified"). A company can **lock** a key, so projects cannot override it, or constrain the range projects may use.
> **30.3 Change control.** Every change is a `Setting.Changed` event: old value, new value, actor, reason (required for `advanced` and `dangerous` keys), and effective time. **Scheduled changes** take effect at a future time. **Dangerous keys** need explicit confirmation ("I accept the risk"). Changes apply live. Full per-key history, with revert.
> **30.4 Interfaces.** CLI: `tl config get | set | reset | lock | diff | export | import`. API: `/settings` endpoints. MCP: `get_settings` (read), `propose_setting_change` (draft for human approval). Export/import as YAML for templates and reviews.

### Specification
Each method is one request and one decode, like `tl_api/client/proposals.py` (read it). The error mapping is done by the base class: you add none.

| Method | Request | Decode |
|---|---|---|
| `list_settings` | `GET /settings` with `project`, `user`, `prefix` and `modified` (`True` only when `modified_only`) as params | `self._models(SettingView, data)` |
| `get_setting` | `GET /settings/{quote(key)}` with `project`, `user` | `self._model(SettingView, data)` |
| `setting_history` | `GET /settings/{quote(key)}/history` with `layer` | `self._models(SettingChange, data)` |
| `set_setting` | `PUT /settings/{quote(key)}` through `self._send("PUT", path, json=body).json()`; body `layer`, `value`, `reason`, `accept_risk`, plus `applies_at` as `applies_at.isoformat()` only when given | `SettingView` |
| `reset_setting` | `POST /settings/{quote(key)}/reset`; body `layer`, `reason`, `accept_risk`, plus `applies_at` only when given | `SettingView` |
| `lock_setting` | `POST /settings/{quote(key)}/lock`; body `locked`, `bounds`, `reason` | `SettingView` |
| `revert_setting` | `POST /settings/{quote(key)}/revert`; body `layer`, `seq`, `reason`, `accept_risk` | `SettingView` |
| `diff_settings` | `GET /settings/diff` with `left`, `right` | `self._models(SettingDiff, data)` |
| `export_settings` | `GET /settings/export` with `layer` through `self._send("GET", path, params={"layer": layer})`; return `.text` | the YAML text |
| `import_settings` | `POST /settings/import`; body `layer`, `document`, `reason`, `accept_risk` | the answer is `{"layer": ..., "keys": [...]}`: return `[str(k) for k in data["keys"]]` |

`_get_json` and `_post_json` drop `None` params and bodies are sent as given (the route accepts `null` for `reason` and `bounds`). Do not touch `tl_api/client/__init__.py`: the mixin is already in `ApiClient`.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I8/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I8/<ticket-id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring and from every docstring or comment you fill in.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py` (it shadows the standard library); run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. The base is green: if a test outside your Allowed paths fails, report it under *Blocked* with the output.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-api/src/tl_api/client/settings.py` (the stub you complete):
```python
"""about:config over HTTP: the client side of the `/settings` routes (P0-I8-T08).

STUB (P0-I8-T08): remove this paragraph when every method has a body.

One method per route, with the names of the `tl_core.settings` service where there is one. A read
returns the models of ``tl_core.settings`` (``SettingView``, ``SettingChange``, ``SettingDiff``).
A write answers with the key as seen at the layer it changed. The token's actor is recorded and
the source is ``api``. Failures raise the embedded exception classes (``UnknownSettingError``,
``SettingLockedError``, ``InvalidSettingValueError``, ``ReasonRequiredError``,
``RiskNotAcceptedError``, ``SettingRevertNotLatestError`` and so on); an agent token gets
``ApiError`` 403 ``agent_must_propose`` for every write.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tl_core.settings.types import SettingChange, SettingDiff
from tl_core.settings.views import SettingView

from tl_api.client.base import ApiClientBase


class SettingsApi(ApiClientBase):
    def list_settings(
        self,
        *,
        project: str | None = None,
        user: str | None = None,
        prefix: str | None = None,
        modified_only: bool = False,
    ) -> list[SettingView]:
        """Every setting with its definition and state, sorted by key (``GET /settings``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.

        Query parameters: ``project``, ``user``, ``prefix`` and ``modified`` (``True`` only when
        ``modified_only``; leave it out otherwise).
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def get_setting(
        self, key: str, *, project: str | None = None, user: str | None = None
    ) -> SettingView:
        """One setting (``GET /settings/{key}``); the key goes through ``quote``.

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def setting_history(self, key: str, *, layer: str | None = None) -> list[SettingChange]:
        """Every change of the key, oldest first (``GET /settings/{key}/history``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

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
        """Set a key at a layer (``PUT /settings/{key}``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.

        The body has ``layer``, ``value``, ``reason``, ``accept_risk`` and ``applies_at`` (an ISO
        text, or left out when None; build it with ``applies_at.isoformat()``).
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def reset_setting(
        self,
        key: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        """Take the layer's own value away (``POST /settings/{key}/reset``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def lock_setting(
        self,
        key: str,
        *,
        locked: bool,
        reason: str,
        bounds: dict[str, Any] | None = None,
    ) -> SettingView:
        """Lock a key for projects, or bound their values (``POST /settings/{key}/lock``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def revert_setting(
        self,
        key: str,
        *,
        layer: str,
        seq: int,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> SettingView:
        """Undo the latest change at a layer (``POST /settings/{key}/revert``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def diff_settings(self, left: str, right: str) -> list[SettingDiff]:
        """The keys whose effective value differs between two layers (``GET /settings/diff``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def export_settings(self, layer: str) -> str:
        """What a layer holds as a YAML document (``GET /settings/export``): the response text.

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def import_settings(
        self,
        document: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> list[str]:
        """Apply a YAML document to a layer, all or nothing (``POST /settings/import``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.

        The answer is ``{"layer": ..., "keys": [...]}``; return the keys.
        """
        raise NotImplementedError("STUB: P0-I8-T08")
```
```python
# imports to add to settings.py (the stub's autofix removed one):
from tl_api.client.base import ApiClientBase, quote
# ApiClientBase: _get_json(path, params) -> Any; _post_json(path, body, params=None) -> Any;
#   _send(method, path, *, params=None, json=None, ...) -> httpx2.Response (raises the mapped exception);
#   _model(Model, data) -> Model; _models(Model, data) -> list[Model]
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-api/src/tl_api/client/settings.py`
- `packages/tl-api/src/tl_api/client/proposals.py` (the style to follow; read only)
- `packages/tl-api/src/tl_api/routes/settings.py` (the routes; read only)
- `docs/tickets/P0-I8/provided/t08-test_client_settings.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/client/settings.py` (edit: the ten bodies and the import)
- `packages/tl-api/tests/test_client_settings.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I8/P0-I8-T08.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I8/provided/t08-test_client_settings.py.txt packages/tl-api/tests/test_client_settings.py`
2. Implement the ten methods; delete the STUB paragraphs; add the import.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-api/tests/test_client_settings.py -q
uv run pytest packages/tl-api packages/tl-tui/tests/test_remote_client.py -q
just check
```
Expected: 10 tests pass; the API package and the remote-client parity test stay green; `just check` clean.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report.

## Escalation triggers
- Stop and report *Blocked* if a route does not behave as the table says (for example a different status or body).

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
