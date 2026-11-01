# P2-WEB1-S2 — Shared command runner `run_command` and the Textual-free `action_ui` module

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: auth, security, api, tui
Depends on: RM-S2 (merged on trunk). Independent of S1 (disjoint files).
Branch: `p2/web1-s2-run-command`
Approver (command access path): human gate list, `04-gates.md` §2; the piece stops at the PR, the orchestrator does not approve it.

## Goal
After this piece the body of a command endpoint after the model is built is one function, `tl_api.commands.run_command`, which both the
JSON endpoints and (in S4) the web action route call, so the module-role access check (`require_command_access`), the company-admin check,
the reserved-field refusal and the effective-time handling exist once. The terminal's `ACTION_UI` table, `ActionUi`, `FormField` and the
pure helpers that build a command from form answers live in `tl_tui/action_ui.py`, which imports no `textual` (the web imports it in S4). Behaviour of
every existing endpoint and screen is unchanged.

## Brief references
`docs/build-spec/specs/web-client-i1.md` **§7 "Actions"** and the S2 row of §11, with these deltas (D3: the web `actions.py` and its route move to S4, so this piece
touches no `tl_web` file):
1. **`run_command`** in `packages/tl-api/src/tl_api/commands.py`. Pinned contract (names of keyword parameters are yours if you keep the meaning):
   ```python
   def run_command(
       ctx: Ctx, spec: CommandSpec, command: Command, *, principal: Principal,
       effective_at: str | None = None, path: str = "",
   ) -> CommandResult: ...
   def command_spec(name: str) -> CommandSpec | None: ...   # lookup in COMMANDS; None for an unknown name
   ```
   It does exactly what `_make_endpoint`'s `endpoint` does from `refuse_reserved(command)` to the handler call: `refuse_reserved`, the `company` +
   `command.scope == "company"` admin authorization (`path` goes where `request.url.path` went), `resolve_effective_at`, `ctx.backend(False)`,
   `require_command_access(...)` with `holder_for_principal(principal)` **before** the handler, then the `needs_holds` / `takes_roles` / plain handler branches.
   `endpoint` keeps: `get_ctx`, building the model from the body (including the agent `source` override), then `return run_command(...)`. No second copy of any check.
2. **`tl_tui/action_ui.py`** (new): move from `log_actions.py` without behaviour change: `ENVELOPE`, `Build`, `Prepare`, `ActionUi`, the private helpers it needs
   (`_reason`, `_flag`, `_opt`, `_stream`, `_stream_only` and the tables they use), `ACTION_UI`, `stamp`, `without_keys`; and `FormField` from `widgets/action_form.py`.
   `log_actions.py` and `widgets/action_form.py` re-export every moved public name so no other import in the repo changes (grep `log_actions import` and
   `action_form import`; there are 8 users). `Runner`, `run_module_command`, `log_actions`, `screen_runner` and the Textual glue stay in `log_actions.py`.
   `action_ui.py` imports no `textual` module and no `tl_tui.widgets.*`, `tl_tui.client` or `tl_tui.log_actions` (check in a fresh interpreter).
