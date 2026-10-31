"""The module roles log: who holds which module role on this project (RM-S3; ADR-0021).

A full-size modal opened with ``m`` on the accounts screen by an admin, a ``LogScreen``. The list is
the explicit grants (account, module, role, who granted it, since); the panel under it describes the
highlighted account: its name, where its roles come from (``Admin``, ``Granted``, ``Derived``) and
one property line per module under **Effective roles**. ``r`` revokes the highlighted grant (after
asking for a reason) and ``n`` adds a grant (a form: account, module, role, reason). The service
decides everything: a refusal (the grant is gone, the caller is not an admin) is shown in the status
line and nothing changes. Every change is one client call and the list is read again afterwards;
nothing is stored here. Plain words; the account id is a column in technical mode only.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import DataTable, Input, Static
from tl_core.auth.module_role_views import EffectiveRoleView, ModuleRoleGrantView
from tl_core.auth.module_roles import load_role_table
from tl_core.modules import load_modules
from tl_core.settings.layers import project_of_scope

from tl_tui.admin_text import (
    ALL_MODULES,
    MODULE_ROLE_COLUMNS,
    TECHNICAL_MODULE_ROLE_COLUMNS,
    effective_page,
    grant_cells,
    module_label,
)
from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Panel, render
from tl_tui.log_text import actions_text
from tl_tui.widgets.action_form import ActionFormScreen, FormField
from tl_tui.widgets.log_screen import LogAction, LogScreen

COMPANY = "company"


class ModuleRolesLog(LogScreen[ModuleRoleGrantView]):
    """The explicit module role grants of ``project`` (``project:<id>`` or ``company``)."""

    LOG_NAME: ClassVar[str] = "Module roles"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    # and F1 lists the rest (HELP_KEYS)
    KEY_HINTS: ClassVar[str] = "n new grant  / filter  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("n new grant", "/ filter")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("n", "Grant a module role to an account (a form)"),
        ("r", "Take the highlighted grant away (asks for a reason)"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("n", "new_grant", "New grant", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str, actor: str) -> None:
        super().__init__()
        self.client = client
        self.project = project  # "project:<id>" or "company"
        self.actor = actor
        self.names: dict[str, str] = {}  # username -> shown name
        self.accounts: dict[str, str] = {}  # username -> account id (the form's choices)
        self.effective: dict[str, list[EffectiveRoleView]] = {}  # account id -> per module
        self._flash = ""  # a note for the status line that the reload would replace

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return project_of_scope(self.project) or "Company"

    def columns(self) -> Sequence[str]:
        if mode_of(self.app).technical:
            return TECHNICAL_MODULE_ROLE_COLUMNS
        return MODULE_ROLE_COLUMNS

    def keep_columns(self) -> Sequence[str]:
        """All of them: a column that is the same in every row (one module) still shows."""
        return list(self.columns())

    def load_rows(self) -> Sequence[ModuleRoleGrantView]:
        found = self.client.list_module_roles(self.project)
        accounts = self.client.list_accounts()
        self.names = {a.username: a.display_name for a in accounts}
        self.accounts = {a.username: a.account_id for a in accounts if a.status == "active"}
        self.effective = {
            account_id: self.client.effective_roles(account_id, self.project)
            for account_id in dict.fromkeys(g.account_id for g in found)
        }
        return found

    def row_key(self, row: ModuleRoleGrantView) -> str:
        return f"{row.account_id}/{row.project}/{row.module}/{row.role}"

    def row_cells(self, row: ModuleRoleGrantView) -> Sequence[str]:
        return grant_cells(row, self.names, technical=mode_of(self.app).technical)

    def row_record(self, row: ModuleRoleGrantView) -> tuple[str, str]:
        """The account's name and what the row grants (never an id)."""
        return (
            self.names.get(row.username, row.username),
            f"{row.role.capitalize()} on {module_label(row.module)}",
        )

    def panel_text(self, row: ModuleRoleGrantView | None) -> Panel:
        if row is None:
            return "No module roles are granted here."
        return render(
            effective_page(
                self.names.get(row.username, row.username), self.effective.get(row.account_id, [])
            )
        )

    def summary_text(self) -> str:
        if self._flash:
            flash, self._flash = self._flash, ""
            return flash
        return f"Module roles ({len(self.rows)})   n adds a grant"

    def open_row(self, row: ModuleRoleGrantView) -> None:
        """Nothing to open: a grant is not a record."""

    def _draw_actions(self, *, failed: bool = False) -> None:
        """The bar without ``[Enter] Open record``: a grant has no record to open."""
        bar = self.query_one("#log-actions", Static)
        bar.update(
            "" if failed or self.current() is None else actions_text(self.offered, can_open=False)
        )

    def refresh_for_display_mode(self) -> None:
        """Redraw the columns and the rows when technical details are switched."""
        table = self.query_one("#log-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*self.columns())
        super().refresh_for_display_mode()

    # --- the actions bar -----------------------------------------------------------------------

    def actions_for(self, row: ModuleRoleGrantView) -> Sequence[LogAction]:
        return [LogAction("r", "Revoke", self._revoke)]

    def _send(self, done: str, call: Callable[[], str | None]) -> None:
        """Send one change. A refusal is kept for the status line and the list is read again
        (the attempt does that) so it shows what the grants really are now. ``call`` may answer a
        note that replaces ``done`` (the role was already held)."""
        try:
            note = call()
        except CLIENT_ERRORS as exc:
            self._flash = "! " + describe_error(exc)
            return
        self._flash = note or done

    def _revoke(self) -> None:
        """Revoke the highlighted grant after asking for a reason."""
        row = self.current()
        if row is None:
            return
        who = self.names.get(row.username, row.username)
        what = f"{row.role} on {module_label(row.module)}"

        def answered(answer: dict[str, str] | None) -> None:
            if answer is None:  # cancelled: nothing is changed
                return
            self.attempt(
                lambda: self._send(
                    f"Revoked {what} from {who}",
                    lambda: self._revoke_call(row, answer["reason"]),
                )
            )

        self.app.push_screen(
            ActionFormScreen(f"Revoke {what} from {who}", (FormField("reason", "Reason"),)),
            answered,
        )

    def _revoke_call(self, row: ModuleRoleGrantView, reason: str) -> None:
        self.client.revoke_module_role(row.account_id, row.project, row.module, row.role, reason)

    # --- the log's own key ---------------------------------------------------------------------

    def action_new_grant(self) -> None:
        """Ask for account, module, role and reason, then grant."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if not self.accounts:
            self.say("There are no accounts to grant a role to.", error=True)
            return
        row = self.current()
        first = row.username if row is not None and row.username in self.accounts else ""
        fields = (
            FormField("account", "Account", "choice", tuple(self.accounts), default=first),
            FormField(
                "module",
                "Module",
                "choice",
                (ALL_MODULES, *sorted(spec.name for spec in load_modules())),
                default=row.module if row is not None else ALL_MODULES,
            ),
            FormField("role", "Role", "choice", tuple(load_role_table().roles)),
            FormField("reason", "Reason"),
        )

        def answered(answer: dict[str, str] | None) -> None:
            if answer is None:  # cancelled: nothing is changed
                return
            account_id = self.accounts[answer["account"]]
            self.attempt(
                lambda: self._send(
                    f"Granted {answer['role']} on {module_label(answer['module'])} "
                    f"to {self.names.get(answer['account'], answer['account'])}",
                    lambda: self._grant(account_id, answer),
                )
            )

        self.app.push_screen(ActionFormScreen("New module role grant", fields), answered)

    def _grant(self, account_id: str, answer: dict[str, str]) -> str | None:
        result = self.client.grant_module_role(
            account_id, self.project, answer["module"], answer["role"], answer["reason"]
        )
        if result.changed:
            return None
        who = self.names.get(answer["account"], answer["account"])
        return f"{who} already holds {answer['role']} on {module_label(answer['module'])}"

    def action_reload(self) -> None:
        self._flash = "Reloaded."
        self.reload()
