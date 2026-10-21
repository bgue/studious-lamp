"""The review of one schema package version (P1-I8-T04b; brief 27.4, 27.8).

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
from tl_tui.display import mode_of
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
        try:
            self.detail = self.client.get_schema_package(self.ref)
        except CLIENT_ERRORS as exc:
            self.detail = None
            self._show()
            self._say(describe_error(exc), error=True)
            return False
        self._show()
        return True

    def _impact(self) -> list[str]:
        """The impact section: the stored report, or the project's when `i` was pressed."""
        detail = self.detail
        if detail is None:
            return []
        technical = mode_of(self.app).technical
        if not self.project_view:
            return ["Impact (stored)", *impact_lines(detail.impact, technical=technical)]
        project = project_of_scope(self.scope)
        if project is None:
            return ["Impact of a project", "The scope is the company: no project to pin it in."]
        try:
            report = self.client.get_project_schema_impact(project, detail.package, detail.version)
        except CLIENT_ERRORS as exc:
            return [f"Impact in {project}", f"! {describe_error(exc)}"]
        return [f"Impact in {project}", *impact_lines(report, technical=technical)]

    def _show(self) -> None:
        detail = self.detail
        if detail is None:
            self.query_one("#review-title", Static).update(self.ref)
            self.query_one("#review-next", Static).update("")
            self.query_one("#review-body", Static).update("This package version could not be read.")
            return
        technical = mode_of(self.app).technical
        self.query_one("#review-title", Static).update(title_line(detail, technical=technical))
        self.query_one("#review-next", Static).update(next_step(detail.state))
        lines = [
            "Classification",
            *classification_lines(detail, technical=technical),
            "",
            *self._impact(),
            "",
            "Test on a sample",
            *sample_lines(self.sample, technical=technical),
        ]
        self.query_one("#review-body", Static).update("\n".join(lines))

    def refresh_for_display_mode(self) -> None:
        """Draw the title, the body and the rest again for the display mode."""
        self._show()

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#review-status", Static).update(("! " if error else "") + text)

    # --- steps ---------------------------------------------------------------------------

    def _run(self, name: str, command: Any, done: str) -> None:
        """Run one command; read the version again; say `done`, or why it was refused."""
        try:
            self.client.schemareg_command(name, command)
        except CLIENT_ERRORS as exc:
            self.reload()  # show what the version really is
            self._say(describe_error(exc), error=True)
            return
        self.sample = None  # a sample belongs to the content it was made for
        if self.reload():
            self._say(done)

    def _ids(self) -> tuple[str, str] | None:
        if self.detail is None:
            self._say("This package version could not be read.", error=True)
            return None
        return self.detail.id, self.detail.key

    def action_analyse(self) -> None:
        ids = self._ids()
        if ids is None:
            return
        command = AnalyseSchemaPackage(
            actor=self.actor, source="tui", scope="company", package_id=ids[0]
        )
        self._run("AnalyseSchemaPackage", command, f"Analysed {ids[1]}.")

    def action_submit(self) -> None:
        ids = self._ids()
        if ids is None:
            return
        command = SubmitSchemaPackage(
            actor=self.actor, source="tui", scope="company", package_id=ids[0]
        )
        self._run("SubmitSchemaPackage", command, f"Submitted {ids[1]} for review.")

    def action_approve(self) -> None:
        ids = self._ids()
        if ids is None:
            return
        command = ApproveSchemaPackage(
            actor=self.actor, source="tui", scope="company", package_id=ids[0]
        )
        self._run("ApproveSchemaPackage", command, f"Approved {ids[1]}.")

    def action_send_back(self) -> None:
        ids = self._ids()
        if ids is None:
            return
        package_id, key = ids

        def asked(reason: str | None) -> None:
            if reason is None:
                self._say("Nothing sent back.")
                return
            command = RequestSchemaChanges(
                actor=self.actor,
                source="tui",
                scope="company",
                package_id=package_id,
                reason=reason,
            )
            self._run("RequestSchemaChanges", command, f"Sent {key} back to its author.")

        self.app.push_screen(
            PromptScreen(f"Send {key} back", "What must the author change?"), callback=asked
        )

    def action_publish(self) -> None:
        ids = self._ids()
        if ids is None:
            return
        package_id, key = ids

        def asked(answer: str | None) -> None:
            if answer != "publish":
                self._say("Not published: the word was not typed.")
                return
            command = PublishSchemaPackage(
                actor=self.actor, source="tui", scope="company", package_id=package_id
            )
            self._run("PublishSchemaPackage", command, f"Published {key}.")

        self.app.push_screen(
            PromptScreen(f"Publish {key}", "Type publish to confirm; it cannot be undone."),
            callback=asked,
        )

    def action_sample(self) -> None:
        """Test the version on a sample of the records the person may read."""
        ids = self._ids()
        if ids is None:
            return
        try:
            self.sample = self.client.sample_test_schema_package(ids[0])
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            return
        self._show()
        self._say(f"Tested {ids[1]} on a sample.")

    def action_project_impact(self) -> None:
        """Switch the impact section between the stored report and the project's."""
        self.project_view = not self.project_view
        if self.detail is not None:
            self._show()

    def action_reload(self) -> None:
        if self.reload():
            self._say("Reloaded.")

    def action_close(self) -> None:
        self.dismiss(None)
