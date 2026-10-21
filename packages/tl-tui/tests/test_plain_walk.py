"""Every screen the key map opens, walked as a plain user and as an admin (P1-UX-T11).

The walk presses each App key of ``KEYMAP`` from the grid, then again with a record open, reads
the screen after each key, presses the view-only keys the screen lists in its ``KEY_HINTS``, and
escapes back to the grid. The leak finder (``find_technical``) must find nothing in plain mode, and
Ctrl+D must bring technical text up and take it away again.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

import rows_integration as rows
from fakes import SCOPE, FakeClient
from fakes_correspondence import seed_correspondence, seed_domains
from fakes_schemareg import make_package
from helpers import run_pilot, screen_text
from textual.binding import Binding
from textual.pilot import Pilot
from tl_tui.app import TlApp
from tl_tui.display import Labels, find_technical, key_hits
from tl_tui.keymap import KEYMAP, KeyEntry, help_text
from tl_tui.labels_load import load_labels, schema_keys
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.help_screen import HelpScreen
from tl_tui.widgets.record_view import RecordView

# Keys the walk does not press, with the reason. A new App binding must be walked or listed here.
# The last four are aliases of walked keys (the same action under a second key).
EXCLUDED: dict[str, str] = {
    "ctrl+q": "quits",
    "escape": "closes a panel",
    "ctrl+d": "tested below",
    "question_mark": "same action as f1",
    "colon": "same action as ctrl+p",
    "alt+right": "forward in history; the walk goes back only",
    "shift+f6": "cycles panels backwards; f6 is walked",
}

# Leaks found in merged screens that a follow-up will fix: binding -> the token it shows.
# Empty: the F11 Schema column is plain in plain mode since T11 (D41). Add an entry only with a
# follow-up named in the report, never to get a run green.
KNOWN_LEAKS: dict[str, str] = {}

# The footer line that says the Ctrl+D mode. It changes on every toggle, so the admin walk compares
# the screens without it.
MODE_STATUS = re.compile(r"Technical details (?:on|off)")

# Screens whose world shows technical details: each differs under Ctrl+D in at least one reading.
MUST_CHANGE: dict[str, str] = {
    "f2": "grid: the Type and Ver cells",
    "f5": "correspondence: record id and clocks",
    "f7": "document register: the record id",
    "f8": "tag register: area=47 mnemonic=FV segments",
    "f9": "settings: the layer key",
    "f11": "derived documents: the schema package and version",
    "f12": "schedule: the snapshot code",
    "ctrl+g": "domain: RFI, commercial and evidence rows with clocks (calendar P123-default@1)",
    "ctrl+o": "schema workbench: the package and version",
}

# Screens that may stay unchanged under Ctrl+D (one-line reason each). Any other reading that
# Ctrl+D leaves unchanged fails the admin walk, so a new unchanged screen gets a decision.
UNCHANGED_OK: dict[str, str] = {
    "f1": "help is the static key map text (help_text); nothing technical is on it",
}

# The view-only keys a walk presses: digits, t, m, h. Any other key a screen lists is not pressed.
VIEW_KEYS = frozenset("12345tmh")

# Registers whose first row the walk opens (Enter), to read the record screen and its tabs.
REGISTER_KEYS = frozenset({"f5", "f7", "f8", "f11", "f12", "ctrl+r", "ctrl+g"})

GRID_STEPS = 8


class Seen(NamedTuple):
    """One reading: the key that led there, the screen class, and the rendered text."""

    binding: str
    screen: str
    text: str


def walk_keys() -> list[KeyEntry]:
    """The App keys the walk presses, in key map order."""
    return [
        entry
        for entry in KEYMAP
        if entry.context == "App" and entry.binding and entry.binding not in EXCLUDED
    ]


def app_binding_keys() -> set[str]:
    keys: set[str] = set()
    for binding in TlApp.BINDINGS:
        raw = binding.key if isinstance(binding, Binding) else binding[0]
        keys.update(raw.split(","))
    return keys


def world() -> FakeClient:
    """The fake project the walk runs on: records, documents, tags, correspondence, schedule,
    derived documents, integration rows and accounts, so that every register has rows."""
    client = FakeClient.with_valve_example()
    client.seed_documents("P123")
    # The fake's readable record id (DOC-ISO-1234) is not what the server issues; a ULID is.
    iso = client.get_document("P123", "ISO-1234")
    ulid = "01J7K2M8Q4T6V9W3X5Y8Z1A2B4"
    client.add_document("P123", iso.model_copy(update={"id": ulid}))
    client.add_stored_record(ulid, "ISO-1234", "documents.Document", iso.title)
    for number, class_code, conformance in (
        ("47-FV-1001", "ControlValve", "nonconformant"),
        ("47-HV-1003", "ManualValve", "ok"),
    ):
        tag = client.add_tag("P123", number, class_code=class_code, conformance=conformance)
        client.add_stored_record(tag.id, tag.number, "engineering.Tag", tag.title or number)
    seed_correspondence(client, "P123")
    seed_domains(client)  # RFI log, Commercial and Evidence rows, with clocks on P123-default@1
    client.seed_schema_package(make_package("co.acme.engineering", "3.2.0", "Published"))
    client.seed_schedule("P123")
    # The registers open these records on Enter; without them the record screen reads "No record".
    client.add_stored_record("SCHED-MAIN", "MAIN", "schedule.Schedule", "MAIN schedule")
    client.add_stored_record(
        "ID-P123-COR-0001", "P123-COR-0001", "correspondence.Correspondence", "Revised programme"
    )
    client.seed_derivation("P123")
    client.seed_integration("apps", **rows.app())
    client.seed_integration("endpoints", **rows.endpoint())
    client.seed_integration("rules", **rows.rule())
    client.seed_integration("actions", **rows.action())
    client.seed_integration("enrichers", **rows.enricher())
    client.seed_integration("invocations", **rows.invocation())
    client.seed_integration("deliveries", **rows.delivery())
    client.seed_integration("enrichments", **rows.enrichment())
    client.seed_account("boss", roles=["admin", "user"])
    client.seed_account("amy", display_name="Amy A")
    bot = client.seed_account("triage", kind="agent")
    client.issue_agent_token(bot.account_id, "mcp", expires_in_days=90)
    return client


def view_keys(app: TlApp) -> list[str]:
    """The view-only keys the open screen lists in its KEY_HINTS (``1-5`` is a range)."""
    keys: list[str] = []
    for widget in [app.screen, *app.screen.walk_children()]:
        if isinstance(widget, RecordGrid):
            continue
        hints: Any = getattr(widget, "KEY_HINTS", None)
        if not isinstance(hints, str):
            continue
        for token in hints.split():
            span = re.fullmatch(r"(\d)-(\d)", token)
            if span:
                keys.extend(str(n) for n in range(int(span.group(1)), int(span.group(2)) + 1))
            elif token in VIEW_KEYS:
                keys.append(token)
    return list(dict.fromkeys(keys))


def read(app: TlApp, binding: str) -> Seen:
    screen = type(app.screen).__name__
    if isinstance(app.screen, HelpScreen):
        return Seen(binding, screen, help_text())
    return Seen(binding, screen, screen_text(app))


async def settle(pilot: Pilot[Any]) -> None:
    await pilot.pause()
    await pilot.pause()


def at_grid(app: TlApp) -> bool:
    """No modal on the stack and no record open (a record view leaves the DOM when closed)."""
    return len(app.screen_stack) == 1 and not app.query(RecordView)


async def to_grid(pilot: Pilot[Any], app: TlApp, where: str) -> None:
    for _ in range(GRID_STEPS):
        await settle(pilot)
        if at_grid(app):
            break
        # Escape closes an open record only when focus is inside it; a panel the walk focused
        # (F3, F6) would keep the record open, so move the focus back to the record first.
        for open_record in app.query(RecordView):
            open_record.focus()
            await settle(pilot)
            break
        await pilot.press("escape")
    await settle(pilot)
    stack = [type(s).__name__ for s in app.screen_stack]
    records = len(app.query(RecordView))
    assert at_grid(app), f"{where}: no grid after escape; stack {stack}, record views {records}"
    # Escape can leave the focus on a panel the walk opened with F3 or F6; focus the grid again.
    app.query_one(RecordGrid).focus()
    await settle(pilot)


async def read_with_view_keys(pilot: Pilot[Any], app: TlApp, binding: str) -> list[Seen]:
    seen = [read(app, binding)]
    for key in view_keys(app):
        await pilot.press(key)
        await settle(pilot)
        seen.append(read(app, binding))
    return seen


async def walk(pilot: Pilot[Any], app: TlApp) -> list[Seen]:
    """Every walked key, from the grid and with a record open; returns each reading."""
    seen: list[Seen] = []
    for entry in walk_keys():
        key = entry.binding
        assert key is not None
        for record_open in (False, True):
            where = f"{key} (record open)" if record_open else key
            await to_grid(pilot, app, where)
            if record_open:
                await pilot.press("home", "enter")
                await settle(pilot)
            await pilot.press(key)
            await settle(pilot)
            seen.extend(await read_with_view_keys(pilot, app, key))
            if key in REGISTER_KEYS:
                await pilot.press("enter")
                await settle(pilot)
                seen.extend(await read_with_view_keys(pilot, app, key))
        await to_grid(pilot, app, f"{key} (end)")
    return seen


def content(text: str) -> str:
    """The screen as the toggle sees it: the mode's status line and the whitespace taken out."""
    return " ".join(MODE_STATUS.sub("", text).split())


