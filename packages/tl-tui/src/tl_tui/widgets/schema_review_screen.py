# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""The review of one schema package version (P1-I8-T04b; brief 27.4, 27.8).

STUB: this file is the interface P1-I8-T04b implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. The layout, the keys, `_say`, `_ids`
and `action_close` are complete.

A full-size modal that ``v`` opens from the workbench. It shows the classification of the version,
what it would touch (the stored impact report, or with ``i`` the impact of pinning it in the
project of the app's scope) and, after ``t``, the test on a sample. The keys are the steps of the
review: ``a`` analyse, ``s`` submit (anyone signed in; for the author), ``y`` approve, ``c`` send
back with a reason, ``p`` publish after typing ``publish`` (administrators). ``F5`` reads again,
``Esc`` closes. Every step is one ``schemareg_command`` call as the signed-in person and the view is
read again afterwards; the module decides what is allowed and a refusal is shown in the status line
and changes nothing. Nothing is stored here.
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static
from tl_core.settings.layers import project_of_scope
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    PublishSchemaPackage,
    RequestSchemaChanges,
    SubmitSchemaPackage,
)
from tl_mod_schemareg.views import PackageDetail, SampleTestView

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.schema_review_text import (
    classification_lines,
    impact_lines,
    next_step,
    sample_lines,
    title_line,
)
from tl_tui.widgets.prompt import PromptScreen


