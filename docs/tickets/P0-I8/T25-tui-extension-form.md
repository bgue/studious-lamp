# P0-I8-T25 — TUI new-record form for an extension type

Status: ready
Tier: haiku
Labels: tui
Depends on: S33 (`ClientInterface.create_instance`, the fake's type support), merged on `p0/i8b`
Branch: `p0/i8b-t25-tui-extension-form`

## Goal
A modal that creates an instance of an extension type from the type's generated form: Key, Title and Description, then one editor per slot under its group heading. It has two parts: a
pure module that turns the type's form fields into the TUI's `FieldMeta` and sorts typed values to where the type keeps them (pset values of a managed type, the body of an
object-backed type), and the modal screen. The supervisor wires the modal into the `n` key afterwards.

## Brief references (pasted)
> §31.1 `form.yaml` lays out the generated form: groups, labels, widget hints, help text.
> §31.2 Through Throughline (TUI/API/MCP): the body is validated, stored as an object, then a metadata event referencing its hash is appended.
> A managed type keeps every slot as a pset value: `create_instance(..., psets={pset: {name: value}})`. An object-backed type needs a body: `create_instance(..., body={name: value})`;
> its index fields are copied to the pset from the body, and `psets` must not be given. A refused body raises `BodyValidationError` whose `issues` list the problems;
> `describe_error` already appends them.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_core/extypes/forms.py
class TypeFormField(BaseModel):
    name: str; path: str; label: str; description: str; kind: str   # string,text,int,decimal,bool,date,datetime,enum,ref
    multivalued: bool = False; required: bool = False; unit: str | None = None
    enum_values: list[EnumValue] | None = None; help: str | None = None; order: int
class TypeFormGroup(BaseModel): name: str; label: str; fields: list[TypeFormField]
class TypeForm(BaseModel):
    type_ref: str; type_name: str; storage_mode: str   # "managed" | "object-backed"
    pset: str; groups: list[TypeFormGroup]
    def fields(self) -> list[TypeFormField]: ...
# tl_schema/forms.py
class FieldMeta(BaseModel):
    path: str; label: str; description: str; kind: FieldKind; unit: str | None = None
    enum_values: list[EnumValue] | None = None; required_in_states: list[str] = []
    enforcement: "advisory" | "required" | "locked" | None = None
    layer: Layer; readonly: bool = False; group: str; order: int
# tl_tui/client.py (ClientInterface)
def create_instance(self, type_name: str, *, scope: str, title: str, key: str | None = None, description: str | None = None,
                    psets: dict[str, Any] | None = None, body: dict[str, Any] | None = None, numbering: dict[str, str] | None = None) -> CommandResult: ...
# tl_tui/widgets/form_fields.py
class FieldEditor(Vertical):   # id "input" child; .value (parsed, None = unset), .validate() -> bool, .set_error(str | None), .meta
# tl_tui/widgets/new_record_form.py: FIELDS: tuple[FieldMeta, ...]   # key, title, description
```
The stubs `packages/tl-tui/src/tl_tui/extension_fields.py` (`field_meta`, `sections`, `split_values`) and `packages/tl-tui/src/tl_tui/widgets/extension_form.py` (`compose`,
`_slot_editors`, `_check`, `action_save`) have the classes, constants, CSS, bindings, `__init__` and comments that say what each stub does. Replace each
`raise NotImplementedError("STUB (P0-I8-T25)")`. Do not change a signature or an element id (`new_<path>` for the core fields, `ext_<slot name>` for slots, `form-status`).

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/extension_fields.py` and `packages/tl-tui/src/tl_tui/widgets/extension_form.py` (the stubs)
- `packages/tl-tui/src/tl_tui/widgets/new_record_form.py` (a finished modal of the same shape)
- `docs/tickets/P0-I8/provided/b-test_extension_fields.py.txt` and `b-test_extension_form.py.txt` (the tests to make pass)
- `packages/tl-tui/tests/fakes_types.py` (read only: the fake the tests use)
may explore: `packages/tl-tui/src/tl_tui/widgets/form_fields.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/extension_fields.py` (replace the stub bodies)
- `packages/tl-tui/src/tl_tui/widgets/extension_form.py` (replace the stub bodies)
- `packages/tl-tui/tests/test_extension_fields.py`, `packages/tl-tui/tests/test_extension_form.py` (create: copies of the provided files, unchanged)
- `docs/reports/P0-I8/P0-I8-T25.md` (create: your report; commit it)

## Steps
1. `uv sync --all-packages`. Run every command from the repository root.
2. `cp docs/tickets/P0-I8/provided/b-test_extension_fields.py.txt packages/tl-tui/tests/test_extension_fields.py` and the same for `b-test_extension_form.py.txt`. Do not edit them.
3. Fill in `extension_fields.py` first (9 tests), then the modal (9 tests). Delete each stub's first line (`# ruff: noqa: F401 ...`) once ruff has no unused import left.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_extension_fields.py packages/tl-tui/tests/test_extension_form.py -q
uv run pytest packages/tl-tui -q
```
Expected: `just check` clean; 18 passed in the two test files; the rest of `packages/tl-tui` still passes (about 5 minutes).

## Tests to add
- `test_extension_fields.py`: editor descriptions (kinds, multivalued as JSON, required, help, enum values), sections, value routing for managed and object-backed types.
- `test_extension_form.py`: the modal on the real form of both example types: groups and required markers, an object-backed body, managed psets, inline refusals (required slot, title,
  unparsable text), a body the server refuses (stays open, shows the issues), a duplicate key, Escape.

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Rules to remember (from the project's learnings)
- Ruff's line limit is 100 columns, including docstrings and comments. Write files with the Write or Edit tool, not shell heredocs. Never use `pkill -f`.
- Never name a module `types.py`. Run Python from the repository root. Textual widgets build their children in `compose`, not `__init__`.
- Commit as `P0-I8-T25: <summary>` with the report in the same commit.

## Escalation triggers
- Stop and report *Blocked* if a comment and a provided test disagree, if a function listed under Interfaces is missing or has another signature, or if you would have to touch a
  file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