3. No schema, no new dependency, no change to `docs/reference/openapi.json` (the endpoints' signatures and docs are unchanged; if `just check` says it drifted, stop).

## Interfaces (existing, verbatim at the branch point)
```python
# packages/tl-api/src/tl_api/commands.py  (excerpt, lines ~300-340)
def _make_endpoint(spec: CommandSpec, body_model: type[BaseModel]) -> Callable[..., CommandResult]:
    action = action_for(spec)
    changes_records = spec.name not in AGENT_DIRECT_COMMANDS
    def endpoint(request, body, actor: Annotated[str, Depends(guard(action, changes_records=changes_records))],
                 principal: Annotated[Principal, Depends(current_principal)], effective_at=...) -> CommandResult:
        ctx = get_ctx(request)
        fields = body.model_dump()
        if actor.startswith("agent:"): fields["source"] = source_for(actor)
        command = spec.model(**fields, actor=actor)
        refuse_reserved(command)
        if effective_access(spec) == "company" and command.scope == "company":
            ctx.authorizer.authorize(principal, f"admin.command.{spec.name}", request.url.path)
        when = resolve_effective_at(effective_at, command.scope)
        with effective_time(when), ctx.backend(False) as uow:
            require_command_access(uow.conn(), command, holder=holder_for_principal(principal))
            if spec.needs_holds: ...            # holds=lambda level: holds_access(principal, actor, level)
            if spec.takes_roles: ...            # roles=workflow_roles(principal)
            return spec.handler(uow, command)
# packages/tl-tui/src/tl_tui/log_actions.py
@dataclass(frozen=True)
class ActionUi:
    key: str
    fields: tuple[FormField, ...] = ()
    confirm: str | None = None
    build: Build = field(kw_only=True)   # (form values, record id, version) -> command model
```

## Context (<= 10 files)
- `packages/tl-api/src/tl_api/commands.py` (lines 1-60 imports, 250-380); `packages/tl-api/tests/test_commands.py` (names only)
- `packages/tl-tui/src/tl_tui/log_actions.py`, `packages/tl-tui/src/tl_tui/widgets/action_form.py` (`FormField`, lines 1-35)
- `dev/accept/P2-W0/RM-S2.py` (the access matrix: reuse its harness for check (b))
may explore: the 8 importers listed by grep

## Allowed paths
- `packages/tl-api/src/tl_api/commands.py` (modify: `run_command`, `command_spec`, `_make_endpoint` body only)
- `packages/tl-tui/src/tl_tui/action_ui.py` (create), `packages/tl-tui/src/tl_tui/log_actions.py` (modify: moves and re-exports), `packages/tl-tui/src/tl_tui/widgets/action_form.py` (modify: `FormField` re-export)
- `dev/accept/P2-WEB1/S2.py` (create), `docs/reports/P2-WEB1/S2.md` (create)
Not allowed: `tl_web/**`, `tl_api/auth.py`, `app.py`, `routes/**`, `openapi.json`, any other `tl_tui` file, `pyproject.toml`, `uv.lock`.

## Acceptance (run these, once; no pytest, no `just gate`)
```
just check
uv run python dev/accept/P2-W0/RM-S2.py
uv run python dev/accept/P2-WEB1/S2.py
```
`RM-S2.py` must still print its full matrix and pass (the endpoints behave as before). `dev/accept/P2-WEB1/S2.py` (SQLite temp ledger, `TL_ENV=test`, exit 0,
one `PASS <check>` per check):
(a) `inspect.getsource(_make_endpoint)` no longer contains `require_command_access`, `refuse_reserved` or `resolve_effective_at`; `run_command` contains each once;
(b) `run_command` called directly (no HTTP) for a `controller` module command as a plain user with no grant raises the same refusal the endpoint gives (403 / `Forbidden`), and as a holder of the word succeeds; for a `company` command with scope `company` a non-admin is refused; a command carrying a reserved field (`refuse_reserved`) is refused;
(c) `command_spec("AnswerTechnical")` is the COMMANDS row, `command_spec("Nope")` is `None`;
(d) in a fresh interpreter (`subprocess`, `python -I -c`) `import tl_tui.action_ui` leaves `textual` out of `sys.modules`;
(e) `tl_tui.log_actions.ACTION_UI is tl_tui.action_ui.ACTION_UI` and the same for `ActionUi`, `FormField` (via `widgets.action_form`), `ENVELOPE`, `stamp`, `without_keys`; `ACTION_UI` has the same keys as at the branch point (keep the sorted key list in the script, taken before you edit);
(f) for every `ACTION_UI` entry with no fields, `build({}, "rec-1", 3)` returns a command whose `stream_id == "rec-1"` (the `ENVELOPE` placeholders unchanged).

## Mutation guards (you run them, own worktree, 1 sentinel + <= 5 targeted, 3 lines)
Sentinel: baseline green. Targets: `require_command_access` removed from `run_command` (b red and RM-S2 matrix red); `refuse_reserved` removed (b red); company-admin check removed (b red); holder taken from the wrong principal (RM-S2 matrix red).

## Tests for the end run (S5 writes them; this piece writes none)
`packages/tl-api/tests/test_run_command.py`, `packages/tl-tui/tests/test_action_ui_pure.py` (`textual` absent from a fresh import; the table keys; every key letter unique). Report the call sites and the line of the access check.

## Report requirements
Standard piece report (<= 60 lines): deviations first; the final `run_command` signature; the list of names re-exported; acceptance output (<= 5 lines per command); mutation result in 3 lines; no discussion of the commit trailer; no model names in any committed file.

## Escalation triggers
- *Blocked* if: moving the table needs a new import cycle that cannot be broken inside Allowed paths; `action_ui` cannot avoid `textual` without changing another module; the RM-S2 matrix changes; `openapi.json` drifts; any existing test outside this piece breaks (name it).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
