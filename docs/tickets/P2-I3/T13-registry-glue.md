# P2-I3-T13 — Registry glue: materials MCP actions and tools, keys, nav, keymap, pins, dependencies

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: mcp, tui
Depends on: T06j (merged); p2/i1 merged into p2/i3 (Q10, done); D27, D32, D40, D44
Branch: `p2/i3-t13-registry-glue`   (from p2/i3; check `git rev-list --left-right --count p2/i3...HEAD` is `0 0`)

## Goal
Everything that is built but not yet reachable becomes reachable, in the registries other increments also edit (P2-WEB1 runs beside: keep each edit a small, local line change so the M4 merge conflicts are one-line). Nothing new is designed here: every name already exists.

## Brief references (pasted)
> D27: T07 exports `MATERIALS_MCP_ACTIONS` (`tl_mcp/materials_tools.py`, ten `mcp.<tool>` actions) and `register_materials_tools(server, ctx)`; `server.py` must call the latter and the MCP action registry (`identity.py`, name `MCP_ACTIONS`) must include the former, otherwise the ten tools are denied (authorization is closed for agents).
> D32: `tl-mod-materials` is declared in `packages/tl-tui/pyproject.toml` and `packages/tl-mcp/pyproject.toml` (the TUI and MCP import it); `uv.lock` follows.
> D40, D44: the palette already has Stock, Movements, MTO lines, Receipts, Items, Locations (`commands.py`, `app.py`). Still missing: key bindings, the navigation panel entries and the keymap rows for the six screens.
> Keys rule: pick keys that no existing binding uses (TlApp binds some with priority: read `app.py` bindings and `keymap.py` first); the keymap rows are what `?` shows, so each new key has exactly one row and each row one binding.

## Steps
1. MCP: add `MATERIALS_MCP_ACTIONS` into `MCP_ACTIONS` (union, as the other modules' tool sets are added) and call `register_materials_tools(server, ctx)` where the other `register_*_tools` calls are. Update the pinned lists that name MCP actions or tools (the test that fails is the pin: find it by running the acceptance, then update it and list it, rule 12).
2. TUI: add the six screens (Receipts, Stock, Movements, Items, Locations, MTO lines) to the key bindings, the navigation panel and the keymap rows, next to the other modules' entries, using the same action methods the palette entries call. Use sibling wording for labels (`Stock`, `Movements`, `MTO lines`, `Receipts`, `Items`, `Locations`).
3. Declare `tl-mod-materials` in both pyprojects (same form as `tl-mod-legacy`, including a `[tool.uv.sources]` workspace line if the siblings have one); run `uv lock` and commit `uv.lock`.
4. Run `just gen` if (and only if) `just check` reports drift; commit what it writes.

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/server.py`, `identity.py`, `materials_tools.py` (the two exports only)
- `packages/tl-tui/src/tl_tui/app.py`, `commands.py`, `keymap.py`, `navigation.py`
- `packages/tl-tui/pyproject.toml`, `packages/tl-mcp/pyproject.toml`
may explore: `tests/` for the pinned lists (grep `mcp.propose_cwp` or `MCP_ACTIONS`, and the keymap/nav tests); `docs/reference/` only if `just check` says a generated reference drifted (regenerate, do not edit)

## Allowed paths
- the files under Context above; `uv.lock`; files written by `just gen`
- Consequential pins (rule 12): tests that list MCP actions, tools, keys, nav entries or keymap rows and break only because the six screens and ten tools are now listed. Update and list them.
- `dev/accept/P2-I3/T13.py` (create), `docs/reports/P2-I3/T13.md` (create), `docs/tickets/P2-I3/text-contracts.md` only if it names a key (replace the placeholder with the chosen key)
No new screen, route, schema or command. No new dependency except `tl-mod-materials`.

## Acceptance (run once; the pinned-list tests named below are the only pytest allowed)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
just check
uv run python dev/accept/P2-I3/T13.py
uv run pytest tests/ -q -k "auth_review or keymap or mcp_actions" -x
```
Expected: exit 0 each. `T13.py` (one `PASS` line each): every name in `MATERIALS_MCP_ACTIONS` is in `MCP_ACTIONS`; an in-process MCP server built with the real `server.py` lists the ten materials tools; the TlApp key table has one binding per new screen with no duplicate key anywhere; each new key has a keymap row; each nav entry pushes its screen on a copy of `.accept/p2-i3.db` (build with `S3.py --keep` first; push by pressing the key under `run_test`, save an SVG per screen to `.accept/shots/T13-<screen>.svg`, 100 columns).

## Tests to add
None (T11 owns tests; the pins above are updates, not new tests).

## Report requirements
Standard report (`docs/templates/haiku-report.md`, <= 60 lines) plus: the keys chosen and why free, the pins changed, and the output of each acceptance command (<= 5 lines each). More than 12 files means stop and say why.
Commit subjects `P2-I3-T13: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
- Stop and report Blocked if a key you need is bound by another module with priority, if `uv lock` changes a version of a package other than the new member, or if a pin names an undecided agent action beyond the ten.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
