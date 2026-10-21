"""The integration registry screen on the fake client, driven with a pilot (P1-I7-T07, which holds
the endpoint views of T04c). Provided; do not edit.

The screen shows one table at a time, switches an app, endpoint, rule or enricher on or off with
the command that does it, retries a failed delivery, shows the kill switch, and leaves a refusal
visible without changing anything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import rows_integration as rows
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_tui.app import TlApp
from tl_tui.widgets.integration_screen import IntegrationScreen


def full_client() -> FakeClient:
    client = FakeClient()
    client.seed_integration("apps", **rows.app())
    client.seed_integration("endpoints", **rows.endpoint())
    client.seed_integration("endpoints", **rows.endpoint(endpoint_id="ep-2", name="photos"))
    client.seed_integration("rules", **rows.rule())
    client.seed_integration("actions", **rows.action())
    client.seed_integration("enrichers", **rows.enricher())
    client.seed_integration("invocations", **rows.invocation())
    client.seed_integration("deliveries", **rows.delivery())
    client.seed_integration(
        "deliveries",
        **rows.delivery(delivery_id="01JDELIVERYBBBBBBB2", state="completed", error_code=None),
    )
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[Any], TlApp, IntegrationScreen], Awaitable[None]],
    *,
    is_admin: bool = True,
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:boss", is_admin=is_admin)

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert isinstance(app.screen, IntegrationScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def table(screen: IntegrationScreen) -> DataTable[str]:
    return screen.query_one("#integration-table", DataTable)


def test_ctrl_e_opens_on_the_endpoints_and_escape_closes() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        text = screen_text(app)
        assert "Endpoints (2)" in text and "[1 Endpoints]" in text
        assert "acme-nde/results" in text and "acme-nde/photos" in text
        assert "Path        /in/acme-nde/results" in text  # the detail of the first row
        assert "Acts as     a service" in text  # plain: no service label is known here
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, IntegrationScreen)

    scenario(full_client(), steps)


def test_only_an_admin_opens_it_and_it_says_why_not() -> None:
    app = TlApp(full_client(), scope=SCOPE, actor="user:kim", is_admin=False)

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert not isinstance(app.screen, IntegrationScreen)
        assert "The integration registry needs the admin role" in screen_text(app)

    run_pilot(app, go)


def test_the_keys_switch_the_table() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        expected = {
            "2": ("Rules (1)", "hse-notify"),
            "3": ("Actions (1)", "send_to_nde"),
            "4": ("Enrichers (1)", "doc_classifier"),
            "5": ("Apps (1)", "Acme NDE"),
            "6": ("Invocations (1)", "send_to_nde"),
            "7": ("Error queue (2)", "Mapping failed"),
            "1": ("Endpoints (2)", "acme-nde/results"),
        }
        for key, (title, cell) in expected.items():
            await pilot.press(key)
            await pilot.pause()
            text = screen_text(app)
            assert title in text and cell in text, key
        await pilot.press("right_square_bracket")  # 1 -> 2
        await pilot.press("left_square_bracket", "left_square_bracket")  # 2 -> 1 -> 7 (wraps)
        await pilot.pause()
        assert "Error queue (2)" in screen_text(app)

    scenario(full_client(), steps)


def test_the_error_queue_names_each_endpoint_by_its_path() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        await pilot.press("7")
        await pilot.pause()
        text = screen_text(app)
        assert "acme-nde/results" in text and "! Failed" in text and "✓ Completed" in text
        assert "Mapping failed: no weld in the payload" in text
        assert "Endpoint    acme-nde/results" in text and "v2" not in text
        await pilot.press("ctrl+d")  # technical details on: the id, version and error code again
        await pilot.pause()
        text = screen_text(app)
        assert "mapping_failed: no weld in the payload" in text
        assert "Endpoint    acme-nde/results v2" in text

    scenario(full_client(), steps)


def test_the_kill_switch_is_in_the_title_and_loud_when_on() -> None:
    async def steps_off(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        assert "Kill switch: off" in screen_text(app)

    scenario(full_client(), steps_off)
    client = full_client()
    client.seed_setting("integration.kill_switch", "company", True)

    async def steps_on(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        assert "! KILL SWITCH ON: nothing runs" in screen_text(app)

    scenario(client, steps_on)


def test_e_switches_a_rule_on_with_enable_rule_and_off_with_disable_rule() -> None:
    client = full_client()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        await pilot.press("2", "e")
        await pilot.pause()
        assert client.integration_calls == [("EnableRule", SCOPE, {"rule_id": "rule-1"})]
        assert "✓ on" in screen_text(app) and "Enabled hse-notify" in screen_text(app)
        await pilot.press("e")
        await pilot.pause()
        assert client.integration_calls[-1] == ("DisableRule", SCOPE, {"rule_id": "rule-1"})
        assert "✗ off" in screen_text(app)

    scenario(client, steps)


def test_e_switches_an_endpoint_an_enricher_and_an_app_with_their_commands() -> None:
    client = full_client()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        await pilot.press("down", "e")  # the second endpoint, photos: on -> off
        await pilot.press("4", "e", "5", "e")
        await pilot.pause()
        assert client.integration_calls == [
            ("SetInboundEndpointEnabled", SCOPE, {"endpoint_id": "ep-2", "enabled": False}),
            ("SetEnricherEnabled", SCOPE, {"enricher_id": "enr-1", "enabled": False}),
            ("SetIntegrationAppEnabled", SCOPE, {"app_id": "app-1", "enabled": False}),
        ]
        assert "Disabled Acme NDE" in screen_text(app).replace("acme-nde", "Acme NDE")

    scenario(client, steps)


def test_actions_invocations_and_retired_rows_are_not_switched() -> None:
    client = full_client()
    client.seed_integration("rules", **rows.rule(rule_id="rule-2", key="old", retired=True))

    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        await pilot.press("3", "e")
        await pilot.pause()
        assert "Actions are not switched here." in screen_text(app)
        await pilot.press("2", "down", "e")  # the retired rule
        await pilot.pause()
        assert "This one is retired and cannot be switched." in screen_text(app)
        assert "✗ retired" in screen_text(app)
        assert client.integration_calls == []

    scenario(client, steps)


def test_y_retries_a_failed_delivery_and_only_on_the_error_queue() -> None:
    client = full_client()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        await pilot.press("y")
        await pilot.pause()
        assert "Retry is on the error queue (key 7)." in screen_text(app)
        assert client.integration_calls == []
        await pilot.press("7", "y")
        await pilot.pause()
        assert client.integration_calls == [
            ("RetryInboundDelivery", SCOPE, {"delivery_id": "01JDELIVERYAAAAAAA1"})
        ]
        text = screen_text(app)
        assert "Queued the delivery again." in text and "… Queued" in text

    scenario(client, steps)


def test_a_stale_switch_is_refused_shown_and_the_table_read_again() -> None:
    client = full_client()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        await pilot.press("2")
        await pilot.pause()
        assert "✗ off" in screen_text(app)
        client._integration["rules"][0]["enabled"] = True  # pyright: ignore
        await pilot.press("e")  # the screen asks EnableRule; the rule is on already
        await pilot.pause()
        text = screen_text(app)
        assert client.integration_calls == [("EnableRule", SCOPE, {"rule_id": "rule-1"})]
        assert "! already on" in text and "✓ on" in text

    scenario(client, steps)


def test_a_non_admin_session_sees_the_services_refusal() -> None:
    client = full_client()
    client.is_admin_integration = False

    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        await pilot.press("2", "e")
        await pilot.pause()
        assert "! EnableRule needs the admin role" in screen_text(app)
        await pilot.press("7")
        await pilot.pause()
        assert "! this needs the admin role" in screen_text(app)
        assert table(screen).row_count == 0

    scenario(client, steps)


def test_the_selection_survives_a_reload() -> None:
    client = full_client()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: IntegrationScreen) -> None:
        await pilot.press("down")
        client.seed_integration("endpoints", **rows.endpoint(endpoint_id="ep-3", name="zzz"))
        await pilot.press("f5")
        await pilot.pause()
        assert table(screen).row_count == 3 and table(screen).cursor_row == 1
        assert "Reloaded." in screen_text(app)

    scenario(client, steps)