def unexpected_hits(seen: list[Seen], labels: Labels, keys: list[str]) -> list[str]:
    """Technical tokens and schema keys in the walk that no KNOWN_LEAKS entry explains."""
    problems: dict[str, None] = {}
    for step in seen:
        known = KNOWN_LEAKS.get(step.binding)
        for token in [*find_technical(step.text, labels), *key_hits(step.text, keys)]:
            if token != known:
                problems[f"{step.binding} on {step.screen}: {token!r}"] = None
    return list(problems)


def test_every_app_key_is_walked_or_excluded() -> None:
    walked = {entry.binding for entry in walk_keys()}
    bound = app_binding_keys()
    for key in sorted(bound):
        assert key in walked or key in EXCLUDED, f"{key} is neither walked nor excluded"
    for key in sorted(walked):
        assert key in bound, f"{key} is walked but TlApp has no such binding"


def test_plain_user_walk_has_no_technical_text() -> None:
    client = world()
    labels = load_labels(client, SCOPE)
    app = TlApp(client, scope=SCOPE, actor="user:kim", is_admin=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        seen = await walk(pilot, app)
        problems = unexpected_hits(seen, labels, schema_keys(client, SCOPE, labels))
        assert problems == [], "technical text in the plain walk:\n" + "\n".join(problems)
        for binding, token in KNOWN_LEAKS.items():
            present = [s for s in seen if s.binding == binding]
            assert any(token in find_technical(s.text, labels) for s in present), (
                f"KNOWN_LEAKS entry {binding}: {token} no longer shows; remove the entry"
            )

    run_pilot(app, scenario)


def walk_after(toggles: int) -> tuple[list[Seen], bool]:
    """The whole walk on a fresh admin app, after Ctrl+D is pressed ``toggles`` times.

    Each walk starts from the same screen (a new app on the same world), so the readings of two
    walks differ only by what Ctrl+D did. Returns the readings and the mode at the end.
    """
    app = TlApp(world(), scope=SCOPE, actor="user:kim", is_admin=True)
    out: list[Seen] = []

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        for _ in range(toggles):
            await pilot.press("ctrl+d")
            await settle(pilot)
        out.extend(await walk(pilot, app))

    run_pilot(app, scenario)
    return out, app.display_mode.technical


def keys_of(seen: list[Seen]) -> list[str]:
    return sorted({s.binding for s in seen})


def test_admin_ctrl_d_walk_shows_technical_text_then_hides_it() -> None:
    client = world()
    labels = load_labels(client, SCOPE)
    keys = schema_keys(client, SCOPE, labels)
    plain, plain_mode = walk_after(0)
    technical, technical_mode = walk_after(1)
    back, back_mode = walk_after(2)
    assert (plain_mode, technical_mode, back_mode) == (False, True, False)

    assert unexpected_hits(plain, labels, keys) == [], "technical text in the plain walk"
    assert unexpected_hits(back, labels, keys) == [], "technical text after Ctrl+D is off again"
    keys = [(s.binding, s.screen) for s in plain]
    assert [(s.binding, s.screen) for s in technical] == keys, "walk on reached other screens"
    assert [(s.binding, s.screen) for s in back] == keys, "walk back off reached other screens"

    # Ctrl+D on then off gives back the plain screens, reading for reading.
    mismatched = [
        f"{a.binding} on {a.screen}"
        for a, b in zip(plain, back, strict=True)
        if content(a.text) != content(b.text)
    ]
    assert mismatched == [], "Ctrl+D off does not give back the plain screens:\n" + "\n".join(
        mismatched
    )

    # Each MUST_CHANGE screen differs under Ctrl+D in at least one reading.
    changed = {
        t.binding
        for t, a in zip(technical, plain, strict=True)
        if content(t.text) != content(a.text)
    }
    missing = [f"{key} ({why})" for key, why in MUST_CHANGE.items() if key not in changed]
    assert missing == [], "Ctrl+D does not change these screens:\n" + "\n".join(missing)

    # A screen (binding) that no reading of Ctrl+D changes must be listed in UNCHANGED_OK, and a
    # listed screen must stay unchanged. A single reading that is the same in both modes is fine:
    # a panel open at 120 columns has no room for a technical cell, for example.
    changed_keys = {
        t.binding
        for t, a in zip(technical, plain, strict=True)
        if content(t.text) != content(a.text)
    }
    unlisted = sorted(set(keys_of(plain)) - changed_keys - set(UNCHANGED_OK))
    assert unlisted == [], "no reading changes under Ctrl+D, and not in UNCHANGED_OK: " + ", ".join(
        unlisted
    )
    stale = sorted(set(UNCHANGED_OK) & changed_keys)
    assert stale == [], "UNCHANGED_OK lists screens that Ctrl+D changes now: " + ", ".join(stale)
    assert not set(MUST_CHANGE) & set(UNCHANGED_OK), "a screen is in both lists"

    # The record screen shows its version in the header only with technical details on.
    assert any("· v1" in s.text for s in technical if s.screen == "RecordScreen"), "record header"
    assert not any("· v1" in s.text for s in plain + back if s.screen == "RecordScreen")


def test_schema_keys_come_from_the_labels_and_the_schema() -> None:
    client = world()
    keys = schema_keys(client, SCOPE, load_labels(client, SCOPE))
    assert {"core.Record", "engineering.Tag", "valve_data.body_material"} <= set(keys)
    assert "psets.valve_data.body_material" in keys
    assert all("." in key for key in keys)


def test_key_check_finds_a_type_key_and_a_property_key_in_plain_text() -> None:
    client = world()
    keys = schema_keys(client, SCOPE, load_labels(client, SCOPE))
    clean = "Valve data: body material SS316L, flow 2 m/s. Done. Type: Tag"
    assert key_hits(clean, keys) == []
    assert key_hits(f"{clean} core.Record", keys) == ["core.Record"]
    assert key_hits("Type engineering.Tag here", keys) == ["engineering.Tag"]
    assert key_hits("valve_data.body_material = CS", keys) == ["valve_data.body_material"]
    assert key_hits("xcore.Record", keys) == []  # inside a longer name
    assert key_hits("core.Records", keys) == []
    assert key_hits("my.core.Record", keys) == []


def test_walk_fails_when_a_plain_screen_shows_a_type_key() -> None:
    client = world()
    labels = load_labels(client, SCOPE)
    keys = schema_keys(client, SCOPE, labels)
    app = TlApp(client, scope=SCOPE, actor="user:kim", is_admin=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await pilot.press("f7")
        await settle(pilot)
        step = read(app, "f7")
        assert unexpected_hits([step], labels, keys) == []
        leaked = Seen(step.binding, step.screen, step.text + "\ncore.Record")
        assert unexpected_hits([leaked], labels, keys) == [
            "f7 on DocumentRegisterScreen: 'core.Record'"
        ]

    run_pilot(app, scenario)


def test_walk_reaches_the_screens() -> None:
    client = world()
    app = TlApp(client, scope=SCOPE, actor="user:kim", is_admin=True)
    expected = {
        "f1": "HelpScreen",
        "f7": "DocumentRegisterScreen",
        "f8": "TagRegisterScreen",
        "f5": "CorrespondenceScreen",
        "f12": "ScheduleScreen",
        "ctrl+r": "ReviewQueueScreen",
        "ctrl+e": "IntegrationScreen",
        "ctrl+o": "SchemaWorkbenchScreen",
        "f9": "SettingsScreen",
        "f10": "AdminScreen",
        "ctrl+g": "DomainScreen",
    }

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        seen = await walk(pilot, app)
        reached = {(s.binding, s.screen) for s in seen}
        missing = [
            f"{key} -> {name}" for key, name in expected.items() if (key, name) not in reached
        ]
        assert missing == [], f"the walk did not reach: {missing}"

    run_pilot(app, scenario)
