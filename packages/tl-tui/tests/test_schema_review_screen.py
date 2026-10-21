"""The schema review screen on the fake client, driven with a pilot (P1-I8-T04b).
Provided; do not edit.

The screen shows the classification, the impact and the sample test of one package version. Each
step of the review is one command as the signed-in person; the module's refusal is shown in the
status line and changes nothing; publishing needs the word `publish` typed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_schemareg import make_package
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    PublishSchemaPackage,
    RequestSchemaChanges,
    SubmitSchemaPackage,
)
from tl_mod_schemareg.impact_types import ImpactEntry, ImpactReport
from tl_mod_schemareg.views import SampleExample, SampleTestView
from tl_schema.classify import Change, build_report
from tl_tui.app import TlApp
from tl_tui.display import DisplayMode
from tl_tui.widgets.prompt import PromptScreen
from tl_tui.widgets.schema_review_screen import SchemaReviewScreen

ID = "PKG-co.acme.engineering-3.3.0"


def stored_impact() -> ImpactReport:
    entry = ImpactEntry(
        section="records",
        target="psets.valve_data.size_in",
        change="property_removed",
        count=12,
        detail="12 records hold a value.",
    )
    return ImpactReport(
        scope="company",
        old_hash="a" * 64,
        new_hash="b" * 64,
        changed_paths=("psets.valve_data.size_in",),
        entries=(entry,),
        counts={"records": 1},
        truncated=False,
    )


def client_with(state: str = "Draft", *, analysed: bool = True) -> FakeClient:
    client = FakeClient()
    report = build_report(
        "co.acme.engineering@3.2.0",
        "co.acme.engineering@3.3.0",
        [Change(cls="constraining", code="required", path="psets.a.c", detail="c is required.")],
    )
    client.seed_schema_package(
        make_package(
            "co.acme.engineering",
            "3.3.0",
            state,
            worst_class="constraining" if analysed else None,
            analysed=analysed,
            classification=report if analysed else None,
            impact=stored_impact() if analysed else None,
        )
    )
    return client


def show_technical(app: TlApp, screen: SchemaReviewScreen, on: bool) -> None:
    """Switch the app's display mode and draw the review again, as the toggle will."""
    mode = DisplayMode()
    mode.technical = on
    app.display_mode = mode  # pyright: ignore[reportAttributeAccessIssue]  # App does not declare it
    screen.refresh_for_display_mode()


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[Any], TlApp, SchemaReviewScreen], Awaitable[None]],
    *,
    scope: str = SCOPE,
    ref: str = ID,
) -> None:
    app = TlApp(client, scope=scope, actor="user:boss", is_admin=True)

    async def go(pilot: Pilot[Any]) -> None:
        app.push_screen(SchemaReviewScreen(client, scope, "user:boss", ref))
        await pilot.pause()
        assert isinstance(app.screen, SchemaReviewScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def test_the_screen_shows_the_title_the_next_step_and_the_reports() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        text = screen_text(app)
        assert "Engineering, version 3.3.0  Draft  class constraining" in text
        assert "Next: analyse (a), then submit (s)." in text
        assert "Worst constraining  auto-adoptable no  blocks submit no" in text
        assert "constraining  A: c  c is required." in text
        assert "Impact (stored)" in text and "Scope company" in text
        assert "Digest" not in text
        assert (
            "records  Valve data: size in  property_removed  12  12 records hold a value." in text
        )
        assert "Not run: press t to test on a sample of records." in text
        show_technical(app, screen, True)
        text = screen_text(app)
        assert "co.acme.engineering@3.3.0  Draft  class constraining" in text
        assert "Base co.acme.engineering@3.2.0" in text and "Digest " in text
        assert "constraining  psets.a.c  c is required." in text
        assert "records  psets.valve_data.size_in  property_removed" in text
        show_technical(app, screen, False)
        assert "co.acme.engineering@3.3.0" not in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SchemaReviewScreen)

    scenario(client_with(), steps)


def test_a_version_not_analysed_says_so_and_analyse_is_one_command_as_the_person() -> None:
    client = client_with(analysed=False)

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        assert "Not analysed: press a to analyse." in screen_text(app)
        await pilot.press("a")
        await pilot.pause()
        assert len(client.schemareg_commands) == 1
        command = client.schemareg_commands[0]
        assert isinstance(command, AnalyseSchemaPackage)
        assert (command.actor, command.source, command.package_id) == ("user:boss", "tui", ID)
        assert "Analysed Engineering, version 3.3.0." in screen_text(app)

    scenario(client, steps)


def test_a_status_line_names_the_package_in_technical_mode_only() -> None:
    client = client_with(analysed=False)

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        show_technical(app, screen, True)
        await pilot.press("a")
        await pilot.pause()
        text = screen_text(app)
        assert "Analysed co.acme.engineering@3.3.0." in text
        assert "Engineering, version" not in text.split("Analysed", 1)[1].split("\n", 1)[0]

    scenario(client, steps)


