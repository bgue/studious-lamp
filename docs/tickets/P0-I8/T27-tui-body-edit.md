# P0-I8-T27 — TUI edit form for the body of an object-backed record

Status: ready
Tier: haiku
Labels: tui
Depends on: S33, T25 (`extension_fields.sections`, the form pattern), merged on `p0/i8b`
Branch: `p0/i8b-t27-tui-body-edit`

## Goal
An object-backed record keeps most of its values in a stored body, so the existing edit form (which edits psets) cannot change them: the index fields are refused (`BodyNotAllowedError`)
and the rest are not shown. This ticket adds the edit modal for the body: one editor per slot of the type's form, filled from the stored body; only the slots the user changed are
applied, the whole body is stored as a new version guarded by the record version the form was opened on. The supervisor wires it into the `e` key of the record view afterwards.

## Brief references (pasted)
> §31.2 Through Throughline (TUI/API/MCP): the body is validated, stored as an object, then a metadata event referencing its hash is appended. Updates are new document versions.
> `put_record_body(record_id, scope=, body=, expected_version=)` stores the whole body; a stale `expected_version` raises `ConcurrencyError`; a body that does not validate raises
> `BodyValidationError` (its `issues` list the problems, `describe_error` appends them). A key of the body that the form does not show must survive an edit.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_core/extypes/forms.py
class TypeForm(BaseModel): type_name: str; groups: list[TypeFormGroup]; def fields(self) -> list[TypeFormField]: ...
class TypeFormField(BaseModel): name: str; path: str; label: str; ...
# tl_tui/extension_fields.py (T25, merged)
@dataclass(frozen=True)
class FormSection: name: str; label: str; fields: list[FieldMeta]
def sections(form: TypeForm) -> list[FormSection]: ...
# tl_tui/client.py (ClientInterface)
def put_record_body(self, record_id: str, *, scope: str, body: dict[str, Any], expected_version: int | None = None) -> BodyStoredOut: ...
# tl_tui/widgets/form_fields.py
class FieldEditor(Vertical):  # FieldEditor(meta, initial_value, id=...); .value (None = unset), .changed, .validate() -> bool, .set_error(str | None), .meta
# tl_tui/errors.py: CLIENT_ERRORS, describe_error(exc) -> str
```
The stubs `packages/tl-tui/src/tl_tui/extension_body.py` (`body_values`, `merged_body`) and `packages/tl-tui/src/tl_tui/widgets/extension_edit_form.py` (`compose`, `_editors`, `action_save`)
have the classes, CSS, bindings, `__init__` and comments that say what each stub does. Replace each `raise NotImplementedError("STUB (P0-I8-T27)")`. Do not change a signature or an
element id (`ext_<slot name>`, `form-status`, buttons `save` and `cancel`).

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/extension_body.py` and `packages/tl-tui/src/tl_tui/widgets/extension_edit_form.py` (the stubs)
- `packages/tl-tui/src/tl_tui/widgets/extension_form.py` (a finished modal of the same shape: create instead of edit)
- `docs/tickets/P0-I8/provided/b-test_extension_body.py.txt` and `b-test_extension_edit_form.py.txt` (the tests to make pass)
- `packages/tl-tui/tests/fakes_types.py` (read only: the fake the tests use)
may explore: `packages/tl-tui/src/tl_tui/widgets/edit_form.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/extension_body.py` (replace the stub bodies)
- `packages/tl-tui/src/tl_tui/widgets/extension_edit_form.py` (replace the stub bodies)
- `packages/tl-tui/tests/test_extension_body.py`, `packages/tl-tui/tests/test_extension_edit_form.py` (create: copies of the provided files, unchanged)
- `docs/reports/P0-I8/P0-I8-T27.md` (create: your report; commit it)

## Steps
1. `uv sync --all-packages`. Run every command from the repository root.
2. `cp docs/tickets/P0-I8/provided/b-test_extension_body.py.txt packages/tl-tui/tests/test_extension_body.py` and the same for `b-test_extension_edit_form.py.txt`. Do not edit them.
3. Fill in `extension_body.py` first (6 tests), then the modal (9 tests). Delete each stub's first line (`# ruff: noqa: F401 ...`) once ruff has no unused import left.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_extension_body.py packages/tl-tui/tests/test_extension_edit_form.py -q
uv run pytest packages/tl-tui -q
```
Expected: `just check` clean; 15 passed in the two test files; the rest of `packages/tl-tui` still passes (about 5 minutes).

## Tests to add
- `test_extension_body.py`: initial values, one edit, clearing, unknown names and body keys, no mutation, no edits.
- `test_extension_edit_form.py`: the modal on the real LiftPlan form: prefilled editors, a change stored with the rest kept, clearing an optional slot, no changes, a required slot cleared,
  unparsable text, a body the server refuses, a record that moved on (conflict blocks the save), Escape.

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Rules to remember (from the project's learnings)
- Ruff's line limit is 100 columns, including docstrings and comments. Write files with the Write or Edit tool, not shell heredocs. Never use `pkill -f`.
- Never name a module `types.py`. Run Python from the repository root. Textual widgets build their children in `compose`, not `__init__`.
- Read a file with the Read tool before you Edit it. Commit as `P0-I8-T27: <summary>` with the report in the same commit.

## Escalation triggers
- Stop and report *Blocked* if a comment and a provided test disagree, if a function listed under Interfaces is missing or has another signature, or if you would have to touch a
  file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
