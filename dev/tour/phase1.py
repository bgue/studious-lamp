"""The Phase 1 screenshot tour: what P1-I0 to P1-I8 added to the platform core.

    uv run python dev/tour/phase1.py [--out docs/reports/tour/phase-1]

Same method as `phase0.py` (see its docstring and `tourkit.py`): a fresh SQLite ledger in a
temporary directory, the real TUI driven headless, the real `tl` commands, an MCP server and an API
client run in this process, SVG screenshots out. Every `tl` command here runs as a named person with
their own signed-in session (`demo`, an admin; `amy`, `ana` and `ben`, plain users; `dora`, who
holds the document controller role when a section needs it), the way the P1 demos do. Passwords are
the documented dev ones and are only ever typed through stdin.

It covers P1-I0 (identity and admin), P1-I1 (standards and engineering tags), P1-I2 and P1-I2b
(document control and its controller role), P1-I3 (the derivation pipeline), P1-I4 (schedules and
cost), P1-I5 (correspondence), P1-I6 (RFIs and commercial notices), P1-I7 (the integration layer
and record threads) and P1-I8 (the schema registry and workbench, waivers and the conformance
dashboard, legacy loads and the lake marts). The sample files come from the helpers of the matching
demos (`dev/demos/p1_i*_demo.py`). The text is
`docs/reports/PHASE-1-TOUR.md`; its section numbers match the file names written here.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib
import io
import os
import shutil
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import tourkit as tk
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, SelectionList
from tourkit import Shell, Transcript, Workspace, expect

REPO = Path(__file__).resolve().parents[2]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
P = ("--project", PROJECT)
PASSWORDS = {  # made-up dev passwords for made-up people
    "demo": "demo",
    "amy": "a long passphrase for amy",
    "ana": "a long passphrase for ana",
    "ben": "a long passphrase for ben",
    "dora": "a long passphrase for dora",
}
NEEDS = "needs the document_controller or admin role"
STANDARDS = "standards/co.acme.standards@1.0.0.yaml"
DOC_STANDARDS = "standards/co.acme.documents@1.0.0.yaml"
TAG_MAPPING = "templates/tag-list-instrument-index.yaml"
TAG_FILE = "legacy/instrument-index.csv"
DMS_MAPPING = "templates/document-register-dms-export.yaml"
DMS_FILE = "legacy/dms-document-register.csv"


# --- setup -----------------------------------------------------------------------------------


def stage_files(ws: Workspace) -> None:
    """Copy the sample standards, legacy files and mappings next to the ledger (short paths)."""
    for source, target in (
        ("schema/fixtures/standards", "standards"),
        ("dev/seed/legacy", "legacy"),
        ("dev/seed/templates", "templates"),
    ):
        shutil.copytree(REPO / source, ws.root / target)
    for name in "ABCD":
        (ws.root / f"sheet-{name}.pdf").write_text(f"%PDF-1.7 sheet {name}\n")


def password(who: str) -> str:
    return PASSWORDS[who] + "\n"


def add_person(ws: Workspace, name: str, display: str) -> None:
    ws.tl(
        "admin",
        "user",
        "add",
        name,
        "--display-name",
        display,
        "--password-stdin",
        stdin=password(name),
        who="demo",
    )


def sign_in(ws: Workspace, who: str) -> None:
    ws.tl("login", who, "--password-stdin", stdin=password(who), who=who)


def renew_sessions(ws: Workspace) -> None:
    """Sign the people of the later sections in again: a session lasts twelve hours, and the
    frozen clock of a long tour moves on three minutes with every command."""
    for who in ("demo", "amy", "dora"):
        sign_in(ws, who)


def setup(ws: Workspace) -> None:
    """The ledger, the admin's session, and the two plain users. Not shown."""
    stage_files(ws)
    ws.tl("init", "--dev")
    sign_in(ws, "demo")
    add_person(ws, "amy", "Amy A")
    add_person(ws, "ana", "Ana B")
    sign_in(ws, "amy")
    sign_in(ws, "ana")
    tk.CLOCK.advance(minutes=30)


def build_app(
    ws: Workspace, *, admin: bool = False, actor: str = "user:demo", controller: bool = False
) -> Any:
    from tl_tui.main import build_app as make

    return make(
        ws.db, PROJECT, live=False, actor=actor, is_admin=admin, is_controller=controller or admin
    )


# --- 01 sign-in ------------------------------------------------------------------------------


def section_sign_in(ws: Workspace) -> None:
    from tl_tui.embedded import EmbeddedAuthenticator
    from tl_tui.sign_in import SignInApp

    authenticator = EmbeddedAuthenticator.for_target(str(ws.db))
    app = SignInApp(authenticator, target="ledger ./tl.db", hint=authenticator.demo_hint())

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.settle(pilot, 4)
        tk.shot_tui(
            ws, app, "01a-sign-in", "Sign in to Throughline (TUI)", "Sign in to Throughline", "demo"
        )
        screen = app.screen
        screen.query_one("#sign-in-username", Input).value = "amy"
        screen.query_one("#sign-in-password", Input).value = "not her passphrase"
        await pilot.press("enter", "enter")  # username to password, then submit
        await tk.until(pilot, lambda: "invalid" in tk.screen_text(app).lower(), "the refusal")
        tk.shot_tui(
            ws,
            app,
            "01b-sign-in-refused",
            "A wrong password is refused, with no hint which half",
            "invalid username or password",
        )

    tk.run_tui(ws, app, scenario, size=(100, 30))

    sh = Shell(ws, "Sessions: who you are, and what that allows", 118)
    sh.note("each person has their own session file, as on their own machine")
    sh.run("whoami", who="amy")
    sh.run("admin", "user", "ls", who="amy", ok=False)
    sh.run("whoami", who="demo")
    sh.run("admin", "user", "ls", who="demo")
    ws.save("01c-sessions-cli", sh.transcript.svg())


# --- 02 accounts, roles and agent tokens -----------------------------------------------------


