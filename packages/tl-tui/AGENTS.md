# AGENTS.md — tl-tui

Read the root `AGENTS.md` first. These rules add to it.

- No business logic here. Screens and widgets call `ClientInterface` only; they never import `tl_core.services` handlers, write SQL, or touch the ledger. Only `embedded.py` and `main.py` import `tl_core` services or `tl_adapters`.
- Widgets render and post messages (`tl_tui/messages.py`); they do not call each other. The app routes messages. A new cross-widget interaction is a new message class, not an attribute poke.
- A `ClientInterface` call may raise `CLIENT_ERRORS`. Catch them where you call, post `StatusMessage(describe_error(exc), "error")`, and keep your state.
- Meaning never rides on colour alone: pair status with a symbol or text (✓ ok, ! warning, ✗ nonconformant, ● required, ○ advisory, ■ locked).
- A widget that owns keys defines `KEY_HINTS: ClassVar[str]`; the footer shows it while the widget (or a descendant) has focus.
- Forms write only through `tl_tui/forms.py` (`save_record_edits`): it groups edits by (pset, layer) and sends one `EditRecord`, so a save is all or nothing. A cleared field is sent as `None` (the pset service treats it as "unset"). Never send a command from a widget directly.
- A new key binding goes in `tl_tui/keymap.py` too; `tests/test_keymap.py` fails when a documented key is not a real binding.
- Never load all rows on the UI thread: sort goes to the server (`order_by`), End pages in a worker (see L-P0-I2-B5).
- Textual traps: do not name an attribute after a DOM property (`visible`); `Static` needs `markup=False` for user text; build `Input`s inside `compose`.
- Tests: no async pytest plugin. Use `tests/helpers.run_pilot` and `screen_text`; use `tests/fakes.FakeClient` instead of a database. Snapshot tests pin the terminal size (120x40 or 80x24) and render no clock or random value.
- pyright runs in standard mode on this package (not strict). Keep ruff clean: lines are at most 100 columns, docstrings included.
- App-level keys (`l`, `w`, `t`, `R`) start with `if self._modal_open(): return` (L-P0-I3-8). After a modal changes a record, call the view's `reload()`; `app.post_message(RecordChanged)` does not reach child widgets.
- Rich markup eats `[x]` in plain-string rows: wrap `OptionList` and `DataTable` row text in `rich.text.Text` (L-P0-I3-7). Do not use a reentrancy flag around a programmatic `Select.value` change; `Select.Changed` arrives later (L-P0-I3-9).
- Test doubles: link, search, workflow and trace behaviour of `FakeClient` lives in `tests/fakes_links.py`; extend the mixin, not `fakes.py`.
- Feed (P0-I6): the pane and the composer parse nothing; tags, importance and suggestions come from the services. `FakeClient`'s feed behaviour lives in `tests/fakes_feed.py` (real parser, real errors; cards only when a test seeds them). `p` in the pane posts `PostRequested` and the app opens the composer; after a post the app reloads the pane. `#hold` suggestions are a notice in Phase 0 (`a`), never a command.
