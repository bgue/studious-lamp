# P0-I8-T20 — `tl types sync|ls|show|validate|lock|deprecate|watch`

Status: ready
Tier: haiku
Labels: cli
Depends on: S22 (registry), S24 (`type_detail`, watcher), both merged on `p0/i8b`
Branch: `p0/i8b-t20-cli-types`

## Goal
`tl types` exists. An operator can register the packages under a directory (`sync`), see what is registered (`ls`, `show`), check a package without registering it
(`validate`), rewrite its `type.lock` (`lock`), retire a version (`deprecate`) and keep a directory registered as it changes (`watch`). The CLI only parses options, makes one
call into `tl_core.extypes` and prints; every rule is in the registry.

## Brief references (pasted)
> §31.1 **Registration:** the registry discovers packages (directory watch, bucket events, or `tl types sync`), validates them (LinkML lint, compile into the effective schema,
> examples validate), and records a `TypeRegistration` holding metadata only: namespace, name, version, location URI, content hash, owner, status, storage mode, index fields.
> The package files stay where they are.
>
> A package is a directory `<root>/<namespace>/<Name>/<version>/` holding `type.yaml`, optional `workflow.yaml`, `form.yaml`, `settings.yaml`, `examples/`, `README.md` and
> `type.lock` (the sha256 of every other file).
>
> What `sync` does (decision D8, D9): a new valid package gets one `TypeRegistration.Registered` event; an invalid one gets `TypeRegistration.Quarantined` with a report of
> issues (`kind`, `path`, `detail`); a package already registered with the same files appends nothing, so running `sync` twice prints `up to date` the second time. Editing
> the files of a registered version is a `conflict`: the registration stays and the change is reported once as a quarantine. `watch` polls the directory every interval and
> runs the same sync when a package is added, edited or removed.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_core/extypes/types.py (frozen)
class TypeRegistration(BaseModel):
    namespace: str; name: str; version: str; type_ref: str; location_uri: str; content_hash: str
    owner: str; status: TypeStatus; storage_mode: StorageMode; index_fields: list[str]; schema_hash: str
class TypeIssue(BaseModel):
    kind: Literal["layout","lock","lint","compile","example","settings","conflict","unsupported"]
    path: str | None
    detail: str
class TypeView(BaseModel):
    registration: TypeRegistration
    seq: int

# tl_core/extypes/registry.py
def scan(root: Path) -> list[Path]: ...                       # package directories, sorted
def sync(uow_factory, root: Path, *, actor: str, source: str, provider=None) -> list[TypeView]: ...
    # the views of the packages that produced an event in this call; [] when nothing changed
def list_types(conn, *, status: TypeStatus | None = None) -> list[TypeView]: ...
def list_quarantined(conn) -> list[QuarantineEntry]: ...      # QuarantineEntry.type_ref, .report: list[TypeIssue]
def deprecate_type(uow, *, type_ref: str, reason: str, actor: str, source: str) -> TypeView: ...

# tl_core/extypes/service.py
class TypeDetail(BaseModel):
    registration: TypeRegistration; seq: int
    form: TypeForm | None; report: list[TypeIssue]; unavailable: str | None
def type_detail(uow, type_ref: str) -> TypeDetail: ...        # UnknownTypeError when there is no such registration

# tl_core/extypes/forms.py
class TypeForm(BaseModel):
    def fields(self) -> list[TypeFormField]: ...
class TypeFormField(BaseModel):
    name: str; kind: str; required: bool; multivalued: bool; indexed: bool   # (and more)

# tl_core/extypes/validate.py, lock.py, watch.py
def validate_package(path: Path, *, provider, root: Path | None = None) -> tuple[TypeRegistration | None, list[TypeIssue]]: ...
def write_lock(path: Path) -> str: ...                        # writes type.lock, returns the content hash; ValueError on a link or an oversized file
def watch(root: Path, *, interval: float, on_change: Callable[[list[Change]], None],
          stop=..., sleep=..., max_cycles: int | None = None) -> int: ...
class Change: path: str; kind: Literal["added", "changed", "removed"]
```
The stub `packages/tl-cli/src/tl_cli/extypes.py` already has every command, option, import, helper signature and the docstring that says exactly what to print. Replace each
`raise NotImplementedError("STUB (P0-I8-T20)")` with the code the docstring describes. Do not change a signature, an option name or a printed string; do not add commands.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/extypes.py` (the stub)
- `packages/tl-cli/src/tl_cli/proposal.py` (a finished group of the same shape: `_fail`, `_service_errors`, `_factory`, how commands read `ctx.obj`)
- `docs/tickets/P0-I8/provided/b-test_cli_extypes.py.txt` (the test to make pass)
- `packages/tl-core/src/tl_core/extypes/registry.py` (docstrings of the functions above)
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/extypes.py` (replace the stub bodies)
- `packages/tl-cli/tests/test_cli_extypes.py` (create: copy of the provided file, unchanged)
- `docs/reports/P0-I8/P0-I8-T20.md` (create: your report; commit it)

## Steps
1. `uv sync --all-packages` (a new worktree has no environment). Run every command from the repository root.
2. `cp docs/tickets/P0-I8/provided/b-test_cli_extypes.py.txt packages/tl-cli/tests/test_cli_extypes.py`. Do not edit it.
3. Fill in the stub bodies, one command at a time, running the matching tests as you go.
4. The `watch` command's `on_change` closure and `sync_lines` share one code path: `watch` prints `changed ...` lines and then the lines `sync_lines` returns.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_extypes.py -q
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean, except the known failure below; 23 passed in `test_cli_extypes.py`; no other CLI test changed.
Known and not yours: `uv run pytest packages/tl-schema` fails `test_every_event_type_the_code_names_is_in_the_catalog` (it names `Setting.Changed`, which another workstream adds). Do not run or fix it.

## Tests to add
- `packages/tl-cli/tests/test_cli_extypes.py`: the provided file. It covers sync (register, twice is silent, quarantine with issues, `--strict`, a missing directory, the actor), `ls` (empty,
  rows, status filter, a bad status), `show` (fields, a quarantined version's issues, an unknown ref), `validate`, `lock`, `deprecate` and `watch`.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Paste the output of the three acceptance commands. Say which stub docstring, if any, was unclear.

## Rules to remember (from the project's learnings)
- A CLI test that only checks "nothing changed" passes against a command that crashes: the provided tests assert `exit_code` and `result.exception`; keep them.
- Ruff's line limit is 100 columns, including docstrings and comments. Write files with the Write or Edit tool, not shell heredocs. Never use `pkill -f`.
- Never name a module `types.py`. Run Python from the repository root, never from `packages/tl-core/src/tl_core/extypes/`.
- Commit as `P0-I8-T20: <summary>` with the report in the same commit.

## Escalation triggers
- Stop and report *Blocked* if a docstring and the provided test disagree, if a function listed under Interfaces is missing or has another signature, or if you would have to touch a
  file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
