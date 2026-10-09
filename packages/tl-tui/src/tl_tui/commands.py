"""The commands the palette offers (brief 10.2): one entry per app action, with its key.

Pure data. ``action`` names a ``TlApp.action_<action>`` method; the palette dismisses with the
command id and the app runs it. Keep this list in step with the key map (`tl_tui/keymap.py`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppCommand:
    id: str
    label: str
    keys: str  # shown right-aligned in the palette, "" when the command has no key
    action: str  # TlApp.action_<action>


APP_COMMANDS: tuple[AppCommand, ...] = (
    AppCommand("new-record", "New record", "n", "new_record"),
    AppCommand("link", "Link the selection or open record to another record", "l", "link"),
    AppCommand(
        "tray-add", "Add the selection or open record to the reference tray", "R", "tray_add"
    ),
    AppCommand("tray-open", "Open the reference tray", "F4", "tray_open"),
    AppCommand("workflow", "Workflow actions for the open record", "w", "workflow"),
    AppCommand("trace", "Trace the open record through its links", "t", "trace"),
    AppCommand("back", "Back to the previous record", "Alt+Left", "back"),
    AppCommand("forward", "Forward to the next record", "Alt+Right", "forward"),
    AppCommand("toggle-nav", "Show or hide the navigation panel", "F2", "toggle_nav"),
    AppCommand("toggle-context", "Show or hide the context panel", "F3", "toggle_context"),
    AppCommand("help", "Show the key map", "F1", "help"),
)


def command_by_id(command_id: str) -> AppCommand | None:
    return next((c for c in APP_COMMANDS if c.id == command_id), None)
