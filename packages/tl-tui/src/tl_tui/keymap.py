"""The key map as data: every documented key, the widget that implements it, and the help text.

The help screen (`F1`, `?`) renders `help_text()`. The tests check that each entry with an owner
names a real binding on that owner's class, so the documented keys cannot drift from the code
(P0-I2-T17b; brief 10.3 and 10.4).
"""

from __future__ import annotations

from dataclasses import dataclass

CONTEXTS: tuple[str, ...] = (
    "App",
    "Grid",
    "Record view",
    "Links tab",
    "Trace tab",
    "Palette",
    "Link picker",
    "Reference tray",
    "Workflow menu",
    "Feed pane",
    "Composer",
    "Forms",
    "About:config",
    "Accounts",
)


@dataclass(frozen=True)
class KeyEntry:
    """One documented key. ``owner`` is the class that implements it, or ``None`` for keys
    Textual provides; ``binding`` is that class's binding key string, or ``None``."""

    context: str
    keys: str
    description: str
    owner: str | None = None
    binding: str | None = None


KEYMAP: tuple[KeyEntry, ...] = (
    KeyEntry("App", "F1  ?", "Show this key map", "TlApp", "f1"),
    KeyEntry("App", "F2", "Show or hide the navigation panel", "TlApp", "f2"),
    KeyEntry("App", "F3", "Show or hide the context panel", "TlApp", "f3"),
    KeyEntry("App", "F6  Shift+F6", "Move focus between panels", "TlApp", "f6"),
    KeyEntry("App", "n", "New record", "TlApp", "n"),
    KeyEntry("App", "/", "Filter the list with the query language", "TlApp", "slash"),
    KeyEntry("App", "Esc", "Close an open side panel (narrow terminals)", "TlApp", "escape"),
    KeyEntry(
        "App", "Ctrl+P  :", "Command palette: commands, records, go to a key", "TlApp", "ctrl+p"
    ),
    KeyEntry("App", "l", "Link the selection or the open record to another record", "TlApp", "l"),
    KeyEntry(
        "App", "R", "Add the selection or the open record to the reference tray", "TlApp", "R"
    ),
    KeyEntry("App", "F4", "Open the reference tray", "TlApp", "f4"),
    KeyEntry("App", "w", "Workflow actions of the open record", "TlApp", "w"),
    KeyEntry("App", "t", "Trace the open record through its links", "TlApp", "t"),
    KeyEntry(
        "App",
        "Alt+Left  Alt+Right",
        "Back or forward through followed records",
        "TlApp",
        "alt+left",
    ),
    KeyEntry("App", "F", "Activity feed of the open record, or of the project", "TlApp", "F"),
    KeyEntry("App", "p", "Post to the feed (composer)", "TlApp", "p"),
    KeyEntry(
        "App",
        "F7",
        "Document register: revisions, stale links, re-pin, transmittals",
        "TlApp",
        "f7",
    ),
    KeyEntry(
        "App",
        "F8",
        "Tag register: the project's tags, their class and what they lack",
        "TlApp",
        "f8",
    ),
    KeyEntry("App", "F9", "about:config: the settings of this project", "TlApp", "f9"),
    KeyEntry("App", "F10", "Accounts and agent tokens (admins only)", "TlApp", "f10"),
    KeyEntry(
        "App",
        "F11",
        "Derived documents: extracted data, validation report, jobs, publish preview",
        "TlApp",
        "f11",
    ),
    KeyEntry(
        "App",
        "F12",
        "Schedules: snapshots, comparison, activities, look-ahead, orphaned links",
        "TlApp",
        "f12",
    ),
    KeyEntry("App", "Ctrl+Q", "Quit"),
    KeyEntry(
        "Grid",
        "Up Down PgUp PgDn Home End",
        "Move the cursor",
        "RecordGrid",
        "up",
    ),
    KeyEntry("Grid", "Left Right", "Choose the column to sort by", "RecordGrid", "left"),
    KeyEntry("Grid", "Space", "Select or unselect the row", "RecordGrid", "space"),
    KeyEntry(
        "Grid",
        "Shift+Up Shift+Down",
        "Extend the selection",
        "RecordGrid",
        "shift+down",
    ),
    KeyEntry("Grid", "Ctrl+A", "Select all loaded rows", "RecordGrid", "ctrl+a"),
    KeyEntry("Grid", "Enter", "Open the record", "RecordGrid", "enter"),
    KeyEntry(
        "Grid",
        "s",
        "Sort by the chosen column (again: descending, then off)",
        "RecordGrid",
        "s",
    ),
    KeyEntry("Grid", "c", "Choose columns", "RecordGrid", "c"),
    KeyEntry("Grid", "y", "Copy the selection as TSV", "RecordGrid", "y"),
    KeyEntry("Grid", "r", "Reload the rows", "RecordGrid", "r"),
    KeyEntry("Record view", "Esc", "Back to the grid", "RecordView", "escape"),
    KeyEntry(
        "Record view",
        "[  ]",
        "Previous or next record in the list",
        "RecordView",
        "left_square_bracket",
    ),
    KeyEntry("Record view", "h", "Show the History tab", "RecordView", "h"),
    KeyEntry("Record view", "e", "Edit the record", "RecordView", "e"),
    KeyEntry(
        "Record view",
        "1  2  3  4  5",
        "Details, Psets, Links, History, Trace tab",
        "RecordView",
        "1",
    ),
    KeyEntry("Links tab", "Enter", "Open the record at the other end", "LinksTab", "enter"),
    KeyEntry("Links tab", "a", "Accept the highlighted suggestion", "LinksTab", "a"),
    KeyEntry("Links tab", "d", "Decline the highlighted suggestion", "LinksTab", "d"),
    KeyEntry("Links tab", "u", "Re-pin the highlighted link to a revision", "LinksTab", "u"),
    KeyEntry("Links tab", "v", "Mark the highlighted link verified", "LinksTab", "v"),
    KeyEntry("Links tab", "x", "Retract the highlighted link (with a reason)", "LinksTab", "x"),
    KeyEntry("Trace tab", "Enter", "Open the highlighted record"),
    KeyEntry("Trace tab", "+  -", "More or fewer hops", "TraceTab", "plus"),
    KeyEntry("Trace tab", "o", "Follow outbound, inbound or both directions", "TraceTab", "o"),
    KeyEntry("Palette", "Up  Down", "Move the highlight", "CommandPalette", "down"),
    KeyEntry("Palette", "Enter", "Run the highlighted entry"),
    KeyEntry("Palette", "Tab", "Narrow to all, records or commands", "CommandPalette", "tab"),
    KeyEntry("Palette", "Esc", "Close", "CommandPalette", "escape"),
    KeyEntry("Link picker", "Up  Down", "Move the highlight", "LinkPicker", "down"),
    KeyEntry(
        "Link picker", "Ctrl+T", "Select or unselect the highlighted record", "LinkPicker", "ctrl+t"
    ),
    KeyEntry("Link picker", "Enter", "Link the selected records (or the highlighted one)"),
    KeyEntry("Link picker", "Ctrl+N", "Create a new record and link it", "LinkPicker", "ctrl+n"),
    KeyEntry("Link picker", "Esc", "Cancel", "LinkPicker", "escape"),
    KeyEntry(
        "Reference tray",
        "Space",
        "Tick or untick the highlighted record",
        "ReferenceTrayScreen",
        "space",
    ),
    KeyEntry(
        "Reference tray", "Delete", "Remove the highlighted record", "ReferenceTrayScreen", "delete"
    ),
    KeyEntry("Reference tray", "Enter", "Link the ticked records to the open record"),
    KeyEntry("Reference tray", "c", "Clear the tray", "ReferenceTrayScreen", "c"),
    KeyEntry("Reference tray", "Esc", "Close", "ReferenceTrayScreen", "escape"),
    KeyEntry("Workflow menu", "Up  Down", "Choose a transition", "WorkflowMenu", "down"),
    KeyEntry("Workflow menu", "Enter", "Run the chosen transition"),
    KeyEntry("Workflow menu", "Esc", "Close", "WorkflowMenu", "escape"),
    KeyEntry("Feed pane", "j  k", "Move down or up", "FeedPane", "j"),
    KeyEntry("Feed pane", "Enter  o", "Open the first record the item references", "FeedPane", "o"),
    KeyEntry("Feed pane", "p", "New post", "FeedPane", "p"),
    KeyEntry(
        "Feed pane", ".  +  x", "React: ack, +1, resolved (again clears)", "FeedPane", "full_stop"
    ),
    KeyEntry("Feed pane", "1  2  3  4", "Filter: all, posts, events, #hold", "FeedPane", "1"),
    KeyEntry("Feed pane", "L", "Include records one link away (record feed)", "FeedPane", "L"),
    KeyEntry(
        "Feed pane", "a", "Accept the suggestion (arrives with the review queue)", "FeedPane", "a"
    ),
    KeyEntry("Feed pane", "t  f", "Open thread, follow (off in Phase 0)", "FeedPane", "t"),
    KeyEntry("Feed pane", "r", "Reload", "FeedPane", "r"),
    KeyEntry("Feed pane", "Esc", "Back to the grid", "TlApp", "escape"),
    KeyEntry(
        "Composer",
        "Tab",
        "Put the highlighted # or @ candidate into the text",
        "ComposerScreen",
        "tab",
    ),
    KeyEntry("Composer", "Up  Down", "Choose a candidate", "ComposerScreen", "down"),
    KeyEntry("Composer", "Enter  Ctrl+S", "Post", "ComposerScreen", "ctrl+s"),
    KeyEntry("Composer", "Esc", "Close the list, then cancel", "ComposerScreen", "escape"),
    KeyEntry("Forms", "Tab  Shift+Tab", "Next or previous field"),
    KeyEntry(
        "Forms",
        "Ctrl+S",
        "Save (edit form) or create (new record)",
        "EditForm",
        "ctrl+s",
    ),
    KeyEntry("Forms", "Esc", "Cancel", "EditForm", "escape"),
    KeyEntry("About:config", "Up  Down  PgUp  PgDn", "Choose a setting"),
    KeyEntry(
        "About:config", "e  Enter", "Change the value at the layer shown", "SettingsScreen", "e"
    ),
    KeyEntry("About:config", "r", "Reset: take this layer's value away", "SettingsScreen", "r"),
    KeyEntry("About:config", "h", "History of the setting, with undo (u)", "SettingsScreen", "h"),
    KeyEntry("About:config", "k", "Lock or unlock for projects (company)", "SettingsScreen", "k"),
    KeyEntry(
        "About:config", "L", "Send changes to the project or the company", "SettingsScreen", "L"
    ),
    KeyEntry("About:config", "m", "Only the settings set at this layer (●)", "SettingsScreen", "m"),
    KeyEntry("About:config", "/", "Filter by name or description", "SettingsScreen", "slash"),
    KeyEntry("About:config", "F5", "Read the list again", "SettingsScreen", "f5"),
    KeyEntry("About:config", "Ctrl+S  Esc", "Apply or cancel a change", "SettingForm", "ctrl+s"),
    KeyEntry("About:config", "Esc", "Close", "SettingsScreen", "escape"),
    KeyEntry("Accounts", "Up  Down  PgUp  PgDn", "Choose an account"),
    KeyEntry(
        "Accounts", "d", "Disable or enable the account (asks for a reason)", "AdminScreen", "d"
    ),
    KeyEntry("Accounts", "r", "Give or take away the admin role (a person)", "AdminScreen", "r"),
    KeyEntry(
        "Accounts",
        "c",
        "Give or take away the document controller role (not an agent)",
        "AdminScreen",
        "c",
    ),
    KeyEntry("Accounts", "t", "Switch between accounts and agent tokens", "AdminScreen", "t"),
    KeyEntry("Accounts", "a", "Add an account (a form)", "AdminScreen", "a"),
    KeyEntry("Accounts", "p", "Set a person's password (a form)", "AdminScreen", "p"),
    KeyEntry("Accounts", "i", "Issue a token for the agent; it is shown once", "AdminScreen", "i"),
    KeyEntry("Accounts", "x", "Revoke the highlighted token (tokens view)", "AdminScreen", "x"),
    KeyEntry("Accounts", "Ctrl+S  Esc", "Apply or cancel a form", "AccountForm", "ctrl+s"),
    KeyEntry("Accounts", "F5", "Read the lists again", "AdminScreen", "f5"),
    KeyEntry("Accounts", "Esc", "Close", "AdminScreen", "escape"),
)


def help_text() -> str:
    """Plain-text key map: a heading per context, one indented line per entry, blank lines
    between contexts."""
    blocks: list[str] = []
    for context in CONTEXTS:
        lines = [context]
        lines.extend(
            f"  {entry.keys:<30}{entry.description}" for entry in KEYMAP if entry.context == context
        )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