def section_accounts(ws: Workspace) -> str:
    """An admin adds a person and an agent and issues the agent a token; returns the token."""
    sh = Shell(ws, "Accounts and agent tokens, as an admin", 118)
    sh.run(
        "admin",
        "user",
        "add",
        "ben",
        "--display-name",
        "Ben C",
        "--password-stdin",
        stdin=password("ben"),
        who="demo",
        show="tl admin user add ben --display-name 'Ben C' --password-stdin",
    )
    sh.run("admin", "user", "add", "triage", "--kind", "agent", who="demo")
    issued = ws.tl("admin", "token", "issue", "triage", "--label", "triage assistant", who="demo")
    token = issued.splitlines()[0].strip()
    expect(token.startswith("tla_"), "no agent token was issued")
    sh.transcript.command("tl admin token issue triage --label 'triage assistant'", "demo")
    sh.transcript.output(tk.redact(issued, "tla_"))
    sh.run("admin", "token", "ls", who="demo")
    sh.run("admin", "user", "ls", who="demo")
    ws.save("02a-accounts-cli", sh.transcript.svg())

    app = build_app(ws, admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await pilot.press("f10")
        await tk.until(pilot, lambda: "triage" in tk.screen_text(app), "the accounts screen")
        tk.shot_tui(
            ws,
            app,
            "02b-admin-accounts",
            "F10: accounts and their roles (admins only)",
            "demo",
            "amy",
            "triage",
        )
        await pilot.press("t")
        await tk.until(pilot, lambda: "triage assistant" in tk.screen_text(app), "the tokens view")
        tk.shot_tui(
            ws,
            app,
            "02c-admin-tokens",
            "F10, t: agent tokens: label, expiry, state; never the token",
            "triage assistant",
        )

    tk.run_tui(ws, app, scenario)
    return token


# --- 03 lockout ------------------------------------------------------------------------------


def section_lockout(ws: Workspace) -> None:
    sh = Shell(ws, "Five wrong passwords lock the name", 118)
    for _ in range(5):
        sh.run("login", "ben", "--password-stdin", stdin="a wrong guess\n", who="ben", ok=False)
    sh.note("the sixth try uses the right passphrase and is still refused: the name is locked")
    sh.run("login", "ben", "--password-stdin", stdin=password("ben"), who="ben", ok=False)
    sh.run("admin", "user", "ls", who="demo")
    sh.run("admin", "audit", "--username", "ben", "--limit", "8", who="demo")
    sh.note("an admin on the machine clears it (there is deliberately no API for this)")
    sh.run("admin", "unlock", "ben", who="demo")
    sh.run("login", "ben", "--password-stdin", stdin=password("ben"), who="ben")
    ws.save("03-lockout", sh.transcript.svg())


# --- 04 an agent over MCP with a service token -----------------------------------------------


def section_agent(ws: Workspace, token: str) -> None:
    server, backend = tk.mcp_for_token(ws, token)
    t = Transcript("An agent with a service token: it proposes, a person decides", 118)
    try:
        t.comment("the host of the agent has the token in TL_AGENT_TOKEN; it is shown nowhere here")
        ws.tl("record", "create", *P, "--key", "FV-1002", "--title", "Reflux valve", who="amy")
        names = sorted(tool.name for tool in asyncio.run(server.list_tools()))
        for forbidden in ("accept_proposal", "reject_proposal"):
            expect(forbidden not in names, f"an agent has the tool {forbidden}")
        t.command("mcp tools/list   (as agent:triage)")
        t.output(" ".join(names))
        t.output("no accept_proposal, no reject_proposal: an agent cannot decide")
        t.blank()
        proposed = asyncio.run(
            tk.call_tool(
                server,
                "update_psets",
                record="FV-1002",
                scope=SCOPE,
                pset="valve_data",
                layer="standard",
                values={"size_in": 6, "manufacturer": "Acme Flow"},
            )
        )
        proposal = proposed["proposal"]
        t.command(
            'mcp tools/call update_psets {record: "FV-1002", pset: "valve_data", '
            'values: {size_in: 6, manufacturer: "Acme Flow"}}'
        )
        t.output(f"status: {proposal['status']}   by: {proposal['agent']}")
        t.output(proposed["message"])
        t.blank()
        pid = proposal["proposal_id"]
        for argv, who in (
            (("proposal", "ls", *P), "ana"),
            (("proposal", "accept", pid), "ana"),
        ):
            t.command("tl " + " ".join(argv), who)
            t.output(ws.tl(*argv, who=who))
        t.blank()
        t.comment("an admin revokes the token while the agent's MCP server is still running")
        tokens = ws.tl("admin", "token", "ls", who="demo")
        token_id = tokens.split()[0]
        t.command("tl admin token ls", "demo")
        t.output(tokens)
        t.command(f"tl admin token revoke {token_id}", "demo")
        t.output(ws.tl("admin", "token", "revoke", token_id, who="demo"))
        try:
            asyncio.run(tk.call_tool(server, "search_records", scope=SCOPE, q=""))
        except Exception as exc:  # noqa: BLE001 - the refusal is what the tour shows
            refusal = str(exc)
        else:
            raise tk.TourFailed("a revoked token still worked")
        expect("invalid or expired token" in refusal, f"unexpected refusal: {refusal}")
        t.blank()
        t.command('mcp tools/call search_records {scope: "project:P123"}   (the next call)')
        t.output(f"refused: {refusal}")
    finally:
        backend.close()
    ws.save("04-agent-service-token", t.svg())


# --- 05 the same services on Postgres (stored evidence) ---------------------------------------


def section_postgres(ws: Workspace) -> None:
    t = Transcript("Evidence kept from the P1-I0 gates (stored, not re-run by this tour)", 118)
    t.comment("figures copied from docs/reports/P1-I0.md; the tour itself uses SQLite only")
    t.command("just demo P1-I0")
    t.output("P1-I0 demo OK on: sqlite postgres")
    t.output("PASS 1 to 5 on each backend (the Postgres run uses a throw-away database)")
    t.command("just test-parity")
    t.output("3161 passed on SQLite and Postgres, 0 failed (1 h 0 min)")
    t.command("just test-tui")
    t.output("708 passed, 34 snapshots")
    ws.save("05-postgres-evidence", t.svg())


# --- 06 the standards registry ---------------------------------------------------------------


def section_standards(ws: Workspace) -> None:
    sh = Shell(ws, "The company standards registry", 118)
    sh.run("standards", "load", STANDARDS, "--dry-run", who="demo")
    sh.run("standards", "load", STANDARDS, who="demo")
    sh.run("standards", "load", STANDARDS, who="demo")
    sh.run("standards", "ls", "--kind", "code-list", who="amy")
    sh.run("standards", "values", "Area", who="amy")
    sh.run("standards", "class", "ls", who="amy")
    ws.save("06-standards-registry", sh.transcript.svg())
    ws.tl("standards", "load", DOC_STANDARDS, who="demo")


# --- 07 engineering tags ---------------------------------------------------------------------


def section_tags(ws: Workspace) -> None:
    sh = Shell(
        ws, "An engineering tag: parsed, checked against its class, renamed by supersession", 118
    )
    sh.run(
        "tag",
        "create",
        "47-FV-2001",
        "--class",
        "ControlValve",
        "--service",
        "Feed gas flow control",
        *P,
        who="demo",
    )
    sh.run("tag", "create", "47-XX-1", *P, who="demo", ok=False)
    sh.note("filling in the property set the class requires makes the tag conform")
    sh.run(
        "pset", "set", *P, "47-FV-2001", "valve_data", "manufacturer=Acme", "size_in=4", who="demo"
    )
    sh.run("tag", "show", "47-FV-2001", *P, who="demo")
    sh.run(
        "tag",
        "rename",
        "47-FV-2001",
        "47-FV-2002",
        "--reason",
        "renumbered by the design office",
        *P,
        who="demo",
    )
    sh.run("tag", "ls", *P, "--all", who="demo")
    ws.save("07-engineering-tags", sh.transcript.svg())


# --- 08 tag register and the legacy tag import -----------------------------------------------


def section_tag_import(ws: Workspace) -> None:
    sh = Shell(ws, "A legacy instrument index: preview, refuse, apply", 118)
    sh.run("tag", "import", TAG_FILE, "--mapping", TAG_MAPPING, *P, who="amy")
    sh.run(
        "tag",
        "import",
        TAG_FILE,
        "--mapping",
        TAG_MAPPING,
        *P,
        "--apply",
        "--skip-invalid",
        who="amy",
        ok=False,
    )
    sh.run(
        "tag",
        "import",
        TAG_FILE,
        "--mapping",
        TAG_MAPPING,
        *P,
        "--apply",
        "--skip-invalid",
        who="demo",
        tail=3,
    )
    sh.run("tag", "report", "summary", *P, who="amy")
    sh.run("tag", "report", "violations", *P, who="amy")
    ws.save("08a-tag-import", sh.transcript.svg())

    app = build_app(ws)

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await pilot.press("f8")
        await tk.until(pilot, lambda: "47-FV-1001" in tk.screen_text(app), "the tag register")
        tk.shot_tui(
            ws,
            app,
            "08b-tag-register",
            "F8: the tag register: class, status, what each tag lacks",
            "47-FV-1001",
            "FV1009",
        )
        await pilot.press("v")
        await tk.until(pilot, lambda: "47-FV-1001" not in tk.screen_text(app), "violations only")
        tk.shot_tui(
            ws,
            app,
            "08c-tag-register-violations",
            "F8, v: only the tags that do not conform",
            "FV1009",
        )

    tk.run_tui(ws, app, scenario)


# --- 09 to 11 documents ----------------------------------------------------------------------


def section_documents(ws: Workspace) -> None:
    sh = Shell(ws, "Documents: a number pattern, revisions, a status class per revision", 118)
    sh.run(
        "doc",
        "register",
        "ISO-12",
        *P,
        "--title",
        "Too short",
        "--type",
        "ISO",
        "--discipline",
        "PIP",
        who="amy",
        ok=False,
    )
    sh.run(
        "doc",
        "register",
        "ISO-1234",
        *P,
        "--title",
        "Isometric, line 47-P-101",
        "--type",
        "ISO",
        "--discipline",
        "PIP",
        "--originator",
        "Acme Piping",
        who="amy",
    )
    ws.tl(
        "doc",
        "register",
        "ISO-2000",
        *P,
        "--title",
        "Isometric, line 47-P-102",
        "--type",
        "ISO",
        "--discipline",
        "PIP",
        who="amy",
    )
    # the tags 47-FV-1001 and 47-FV-1002 came with the legacy instrument index (section 8)
    sh.run("doc", "rev", "create", "ISO-1234", *P, "--purpose", "For review", who="amy")
    sh.run(
        "doc",
        "rendition",
        "add",
        "ISO-1234",
        "A",
        "sheet-A.pdf",
        *P,
        "--kind",
        "pdf",
        "--pages",
        "3",
        who="amy",
    )
    sh.run("doc", "rev", "issue", "ISO-1234", "A", *P, "--status", "IFR", who="amy", ok=False)
    sh.run("doc", "rev", "issue", "ISO-1234", "A", *P, "--status", "IFR", who="demo")
    ws.save("09a-documents-cli", sh.transcript.svg())


def section_stale(ws: Workspace) -> None:
    sh = Shell(ws, "A pinned link goes stale; the re-pin shows what changed first", 118)
    sh.run("doc", "link", "47-FV-1001", "ISO-1234", *P, "--pin", "A", who="amy")
    sh.run(
        "doc", "rev", "create", "ISO-1234", *P, "--purpose", "Issued for construction", who="amy"
    )
    ws.tl(
        "doc",
        "rendition",
        "add",
        "ISO-1234",
        "B",
        "sheet-B.pdf",
        *P,
        "--kind",
        "pdf",
        "--pages",
        "5",
        who="amy",
    )
    sh.run("doc", "rev", "issue", "ISO-1234", "B", *P, "--status", "IFC", who="demo")
    stale = sh.run("doc", "stale", *P, who="amy")
    link = stale.splitlines()[0].split()[-1]
    sh.run("doc", "repin", link, *P, who="amy")
    sh.run("doc", "repin", link, *P, "--apply", who="amy", tail=1)
    ws.save("10a-stale-and-repin", sh.transcript.svg())

    sh = Shell(ws, "The stale rule knows revision classes (ADR-0012)", 118)
    sh.run("doc", "link", "47-FV-1002", "ISO-1234", *P, "--pin", "B", who="amy")
    sh.run(
        "doc",
        "rev",
        "create",
        "ISO-1234",
        *P,
        "--purpose",
        "Review comments incorporated",
        who="amy",
    )
    ws.tl("doc", "rendition", "add", "ISO-1234", "C", "sheet-C.pdf", *P, "--kind", "pdf", who="amy")
    sh.note("C is issued for review (IFR) after B was issued for construction (IFC)")
    sh.run("doc", "rev", "issue", "ISO-1234", "C", *P, "--status", "IFR", who="demo")
    stale = sh.run("doc", "stale", *P, who="amy")
    expect(not stale.strip(), "an IFR issued after an IFC flagged the IFC pin")
    sh.note("nothing is stale: nobody builds from a review draft. Now D is issued for construction")
    sh.run("doc", "rev", "create", "ISO-1234", *P, "--purpose", "Final for construction", who="amy")
    ws.tl("doc", "rendition", "add", "ISO-1234", "D", "sheet-D.pdf", *P, "--kind", "pdf", who="amy")
    sh.run("doc", "rev", "issue", "ISO-1234", "D", *P, "--status", "IFC", who="demo")
    sh.run("doc", "stale", *P, who="amy")
    sh.run("doc", "show", "ISO-1234", *P, who="amy")
    ws.save("10b-class-aware-stale", sh.transcript.svg())


def section_transmittal_review(ws: Workspace) -> None:
    sh = Shell(ws, "A transmittal of exact revisions; a review with a deadline", 118)
    created = sh.run(
        "transmittal",
        "create",
        *P,
        "--subject",
        "Isometrics for construction",
        "--purpose",
        "for_construction",
        "--to",
        "Site Office:Acme Construction:site@example.com",
        "--revision",
        "ISO-1234@D",
        who="amy",
    )
    number = next(
        line.split()[-1] for line in created.splitlines() if line.startswith("created transmittal")
    )
    sh.run("transmittal", "issue", number, *P, who="amy", ok=False)
    sh.run("transmittal", "issue", number, *P, who="demo")
    sh.run("transmittal", "show", number, *P, who="amy")
    ws.save("11a-transmittal", sh.transcript.svg())

    sh = Shell(ws, "A review round: who has not answered, and how late", 118)
    ws.tl("doc", "rev", "create", "ISO-2000", *P, "--purpose", "First draft", who="amy")
    sh.run(
        "review",
        "open",
        "ISO-2000",
        "A",
        *P,
        "--reviewer",
        "user:ana",
        "--reviewer",
        "user:amy",
        "--due",
        "2026-10-01",
        who="demo",
    )
    sh.run("doc", "report", "overdue", *P, "--on", "2026-10-13", who="demo")
    sh.run(
        "review",
        "answer",
        "ISO-2000@A/RC1",
        *P,
        "--outcome",
        "approved_with_comments",
        "--comment",
        "check the weld map",
        who="ana",
    )
    sh.run("doc", "report", "overdue", *P, "--on", "2026-10-13", who="demo")
    ws.save("11b-review-overdue", sh.transcript.svg())


def section_register_tui(ws: Workspace) -> None:
    """The F7 register (a status class per revision), the re-pin dialog and the composer."""
    app = build_app(ws)

    async def scenario(pilot: Pilot[Any]) -> None:
        from tl_tui.widgets.document_register import DocumentRegisterScreen

        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await pilot.press("f7")
        await tk.until(pilot, lambda: "ISO-1234" in tk.screen_text(app), "the document register")
        screen = app.screen
        expect(isinstance(screen, DocumentRegisterScreen), "F7 did not open the register")
        table = screen.query_one("#log-table", DataTable)
        table.move_cursor(row=[v.number for v in screen.shown].index("ISO-1234"))
        await tk.until(pilot, lambda: "IFC" in tk.screen_text(app), "the detail panel")
        tk.shot_tui(
            ws,
            app,
            "09b-document-register",
            "F7: the register; one current revision per status class",
            "ISO-1234",
            "IFR",
            "IFC",
            "construction",
        )
        await pilot.press("r")
        await tk.until(pilot, lambda: "Re-pin a stale link" in tk.screen_text(app), "the dialog")
        tk.shot_tui(
            ws,
            app,
            "10c-repin-dialog",
            "F7, r: the re-pin dialog shows the diff before it asks",
            "Re-pin a stale link",
            "ISO-1234",
        )
        await pilot.press("escape")
        await tk.settle(pilot, 4)
        await pilot.press("t")
        await tk.until(pilot, lambda: "New transmittal" in tk.screen_text(app), "the composer")
        composer = app.screen
        composer.query_one("#tc-subject", Input).value = "Isometrics for construction, rev D"
        composer.query_one("#tc-to", Input).value = "Site Office:Acme Construction:site@example.com"
        await tk.settle(pilot, 4)
        expect(len(composer.query_one("#tc-revisions", SelectionList).selected) == 1, "no tick")
        tk.shot_tui(
            ws,
            app,
            "11c-transmittal-composer",
            "F7, t: a transmittal draft with the current revision ticked",
            "New transmittal",
            "ISO-1234",
        )
        await pilot.press("escape")
        await tk.settle(pilot, 3)

    tk.run_tui(ws, app, scenario, size=(160, 48))


# --- 12 legacy DMS import --------------------------------------------------------------------


def section_dms_import(ws: Workspace) -> None:
    sh = Shell(ws, "A legacy DMS register: judged before anything is written", 118)
    sh.run("doc", "import", DMS_FILE, "--mapping", DMS_MAPPING, *P, who="amy")
    sh.run(
        "doc",
        "import",
        DMS_FILE,
        "--mapping",
        DMS_MAPPING,
        *P,
        "--apply",
        "--skip-invalid",
        who="amy",
        ok=False,
    )
    sh.run(
        "doc",
        "import",
        DMS_FILE,
        "--mapping",
        DMS_MAPPING,
        *P,
        "--apply",
        "--skip-invalid",
        "--job",
        "dms-2024",
        who="demo",
        tail=2,
    )
    sh.run("doc", "show", "ISO-0101", *P, who="amy", tail=14)
    ws.save("12-dms-import", sh.transcript.svg())


# --- 13 what a plain user cannot do ----------------------------------------------------------


def section_refused(ws: Workspace) -> None:
    sh = Shell(ws, "What a plain user (amy) is refused", 118)
    sh.note("amy has the role `user`: she registers, edits, links and drafts;")
    sh.note("controlling acts need the document_controller or admin role (section 14);")
    sh.note("loading standards and managing accounts stay with admins")
    refused = (
        ("standards", "load", STANDARDS),
        ("doc", "rev", "issue", "ISO-1234", "D", *P, "--status", "IFC"),
        ("transmittal", "issue", "P123-TRN-0001", *P),
        ("tag", "import", TAG_FILE, "--mapping", TAG_MAPPING, *P, "--apply"),
        ("admin", "token", "ls"),
    )
    for argv in refused:
        sh.run(*argv, who="amy", ok=False)
    sh.note("the API refuses the same acts with 403, and no one, admin or not, can void a document")
    sh.note("through a generic command (tests/auth and the P1-I2 demo, clause 8)")
    ws.save("13-refused-acts", sh.transcript.svg())


# --- 14 the document controller role (P1-I2b) ------------------------------------------------


def section_controller(ws: Workspace) -> None:
    """An admin grants the role; the controller issues; the controller stops at accounts."""
    sh = Shell(ws, "A plain user is refused; an admin grants the document controller role", 118)
    sh.run(
        "admin",
        "user",
        "add",
        "dora",
        "--display-name",
        "Dora C",
        "--password-stdin",
        stdin=password("dora"),
        who="demo",
        show="tl admin user add dora --display-name 'Dora C' --password-stdin",
    )
    sign_in(ws, "dora")
    sh.note("amy, a plain user, registers ISO-3000, drafts revision A and attaches its PDF")
    sh.run(
        "doc",
        "register",
        "ISO-3000",
        *P,
        "--title",
        "Isometric, line 47-P-103",
        "--type",
        "ISO",
        "--discipline",
        "PIP",
        who="amy",
    )
    sh.run("doc", "rev", "create", "ISO-3000", *P, "--purpose", "For construction", who="amy")
    sh.run(
        "doc",
        "rendition",
        "add",
        "ISO-3000",
        "A",
        "sheet-A.pdf",
        *P,
        "--kind",
        "pdf",
        "--pages",
        "3",
        who="amy",
    )
    sh.note("dora has the role `user`, so issuing is refused, with the roles that would allow it")
    sh.run("admin", "user", "show", "dora", who="demo", tail=6)
    refused = sh.run(
        "doc", "rev", "issue", "ISO-3000", "A", *P, "--status", "IFC", who="dora", ok=False
    )
    expect(NEEDS in refused, f"unexpected refusal: {refused}")
    sh.note("an admin grants the role, with a reason that goes into the history")
    sh.run(
        "admin",
        "user",
        "roles",
        "dora",
        "--add",
        "document_controller",
        "--reason",
        "takes over document control",
        who="demo",
    )
    sh.run("admin", "user", "show", "dora", who="demo", tail=6)
    ws.save("14a-grant-the-role", sh.transcript.svg())

    app = build_app(ws, admin=True)

    async def accounts(pilot: Pilot[Any]) -> None:
        from textual.widgets import DataTable

        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await pilot.press("f10")
        await tk.until(pilot, lambda: "dora" in tk.screen_text(app), "the accounts screen")
        table = app.screen.query_one("#admin-accounts", DataTable)
        names = [str(table.get_row_at(i)[0]) for i in range(table.row_count)]
        table.move_cursor(row=names.index("ana"))
        await tk.settle(pilot, 3)
        await pilot.press("c")
        await tk.until(pilot, lambda: "Make document controller ana" in tk.screen_text(app), "form")
        tk.shot_tui(
            ws,
            app,
            "14b-admin-grants-the-role",
            "F10, c: the accounts screen offers the role; the reason goes into the history",
            "document_controller",
            "Make document controller ana",
        )
        await pilot.press("escape")  # nothing is changed
        await tk.settle(pilot, 3)

    tk.run_tui(ws, app, accounts)

    sh = Shell(ws, "The controller issues a revision and a transmittal; no admin is involved", 118)
    sh.run("doc", "rev", "issue", "ISO-3000", "A", *P, "--status", "IFC", who="dora")
    created = sh.run(
        "transmittal",
        "create",
        *P,
        "--subject",
        "Isometrics for construction",
        "--purpose",
        "for_construction",
        "--to",
        "Site Office:Acme Construction:site@example.com",
        "--revision",
        "ISO-3000@A",
        who="amy",
    )
    number = next(
        line.split()[-1] for line in created.splitlines() if line.startswith("created transmittal")
    )
    sh.note("amy drafted it; issuing it is a controlling act")
    sh.run("transmittal", "issue", number, *P, who="amy", ok=False)
    sh.run("transmittal", "issue", number, *P, who="dora")
    sh.run("transmittal", "show", number, *P, who="amy")
    sh.run("doc", "show", "ISO-3000", *P, who="amy", tail=6)
    ws.save("14c-controller-issues", sh.transcript.svg())

    ws.tl("doc", "rev", "create", "ISO-3000", *P, "--purpose", "Re-issued", who="amy")
    (ws.root / "sheet-E.pdf").write_text("%PDF-1.7 sheet E\n")
    ws.tl("doc", "rendition", "add", "ISO-3000", "B", "sheet-E.pdf", *P, "--kind", "pdf", who="amy")
    ws.tl("doc", "rev", "issue", "ISO-3000", "B", *P, "--status", "IFC", who="dora")
    controller_app = build_app(ws, actor="user:dora", controller=True)

    async def composer(pilot: Pilot[Any]) -> None:
        from textual.widgets import DataTable

        await tk.until(pilot, lambda: len(controller_app.query("RecordGrid")) > 0, "the shell")
        await pilot.press("f7")
        await tk.until(pilot, lambda: "ISO-3000" in tk.screen_text(controller_app), "the register")
        table = controller_app.screen.query_one("#log-table", DataTable)
        shown = [v.number for v in controller_app.screen.shown]  # type: ignore[attr-defined]
        table.move_cursor(row=shown.index("ISO-3000"))
        await tk.settle(pilot, 4)
        await pilot.press("t")
        await tk.until(pilot, lambda: "New transmittal" in tk.screen_text(controller_app), "form")
        form = controller_app.screen
        form.query_one("#tc-subject", Input).value = "Isometrics for construction, rev B"
        form.query_one("#tc-to", Input).value = "Site Office:Acme Construction:site@example.com"
        await tk.settle(pilot, 4)
        expect(len(form.query_one("#tc-revisions", SelectionList).selected) >= 1, "no revision")
        tk.shot_tui(
            ws,
            controller_app,
            "14d-composer-draft-and-issue",
            "dora, F7, t: the composer offers Ctrl+T, draft and issue in one step",
            "New transmittal",
            "Ctrl+T draft and issue",
        )
        await pilot.press("ctrl+t")
        await tk.until(
            pilot, lambda: "Drafted and issued" in tk.screen_text(controller_app), "issue"
        )
        tk.shot_tui(
            ws,
            controller_app,
            "14e-composer-issued",
            "The register says what happened",
            "Drafted and issued transmittal",
        )

    tk.run_tui(ws, controller_app, composer, size=(160, 48))
    expect("Issued" in ws.tl("transmittal", "show", "P123-TRN-0003", *P, who="amy"), "not issued")

    sh = Shell(ws, "The controller stops where document control stops", 118)
    for argv in (
        ("admin", "user", "ls"),
        ("admin", "token", "ls"),
        ("admin", "user", "roles", "dora", "--add", "admin"),
        ("admin", "user", "roles", "amy", "--add", "document_controller"),
    ):
        sh.run(*argv, who="dora", ok=False)
    sh.run(
        "admin",
        "user",
        "add",
        "eve",
        "--password-stdin",
        stdin="a long passphrase for eve\n",
        who="dora",
        ok=False,
        show="tl admin user add eve --password-stdin",
    )
    sh.note("an agent account cannot hold the role either")
    sh.run(
        "admin",
        "user",
        "add",
        "bot",
        "--kind",
        "agent",
        "--role",
        "document_controller",
        who="demo",
        ok=False,
    )
    sh.note("taking the role away closes the same commands again")
    sh.run(
        "admin",
        "user",
        "roles",
        "dora",
        "--remove",
        "document_controller",
        "--reason",
        "moved to site",
        who="demo",
    )
    ws.tl("doc", "rev", "create", "ISO-3000", *P, "--purpose", "Issued for review", who="amy")
    (ws.root / "sheet-F.pdf").write_text("%PDF-1.7 sheet F\n")
    ws.tl("doc", "rendition", "add", "ISO-3000", "C", "sheet-F.pdf", *P, "--kind", "pdf", who="amy")
    sh.run("doc", "rev", "issue", "ISO-3000", "C", *P, "--status", "IFR", who="dora", ok=False)
    ws.save("14f-controller-limits", sh.transcript.svg())


# --- helpers for sections 15 to 19 (P1-I3 to P1-I7) -------------------------------------------


def demo_module(name: str) -> Any:
    """The helper module of a demo (`dev/demos/<name>.py`); its setup code writes sample files."""
    path = str(REPO / "dev" / "demos")
    if path not in sys.path:
        sys.path.append(path)
    return importlib.import_module(name)


def quietly(call: Callable[..., Any], *args: Any) -> Any:
    """Run a demo helper without its console chatter (it names temporary paths)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args)


def made(output: str, word: str) -> str:
    """The number a command printed after ``word`` (`received P123-COR-0001` gives the number)."""
    for line in output.splitlines():
        if line.startswith(word + " "):
            return line.split()[1]
    raise tk.TourFailed(f"no line starting {word!r} in:\n{output}")


async def open_screen(pilot: Pilot[Any], app: Any, key: str, needle: str, what: str) -> None:
    """Press a main-screen key and wait for the screen it opens to show ``needle``."""
    await pilot.press(key)
    await tk.until(pilot, lambda: needle in tk.screen_text(app), what)


# --- 15 the derivation pipeline (P1-I3) -------------------------------------------------------

AREAS = {"47": "50", "10": "30", "20": "40"}  # the sample index repeats tags of section 8: renumber


def renumbered(source: Path, target: Path) -> None:
    """Copy a sample CSV with the area of each tag changed, so its tags are new to this ledger."""
    lines = source.read_text(encoding="utf-8").splitlines()
    out = [lines[0]]
    for line in lines[1:]:
        area, _, rest = line.partition("-")
        out.append(f"{AREAS[area]}-{rest}")
    target.write_text("\n".join(out) + "\n", encoding="utf-8")


def section_derive(ws: Workspace) -> None:
    renew_sessions(ws)
    demo = demo_module("p1_i3_demo")
    demo.FIXTURES = REPO / "schema/fixtures/document-schemas"
    work = ws.root / "derive"
    work.mkdir()
    quietly(demo.prepare, str(work))
    for kind in ("invalid", "sample"):
        renumbered(demo.FIXTURES / f"instrument-index@1.0.0.{kind}.csv", work / f"index-{kind}.csv")
    key = "LD-4701@A/instrument-index"
    amy = "derive/index-invalid.csv"

    sh = Shell(ws, "A spreadsheet that tells the author which cell is wrong", 118)
    sh.run(
        "derive",
        "schema",
        "register",
        "derive/instrument-index.yaml",
        "--company",
        who="amy",
        ok=False,
    )
    sh.run("derive", "schema", "register", "derive/instrument-index.yaml", "--company", who="demo")
    ws.tl(
        "doc",
        "register",
        "LD-4701",
        *P,
        "--title",
        "Instrument index, unit 47",
        "--type",
        "LD",
        "--discipline",
        "INS",
        who="amy",
    )
    ws.tl("doc", "rev", "create", "LD-4701", *P, "--purpose", "First issue", who="amy")
    ws.tl(
        "doc",
        "rendition",
        "add",
        "LD-4701",
        "A",
        "derive/isd-001-A.pdf",
        *P,
        "--kind",
        "pdf",
        "--pages",
        "3",
        who="amy",
    )
    sh.note("amy registers LD-4701 and attaches its PDF (as in section 9); then a derived document")
    sh.run("derive", "open", "LD-4701", "A", "--schema", "instrument-index", *P, who="amy")
    sh.run("derive", "content", key, amy, *P, who="amy")
    sh.run("derive", "start", key, *P, who="amy")
    sh.run("derive", "worker", "--once", who="amy")
    sh.run("derive", "report", key, *P, who="amy")
    ws.save("15a-derive-cli", sh.transcript.svg())

    app = build_app(ws, admin=True)

    async def invalid(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_screen(pilot, app, "f11", "LD-4701", "the derived documents")
        await tk.until(pilot, lambda: "fail_action" in tk.screen_text(app), "the report")
        tk.shot_tui(
            ws,
            app,
            "15b-derived-report",
            "F11: the derived document and its report: the row, the field, the value",
            "LD-4701",
            "Invalid",
            "fail_action",
            "OPEN",
        )

    tk.run_tui(ws, app, invalid, size=(160, 44))

    ws.tl("derive", "content", key, "derive/index-sample.csv", *P, who="amy")
    ws.tl("derive", "start", key, *P, who="amy")
    ws.tl("derive", "worker", "--once", who="amy")
    app = build_app(ws, admin=True)

    async def valid(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_screen(pilot, app, "f11", "LD-4701", "the derived documents")
        await tk.until(pilot, lambda: "Valid" in tk.screen_text(app), "the valid pass")
        await pilot.press("d")
        await tk.until(pilot, lambda: "changed" in tk.screen_text(app).lower(), "the diff")
        tk.shot_tui(
            ws,
            app,
            "15c-derived-diff",
            "F11, d: the corrected file read again: the diff is one cell",
            "Valid",
            "fail_action",
        )
        await pilot.press("p")
        await tk.until(pilot, lambda: "create" in tk.screen_text(app).lower(), "the preview")
        tk.shot_tui(
            ws,
            app,
            "15d-publish-preview",
            "F11, p: the preview of the 40 tags a publication would create",
            "create",
        )

    tk.run_tui(ws, app, valid, size=(160, 44))

    sh = Shell(
        ws, "Publishing 40 tags that remember where they came from, and taking them back", 118
    )
    sh.run("derive", "publish", key, *P, who="amy", head=4)
    sh.run("derive", "publish", key, *P, "--apply", who="amy", ok=False)
    sh.run("derive", "publish", key, *P, "--apply", who="demo", tail=2)
    sh.run("pset", "get", "50-FV-1001", *P, who="amy")
    undo = ("derive", "compensate", key, *P, "--reason", "wrong unit: roll it back")
    sh.run(*undo, who="demo", head=3)
    sh.run(*undo, "--apply", who="demo", tail=1)
    sh.run("tag", "ls", *P, "--all", who="amy", tail=2)
    ws.save("15e-publish-and-undo", sh.transcript.svg())


# --- 16 schedules and cost (P1-I4) ------------------------------------------------------------

SCHEDULE = ("--schedule", "MAIN")


def section_schedules(ws: Workspace) -> None:
    renew_sessions(ws)
    demo = demo_module("p1_i4_demo")
    work = ws.root / "xer"
    work.mkdir()
    quietly(demo.prepare, str(work))

    sh = Shell(ws, "Primavera XER updates: defined, uploaded, built by the worker", 118)
    sh.note(
        "section 14 took the controller role from dora; an admin gives it back for the planning"
    )
    sh.run(
        "admin",
        "user",
        "roles",
        "dora",
        "--add",
        "document_controller",
        "--reason",
        "takes over planning data",
        who="demo",
    )
    sh.run("xer", "define", "MAIN", *P, "--name", "Pipe rack schedule", who="amy", ok=False)
    sh.run(
        "xer", "define", "MAIN", *P, "--name", "Pipe rack schedule", "--type", "current", who="dora"
    )
    sh.run("xer", "upload", "xer/update-1.xer", *P, *SCHEDULE, who="amy")
    sh.run("xer", "upload", "xer/update-2.xer", *P, *SCHEDULE, who="amy")
    sh.run("xer", "upload", "xer/update-2.xer", *P, *SCHEDULE, who="amy", ok=False)
    sh.run("xer", "worker", "--once", who="demo")
    sh.run("xer", "show", *P, *SCHEDULE, who="amy")
    ws.save("16a-xer-cli", sh.transcript.svg())

    sh = Shell(ws, "Records tied to activities: now, as of an earlier update, and orphaned", 118)
    sh.run("xer", "publish", "1", *P, *SCHEDULE, who="dora")
    for key, title in (
        ("REC-A", "Pipe rack supports work package"),
        ("REC-B", "Temporary fencing permit"),
        ("REC-C", "Unplanned site visit"),
    ):
        ws.tl("record", "create", *P, "--key", key, "--title", title, who="amy")
    sh.note("amy created three records (REC-A to REC-C) and ties two of them to activities")
    sh.run("xer", "link", "REC-A", "A1230", *P, *SCHEDULE, who="amy")
    sh.run("xer", "link", "REC-B", "A1990", *P, *SCHEDULE, who="amy")
    sh.run("xer", "publish", "2", *P, *SCHEDULE, who="dora")
    sh.run("xer", "worker", "--once", who="demo")
    sh.run("xer", "resolve", "A1230", *P, *SCHEDULE, who="amy")
    sh.run("xer", "resolve", "A1230", *P, *SCHEDULE, "--as-of", "1", who="amy")
    sh.run("xer", "resolve", "A1990", *P, *SCHEDULE, who="amy")
    sh.run("xer", "health", *P, *SCHEDULE, who="amy")
    sh.run("xer", "trend", "A1230", *P, *SCHEDULE, who="amy")
    ws.save("16b-activity-links", sh.transcript.svg())

    app = build_app(ws)

    async def screens(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_screen(pilot, app, "f12", "MAIN", "the schedules")
        tk.shot_tui(
            ws,
            app,
            "16c-schedules",
            "F12: the schedule and its snapshots, newest first",
            "MAIN",
            "Published",
        )
        await pilot.press("tab", "c")  # into the snapshot table (snapshot 2 is on top), compare
        await tk.until(pilot, lambda: "A2500" in tk.screen_text(app), "the comparison")
        await pilot.press("n", "n", "n")  # added, removed, date shifts, then float
        await tk.until(pilot, lambda: "A1230" in tk.screen_text(app), "the float section")
        tk.shot_tui(
            ws,
            app,
            "16d-compare",
            "F12, c, n: snapshot 2 against snapshot 1; the float section: A1230 lost five days",
            "A1230",
        )

    tk.run_tui(ws, app, screens, size=(160, 48))

    sh = Shell(ws, "Cost periods: previewed, applied by an admin, reported against the budget", 118)
    sh.run(
        "cost",
        "import",
        "xer/cost-2026-07.csv",
        *P,
        "--period",
        "2026-07",
        "--as-of",
        "2026-07-31",
        who="amy",
        head=3,
    )
    sh.run(
        "cost",
        "import",
        "xer/cost-2026-07.csv",
        *P,
        "--period",
        "2026-07",
        "--as-of",
        "2026-07-31",
        "--apply",
        who="amy",
        ok=False,
    )
    sh.run(
        "cost",
        "import",
        "xer/cost-2026-07.csv",
        *P,
        "--period",
        "2026-07",
        "--as-of",
        "2026-07-31",
        "--apply",
        who="demo",
        tail=1,
    )
    ws.tl(
        "cost",
        "import",
        "xer/cost-2026-08.csv",
        *P,
        "--period",
        "2026-08",
        "--as-of",
        "2026-08-31",
        "--apply",
        who="demo",
    )
    ws.tl("link", "add", "REC-A", "4210-PIP", *P, "--relation", "references", who="demo")
    sh.run("cost", "snapshots", *P, who="amy")
    sh.run("cost", "report", "budget", *P, "--unit", "quantity", who="amy")
    sh.run("cost", "report", "uncoded", *P, "--type", "core.Record", who="amy")
    sh.run("xer", "unscheduled", *P, "--type", "core.Record", who="amy")
    ws.save("16e-cost-periods", sh.transcript.svg())


# --- 17 correspondence (P1-I5) ----------------------------------------------------------------

NOON = "Mon, 12 Oct 2026 12:00:00 +0000"  # the Date header of the tour's email: a real one varies


def section_correspondence(ws: Workspace) -> None:
    renew_sessions(ws)
    demo = demo_module("p1_i5_demo")
    demo.formatdate = lambda: NOON  # the demo's own helper writes the email, with a fixed date
    quietly(demo.make_eml, "reply.eml")
    (ws.root / "letter.txt").write_text(
        "Please find our revised programme. We would be grateful for your comments.\n"
    )

    sh = Shell(
        ws, "A letter arrives, a person confirms the triage, a controller issues the reply", 118
    )
    sh.run(
        "corr",
        "party",
        "add",
        "ACME",
        *P,
        "--name",
        "Acme Construction",
        "--role",
        "contractor",
        "--email-domain",
        "acme.example",
        "--contact",
        "Ann:ann@acme.example",
        who="dora",
    )
    received = sh.run(
        "corr",
        "receive",
        *P,
        "--subject",
        "Revised programme",
        "--from",
        "Acme Construction",
        "--file",
        "letter.txt",
        "--body-file",
        "letter.txt",
        who="amy",
    )
    letter = made(received, "received")
    sh.run("corr", "suggest", letter, *P, who="amy")
    sh.run("corr", "triage", letter, *P, "--accept", who="amy")
    drafted = sh.run(
        "corr",
        "draft",
        *P,
        "--subject",
        "Re: Revised programme",
        "--to",
        "Acme Construction:ann@acme.example",
        "--reply-to",
        letter,
        "--domain",
        "general",
        "--subtype",
        "letter",
        "--body",
        "We have received the programme and will reply by the due date.",
        who="amy",
    )
    reply = made(drafted, "drafted")
    sh.run("corr", "issue", reply, *P, who="amy", ok=False)
    sh.run("corr", "issue", reply, *P, who="dora")
    sh.run("corr", "clock", "ls", *P, who="amy")
    ws.save("17a-letter-triage-reply", sh.transcript.svg())

    sh = Shell(
        ws,
        "An email joins the thread of the letter; a restricted item does not exist for a user",
        118,
    )
    ingested = sh.run("corr", "mail", "ingest", "reply.eml", *P, who="amy")
    mail = made(ingested, "ingested")
    sh.run("corr", "mail", "ingest", "reply.eml", *P, who="amy", ok=False)
    sh.run("corr", "show", mail, *P, who="amy", head=11)
    sh.note("a controller marks the email restricted (commercial terms)")
    sh.run(
        "corr",
        "class",
        "set",
        mail,
        *P,
        "--to",
        "restricted",
        "--reason",
        "commercial terms",
        who="dora",
    )
    sh.run("corr", "show", mail, *P, who="amy", ok=False)
    sh.run("corr", "show", "P123-COR-9999", *P, who="amy", ok=False)
    ws.save("17b-email-thread-restricted", sh.transcript.svg())

    def tui(
        actor: str, controller: bool, name: str, title: str, select: str, *needles: str
    ) -> None:
        app = build_app(ws, actor=actor, controller=controller)

        async def register(pilot: Pilot[Any]) -> None:
            await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
            await open_screen(pilot, app, "f5", letter, "the register")
            numbers = [line.number for line in app.screen.lines]  # type: ignore[attr-defined]
            app.screen.query_one("#log-table", DataTable).move_cursor(row=numbers.index(select))
            await tk.settle(pilot, 3)
            tk.shot_tui(ws, app, name, title, letter, reply, select, *needles)

        tk.run_tui(ws, app, register, size=(170, 44))

    tui(
        "user:amy",
        False,
        "17c-register-as-user",
        "F5 as amy, a plain user: the register without the restricted email",
        letter,
    )
    tui(
        "user:dora",
        True,
        "17d-register-as-controller",
        "F5 as dora, a cleared controller: the same register, with the restricted email",
        mail,
        "class restricted",
    )

    app = build_app(ws, actor="user:dora", controller=True)

    async def clocks(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_screen(pilot, app, "f5", letter, "the register")
        await pilot.press("3")
        await tk.until(pilot, lambda: "Reply expected" in tk.screen_text(app), "the clocks")
        tk.shot_tui(
            ws,
            app,
            "17e-clocks",
            "F5, 3: the clocks: reply due in 14 calendar days, with the days left",
            reply,
            "Reply expected",
        )

    tk.run_tui(ws, app, clocks, size=(170, 44))


# --- 18 RFIs and commercial notices (P1-I6) ---------------------------------------------------

MERIDIAN = "Meridian:pm@meridian.example"


def section_rfi(ws: Workspace) -> None:
    renew_sessions(ws)
    shutil.copytree(REPO / "dev/seed/rules", ws.root / "rules")
    today = tk.CLOCK.now.date()
    needed = (today + timedelta(days=10)).isoformat()
    aware = (today - timedelta(days=20)).isoformat()

    sh = Shell(
        ws, "An RFI: raised by a person, issued by a controller, answered with a cost flag", 118
    )
    sh.run("rule", "create", "--file", "rules/rfi-escalation.json", *P, who="demo")
    sh.run("rule", "enable", "rfi-escalation", *P, who="demo")
    raised = sh.run(
        "rfi",
        "raise",
        *P,
        "--subject",
        "Beam B12 clashes with line 47",
        "--question",
        "The isometric clashes with beam B12; confirm the routing.",
        "--discipline",
        "structural",
        "--required-by",
        needed,
        "--to",
        MERIDIAN,
        who="amy",
    )
    rfi = made(raised, "raised")
    sh.run("rfi", "submit", rfi, *P, who="amy")
    sh.run("rfi", "issue", rfi, *P, who="amy", ok=False)
    sh.run("rfi", "issue", rfi, *P, who="dora")
    sh.run(
        "rfi",
        "answer",
        rfi,
        *P,
        "--answer",
        "Re-route above the beam; revision C follows.",
        "--cost-impact",
        "yes",
        "--schedule-impact",
        "no",
        who="amy",
    )
    sh.run("rfi", "ls", *P, "--impact", who="amy")
    ws.save("18a-rfi-cli", sh.transcript.svg())

    sh = Shell(
        ws, "A rule proposes the early warning; a controller accepts; a user never sees it", 118
    )
    sh.run("integration", "serve", "--once", who="demo")
    listed = sh.run("proposal", "ls", *P, who="dora")
    proposal = next(
        line.split()[0] for line in listed.splitlines() if "svc:rule-rfi-escalation" in line
    )
    sh.run("proposal", "show", proposal, who="dora", head=12)
    sh.run("proposal", "accept", proposal, who="amy", ok=False)
    sh.run("proposal", "accept", proposal, who="dora")
    sh.run("rfi", "show", rfi, *P, who="dora", tail=4)
    sh.run("comm", "show", "P123-EW-0001", *P, who="dora", head=6)
    sh.run("comm", "ls", *P, who="amy", ok=False)
    ws.save("18b-rule-escalation", sh.transcript.svg())

    # pricing and issuing the notice, a late one, and the assessments (all as the controller)
    ws.tl(
        "comm",
        "update",
        "P123-EW-0001",
        *P,
        "--currency",
        "USD",
        "--value",
        "12500",
        "--hours",
        "240",
        "--cost-code",
        "2.3.1=10000",
        "--cost-code",
        "2.3.2=2500:100",
        "--schedule-days",
        "3",
        "--basis",
        f"Answer to {rfi}",
        "--to",
        MERIDIAN,
        who="dora",
    )
    ws.tl("comm", "submit", "P123-EW-0001", *P, who="dora")
    ws.tl("comm", "review", "P123-EW-0001", *P, "--note", "figures checked", who="dora")
    ws.tl("comm", "issue", "P123-EW-0001", *P, who="dora")
    ws.tl(
        "comm",
        "raise",
        *P,
        "--subject",
        "Valve delivery slip",
        "--subtype",
        "early_warning",
        "--aware-on",
        aware,
        "--currency",
        "EUR",
        "--value",
        "4000",
        "--to",
        MERIDIAN,
        who="dora",
    )
    for step in ("submit", "review", "issue"):
        ws.tl("comm", step, "P123-EW-0002", *P, who="dora")
    ws.tl(
        "comm",
        "assess",
        "P123-EW-0001",
        *P,
        "--status",
        "agreed",
        "--value",
        "9000",
        "--note",
        "as stated",
        who="dora",
    )
    ws.tl(
        "comm",
        "assess",
        "P123-EW-0002",
        *P,
        "--status",
        "disputed",
        "--note",
        "no entitlement",
        who="dora",
    )

    app = build_app(ws, actor="user:dora", controller=True)

    async def domains(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_screen(pilot, app, "ctrl+g", rfi, "the RFI log")
        tk.shot_tui(
            ws,
            app,
            "18c-rfi-log",
            "Ctrl+G: the RFI log: state, days to answer, cost and schedule flags",
            rfi,
        )
        await open_screen(pilot, app, "2", "P123-EW-0002", "the commercial register")
        tk.shot_tui(
            ws,
            app,
            "18d-commercial-register",
            "Ctrl+G, 2: the commercial register: time bars, LATE, a total per currency",
            "P123-EW-0001",
            "LATE",
        )
        numbers = [line.number for line in app.screen.notices.lines]  # type: ignore[attr-defined]
        table = app.screen.query_one("#log-table", DataTable)
        table.move_cursor(row=numbers.index("P123-EW-0001"))
        await tk.settle(pilot, 3)
        await pilot.press("t")
        await tk.until(pilot, lambda: rfi in tk.screen_text(app), "the evidence trail")
        tk.shot_tui(
            ws,
            app,
            "18e-evidence-trail",
            "Ctrl+G, t: the evidence trail of the notice, back to the RFI it came from",
            rfi,
        )

    tk.run_tui(ws, app, domains, size=(180, 46))


# --- 19 integration layer and record threads (P1-I7) -----------------------------------------


def inbound_posts(
    secret: str, payload: Path, cases: list[tuple[str, bool]], path: str = "/in/acme-nde/results"
) -> list[int]:
    """POST ``payload`` to the API in process once per ``(message id, signed)``; the statuses.

    A signed request carries the Standard Webhooks headers, stamped with the tour's clock; the
    secret is the one the endpoint printed once when it was created.
    """
    from fastapi.testclient import TestClient
    from tl_adapters.objectstore import make_object_store
    from tl_api.app import create_app
    from tl_api.backend import open_backend
    from tl_api.settings import ApiSettings
    from tl_core.webhooks.signing import SigningSecret, sign_headers

    body = payload.read_bytes()
    settings = ApiSettings.from_env()
    backend = open_backend(settings.db_path)
    try:
        client = TestClient(
            create_app(backend, settings=settings, object_store=make_object_store())
        )
        statuses: list[int] = []
        for message_id, signed in cases:
            headers = {"Content-Type": "application/json"}
            if signed:
                stamp = int(tk.CLOCK.now.timestamp())
                headers.update(
                    sign_headers(message_id, stamp, body.decode(), [SigningSecret(secret)])
                )
            statuses.append(client.post(path, content=body, headers=headers).status_code)
    finally:
        backend.close()
    return statuses


def section_integration(ws: Workspace) -> None:
    renew_sessions(ws)
    demo = demo_module("p1_i7_demo")
    work = ws.root / "integ"
    work.mkdir()
    quietly(demo.prepare, str(work))
    for key, title in (("V-1001", "Valve 1"), ("V-1002", "Valve 2")):
        ws.tl("record", "create", *P, "--key", key, "--title", title, who="amy")
    endpoint = ("acme-nde/results", *P)

    sh = Shell(ws, "An inbound endpoint: a dry run, then a signed delivery from a contractor", 118)
    sh.run("integration", "app", "add", "acme-nde", "--label", "Acme NDE", *P, who="amy", ok=False)
    sh.run("integration", "app", "add", "acme-nde", "--label", "Acme NDE", *P, who="demo")
    created = sh.run(
        "endpoint",
        "create",
        endpoint[0],
        *P,
        "--mapping-file",
        "integ/map.jsonata",
        "--allow",
        "SetPsetValues",
        who="demo",
        hide=("secret ",),
    )
    secret = next(
        line.split(None, 1)[1] for line in created.splitlines() if line.startswith("secret ")
    )
    sh.run("delivery", "dry-run", *endpoint, "--sample", "integ/payload.json", who="demo")
    sh.run(
        "endpoint", "mode", *endpoint, "live", "--reason", "the dry run looked right", who="demo"
    )
    sh.run("endpoint", "enable", *endpoint, who="demo")
    cases = [("m1", True), ("m1", True), ("m2", False)]
    statuses = inbound_posts(secret, work / "payload.json", cases)
    expect(statuses == [202, 401, 401], f"unexpected inbound answers {statuses}")
    answers = {202: "202 accepted", 401: "401 unauthorized"}
    for status, label in zip(
        statuses, ("signed", "the same message again", "no signature"), strict=True
    ):
        sh.line(f"POST /in/acme-nde/results  ({label})", answers[status])
    sh.run("integration", "serve", "--once", who="demo")
    sh.run("pset", "get", "V-1001", *P, who="amy")
    ws.save("19a-inbound-endpoint", sh.transcript.svg())

    sh = Shell(
        ws, "A rule that tells HSE, shown before it runs; a classifier that only proposes", 118
    )
    sh.run("feed", "post", "Earlier: gas alarm in unit 47 #safety", *P, who="demo")
    sh.run("rule", "create", "--file", "integ/hse.json", *P, who="demo")
    sh.run("rule", "dry-run", "hse-notify", *P, who="demo")
    sh.run(
        "rule", "mode", "hse-notify", "act", "--reason", "the dry run looked right", *P, who="demo"
    )
    sh.run("rule", "enable", "hse-notify", *P, who="demo")
    sh.run("feed", "post", "Gas alarm in unit 47 #safety", *P, who="demo")
    sh.run("integration", "serve", "--once", who="demo")
    sh.run("feed", "ls", *P, who="demo", head=3)
    sh.note(
        "a keyword classifier proposes a document type; nothing is written until a person decides"
    )
    sh.run(
        "enricher", "register", "doc_classifier", "--file", "integ/enricher.json", *P, who="demo"
    )
    sh.run("enricher", "enable", "doc_classifier", *P, who="demo")
    ws.tl(
        "doc", "register", "ISO-5001", *P, "--title", "Piping isometric drawing, unit 47", who="amy"
    )
    ws.tl("integration", "serve", "--once", who="demo")
    ws.save("19b-rules-and-enrichers", sh.transcript.svg())

    app = build_app(ws, admin=True)

    async def registry(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_screen(pilot, app, "ctrl+e", "acme-nde", "the integration registry")
        tk.shot_tui(
            ws,
            app,
            "19c-integration-registry",
            "Ctrl+E: the integration registry: endpoints, rules, enrichers, actions",
            "acme-nde",
        )
        await pilot.press("escape")
        await tk.settle(pilot, 3)
        await open_screen(pilot, app, "ctrl+r", "Doc classifier", "the review queue")
        tk.shot_tui(
            ws,
            app,
            "19d-review-queue",
            "Ctrl+R: the review queue: what the classifier proposes, with its evidence",
            "Doc classifier",
        )

    tk.run_tui(ws, app, registry, size=(170, 44))

    ws.tl(
        "config",
        "set",
        "threads.enabled",
        "true",
        "--company",
        "--reason",
        "switch threads on",
        who="demo",
    )
    ws.tl(
        "config",
        "set",
        "threads.enabled_types",
        "core.Record",
        "--company",
        "--reason",
        "threads on plain records",
        who="demo",
    )
    ws.tl("thread", "post", *P, "V-1001", "Flanges are short at grid C4, see #V-1002", who="amy")
    ws.tl("thread", "dispatch", *P, "V-1001", "/raise record Clash at grid C4", "--yes", who="amy")
    thread_app = build_app(ws, actor="user:amy")

    async def thread(pilot: Pilot[Any]) -> None:
        from phase0 import open_record

        await tk.until(pilot, lambda: len(thread_app.query("RecordGrid")) > 0, "the shell")
        await tk.until(pilot, lambda: "V-1001" in tk.screen_text(thread_app), "the grid")
        await open_record(pilot, thread_app, "V-1001")
        await pilot.press("T")
        await tk.until(
            pilot, lambda: "Flanges are short" in tk.screen_text(thread_app), "the thread"
        )
        thread_app.query_one("ThreadTab").focus()
        await tk.settle(pilot, 2)
        await pilot.press("c")
        await tk.until(
            pilot, lambda: "Message. / for commands" in tk.screen_text(thread_app), "the composer"
        )
        thread_app.screen.query_one("#tc-input", Input).value = "/link #V-1002 as requires"
        await tk.settle(pilot, 4)
        await pilot.press("enter")
        await tk.settle(pilot, 4)
        await tk.until(pilot, lambda: "AddLink" in tk.screen_text(thread_app), "the preview")
        tk.shot_tui(
            ws,
            thread_app,
            "19e-thread-dispatch-preview",
            "Record view, T, c: a slash command is previewed, with the caller's own access, first",
            "AddLink",
            "Flanges are short",
        )
        await pilot.press("escape", "escape")
        await tk.settle(pilot, 3)

    tk.run_tui(ws, thread_app, thread, size=(170, 48))


# --- 20 to 22 the schema registry, conformance and legacy loads (P1-I8) ----------------------

PACKAGE = "co.acme.engineering"
ADDITIVE = f"{PACKAGE}@3.3.0"
BREAKING = f"{PACKAGE}@4.0.0"


def section_schema_registry(ws: Workspace) -> None:
    renew_sessions(ws)
    demo = demo_module("p1_i8_demo")
    work = ws.root / "pkgs"
    work.mkdir()
    quietly(demo.prepare, work)

    sh = Shell(ws, "A schema change: drafted, analysed, reviewed by someone else, published", 118)
    sh.run(
        "schema",
        "package",
        "draft",
        "pkgs/pkg-3.3.0.yaml",
        "--changelog",
        "Adds the actuator make.",
        who="amy",
    )
    sh.run("schema", "package", "analyse", ADDITIVE, who="amy")
    sh.run("schema", "package", "classify", ADDITIVE, who="amy")
    sh.run("schema", "package", "submit", ADDITIVE, who="amy")
    sh.run("schema", "package", "approve", ADDITIVE, who="amy", ok=False)
    sh.run("schema", "package", "approve", ADDITIVE, "--comment", "additive, reviewed", who="demo")
    sh.run("schema", "package", "publish", ADDITIVE, who="demo")
    sh.note(
        "the admin drafts a second version that retypes size_in: breaking, so submit is refused"
    )
    sh.run("schema", "package", "draft", "pkgs/pkg-4.0.0.yaml", who="demo")
    sh.run("schema", "package", "analyse", BREAKING, who="demo")
    sh.run("schema", "package", "classify", BREAKING, who="demo", head=5)
    sh.run("schema", "package", "submit", BREAKING, who="demo", ok=False)
    ws.save("20a-package-lifecycle", sh.transcript.svg())

    app = build_app(ws, admin=True)

    async def workbench(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_screen(pilot, app, "ctrl+o", "Schema packages", "the workbench")
        await tk.until(pilot, lambda: "3.3.0" in tk.screen_text(app), "the package versions")
        tk.shot_tui(
            ws,
            app,
            "20b-workbench-tree",
            "Ctrl+O: the schema workbench: each version of each package, with its state and class",
            "Schema packages",
            "Published",
            "Draft",
        )
        await pilot.press("down", "3")
        await tk.settle(pilot, 3)
        scroll = app.screen.query_one("#log-panel")
        for _ in range(40):  # down to the hunk that adds the property
            if "actuator_make" in tk.screen_text(app):
                break
            scroll.scroll_relative(y=3, animate=False)
            await tk.settle(pilot, 2)
        scroll.scroll_relative(y=7, animate=False)
        await tk.settle(pilot, 2)
        tk.shot_tui(
            ws,
            app,
            "20c-workbench-diff",
            "Ctrl+O, 3: the diff of the highlighted version against the one below it",
            "@@",
        )
        await pilot.press("up")  # the breaking draft, on top
        await tk.until(
            pilot, lambda: "Review and publish" in tk.screen_text(app), "the review action"
        )
        await pilot.press("v")
        await tk.until(pilot, lambda: "Impact" in tk.screen_text(app), "the review screen")
        tk.shot_tui(
            ws,
            app,
            "20d-review-screen",
            "Ctrl+O, v: the review: classification, impact and the next step",
            "Impact",
        )
        await pilot.press("t")
        await tk.until(pilot, lambda: "Tested" in tk.screen_text(app), "the sample test")
        await pilot.press("s")
        await tk.until(pilot, lambda: "not allowed in place" in tk.screen_text(app), "the refusal")
        tk.shot_tui(
            ws,
            app,
            "20e-review-refused",
            "t, then s: tried on a sample of records; submitting the breaking change is refused",
            "Tested",
            "! ",
        )

    tk.run_tui(ws, app, workbench, size=(170, 48))

    sh = Shell(ws, "What a change touches in a project, and the project pinning a version", 118)
    impact = sh.run("schema", "package", "impact", ADDITIVE, "--project", "P999", who="demo")
    digest = next(line.split()[1] for line in impact.splitlines() if line.startswith("digest "))
    sh.run("schema", "adopt", "P999", PACKAGE, "3.3.0", who="amy", ok=False)
    sh.run("schema", "adopt", "P999", PACKAGE, "3.3.0", "--impact-sha256", digest, who="demo")
    sh.run("schema", "adoptions", who="demo")
    ws.save("20f-impact-and-pin", sh.transcript.svg())


# --- 21 waivers, conformance, crosswalk, export and import (P1-I8) -----------------------------

WAIVED = "psets.valve_data.size_in"
OTHER = "P999"  # pinned to 3.3.0 in section 20; P123 declares the strict conformance mode
WAIVER = f"{OTHER}/{WAIVED}@1"


def section_conformance(ws: Workspace) -> None:
    renew_sessions(ws)
    until = (tk.CLOCK.now.date() + timedelta(days=30)).isoformat()

    sh = Shell(ws, "A time-limited waiver: asked for, approved by an admin, counted apart", 118)
    request = ("schema", "waiver", "request", OTHER, WAIVED)
    sh.run(
        *request,
        "--reason",
        "Legacy valves keep the old nominal size.",
        "--expires",
        until,
        who="amy",
    )
    sh.run("schema", "waiver", "approve", WAIVER, who="amy", ok=False)
    sh.run("schema", "waiver", "approve", WAIVER, "--comment", "for 30 days", who="demo")
    sh.run("schema", "waiver", "ls", "--project", OTHER, who="amy")
    sh.run("schema", "conformance", "--project", OTHER, who="amy")
    sh.run("schema", "waiver", "revoke", WAIVER, "--reason", "Fixed at the source.", who="demo")
    sh.run("schema", "waiver", "ls", "--project", OTHER, who="amy")
    ws.save("21a-waivers", sh.transcript.svg())

    sh = Shell(ws, "How a project stands against the company schema, and its code crosswalk", 118)
    sh.run("schema", "conformance", *P, who="amy")
    sh.run("schema", "crosswalk", *P, who="amy")
    ws.save("21b-crosswalk", sh.transcript.svg())

    sh = Shell(ws, "Published packages to a git directory, and back in as drafts", 118)
    sh.run("schema", "export-git", "schema-git", who="amy", ok=False)
    sh.run("schema", "export-git", "schema-git", who="demo")
    sh.run("schema", "export-git", "schema-git", who="demo")
    sh.run("schema", "import-git", "schema-git", "--dry-run", who="demo")
    edited = ws.root / "schema-git" / f"{ADDITIVE}.yaml"
    edited.write_text(edited.read_text(encoding="utf-8") + "# edited by hand\n", encoding="utf-8")
    sh.note(f"someone edits {edited.name} in the checkout; the import checks every file first")
    sh.run("schema", "import-git", "schema-git", who="demo", ok=False)
    ws.save("21c-export-import", sh.transcript.svg())


# --- 22 legacy loads and lake marts (P1-I8) ---------------------------------------------------

LOAD_KEYS = {"ISO-0101": "ISO-0301", "ISO-0102": "ISO-0302", "PID-0201": "PID-0303"}
RUN = "dms/register#1"
STATUS_MART = "mart_document_status"


def section_legacy_load(ws: Workspace) -> None:
    renew_sessions(ws)
    demo = demo_module("p1_i8_demo")
    work = ws.root / "loads"
    quietly(demo.registers, work)
    register = work / "register.csv"
    text = register.read_text(encoding="utf-8")
    for old, new in LOAD_KEYS.items():  # the numbers of section 12 are taken: use new ones
        text = text.replace(old, new)
    register.write_text(text, encoding="utf-8")
    restricted = work / "restricted.csv"  # SEC is no document type of the standards: use PRC
    restricted.write_text(
        restricted.read_text(encoding="utf-8").replace("SEC-", "PRC-"), encoding="utf-8"
    )
    loader = ("--project", PROJECT, "--loader", "dms-register")
    run = (RUN, *P)

    sh = Shell(ws, "A legacy register: read, profiled and planned; nothing written yet", 118)
    sh.run("load", "open", "loads/register.csv", *loader, who="amy", ok=False)
    sh.run("load", "open", "loads/register.csv", *loader, who="demo")
    sh.run("load", "extract", *run, who="demo")
    sh.run("load", "profile", *run, who="demo")
    sh.run("load", "plan", *run, who="demo")
    sh.note("the lake is read before the load: the document mart for this project")
    sh.run("lake", "sync", who="demo")
    sh.run("lake", "mart", "show", STATUS_MART, who="demo")
    ws.save("22a-load-plan", sh.transcript.svg())

    sh = Shell(ws, "Loading what the plan said, reconciling, and the lake after", 118)
    sh.run("load", "load", *run, "--expect-new", "2", who="demo", ok=False)
    sh.run("load", "load", *run, "--expect-new", "3", who="demo")
    sh.run("load", "reconcile", *run, who="demo")
    sh.note("a second file holds one restricted document, loaded as a restricted run")
    ws.tl(
        "load",
        "open",
        "loads/restricted.csv",
        *loader,
        "--confidentiality",
        "restricted",
        who="demo",
    )
    for step in ("extract", "profile", "plan"):
        ws.tl("load", step, "dms/register#2", *P, who="demo")
    ws.tl("load", "load", "dms/register#2", *P, "--expect-new", "1", who="demo")
    sh.run("doc", "show", "PRC-0001", *P, who="demo", head=9)
    sh.run("lake", "sync", who="demo")
    sh.run("lake", "mart", "ls", who="demo")
    sh.run("lake", "mart", "show", STATUS_MART, who="demo")
    ws.save("22b-load-and-marts", sh.transcript.svg())

    sh = Shell(ws, "Taking the load back: compensated, and the mart falls back", 118)
    sh.run("load", "compensate", *run, "--reason", "demo: the load is taken back", who="demo")
    sh.run("doc", "show", "ISO-0301", *P, who="demo", head=4)
    sh.run("lake", "sync", who="demo")
    sh.run("lake", "mart", "show", STATUS_MART, who="demo")
    ws.tl("load", "open", "loads/register.csv", *loader, who="demo")
    ws.tl("load", "extract", "dms/register#3", *P, who="demo")
    ws.tl("load", "profile", "dms/register#3", *P, who="demo")
    sh.run("load", "plan", "dms/register#3", *P, who="demo")
    ws.tl("load", "void", "dms/register#3", *P, "--reason", "the plan was only a check", who="demo")
    ws.save("22c-compensate", sh.transcript.svg())


# --- 23 plain language and the record screen (P1-UX) -----------------------------------------

# Values for the three example sets of the company standard (codes from its lists), set on records
# the earlier sections made: key, set, name=value pairs. A string that is also a JSON number is
# quoted for `tl pset set`.
PLAIN_VALUES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "ISO-1234",
        "document_data",
        (
            "originator=Acme Piping",
            "area=Unit 47",
            "system=Fuel gas",
            "confidentiality_note=Vendor data, share with the owner only",
            "native_format=DWG",
            "review_due=2027-01-15",
        ),
    ),
    (
        "P123-RFI-0001",
        "rfi_data",
        (
            "location=Grid C-4",
            "drawing_ref=DWG-4711",
            "trade=structural",
            "cost_estimate=12500",
            "cost_currency=USD",
            "schedule_impact_days=3",
        ),
    ),
    (
        "P123-COR-0001",
        "correspondence_data",
        (
            'contract_clause="14.2"',
            "other_party_ref=ACME-LTR-0042",
            "response_required_by=2027-02-01",
            "delivery_method=email",
        ),
    ),
)


def row_with(table: DataTable[Any], text: str) -> int:
    """The index of the row of ``table`` that shows ``text`` in some cell."""
    for index in range(table.row_count):
        if any(text in str(cell) for cell in table.get_row_at(index)):
            return index
    raise tk.TourFailed(f"no row shows {text!r}")


async def open_row_record(pilot: Pilot[Any], app: Any, key: str, number: str, what: str) -> None:
    """Open the register on ``key``, put the cursor on the row of ``number`` and press Enter."""
    from tl_tui.widgets.record_screen import RecordScreen

    await open_screen(pilot, app, key, number, what)
    table = next(iter(app.screen.query(DataTable)))
    table.move_cursor(row=row_with(table, number))
    await tk.settle(pilot, 3)
    await pilot.press("enter")
    await tk.until(pilot, lambda: isinstance(app.screen, RecordScreen), f"the record of {number}")
    await tk.settle(pilot, 4)


def section_plain_record_screen(ws: Workspace) -> None:
    """The record screen opened from each register, its Properties tab, and the Ctrl+D toggle."""
    renew_sessions(ws)
    for record, pset, pairs in PLAIN_VALUES:
        out = ws.tl("pset", "set", *P, record, pset, *pairs, who="demo")
        expect("conformance" in out, f"{record} {pset}: no conformance line:\n{out}")

    def from_register(
        name: str,
        title: str,
        key: str,
        number: str,
        *needles: str,
        actor: str = "user:amy",
    ) -> None:
        app = build_app(ws, actor=actor)

        async def scenario(pilot: Pilot[Any]) -> None:
            await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
            await open_row_record(pilot, app, key, number, f"the register of {number}")
            await pilot.press("2")
            await tk.until(pilot, lambda: needles[0] in tk.screen_text(app), "the Properties tab")
            tk.shot_tui(ws, app, name, title, number, *needles)

        tk.run_tui(ws, app, scenario, size=(160, 48))

    from_register(
        "23a-document-properties",
        "F7, Enter, 2: a document's own properties, as a plain user sees them",
        "f7",
        "ISO-1234",
        "Document data",
        "Originator",
        "Acme Piping",
    )
    from_register(
        "23b-tag-properties",
        "F8, Enter, 2: a tag's properties, with the class's set",
        "f8",
        "47-FV-1001",
        "Valve data",
        "Body material",
    )
    from_register(
        "23c-rfi-properties",
        "Ctrl+G, Enter, 2: an RFI's properties",
        "ctrl+g",
        "P123-RFI-0001",
        "RFI data",
        "Trade",
        "Structural",
        "12500 USD",
        "US dollar",
    )
    from_register(
        "23d-correspondence-properties",
        "F5, Enter, 2: a letter's properties",
        "f5",
        "P123-COR-0001",
        "Correspondence data",
        "Contract clause",
        "14.2",
    )

    admin = build_app(ws, admin=True)

    async def toggle(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app_rows(admin)) > 0, "the shell")
        await open_row_record(pilot, admin, "f7", "ISO-1234", "the document register")
        tk.shot_tui(
            ws,
            admin,
            "23e-record-plain",
            "The record screen as an admin sees it by default: plain words",
            "ISO-1234",
        )
        await pilot.press("ctrl+d")
        await tk.until(pilot, lambda: "Schema hash" in tk.screen_text(admin), "details on")
        tk.shot_tui(
            ws,
            admin,
            "23f-record-technical",
            "Ctrl+D: the same record with ids, versions and keys (admins only)",
            "Schema hash",
            "Version",
            technical=True,
        )
        await pilot.press("ctrl+d")
        await tk.until(pilot, lambda: "Schema hash" not in tk.screen_text(admin), "details off")
        tk.shot_tui(
            ws,
            admin,
            "23g-record-plain-again",
            "Ctrl+D again: back to plain words",
            "Originator",
            "ISO-1234",
        )

    tk.run_tui(ws, admin, toggle, size=(160, 48))


def app_rows(app: Any) -> list[Any]:
    from tl_tui.widgets.grid import RecordGrid

    return list(app.query(RecordGrid))


# --- 24 the log standard, the RFI record and document preview (P1-UX2) -----------------------

QUESTION_24 = (
    "The piling layout in revision B puts pile P-17 inside the route of the fuel gas line "
    "47-P-101, and the utilities drawing shows the same corridor for the cooling water return. "
    "Please confirm which of the two keeps the corridor, whether the pile can move 400 mm to the "
    "east without a new load calculation, and whether the cooling water line may be re-routed "
    "above the beam B12 if the pile stays where it is. We need the answer before the pile cap "
    "formwork is ordered."
)
SUBJECT_24 = "Conflict in piling and utilities at AZ203"
SUBJECT_24B = "Cable tray support spacing in the pipe rack"
DOCUMENT_24 = "ISO-6100"


def make_pdf(path: Path, pages: int) -> None:
    """A small real PDF (pypdfium2 writes it), so the preview can count its pages."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(300, 400)
    document.save(str(path))


def section_log_standard(ws: Workspace) -> str:
    """An RFI after an answer round with two files, a document with a 3-page PDF, and six shots:
    the log wide and stacked, the RFI record and its files, the document log with the page-count
    fallback (images off), and the same RFI log for a reader. Returns the RFI number."""
    renew_sessions(ws)
    ws.tl("admin", "user", "add", "reader", "--kind", "agent", who="demo")
    make_pdf(ws.root / "iso-6100.pdf", 3)
    make_pdf(ws.root / "beam-b12-sketch.pdf", 1)
    (ws.root / "survey-notes.txt").write_text(
        "Survey of the corridor at AZ203\npile P-17 at grid C-4, east offset to be confirmed\n"
    )
    needed = (tk.CLOCK.now.date() + timedelta(days=10)).isoformat()
    raised = ws.tl(
        "rfi",
        "raise",
        *P,
        "--subject",
        SUBJECT_24,
        "--question",
        QUESTION_24,
        "--discipline",
        "structural",
        "--required-by",
        needed,
        "--to",
        MERIDIAN,
        who="amy",
    )
    rfi = made(raised, "raised")
    for name in ("beam-b12-sketch.pdf", "survey-notes.txt"):
        ws.tl(
            "file",
            "put",
            name,
            *P,
            "--record",
            rfi,
            "--slot",
            "attachment",
            "--actor",
            "user:amy",
            who="amy",
        )
    ws.tl("rfi", "submit", rfi, *P, who="amy")
    ws.tl("rfi", "issue", rfi, *P, who="dora")
    ws.tl(
        "rfi",
        "answer",
        rfi,
        *P,
        "--answer",
        "Use the original routing.",
        "--cost-impact",
        "no",
        "--schedule-impact",
        "no",
        who="amy",
    )
    ws.tl(
        "rfi",
        "review",
        rfi,
        *P,
        "--reject",
        "--note",
        "The beam moved in revision C; please check again.",
        who="dora",
    )
    ws.tl("rfi", "reissue", rfi, *P, "--reason", "Revision C attached", who="amy")
    ws.tl("rfi", "issue", rfi, *P, who="dora")  # a reissued item goes back through the controller
    waiting = made(
        ws.tl(
            "rfi",
            "raise",
            *P,
            "--subject",
            SUBJECT_24B,
            "--question",
            "Confirm 1.5 m support spacing for the cable trays on rack R-2.",
            "--discipline",
            "structural",
            "--required-by",
            needed,
            "--to",
            MERIDIAN,
            who="amy",
        ),
        "raised",
    )
    ws.tl("rfi", "submit", waiting, *P, who="amy")
    ws.tl(
        "doc",
        "register",
        DOCUMENT_24,
        *P,
        "--title",
        "Isometric, line 47-P-103",
        "--type",
        "ISO",
        "--discipline",
        "PIP",
        who="amy",
    )
    ws.tl("doc", "rev", "create", DOCUMENT_24, *P, "--purpose", "For review", who="amy")
    ws.tl(
        "doc", "rendition", "add", DOCUMENT_24, "A", "iso-6100.pdf", *P, "--kind", "pdf", who="amy"
    )
    ws.tl("doc", "rev", "issue", DOCUMENT_24, "A", *P, "--status", "IFR", who="demo")

    def rfi_log(
        actor: str,
        name: str,
        title: str,
        size: tuple[int, int],
        *needles: str,
        bar: str,
        absent: str = "",
        number: str = "",
        subject: str = SUBJECT_24,
        controller: bool = False,
    ) -> None:
        number = number or rfi
        app = build_app(ws, actor=actor, controller=controller)

        async def scenario(pilot: Pilot[Any]) -> None:
            await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
            await open_screen(pilot, app, "ctrl+g", number, "the RFI log")
            table = app.screen.query_one("#log-table", DataTable)
            table.move_cursor(row=row_with(table, number))
            await tk.until(pilot, lambda: bar in tk.screen_text(app), "the actions bar")
            tk.expect(
                not absent or absent not in tk.screen_text(app),
                f"{name}: {absent!r} is offered to {actor}:\n{tk.screen_text(app)}",
            )
            tk.shot_tui(ws, app, name, title, number, subject, bar, *needles)

        tk.run_tui(ws, app, scenario, size=size)

    rfi_log(
        "user:amy",
        "24a-rfi-log-wide",
        "Ctrl+G: the RFI log at 170 columns: crumb, list, the record beside it, the actions bar",
        (170, 40),
        "RFI log",
        "[a] Answer",
        bar="Open record",
    )
    rfi_log(
        "user:amy",
        "24b-rfi-log-stacked",
        "The same log at 100 columns: the record panel moves below the list",
        (100, 40),
        "RFI log",
        bar="Open record",
    )

    app = build_app(ws, actor="user:amy")

    async def record(pilot: Pilot[Any]) -> None:
        from tl_tui.widgets.record_screen import RecordScreen

        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_screen(pilot, app, "ctrl+g", rfi, "the RFI log")
        table = app.screen.query_one("#log-table", DataTable)
        table.move_cursor(row=row_with(table, rfi))
        await tk.settle(pilot, 3)
        await pilot.press("enter")
        await tk.until(pilot, lambda: isinstance(app.screen, RecordScreen), "the record screen")
        await tk.until(pilot, lambda: "Answer rejected" in tk.screen_text(app), "the timeline")
        tk.shot_tui(
            ws,
            app,
            "24c-rfi-record",
            "Enter on the RFI: the question whole, then the timeline of the answer round",
            "Question",
            "Answer rejected",
            "Reissued",
            "amy",
        )
        await pilot.press("6")
        await tk.until(pilot, lambda: "survey-notes.txt" in tk.screen_text(app), "the Files tab")
        tk.shot_tui(
            ws,
            app,
            "24d-rfi-files",
            "6: the Files tab: each attachment with its kind, size and (for a PDF) pages",
            "beam-b12-sketch.pdf",
            "survey-notes.txt",
        )

    tk.run_tui(ws, app, record, size=(150, 62))

    saved = os.environ.get("TL_IMAGES")
    os.environ["TL_IMAGES"] = "off"  # a terminal without images: the panel gives the page count
    try:
        docs = build_app(ws, actor="user:amy")

        async def register(pilot: Pilot[Any]) -> None:
            await tk.until(pilot, lambda: len(app_rows(docs)) > 0, "the shell")
            await open_screen(pilot, docs, "f7", DOCUMENT_24, "the document register")
            table = docs.screen.query_one("#log-table", DataTable)
            table.move_cursor(row=row_with(table, DOCUMENT_24))
            await tk.until(pilot, lambda: "3 pages" in tk.screen_text(docs), "the page count")
            tk.shot_tui(
                ws,
                docs,
                "24e-document-preview-fallback",
                "F7: the document log: the PDF's kind, size and 3 pages where images are not shown",
                DOCUMENT_24,
                "PDF document",
                "3 pages",
                "[v] Open file",
            )

        tk.run_tui(ws, docs, register, size=(170, 44))
    finally:
        if saved is None:
            os.environ.pop("TL_IMAGES", None)
        else:
            os.environ["TL_IMAGES"] = saved

    rfi_log(
        "user:amy",
        "24f-rfi-log-plain-user",
        "An RFI waiting to be issued, for a plain user: Return to draft, but no Issue",
        (170, 40),
        "RFI log",
        "[r] Return to draft",
        bar="Open record",
        absent="[u] Issue",
        number=waiting,
        subject=SUBJECT_24B,
    )
    rfi_log(
        "user:dora",
        "24g-rfi-log-controller",
        "The same RFI for a controller: Issue is offered as well",
        (170, 40),
        "RFI log",
        "[u] Issue",
        bar="Open record",
        number=waiting,
        subject=SUBJECT_24B,
        controller=True,
    )
    return rfi


# --- the tour --------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=REPO / "docs/reports/tour/phase-1")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    for old in out.glob("*.svg"):
        old.unlink()
    tk.freeze()
    tk.fixed_archive_key()
    ws = Workspace(out)
    try:
        print("setting up the ledger and its people", flush=True)
        setup(ws)
        print("P1-I0: identity and admin", flush=True)
        section_sign_in(ws)
        token = section_accounts(ws)
        section_lockout(ws)
        section_agent(ws, token)
        section_postgres(ws)
        print("P1-I1: standards and tags", flush=True)
        section_standards(ws)
        section_tags(ws)
        section_tag_import(ws)
        print("P1-I2: document control", flush=True)
        section_documents(ws)
        section_stale(ws)
        section_transmittal_review(ws)
        section_register_tui(ws)
        section_dms_import(ws)
        section_refused(ws)
        print("P1-I2b: the document controller role", flush=True)
        section_controller(ws)
        print("P1-I3: the derivation pipeline", flush=True)
        section_derive(ws)
        print("P1-I4: schedules and cost", flush=True)
        section_schedules(ws)
        print("P1-I5: correspondence", flush=True)
        section_correspondence(ws)
        print("P1-I6: RFIs and commercial notices", flush=True)
        section_rfi(ws)
        print("P1-I7: the integration layer and record threads", flush=True)
        section_integration(ws)
        print("P1-I8: the schema registry, conformance and legacy loads", flush=True)
        section_schema_registry(ws)
        section_conformance(ws)
        section_legacy_load(ws)
        print("P1-UX: plain language and the record screen", flush=True)
        section_plain_record_screen(ws)
        print("P1-UX2: the log standard, the RFI record and document preview", flush=True)
        section_log_standard(ws)
    finally:
        ws.close()
    print(f"wrote {len(ws.written)} screenshots to {out}")
    return tk.report_leaks()


if __name__ == "__main__":
    sys.exit(main())
