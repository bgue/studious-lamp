# AGENTS.md — tl-mod-cost

Read the root `AGENTS.md` first. These rules add to it.

- The tables `cur_cost_*` are generated from `schema/modules/cost/` and written only by the projectors. A record is made with `create_module_record` (ADR-0010), never with `CreateRecord`.
- The module mirrors the cost system and never edits a figure. The only write is `ImportCostSnapshot`, access `admin` (`admin.command.ImportCostSnapshot`, ADR-0015 §7). Agents never import; no MCP tool writes.
- The CSV is untrusted: the reader is bounded and strict (size, rows, columns, line length, number shape, forbidden characters) and refuses rather than cuts. A new column or format gets a limit and a test that fails without it. Text goes through `tl_core.text.clean_text`; the command checks the same bounds as the reader (the plan and the apply must not disagree).
- The plan runs the same code in the preview and in the apply. Do not copy its checks elsewhere.
- Figures are plain decimals of at most 1e15; money is never a float literal in a message. A late snapshot (an earlier as-of date) adds history and does not change the latest matrix of a code.
- No business logic in the CLI, the API route or the TUI: they call the handlers and the `registry`/`views` reads.
- Every handler and projector has a test beside it; tests use the shared fixtures so they run on both databases. Synthetic data only.
