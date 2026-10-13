# P1-I2-T13c — TUI: the re-pin dialog

Status: ready
Tier: haiku
Labels: tui
Depends on: S17 on `p1/i2` (the diff text function and the client write method, in the tree); no other ticket
Branch: `p1/i2-t13c-tui-repin-dialog`

## Goal
A person re-pins a stale link after seeing what changed between the revision it points to and the document's current one (brief 7.3). `packages/tl-tui/src/tl_tui/widgets/repin_dialog.py` has the dialog's layout, bindings and `action_cancel` written; `on_mount` and `action_confirm` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 7.3.** When a new revision is issued, pinned links go stale; the owner is notified and re-pins with a diff of the two revisions shown before confirming.
>
> **ADR-0011.** Re-pinning is open to any signed-in person (no per-record access lists in Phase 1). **ADR-0012.** Whether a pin is stale is the module's decision; the dialog shows the diff and moves the link, it decides nothing.

### Specification
- The dialog is a modal (`ModalScreen[bool]`): it dismisses with `True` when the link was moved and `False` when it was left alone. Enter or `y` confirms; Esc or `n` cancels.
- The diff comes from `ClientInterface.document_diff(project, number, from_code, to_code)`; its text from `tl_tui/document_text.py::repin_lines` (final).
- The move is `ClientInterface.repin_document_link(RepinDocumentLink(...))` with `pin` set to the document's current revision code (`link.current_code`).
- A refusal (`CLIENT_ERRORS`) is shown in `#repin-status` with `describe_error`; the dialog stays open. A link that floats, a document with no current revision, and a link that already points at the current revision have nothing to re-pin: say so in `#repin-body`, and the confirm key says `Nothing to re-pin.` and leaves the dialog open.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/widgets/repin_dialog.py` (the stub you complete):
```python
"""The re-pin dialog: show what changed between two revisions, then move the link on a yes.

Opened from the document register (``r``) for a stale link. It reads the module's diff between the
revision the link is pinned to and the document's current one, shows it, and only on a yes sends
``RepinDocumentLink`` (brief 7.3: the person sees what changed before confirming). Enter or ``y``
confirms; Esc or ``n`` leaves the link as it is. A refusal stays on screen and the dialog stays
open. The dialog decides nothing: the diff is the module's words and the move is the module's
command (any signed-in person may re-pin; ADR-0011).

STUB (P1-I2-T13c): the bodies of on_mount and action_confirm raise NotImplementedError; their
signatures, options, docstrings and the helpers are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static
from tl_mod_documents.resolver import RepinDocumentLink
from tl_mod_documents.views import DocumentLinkView, RevisionDiffView

from tl_tui.client import ClientInterface
from tl_tui.document_text import repin_lines
from tl_tui.errors import CLIENT_ERRORS, describe_error


class RepinScreen(ModalScreen[bool]):
    """Dismisses with ``True`` when the link was moved, ``False`` when it was left alone."""

    KEY_HINTS: ClassVar[str] = "Enter or y re-pin  Esc or n leave it"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "confirm", "Re-pin", show=False),
        Binding("y", "confirm", "Re-pin", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("n", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    RepinScreen { align: center middle; }
    RepinScreen > Vertical {
        width: 90%;
        height: auto;
        max-height: 90%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    RepinScreen #repin-title { text-style: bold; }
    RepinScreen #repin-status { color: $error; height: auto; }
    RepinScreen #repin-hints { color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        number: str,
        link: DocumentLinkView,
        actor: str,
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.number = number
        self.link = link
        self.actor = actor
        self.diff: RevisionDiffView | None = None
        self.target: str | None = None  # the revision the link would move to

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Re-pin a stale link", markup=False, id="repin-title")
            yield Static("", markup=False, id="repin-body")
            yield Static("", markup=False, id="repin-status")
            yield Static(self.KEY_HINTS, markup=False, id="repin-hints")

    def on_mount(self) -> None:
        """Read the diff the link would move through and show it."""
        # STEPS
        # 1. link = self.link. If link.pin is None, or link.current_code is None, or the two are
        #    the same code, show the reason in #repin-body ("This link floats; nothing to
        #    re-pin.", "<number> has no issued revision to move to." or "The link already points
        #    to <code>.") and return. self.target stays None.
        # 2. Otherwise self.target = link.current_code, and try self.diff =
        #    self.client.document_diff(self.project, self.number, link.pin, self.target).
        #    On CLIENT_ERRORS show describe_error(exc) in #repin-status, set self.target = None
        #    and return.
        # 3. Show "\n".join(repin_lines(link, diff)) in #repin-body.
        raise NotImplementedError

    def action_confirm(self) -> None:
        """Move the link to the current revision, or say why it cannot be moved."""
        # STEPS
        # 1. With self.target None there is nothing to confirm: set #repin-status to "Nothing to
        #    re-pin." and return.
        # 2. Send self.client.repin_document_link(RepinDocumentLink(actor=self.actor,
        #    source="tui", scope=f"project:{self.project}", link_id=self.link.link_id,
        #    pin=self.target)). On CLIENT_ERRORS show describe_error(exc) in #repin-status and
        #    stay open.
        # 3. Otherwise self.dismiss(True).
        raise NotImplementedError

    def action_cancel(self) -> None:
        self.dismiss(False)
```

`packages/tl-tui/src/tl_tui/document_text.py` (excerpts; read-only, do not edit):
```python
def repin_lines(link: DocumentLinkView, diff: RevisionDiffView) -> list[str]:
    """The re-pin dialog body: who is linked, the move, then what changed (the module's words)."""
    ...
```

`packages/tl-modules/documents/src/tl_mod_documents/views.py` (excerpts; read-only, do not edit):
```python
class DocumentLinkView(BaseModel):
    """A link to the document and what its pin means now."""

    link_id: str
    from_key: str | None
    from_type: str
    from_title: str
    relation: str
    link_status: str  # active | stale
    pin: str | None  # None floats
    pin_state: str  # current | stale | floating | no_current | unknown
    current_code: str | None
    newer_codes: list[str]


class RevisionDiffView(BaseModel):
    document_number: str
    from_code: str
    to_code: str
    from_status: str | None
    to_status: str | None
    summary: list[str]
```

`packages/tl-modules/documents/src/tl_mod_documents/resolver.py` (excerpts; read-only, do not edit):
```python
class RepinDocumentLink(Command):
    """Move a link to another revision of its document (``current`` for the current one).

    Bring a stale link back to active. Show the person ``revision_diff`` first; the command itself
    only records the decision.
    """

    model_config = ConfigDict(extra="forbid")

    link_id: str
    pin: str | None = Field(default=CURRENT, max_length=MAX_NUMBER)
    expected_version: int | None = None
```

`packages/tl-tui/src/tl_tui/client.py` (the document methods of `ClientInterface` the dialog uses; read-only):
```python
def document_diff(self, project: str, number: str, from_code: str, to_code: str) -> RevisionDiffView: ...
def repin_document_link(self, cmd: RepinDocumentLink) -> CommandResult: ...
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/repin_dialog.py` (the file you edit)
- `packages/tl-tui/src/tl_tui/document_text.py` (final)
- `packages/tl-tui/src/tl_tui/errors.py` (`CLIENT_ERRORS`, `describe_error`)
- `packages/tl-tui/tests/fakes_documents.py` and `packages/tl-tui/tests/helpers.py` (already in the tree)
- `docs/tickets/P1-I2/provided/t13c-test_repin_dialog.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-modules`, `tl-cli`, `tl-api`; strict for `tl_core`, `tl_schema`, `tl_adapters`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run only the scoped commands in *Acceptance* (a ticket whose tests do not use the database fixtures has no Postgres command), never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- A cell of a table is a `rich.text.Text`, not a string: a title such as `[a, b]` is not markup (L-P1-I1-9 in spirit; the tag register does the same).
- The screen reads and writes only through `ClientInterface` (`self.client`); it never imports a service, a handler or the database. The tests use `FakeClient` (`tests/fakes.py`, with the document methods of `tests/fakes_documents.py`).
- Key presses are tested with `pilot.press`; a letter key does nothing while an `Input` has focus.
- `uv run pytest packages/tl-tui -q` is the package gate; the TUI tests run once (they do not use the database fixtures).

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/repin_dialog.py` (edit)
- `packages/tl-tui/tests/test_repin_dialog.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T13c.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t13c-test_repin_dialog.py.txt` to `packages/tl-tui/tests/test_repin_dialog.py`.
3. Implement `on_mount` and `action_confirm` by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_repin_dialog.py -q
uv run pytest packages/tl-tui -q
```
Expected: `just check` clean; 9 test functions pass; the whole package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). There is no parity run for this ticket: its tests do not use the database fixtures, so Acceptance has no `--adapters` command.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
