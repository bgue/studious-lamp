"""Where the terminal opens after sign-in (P2-I5 T06c2): the pure ``landing`` over ``FakeClient``,
and the app's first screen through the Textual pilot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from fakes import FakeClient
from fakes_iwp import PROJECT, seed_iwp
from helpers import run_pilot, settle
from textual.pilot import Pilot
from tl_core.services.errors import ServiceError
from tl_tui.app import TlApp
from tl_tui.landing import landing
from tl_tui.widgets.iwp_register import IwpRegisterScreen

if TYPE_CHECKING:
    from tl_tui.client import ClientInterface

KEY = "tui.landing"
FOREMAN = "user:sue"  # foreman of PIP-0002 and CIV-0001
PLAIN = "user:kim"  # foreman of no IWP
SIZE = (170, 44)


def seeded() -> FakeClient:
    client = FakeClient()
    seed_iwp(client)
    return client


class RaisingClient(FakeClient):
    """Every read of a setting or an IWP fails the way a down server does."""

    def get_setting(self, key: str, **kwargs: Any) -> Any:
        raise ServiceError("the settings are unavailable")

    def list_iwps(self, project: str, **kwargs: Any) -> Any:
        raise ServiceError("the IWPs are unavailable")


# --- the pure decision -------------------------------------------------------------------------


def test_unset_and_a_foreman_lands_on_iwp_mine() -> None:
    assert landing(seeded(), PROJECT, FOREMAN) == "iwp_mine"


def test_unset_and_no_iwp_lands_on_default() -> None:
    assert landing(seeded(), PROJECT, PLAIN) == "default"


def test_user_set_default_stays_default_for_a_foreman() -> None:
    client = seeded()
    client.seed_setting(KEY, "user:sue", "default")
    assert landing(client, PROJECT, FOREMAN) == "default"


def test_user_set_iwp_mine_lands_on_iwp_mine_without_any_iwp() -> None:
    client = seeded()
    client.seed_setting(KEY, "user:kim", "iwp_mine")
    assert landing(client, PROJECT, PLAIN) == "iwp_mine"


class ViewAt:
    """A client whose setting read answers with one origin: ``tui.landing`` has no company layer
    in the platform file (scopes: platform, user), so the company case is a stubbed view."""

    def __init__(self, origin: str, value: str) -> None:
        self.origin = origin
        self.value = value

    def get_setting(self, key: str, **kwargs: Any) -> Any:
        return SimpleNamespace(effective=SimpleNamespace(origin=self.origin, value=self.value))

    def list_iwps(self, project: str, **kwargs: Any) -> list[Any]:
        return [object()]  # a foreman on an IWP: the default must not win over a chosen value


def test_a_company_set_value_is_honoured() -> None:
    assert landing(cast("ClientInterface", ViewAt("company", "iwp_mine")), PROJECT, PLAIN) == (
        "iwp_mine"
    )
    assert landing(cast("ClientInterface", ViewAt("company", "default")), PROJECT, FOREMAN) == (
        "default"
    )


def test_a_raising_client_lands_on_default() -> None:
    assert landing(RaisingClient(), PROJECT, FOREMAN) == "default"


# --- the app's first screen --------------------------------------------------------------------

Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def run(app: TlApp, steps: Step) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=SIZE)


def test_a_foreman_opens_on_the_iwp_log_filtered_to_mine() -> None:
    seen: dict[str, Any] = {}
    app = TlApp(seeded(), scope=f"project:{PROJECT}", actor=FOREMAN)

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        seen["screen"] = app.screen
        assert isinstance(app.screen, IwpRegisterScreen)
        seen["summary"] = app.screen.summary_text()
        seen["mine"] = getattr(app.screen, "mine", None)
        await pilot.press("escape")
        await settle(pilot)
        seen["depth_after_esc"] = len(app.screen_stack)
        seen["after_esc"] = app.screen

    run(app, steps)
    assert isinstance(seen["screen"], IwpRegisterScreen)
    assert seen["mine"] is True
    assert seen["summary"].startswith("2 of 4 IWPs, foreman ")
    assert seen["depth_after_esc"] == 1
    assert not isinstance(seen["after_esc"], IwpRegisterScreen)


def test_a_plain_user_opens_as_before() -> None:
    seen: dict[str, Any] = {}
    app = TlApp(seeded(), scope=f"project:{PROJECT}", actor=PLAIN)

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        seen["screen"] = app.screen
        seen["depth"] = len(app.screen_stack)

    run(app, steps)
    assert not isinstance(seen["screen"], IwpRegisterScreen)
    assert seen["depth"] == 1


def test_no_project_scope_pushes_nothing() -> None:
    seen: dict[str, Any] = {}
    app = TlApp(seeded(), scope="company:ACME", actor=FOREMAN)

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        seen["depth"] = len(app.screen_stack)
        seen["screen"] = app.screen

    run(app, steps)
    assert seen["depth"] == 1
    assert not isinstance(seen["screen"], IwpRegisterScreen)
