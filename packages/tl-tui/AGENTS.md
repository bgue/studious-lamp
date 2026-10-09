# AGENTS.md — tl-tui

Read the root `AGENTS.md` first. These rules add to it.

- No business logic here. Screens and widgets call `ClientInterface` only; they never import `tl_core.services` handlers, write SQL, or touch the ledger. Only `embedded.py` and `main.py` import `tl_core` services or `tl_adapters`.
- Widgets render and post messages (`tl_tui/messages.py`); they do not call each other. The app routes messages. A new cross-widget interaction is a new message class, not an attribute poke.
- A `ClientInterface` call may raise `CLIENT_ERRORS`. Catch them where you call, post `StatusMessage(describe_error(exc), "error")`, and keep your state.
- Meaning never rides on colour alone: pair status with a symbol or text (✓ ok, ! warning, ✗ nonconformant, ● required, ○ advisory, ■ locked).
- A widget that owns keys defines `KEY_HINTS: ClassVar[str]`; the footer shows it while the widget (or a descendant) has focus.
- Tests: no async pytest plugin. Use `tests/helpers.run_pilot` and `screen_text`; use `tests/fakes.FakeClient` instead of a database. Snapshot tests pin the terminal size (120x40 or 80x24) and render no clock or random value.
- pyright runs in standard mode on this package (not strict). Keep ruff clean: lines are at most 100 columns, docstrings included.