def test_submit_and_approve_each_run_their_command() -> None:
    client = client_with("InReview")

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        assert "Next: approve (y) or ask for changes (c)." in screen_text(app)
        await pilot.press("s")
        await pilot.pause()
        assert "Submitted Engineering, version 3.3.0 for review." in screen_text(app)
        await pilot.press("y")
        await pilot.pause()
        assert "Approved Engineering, version 3.3.0." in screen_text(app)
        kinds = [type(c) for c in client.schemareg_commands]
        assert kinds == [SubmitSchemaPackage, ApproveSchemaPackage]
        assert all(c.package_id == ID for c in client.schemareg_commands)  # type: ignore[attr-defined]

    scenario(client, steps)


def test_a_refusal_is_shown_and_nothing_is_recorded() -> None:
    client = client_with("InReview")
    client.is_admin = False  # type: ignore[attr-defined]  # approving is the administrator's

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        await pilot.press("y")
        await pilot.pause()
        text = screen_text(app)
        assert "! " in text and "admin" in text
        assert client.schemareg_commands == []
        assert isinstance(app.screen, SchemaReviewScreen)

    scenario(client, steps)


def test_sending_back_asks_for_a_reason_and_escape_sends_nothing() -> None:
    client = client_with("InReview")

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, PromptScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert client.schemareg_commands == [] and "Nothing sent back." in screen_text(app)
        await pilot.press("c")
        await pilot.pause()
        await pilot.press(*"Too wide", "enter")
        await pilot.pause()
        sent = client.schemareg_commands[0]
        assert isinstance(sent, RequestSchemaChanges) and sent.reason == "Too wide"
        assert "Sent Engineering, version 3.3.0 back to its author." in screen_text(app)

    scenario(client, steps)


def test_publishing_needs_the_word_typed() -> None:
    client = client_with("Approved")

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        assert "Next: publish (p)." in screen_text(app)
        await pilot.press("p")
        await pilot.pause()
        await pilot.press(*"yes", "enter")
        await pilot.pause()
        assert client.schemareg_commands == []
        assert "Not published: the word was not typed." in screen_text(app)
        await pilot.press("p")
        await pilot.pause()
        await pilot.press(*"publish", "enter")
        await pilot.pause()
        published = client.schemareg_commands[0]
        assert isinstance(published, PublishSchemaPackage) and published.package_id == ID
        assert published.auto_adopt is False
        assert "Published Engineering, version 3.3.0." in screen_text(app)

    scenario(client, steps)


def test_t_runs_the_sample_test_and_a_command_clears_it() -> None:
    client = client_with()
    client.seed_schema_sample(
        ID,
        SampleTestView(
            package="co.acme.engineering@3.3.0",
            scope="company",
            sample=1000,
            checked=40,
            newly_nonconformant=2,
            newly_warning=1,
            fixed=3,
            examples=[
                SampleExample(key="V-101", path="psets.a.c", rule="required", message="Missing.")
            ],
        ),
    )

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        await pilot.press("t")
        await pilot.pause()
        text = screen_text(app)
        assert "Tested Engineering, version 3.3.0  scope company  sample 1000  checked 40" in text
        assert "Newly nonconformant 2  newly warning 1  fixed 3" in text
        assert "V-101  A: c  required  Missing." in text
        show_technical(app, screen, True)
        assert "Tested co.acme.engineering@3.3.0  scope company  sample 1000  checked 40" in (
            screen_text(app)
        )
        show_technical(app, screen, False)
        await pilot.press("s")  # a sample belongs to the content it was made for
        await pilot.pause()
        assert "Not run: press t to test on a sample of records." in screen_text(app)

    scenario(client, steps)


def test_i_switches_to_the_impact_of_the_project_of_the_scope() -> None:
    client = client_with()
    entry = ImpactEntry(
        section="views", target="valves", change="column_removed", count=None, detail="A view."
    )
    client.seed_schema_impact(
        "P123",
        "co.acme.engineering",
        "3.3.0",
        ImpactReport(
            scope="project:P123",
            old_hash=None,
            new_hash="c" * 64,
            changed_paths=(),
            entries=(entry,),
            counts={"views": 1},
            truncated=False,
        ),
    )

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        await pilot.press("i")
        await pilot.pause()
        text = screen_text(app)
        assert "Impact in P123" in text and "Scope project:P123" in text
        assert "views  valves  column_removed  -  A view." in text
        await pilot.press("i")
        await pilot.pause()
        assert "Impact (stored)" in screen_text(app)

    scenario(client, steps)


def test_the_company_scope_has_no_project_to_pin_it_in() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        await pilot.press("i")
        await pilot.pause()
        assert "The scope is the company: no project to pin it in." in screen_text(app)

    scenario(client_with(), steps, scope="company")


def test_a_package_that_cannot_be_read_is_said_and_the_keys_do_nothing() -> None:
    client = client_with()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: SchemaReviewScreen) -> None:
        text = screen_text(app)
        assert "This package version could not be read." in text and "! " in text
        await pilot.press("a", "s", "t", "y", "p")
        await pilot.pause()
        assert client.schemareg_commands == [] and isinstance(app.screen, SchemaReviewScreen)

    scenario(client, steps, ref="nope")


def test_the_key_hints_fit_an_80_column_terminal() -> None:
    assert all(len(line) <= 80 for line in SchemaReviewScreen.KEY_HINTS.splitlines())