class SchemaReviewScreen(ModalScreen[None]):
    """The review of package version `ref` (an id or `name@version`) for `scope`."""

    KEY_HINTS: ClassVar[str] = (
        "a analyse  s submit  y approve  c send back  p publish  Esc close\n"
        "t test on sample  i impact in the project  F5 reload"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("a", "analyse", "Analyse", show=False),
        Binding("s", "submit", "Submit", show=False),
        Binding("t", "sample", "Test on sample", show=False),
        Binding("i", "project_impact", "Impact of the project", show=False),
        Binding("y", "approve", "Approve", show=False),
        Binding("c", "send_back", "Send back", show=False),
        Binding("p", "publish", "Publish", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    SchemaReviewScreen { background: $surface; }
    SchemaReviewScreen > Vertical { padding: 0 1; }
    SchemaReviewScreen #review-title { text-style: bold; height: 1; }
    SchemaReviewScreen #review-next { height: 1; }
    SchemaReviewScreen #review-scroll { height: 1fr; border-top: solid $accent; padding: 0 1; }
    SchemaReviewScreen #review-status { height: 1; }
    SchemaReviewScreen #review-hints { height: 2; color: $text-muted; }
    """

    def __init__(self, client: ClientInterface, scope: str, actor: str, ref: str) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.actor = actor
        self.ref = ref
        self.detail: PackageDetail | None = None
        self.sample: SampleTestView | None = None
        self.project_view = False  # the impact of pinning it in the scope's project

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="review-title")
            yield Static("", markup=False, id="review-next")
            with VerticalScroll(id="review-scroll"):
                yield Static("", markup=False, id="review-body")
            yield Static("", markup=False, id="review-status")
            yield Static(self.KEY_HINTS, markup=False, id="review-hints")

    def on_mount(self) -> None:
        self.reload()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> bool:
        """Read the version again and show it; False (with the error shown) when that failed."""
        # STEPS
        # 1. In a try: self.detail = self.client.get_schema_package(self.ref). On
        #    CLIENT_ERRORS as exc: self.detail = None, self._show(),
        #    self._say(describe_error(exc), error=True) and return False.
        # 2. self._show(); return True.
        raise NotImplementedError("STEPS: see the comments")

    def _impact(self) -> list[str]:
        """The impact section: the stored report, or the project's when `i` was pressed."""
        # STEPS
        # 1. Lines of the impact section. Without self.project_view: ['Impact (stored)',
        #    *impact_lines(self.detail.impact)].
        # 2. With it: project = project_of_scope(self.scope). No project (the company
        #    scope): ['Impact of a project', 'The scope is the company: no project to
        #    pin it in.'].
        # 3. Otherwise report = self.client.get_project_schema_impact(project,
        #    self.detail.package, self.detail.version) and [f'Impact in {project}',
        #    *impact_lines(report)]. On CLIENT_ERRORS: [f'Impact in {project}', f'!
        #    {describe_error(exc)}'].
        raise NotImplementedError("STEPS: see the comments")

    def _show(self) -> None:
        # STEPS
        # 1. Without a detail: #review-title gets self.ref, #review-next '' and #review-
        #    body 'This package version could not be read.'; return.
        # 2. Otherwise #review-title gets title_line(detail), #review-next
        #    next_step(detail.state), and #review-body the lines joined by newlines:
        #    'Classification', *classification_lines(detail), '', *self._impact(), '',
        #    'Test on a sample', *sample_lines(self.sample).
        raise NotImplementedError("STEPS: see the comments")

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#review-status", Static).update(("! " if error else "") + text)

    # --- steps ---------------------------------------------------------------------------

    def _run(self, name: str, command: Any, done: str) -> None:
        """Run one command; read the version again; say `done`, or why it was refused."""
        # STEPS
        # 1. Call self.client.schemareg_command(name, command). On CLIENT_ERRORS as exc:
        #    self.reload() (to show what the version really is), then
        #    self._say(describe_error(exc), error=True) and return.
        # 2. On success: self.sample = None (a sample belongs to the content it was made
        #    for); if self.reload(): self._say(done).
        raise NotImplementedError("STEPS: see the comments")

    def _ids(self) -> tuple[str, str] | None:
        if self.detail is None:
            self._say("This package version could not be read.", error=True)
            return None
        return self.detail.id, self.detail.key

    def action_analyse(self) -> None:
        # STEPS
        # ids = self._ids(); None: return. AnalyseSchemaPackage(actor=self.actor,
        #    source='tui', scope='company', package_id=ids[0]) through
        #    self._run('AnalyseSchemaPackage', command, f'Analysed {ids[1]}.').
        raise NotImplementedError("STEPS: see the comments")

    def action_submit(self) -> None:
        # STEPS
        # As analyse, with SubmitSchemaPackage and the text f'Submitted {ids[1]} for
        #    review.'.
        raise NotImplementedError("STEPS: see the comments")

    def action_approve(self) -> None:
        # STEPS
        # As analyse, with ApproveSchemaPackage and the text f'Approved {ids[1]}.'.
        raise NotImplementedError("STEPS: see the comments")

    def action_send_back(self) -> None:
        # STEPS
        # 1. ids = self._ids(); None: return.
        # 2. Push PromptScreen(f'Send {ids[1]} back', 'What must the author change?')
        #    with a callback `asked(reason)`: None says 'Nothing sent back.'; otherwise
        #    run RequestSchemaChanges(..., package_id=ids[0], reason=reason) through
        #    self._run with the text f'Sent {ids[1]} back to its author.'.
        raise NotImplementedError("STEPS: see the comments")

    def action_publish(self) -> None:
        # STEPS
        # 1. ids = self._ids(); None: return.
        # 2. Push PromptScreen(f'Publish {ids[1]}', 'Type publish to confirm; it cannot
        #    be undone.') with a callback `asked(answer)`: any answer but exactly
        #    'publish' says 'Not published: the word was not typed.'; otherwise run
        #    PublishSchemaPackage(..., package_id=ids[0]) through self._run with the
        #    text f'Published {ids[1]}.'.
        raise NotImplementedError("STEPS: see the comments")

    def action_sample(self) -> None:
        """Test the version on a sample of the records the person may read."""
        # STEPS
        # 1. ids = self._ids(); None: return. self.sample =
        #    self.client.sample_test_schema_package(ids[0]); on CLIENT_ERRORS say the
        #    error with error=True and return.
        # 2. self._show(); self._say(f'Tested {ids[1]} on a sample.').
        raise NotImplementedError("STEPS: see the comments")

    def action_project_impact(self) -> None:
        """Switch the impact section between the stored report and the project's."""
        # STEPS
        # Flip self.project_view; call self._show() when self.detail is not None.
        raise NotImplementedError("STEPS: see the comments")

    def action_reload(self) -> None:
        # STEPS
        # if self.reload(): self._say('Reloaded.')  (a failed read keeps its error
        #    text).
        raise NotImplementedError("STEPS: see the comments")

    def action_close(self) -> None:
        self.dismiss(None)
