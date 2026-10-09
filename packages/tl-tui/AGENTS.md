# AGENTS.md — tl-tui

Read the root `AGENTS.md` first. These rules add to it.

- No business logic here. Screens and widgets call `ClientInterface` only; they never import `tl_core.services` handlers, write SQL, or touch the ledger. Only `embedded.py` and `main.py` import `tl_core` services or `tl_adapters`.
- Widgets render and post messages (`tl_tui/messages.py`); they do not call each other. The app routes messages. A new cross-widget interaction is a new message class, not an attribute poke.
- A `ClientInterface` call may raise `CLIENT_ERRORS`. Catch them where you call, post `StatusMessage(describe_error(exc), "error")`, and keep your state.
- Meaning never rides on colour alone: pair status with a symbol or text (✓ ok, ! warning, ✗ nonconformant, ● required, ○ advisory, ■ locked).
- A widget that owns keys defines `KEY_HINTS: ClassVar[str]`; the footer shows it while the widget (or a descendant) has focus.
- Forms write only through `tl_tui/forms.py` (`save_record_edits`): it groups edits by (pset, layer) and chains versions. A cleared field is sent as `None` (the pset service treats it as "unset"). Never send a command from a widget directly.
- A new key binding goes in `tl_tui/keymap.py` too; `tests/test_keymap.py` fails when a documented key is not a real binding.
- Never load all rows on the UI thread: sort goes to the server (`order_by`), End pages in a worker (see L-P0-I2-B5).
- Textual traps: do not name an attribute after a DOM property (`visible`); `Static` needs `markup=False` for user text; build `Input`s inside `compose`.
- Tests: no async pytest plugin. Use `tests/helpers.run_pilot` and `screen_text`; use `tests/fakes.FakeClient` instead of a database. Snapshot tests pin the terminal size (120x40 or 80x24) and render no clock or random value.
- pyright runs in standard mode on this package (not strict). Keep ruff clean: lines are at most 100 columns, docstrings included.
